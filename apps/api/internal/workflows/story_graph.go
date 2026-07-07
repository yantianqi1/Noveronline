package workflows

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	StoryGraphBuildWorkflowType = "story_graph_build"
	StoryGraphBuildModuleKey    = "story_graph_build"
	StoryGraphBuildWorkflowName = "StoryGraphBuildWorkflow"
	StoryGraphTaskQueue         = "graph-heavy"
)

type StartStoryGraphBuildInput struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	RequestID   string
	Mode        string
	Options     map[string]any
}

type StoryGraphBuildRun struct {
	RunID        string
	ProjectID    string
	WorkflowType string
	Status       string
}

type StoryGraphBuildStarter interface {
	StartStoryGraphBuild(context.Context, StartStoryGraphBuildInput) (StoryGraphBuildRun, error)
}

type DisabledStoryGraphBuildStarter struct{}

func NewDisabledStoryGraphBuildStarter() *DisabledStoryGraphBuildStarter {
	return &DisabledStoryGraphBuildStarter{}
}

func (s *DisabledStoryGraphBuildStarter) StartStoryGraphBuild(context.Context, StartStoryGraphBuildInput) (StoryGraphBuildRun, error) {
	return StoryGraphBuildRun{}, &AppError{
		Code:    "STORY_GRAPH_BUILD_BACKEND_UNCONFIGURED",
		Message: "story graph build workflow backend is not configured",
	}
}

type StoryGraphBuildAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	Mode               string
	Status             string
}

type StoryGraphBuildAdmissionStore interface {
	AdmitStoryGraphBuild(context.Context, StoryGraphBuildAdmissionInput) error
}

type TemporalStoryGraphBuildConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore StoryGraphBuildAdmissionStore
}

type TemporalStoryGraphBuildStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore StoryGraphBuildAdmissionStore
}

func NewTemporalStoryGraphBuildStarter(config TemporalStoryGraphBuildConfig) *TemporalStoryGraphBuildStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = StoryGraphTaskQueue
	}
	return &TemporalStoryGraphBuildStarter{
		client:         config.Client,
		taskQueue:      taskQueue,
		admissionStore: config.AdmissionStore,
	}
}

func (s *TemporalStoryGraphBuildStarter) StartStoryGraphBuild(ctx context.Context, input StartStoryGraphBuildInput) (StoryGraphBuildRun, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return StoryGraphBuildRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and project_id are required",
		}
	}
	if s.client == nil {
		return StoryGraphBuildRun{}, &AppError{
			Code:    "STORY_GRAPH_BUILD_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for story_graph_build",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return StoryGraphBuildRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate story graph build run id",
		}
	}
	traceID := traceIDForRun(runID)
	mode := NormalizeStoryGraphBuildMode(input.Mode)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	requestID := strings.TrimSpace(input.RequestID)
	temporalWorkflowID := "story_graph_build_" + runID
	permissions := map[string][]string{
		StoryGraphBuildModuleKey: {"run"},
	}
	contextPayload := map[string]any{
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": StoryGraphBuildWorkflowType,
		"actor_user_id": actorUserID,
		"module_key":    StoryGraphBuildModuleKey,
		"trace_id":      traceID,
		"permissions":   permissions,
	}
	payload := map[string]any{
		"context":       contextPayload,
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": StoryGraphBuildWorkflowType,
		"actor_user_id": actorUserID,
		"request_id":    requestID,
		"trace_id":      traceID,
		"module_key":    StoryGraphBuildModuleKey,
		"mode":          mode,
		"options":       sanitizeStoryGraphBuildOptions(input.Options),
	}
	if s.admissionStore != nil {
		err = s.admissionStore.AdmitStoryGraphBuild(ctx, StoryGraphBuildAdmissionInput{
			TenantID:           tenantID,
			ProjectID:          projectID,
			RunID:              runID,
			TraceID:            traceID,
			WorkflowType:       StoryGraphBuildWorkflowType,
			TemporalWorkflowID: temporalWorkflowID,
			ActorUserID:        actorUserID,
			RequestID:          requestID,
			Mode:               mode,
			Status:             "queued",
		})
		if err != nil {
			if ErrorCode(err) == "WORKFLOW_ADMISSION_FAILED" {
				return StoryGraphBuildRun{}, err
			}
			return StoryGraphBuildRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
		}
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 2 * time.Hour,
		WorkflowRunTimeout:       2 * time.Hour,
	}, StoryGraphBuildWorkflowName, payload)
	if err != nil {
		return StoryGraphBuildRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("failed to start story_graph_build workflow: %v", err),
		}
	}
	return StoryGraphBuildRun{
		RunID:        runID,
		ProjectID:    projectID,
		WorkflowType: StoryGraphBuildWorkflowType,
		Status:       "queued",
	}, nil
}

func NormalizeStoryGraphBuildMode(mode string) string {
	mode = strings.TrimSpace(mode)
	if mode == "" {
		return "full"
	}
	return mode
}

func sanitizeStoryGraphBuildOptions(options map[string]any) map[string]any {
	sanitized := map[string]any{}
	for key, value := range options {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if normalizedKey == "" || storyGraphBuildOptionKeySensitive(normalizedKey) {
			continue
		}
		sanitized[key] = sanitizeStoryGraphBuildValue(value)
	}
	return sanitized
}

func sanitizeStoryGraphBuildValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeStoryGraphBuildOptions(typed)
	case []any:
		sanitized := make([]any, 0, len(typed))
		for _, item := range typed {
			sanitized = append(sanitized, sanitizeStoryGraphBuildValue(item))
		}
		return sanitized
	default:
		return value
	}
}

func storyGraphBuildOptionKeySensitive(key string) bool {
	switch key {
	case "api_key", "body", "content", "credential_ref", "draft", "encrypted_api_key", "manuscript", "prompt", "raw_content", "raw_text", "response", "seed_analysis_body", "snippet", "source_text", "text":
		return true
	default:
		return false
	}
}
