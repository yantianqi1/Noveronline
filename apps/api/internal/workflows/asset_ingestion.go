package workflows

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	AssetIngestionWorkflowType = "asset_ingestion"
	AssetIngestionModuleKey    = "asset_ingestion"
	AssetIngestionWorkflowName = "AssetIngestionWorkflow"
	AssetIngestionTaskQueue    = "asset-light"
)

type StartAssetIngestionInput struct {
	TenantID     string
	ProjectID    string
	ActorUserID  string
	RequestID    string
	MaterialText string
	HintType     string
	Scope        string
	Options      map[string]any
}

type AssetIngestionRun struct {
	RunID        string
	ProjectID    string
	WorkflowType string
	Status       string
}

type GetAssetIngestionInput struct {
	TenantID string
	RunID    string
}

type AssetIngestionStarter interface {
	StartAssetIngestion(context.Context, StartAssetIngestionInput) (AssetIngestionRun, error)
}

type AssetIngestionReader interface {
	GetAssetIngestion(context.Context, GetAssetIngestionInput) (WorkflowRun, error)
}

type DisabledAssetIngestionStarter struct{}

func NewDisabledAssetIngestionStarter() *DisabledAssetIngestionStarter {
	return &DisabledAssetIngestionStarter{}
}

func (s *DisabledAssetIngestionStarter) StartAssetIngestion(context.Context, StartAssetIngestionInput) (AssetIngestionRun, error) {
	return AssetIngestionRun{}, &AppError{
		Code:    "ASSET_INGESTION_BACKEND_UNCONFIGURED",
		Message: "asset ingestion workflow backend is not configured",
	}
}

type AssetIngestionAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	HintType           string
	Scope              string
	Status             string
}

type AssetIngestionAdmissionStore interface {
	AdmitAssetIngestionRun(context.Context, AssetIngestionAdmissionInput) error
}

type TemporalAssetIngestionConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore AssetIngestionAdmissionStore
}

type TemporalAssetIngestionStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore AssetIngestionAdmissionStore
}

func NewTemporalAssetIngestionStarter(config TemporalAssetIngestionConfig) *TemporalAssetIngestionStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = AssetIngestionTaskQueue
	}
	return &TemporalAssetIngestionStarter{
		client:         config.Client,
		taskQueue:      taskQueue,
		admissionStore: config.AdmissionStore,
	}
}

func (s *TemporalAssetIngestionStarter) StartAssetIngestion(ctx context.Context, input StartAssetIngestionInput) (AssetIngestionRun, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	materialText := strings.TrimSpace(input.MaterialText)
	if tenantID == "" || projectID == "" || materialText == "" {
		return AssetIngestionRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and material_text are required",
		}
	}
	if s.client == nil {
		return AssetIngestionRun{}, &AppError{
			Code:    "ASSET_INGESTION_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for asset_ingestion",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return AssetIngestionRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate asset ingestion run id",
		}
	}
	traceID := traceIDForRun(runID)
	scope := strings.TrimSpace(input.Scope)
	if scope == "" {
		scope = "project"
	}
	hintType := strings.TrimSpace(input.HintType)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	requestID := strings.TrimSpace(input.RequestID)
	temporalWorkflowID := "asset_ingestion_" + runID
	permissions := map[string][]string{
		AssetIngestionModuleKey: {"run"},
	}
	contextPayload := map[string]any{
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": AssetIngestionWorkflowType,
		"actor_user_id": actorUserID,
		"module_key":    AssetIngestionModuleKey,
		"trace_id":      traceID,
		"permissions":   permissions,
	}
	payload := map[string]any{
		"context":       contextPayload,
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": AssetIngestionWorkflowType,
		"actor_user_id": actorUserID,
		"request_id":    requestID,
		"trace_id":      traceID,
		"module_key":    AssetIngestionModuleKey,
		"material_text": materialText,
		"hint_type":     hintType,
		"scope":         scope,
		"options":       cloneAssetIngestionOptions(input.Options),
	}
	if s.admissionStore != nil {
		err = s.admissionStore.AdmitAssetIngestionRun(ctx, AssetIngestionAdmissionInput{
			TenantID:           tenantID,
			ProjectID:          projectID,
			RunID:              runID,
			TraceID:            traceID,
			WorkflowType:       AssetIngestionWorkflowType,
			TemporalWorkflowID: temporalWorkflowID,
			ActorUserID:        actorUserID,
			RequestID:          requestID,
			HintType:           hintType,
			Scope:              scope,
			Status:             "queued",
		})
		if err != nil {
			if ErrorCode(err) == "WORKFLOW_ADMISSION_FAILED" {
				return AssetIngestionRun{}, err
			}
			return AssetIngestionRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
		}
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 2 * time.Hour,
		WorkflowRunTimeout:       2 * time.Hour,
	}, AssetIngestionWorkflowName, payload)
	if err != nil {
		return AssetIngestionRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("failed to start asset_ingestion workflow: %v", err),
		}
	}
	return AssetIngestionRun{
		RunID:        runID,
		ProjectID:    projectID,
		WorkflowType: AssetIngestionWorkflowType,
		Status:       "queued",
	}, nil
}

func cloneAssetIngestionOptions(options map[string]any) map[string]any {
	cloned := map[string]any{}
	for key, value := range options {
		cloned[key] = value
	}
	return cloned
}

type DisabledAssetIngestionReader struct{}

func NewDisabledAssetIngestionReader() *DisabledAssetIngestionReader {
	return &DisabledAssetIngestionReader{}
}

func (r *DisabledAssetIngestionReader) GetAssetIngestion(context.Context, GetAssetIngestionInput) (WorkflowRun, error) {
	return WorkflowRun{}, &AppError{
		Code:    "ASSET_INGESTION_BACKEND_UNCONFIGURED",
		Message: "asset ingestion workflow reader is not configured",
	}
}

type WorkflowAssetIngestionReader struct {
	workflowReader WorkflowReader
}

func NewWorkflowAssetIngestionReader(workflowReader WorkflowReader) *WorkflowAssetIngestionReader {
	return &WorkflowAssetIngestionReader{workflowReader: workflowReader}
}

func (r *WorkflowAssetIngestionReader) GetAssetIngestion(ctx context.Context, input GetAssetIngestionInput) (WorkflowRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return WorkflowRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if r.workflowReader == nil {
		return WorkflowRun{}, &AppError{
			Code:    "ASSET_INGESTION_BACKEND_UNCONFIGURED",
			Message: "asset ingestion workflow reader is not configured",
		}
	}
	run, err := r.workflowReader.GetWorkflowRun(ctx, GetWorkflowRunInput{
		TenantID: strings.TrimSpace(input.TenantID),
		RunID:    strings.TrimSpace(input.RunID),
	})
	if err != nil {
		return WorkflowRun{}, err
	}
	if run.WorkflowType != AssetIngestionWorkflowType {
		return WorkflowRun{}, &AppError{Code: "NOT_FOUND", Message: "asset ingestion run not found"}
	}
	return run, nil
}
