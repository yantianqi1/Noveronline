package workflows

import (
	"context"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	AssetReindexWorkflowType = "asset_reindex"
	AssetReindexModuleKey    = "asset_reindex"
	AssetReindexWorkflowName = "AssetReindexWorkflow"

	assetReindexStartFailedMessage = "failed to start asset_reindex workflow"
)

type StartAssetReindexInput struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	RequestID   string
	Scope       string
	Mode        string
	Options     map[string]any
}

type AssetReindexRun struct {
	RunID        string
	ProjectID    string
	WorkflowType string
	Status       string
}

type AssetReindexStarter interface {
	StartAssetReindex(context.Context, StartAssetReindexInput) (AssetReindexRun, error)
}

type DisabledAssetReindexStarter struct{}

func NewDisabledAssetReindexStarter() *DisabledAssetReindexStarter {
	return &DisabledAssetReindexStarter{}
}

func (s *DisabledAssetReindexStarter) StartAssetReindex(context.Context, StartAssetReindexInput) (AssetReindexRun, error) {
	return AssetReindexRun{}, &AppError{
		Code:    "ASSET_REINDEX_BACKEND_UNCONFIGURED",
		Message: "asset reindex workflow backend is not configured",
	}
}

type AssetReindexAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	Scope              string
	Mode               string
	Status             string
}

type AssetReindexAdmissionStore interface {
	AdmitAssetReindexRun(context.Context, AssetReindexAdmissionInput) error
	RecordAssetReindexStartFailure(context.Context, AssetReindexAdmissionInput) error
}

type TemporalAssetReindexConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore AssetReindexAdmissionStore
}

type TemporalAssetReindexStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore AssetReindexAdmissionStore
}

func NewTemporalAssetReindexStarter(config TemporalAssetReindexConfig) *TemporalAssetReindexStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = AssetIngestionTaskQueue
	}
	return &TemporalAssetReindexStarter{
		client:         config.Client,
		taskQueue:      taskQueue,
		admissionStore: config.AdmissionStore,
	}
}

func (s *TemporalAssetReindexStarter) StartAssetReindex(ctx context.Context, input StartAssetReindexInput) (AssetReindexRun, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	requestID := strings.TrimSpace(input.RequestID)
	if tenantID == "" || projectID == "" || actorUserID == "" || requestID == "" {
		return AssetReindexRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, actor_user_id, and request_id are required",
		}
	}
	if s.client == nil || s.admissionStore == nil {
		return AssetReindexRun{}, &AppError{
			Code:    "ASSET_REINDEX_BACKEND_UNCONFIGURED",
			Message: "asset reindex workflow backend is not configured",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return AssetReindexRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate asset reindex run id",
		}
	}
	traceID := traceIDForRun(runID)
	scope := NormalizeAssetReindexScope(input.Scope)
	mode := NormalizeAssetReindexMode(input.Mode)
	temporalWorkflowID := "asset_reindex_" + runID
	permissions := map[string][]string{
		AssetReindexModuleKey: {"run"},
	}
	contextPayload := map[string]any{
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": AssetReindexWorkflowType,
		"actor_user_id": actorUserID,
		"module_key":    AssetReindexModuleKey,
		"trace_id":      traceID,
		"permissions":   permissions,
	}
	payload := map[string]any{
		"context":       contextPayload,
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": AssetReindexWorkflowType,
		"actor_user_id": actorUserID,
		"request_id":    requestID,
		"trace_id":      traceID,
		"module_key":    AssetReindexModuleKey,
		"scope":         scope,
		"mode":          mode,
		"options":       sanitizeAssetReindexOptions(input.Options),
	}
	admissionInput := AssetReindexAdmissionInput{
		TenantID:           tenantID,
		ProjectID:          projectID,
		RunID:              runID,
		TraceID:            traceID,
		WorkflowType:       AssetReindexWorkflowType,
		TemporalWorkflowID: temporalWorkflowID,
		ActorUserID:        actorUserID,
		RequestID:          requestID,
		Scope:              scope,
		Mode:               mode,
		Status:             "queued",
	}
	err = s.admissionStore.AdmitAssetReindexRun(ctx, admissionInput)
	if err != nil {
		return AssetReindexRun{}, assetReindexAdmissionFailed()
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 2 * time.Hour,
		WorkflowRunTimeout:       2 * time.Hour,
	}, AssetReindexWorkflowName, payload)
	if err != nil {
		compensationContext, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		if compensateErr := s.admissionStore.RecordAssetReindexStartFailure(compensationContext, admissionInput); compensateErr != nil {
			return AssetReindexRun{}, assetReindexStartFailureRecordFailed()
		}
		return AssetReindexRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: assetReindexStartFailedMessage,
		}
	}
	return AssetReindexRun{
		RunID:        runID,
		ProjectID:    projectID,
		WorkflowType: AssetReindexWorkflowType,
		Status:       "queued",
	}, nil
}

func NormalizeAssetReindexScope(scope string) string {
	scope = strings.TrimSpace(scope)
	if scope == "" {
		return "project"
	}
	return scope
}

func NormalizeAssetReindexMode(mode string) string {
	mode = strings.TrimSpace(mode)
	if mode == "" {
		return "keyword"
	}
	return mode
}

func sanitizeAssetReindexOptions(options map[string]any) map[string]any {
	sanitized := map[string]any{}
	for key, value := range options {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if normalizedKey == "" || assetReindexOptionKeySensitive(normalizedKey) {
			continue
		}
		sanitized[key] = sanitizeAssetReindexValue(value)
	}
	return sanitized
}

func sanitizeAssetReindexValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeAssetReindexOptions(typed)
	case []any:
		sanitized := make([]any, 0, len(typed))
		for _, item := range typed {
			sanitized = append(sanitized, sanitizeAssetReindexValue(item))
		}
		return sanitized
	default:
		return value
	}
}

func assetReindexOptionKeySensitive(key string) bool {
	switch key {
	case "api_key", "body", "content", "credential_ref", "draft", "encrypted_api_key", "embedding_chunk", "embedding_chunks", "manuscript", "prompt", "raw_content", "response", "search_body", "source_text", "text":
		return true
	default:
		return false
	}
}
