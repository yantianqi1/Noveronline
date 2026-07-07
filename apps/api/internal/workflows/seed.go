package workflows

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	SeedWorkflowType = "seed_pipeline"
	SeedWorkflowName = "SeedPipelineWorkflow"
	SeedTaskQueue    = "seed-heavy"

	seedWorkflowStartFailedMessage = "failed to start seed_pipeline workflow"
)

type StartSeedRunInput struct {
	TenantID        string
	ProjectID       string
	UploadID        string
	ActorUserID     string
	RequestID       string
	SourceFileID    string
	SourceObjectKey string
	SourceFilename  string
	SourceMimeType  string
	SourceSizeBytes int64
	SourceSHA256    string
	Options         map[string]any
}

type SeedRun struct {
	RunID        string
	ProjectID    string
	WorkflowType string
	Status       string
}

type SeedRunStarter interface {
	StartSeedRun(context.Context, StartSeedRunInput) (SeedRun, error)
}

type SeedAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	UploadID           string
	SourceFileID       string
	Status             string
}

type SeedStartFailureInput struct {
	TenantID     string
	ProjectID    string
	RunID        string
	TraceID      string
	WorkflowType string
	ActorUserID  string
	RequestID    string
	UploadID     string
	SourceFileID string
	ErrorCode    string
	ErrorMessage string
}

type SeedAdmissionStore interface {
	AdmitSeedRun(context.Context, SeedAdmissionInput) error
	RecordSeedRunStartFailure(context.Context, SeedStartFailureInput) error
}

type DisabledSeedRunStarter struct{}

func NewDisabledSeedRunStarter() *DisabledSeedRunStarter {
	return &DisabledSeedRunStarter{}
}

func (s *DisabledSeedRunStarter) StartSeedRun(_ context.Context, _ StartSeedRunInput) (SeedRun, error) {
	return SeedRun{}, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "Temporal workflow backend is not configured for seed_pipeline",
	}
}

type TemporalSeedRunConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore SeedAdmissionStore
}

type TemporalSeedRunStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore SeedAdmissionStore
}

func NewTemporalSeedRunStarter(config TemporalSeedRunConfig) *TemporalSeedRunStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = SeedTaskQueue
	}
	return &TemporalSeedRunStarter{client: config.Client, taskQueue: taskQueue, admissionStore: config.AdmissionStore}
}

func (s *TemporalSeedRunStarter) StartSeedRun(ctx context.Context, input StartSeedRunInput) (SeedRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.UploadID) == "" {
		return SeedRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and upload_id are required",
		}
	}
	if invalidSeedStartUUIDContext(input) {
		return SeedRun{}, invalidSeedStartContext()
	}
	if s.client == nil {
		return SeedRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for seed_pipeline",
		}
	}
	if s.admissionStore == nil {
		return SeedRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "seed admission store is not configured",
		}
	}
	if err := validateSeedSourceHandoff(input); err != nil {
		return SeedRun{}, err
	}
	runID, err := newRunID()
	if err != nil {
		return SeedRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate seed run id",
		}
	}
	traceID := traceIDForRun(runID)
	temporalWorkflowID := "seed_run_" + runID
	payload := map[string]any{
		"context": map[string]any{
			"tenant_id":     strings.TrimSpace(input.TenantID),
			"project_id":    strings.TrimSpace(input.ProjectID),
			"run_id":        runID,
			"workflow_type": SeedWorkflowType,
			"actor_user_id": strings.TrimSpace(input.ActorUserID),
			"trace_id":      traceID,
			"permissions": map[string][]string{
				"seed_pipeline": {"run"},
			},
		},
		"tenant_id":         strings.TrimSpace(input.TenantID),
		"project_id":        strings.TrimSpace(input.ProjectID),
		"run_id":            runID,
		"workflow_type":     SeedWorkflowType,
		"actor_user_id":     strings.TrimSpace(input.ActorUserID),
		"request_id":        strings.TrimSpace(input.RequestID),
		"trace_id":          traceID,
		"upload_id":         strings.TrimSpace(input.UploadID),
		"source_file_id":    strings.TrimSpace(input.SourceFileID),
		"source_object_key": strings.TrimSpace(input.SourceObjectKey),
		"source_filename":   strings.TrimSpace(input.SourceFilename),
		"source_mime_type":  strings.TrimSpace(input.SourceMimeType),
		"source_size_bytes": input.SourceSizeBytes,
		"source_sha256":     strings.TrimSpace(input.SourceSHA256),
		"options":           cloneSeedOptions(input.Options),
		"permissions": map[string][]string{
			"seed_pipeline": {"run"},
		},
	}
	err = s.admissionStore.AdmitSeedRun(ctx, SeedAdmissionInput{
		TenantID:           strings.TrimSpace(input.TenantID),
		ProjectID:          strings.TrimSpace(input.ProjectID),
		RunID:              runID,
		TraceID:            traceID,
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: temporalWorkflowID,
		ActorUserID:        strings.TrimSpace(input.ActorUserID),
		RequestID:          strings.TrimSpace(input.RequestID),
		UploadID:           strings.TrimSpace(input.UploadID),
		SourceFileID:       strings.TrimSpace(input.SourceFileID),
		Status:             "queued",
	})
	if err != nil {
		var appErr *AppError
		if errors.As(err, &appErr) {
			return SeedRun{}, err
		}
		return SeedRun{}, workflowAdmissionFailed()
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 24 * time.Hour,
		WorkflowRunTimeout:       24 * time.Hour,
	}, SeedWorkflowName, payload)
	if err != nil {
		failureErr := s.admissionStore.RecordSeedRunStartFailure(ctx, SeedStartFailureInput{
			TenantID:     strings.TrimSpace(input.TenantID),
			ProjectID:    strings.TrimSpace(input.ProjectID),
			RunID:        runID,
			TraceID:      traceID,
			WorkflowType: SeedWorkflowType,
			ActorUserID:  strings.TrimSpace(input.ActorUserID),
			RequestID:    strings.TrimSpace(input.RequestID),
			UploadID:     strings.TrimSpace(input.UploadID),
			SourceFileID: strings.TrimSpace(input.SourceFileID),
			ErrorCode:    "WORKFLOW_FAILED",
			ErrorMessage: seedWorkflowStartFailedMessage,
		})
		if failureErr != nil {
			return SeedRun{}, workflowStartFailureRecordFailed()
		}
		return SeedRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: seedWorkflowStartFailedMessage,
		}
	}
	return SeedRun{
		RunID:        runID,
		ProjectID:    strings.TrimSpace(input.ProjectID),
		WorkflowType: SeedWorkflowType,
		Status:       "queued",
	}, nil
}

