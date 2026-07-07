package workflows

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	StyleExtractionWorkflowType = "style_extraction"
	StyleExtractionModuleKey    = "style_extractor"
	StyleExtractionWorkflowName = "StyleExtractionWorkflow"
	StyleExtractionTaskQueue    = AssetIngestionTaskQueue
)

type StartStyleExtractionInput struct {
	TenantID      string
	ProjectID     string
	ActorUserID   string
	RequestID     string
	MaterialText  string
	SourceAssetID string
	Scope         string
	Options       map[string]any
}

type StyleExtractionRun struct {
	RunID        string
	ProjectID    string
	WorkflowType string
	Status       string
}

type GetStyleExtractionInput struct {
	TenantID string
	RunID    string
}

type StyleExtractionStarter interface {
	StartStyleExtraction(context.Context, StartStyleExtractionInput) (StyleExtractionRun, error)
}

type StyleExtractionReader interface {
	GetStyleExtraction(context.Context, GetStyleExtractionInput) (WorkflowRun, error)
}

type DisabledStyleExtractionStarter struct{}

func NewDisabledStyleExtractionStarter() *DisabledStyleExtractionStarter {
	return &DisabledStyleExtractionStarter{}
}

func (s *DisabledStyleExtractionStarter) StartStyleExtraction(context.Context, StartStyleExtractionInput) (StyleExtractionRun, error) {
	return StyleExtractionRun{}, &AppError{
		Code:    "STYLE_EXTRACTION_BACKEND_UNCONFIGURED",
		Message: "style extraction workflow backend is not configured",
	}
}

type StyleExtractionAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	SourceAssetID      string
	Scope              string
	Status             string
}

type StyleExtractionAdmissionStore interface {
	AdmitStyleExtractionRun(context.Context, StyleExtractionAdmissionInput) error
}

type TemporalStyleExtractionConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore StyleExtractionAdmissionStore
}

type TemporalStyleExtractionStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore StyleExtractionAdmissionStore
}

func NewTemporalStyleExtractionStarter(config TemporalStyleExtractionConfig) *TemporalStyleExtractionStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = StyleExtractionTaskQueue
	}
	return &TemporalStyleExtractionStarter{
		client:         config.Client,
		taskQueue:      taskQueue,
		admissionStore: config.AdmissionStore,
	}
}

func (s *TemporalStyleExtractionStarter) StartStyleExtraction(ctx context.Context, input StartStyleExtractionInput) (StyleExtractionRun, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	materialText := strings.TrimSpace(input.MaterialText)
	sourceAssetID := strings.TrimSpace(input.SourceAssetID)
	if tenantID == "" || projectID == "" || (materialText == "" && sourceAssetID == "") {
		return StyleExtractionRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and material_text or source_asset_id are required",
		}
	}
	if s.client == nil {
		return StyleExtractionRun{}, &AppError{
			Code:    "STYLE_EXTRACTION_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for style_extraction",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return StyleExtractionRun{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to allocate style extraction run id"}
	}
	traceID := traceIDForRun(runID)
	scope := strings.TrimSpace(input.Scope)
	if scope == "" {
		scope = "project"
	}
	actorUserID := strings.TrimSpace(input.ActorUserID)
	requestID := strings.TrimSpace(input.RequestID)
	temporalWorkflowID := "style_extraction_" + runID
	permissions := map[string][]string{
		StyleExtractionModuleKey: {"run"},
	}
	contextPayload := map[string]any{
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": StyleExtractionWorkflowType,
		"actor_user_id": actorUserID,
		"module_key":    StyleExtractionModuleKey,
		"trace_id":      traceID,
		"permissions":   permissions,
	}
	payload := map[string]any{
		"context":         contextPayload,
		"tenant_id":       tenantID,
		"project_id":      projectID,
		"run_id":          runID,
		"workflow_type":   StyleExtractionWorkflowType,
		"actor_user_id":   actorUserID,
		"request_id":      requestID,
		"trace_id":        traceID,
		"module_key":      StyleExtractionModuleKey,
		"material_text":   materialText,
		"source_asset_id": sourceAssetID,
		"scope":           scope,
		"options":         cloneAssetIngestionOptions(input.Options),
	}
	if s.admissionStore != nil {
		err = s.admissionStore.AdmitStyleExtractionRun(ctx, StyleExtractionAdmissionInput{
			TenantID:           tenantID,
			ProjectID:          projectID,
			RunID:              runID,
			TraceID:            traceID,
			WorkflowType:       StyleExtractionWorkflowType,
			TemporalWorkflowID: temporalWorkflowID,
			ActorUserID:        actorUserID,
			RequestID:          requestID,
			SourceAssetID:      sourceAssetID,
			Scope:              scope,
			Status:             "queued",
		})
		if err != nil {
			if ErrorCode(err) == "WORKFLOW_ADMISSION_FAILED" {
				return StyleExtractionRun{}, err
			}
			return StyleExtractionRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
		}
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 2 * time.Hour,
		WorkflowRunTimeout:       2 * time.Hour,
	}, StyleExtractionWorkflowName, payload)
	if err != nil {
		return StyleExtractionRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("failed to start style_extraction workflow: %v", err),
		}
	}
	return StyleExtractionRun{
		RunID:        runID,
		ProjectID:    projectID,
		WorkflowType: StyleExtractionWorkflowType,
		Status:       "queued",
	}, nil
}

type DisabledStyleExtractionReader struct{}

func NewDisabledStyleExtractionReader() *DisabledStyleExtractionReader {
	return &DisabledStyleExtractionReader{}
}

func (r *DisabledStyleExtractionReader) GetStyleExtraction(context.Context, GetStyleExtractionInput) (WorkflowRun, error) {
	return WorkflowRun{}, &AppError{
		Code:    "STYLE_EXTRACTION_BACKEND_UNCONFIGURED",
		Message: "style extraction workflow reader is not configured",
	}
}

type WorkflowStyleExtractionReader struct {
	workflowReader WorkflowReader
}

func NewWorkflowStyleExtractionReader(workflowReader WorkflowReader) *WorkflowStyleExtractionReader {
	return &WorkflowStyleExtractionReader{workflowReader: workflowReader}
}

func (r *WorkflowStyleExtractionReader) GetStyleExtraction(ctx context.Context, input GetStyleExtractionInput) (WorkflowRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return WorkflowRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if r.workflowReader == nil {
		return WorkflowRun{}, &AppError{
			Code:    "STYLE_EXTRACTION_BACKEND_UNCONFIGURED",
			Message: "style extraction workflow reader is not configured",
		}
	}
	run, err := r.workflowReader.GetWorkflowRun(ctx, GetWorkflowRunInput{
		TenantID: strings.TrimSpace(input.TenantID),
		RunID:    strings.TrimSpace(input.RunID),
	})
	if err != nil {
		return WorkflowRun{}, err
	}
	if run.WorkflowType != StyleExtractionWorkflowType {
		return WorkflowRun{}, &AppError{Code: "NOT_FOUND", Message: "style extraction run not found"}
	}
	return run, nil
}