func cloneSeedOptions(options map[string]any) map[string]any {
	cloned := make(map[string]any, len(options))
	for key, value := range options {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if normalizedKey == "" || seedOptionKeySensitive(normalizedKey) {
			continue
		}
		cloned[key] = sanitizeSeedOptionValue(value)
	}
	return cloned
}

func sanitizeSeedOptionValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneSeedOptions(typed)
	case []any:
		values := make([]any, 0, len(typed))
		for _, item := range typed {
			values = append(values, sanitizeSeedOptionValue(item))
		}
		return values
	default:
		return value
	}
}

func seedOptionKeySensitive(key string) bool {
	normalized := strings.ReplaceAll(strings.ToLower(strings.TrimSpace(key)), "-", "_")
	compact := strings.ReplaceAll(normalized, "_", "")
	switch compact {
	case "apikey",
		"body", "bodytext",
		"candidatebody", "candidateeventbody",
		"content", "contenttext",
		"credential", "credentials", "credentialref",
		"draft",
		"encryptedapikey",
		"eventbody",
		"manuscript",
		"materialtext",
		"projectid",
		"prompt",
		"rawbody", "rawcontent", "rawtext",
		"response",
		"sourcematerial", "sourcetext",
		"tenantid",
		"text":
		return true
	default:
		return false
	}
}

func validateSeedSourceHandoff(input StartSeedRunInput) error {
	if strings.TrimSpace(input.SourceFileID) == "" ||
		strings.TrimSpace(input.SourceObjectKey) == "" ||
		!isSupportedSeedSourceHandoffMime(input.SourceMimeType) ||
		!isSeedSourceSHA256(input.SourceSHA256) ||
		input.SourceSizeBytes < 0 {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "seed source metadata is incomplete",
		}
	}
	return nil
}

func isSupportedSeedSourceHandoffMime(mimeType string) bool {
	normalized := strings.ToLower(strings.TrimSpace(mimeType))
	if index := strings.Index(normalized, ";"); index >= 0 {
		normalized = strings.TrimSpace(normalized[:index])
	}
	switch normalized {
	case "text/plain", "text/markdown", "text/x-markdown", "application/x-markdown", "application/pdf":
		return true
	default:
		return false
	}
}

func isSeedSourceSHA256(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 64 {
		return false
	}
	for _, char := range value {
		if (char < '0' || char > '9') && (char < 'a' || char > 'f') && (char < 'A' || char > 'F') {
			return false
		}
	}
	return true
}

func invalidSeedStartUUIDContext(input StartSeedRunInput) bool {
	return !isSeedUUID(input.TenantID) ||
		!isSeedUUID(input.ProjectID) ||
		!isSeedUUID(input.UploadID) ||
		!isOptionalSeedUUID(input.ActorUserID) ||
		!isSeedUUID(input.SourceFileID)
}

func invalidSeedStartContext() *AppError {
	return &AppError{Code: "VALIDATION_FAILED", Message: "seed workflow context is invalid"}
}
