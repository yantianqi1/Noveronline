package workflows

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	StoryGraphBondGenerationWorkflowType = "story_graph_bond_generation"
	StoryGraphBondGenerationModuleKey    = "graph_bond_generator"
	StoryGraphBondGenerationWorkflowName = "GraphBondGenerationWorkflow"
)

type StartStoryGraphBondGenerationInput struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	RequestID   string
	GraphID     string
	NodeIDs     []string
	Focus       string
	Options     map[string]any
}

type StoryGraphBondGenerationRun struct {
	RunID        string
	ProjectID    string
	WorkflowType string
	Status       string
}

type StoryGraphBondGenerationStarter interface {
	StartStoryGraphBondGeneration(context.Context, StartStoryGraphBondGenerationInput) (StoryGraphBondGenerationRun, error)
}

type StoryGraphBondGenerationAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	GraphID            string
	NodeCount          int
	HasFocus           bool
	Status             string
}

type StoryGraphBondGenerationAdmissionStore interface {
	AdmitStoryGraphBondGeneration(context.Context, StoryGraphBondGenerationAdmissionInput) error
}

type DisabledStoryGraphBondGenerationStarter struct{}

func NewDisabledStoryGraphBondGenerationStarter() *DisabledStoryGraphBondGenerationStarter {
	return &DisabledStoryGraphBondGenerationStarter{}
}

func (s *DisabledStoryGraphBondGenerationStarter) StartStoryGraphBondGeneration(context.Context, StartStoryGraphBondGenerationInput) (StoryGraphBondGenerationRun, error) {
	return StoryGraphBondGenerationRun{}, &AppError{
		Code:    "STORY_GRAPH_BOND_BACKEND_UNCONFIGURED",
		Message: "story graph bond generation backend is not configured",
	}
}

type TemporalStoryGraphBondGenerationConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore StoryGraphBondGenerationAdmissionStore
}

type TemporalStoryGraphBondGenerationStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore StoryGraphBondGenerationAdmissionStore
}

func NewTemporalStoryGraphBondGenerationStarter(config TemporalStoryGraphBondGenerationConfig) *TemporalStoryGraphBondGenerationStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = StoryGraphTaskQueue
	}
	return &TemporalStoryGraphBondGenerationStarter{
		client:         config.Client,
		taskQueue:      taskQueue,
		admissionStore: config.AdmissionStore,
	}
}

func (s *TemporalStoryGraphBondGenerationStarter) StartStoryGraphBondGeneration(ctx context.Context, input StartStoryGraphBondGenerationInput) (StoryGraphBondGenerationRun, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	nodeIDs := NormalizeStoryGraphBondNodeIDs(input.NodeIDs)
	if tenantID == "" || projectID == "" || len(nodeIDs) < 2 {
		return StoryGraphBondGenerationRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and at least two node_ids are required",
		}
	}
	if s.client == nil {
		return StoryGraphBondGenerationRun{}, &AppError{
			Code:    "STORY_GRAPH_BOND_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for story_graph_bond_generation",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return StoryGraphBondGenerationRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate story graph bond generation run id",
		}
	}
	traceID := traceIDForRun(runID)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	requestID := strings.TrimSpace(input.RequestID)
	graphID := strings.TrimSpace(input.GraphID)
	focus := strings.TrimSpace(input.Focus)
	temporalWorkflowID := "story_graph_bond_generation_" + runID
	permissions := map[string][]string{
		StoryGraphBondGenerationModuleKey: {"run"},
	}
	contextPayload := map[string]any{
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": StoryGraphBondGenerationWorkflowType,
		"actor_user_id": actorUserID,
		"module_key":    StoryGraphBondGenerationModuleKey,
		"trace_id":      traceID,
		"permissions":   permissions,
	}
	payload := map[string]any{
		"context":       contextPayload,
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": StoryGraphBondGenerationWorkflowType,
		"actor_user_id": actorUserID,
		"request_id":    requestID,
		"trace_id":      traceID,
		"module_key":    StoryGraphBondGenerationModuleKey,
		"graph_id":      graphID,
		"node_ids":      nodeIDs,
		"focus":         focus,
		"options":       sanitizeStoryGraphBondGenerationOptions(input.Options),
	}
	if s.admissionStore != nil {
		err = s.admissionStore.AdmitStoryGraphBondGeneration(ctx, StoryGraphBondGenerationAdmissionInput{
			TenantID:           tenantID,
			ProjectID:          projectID,
			RunID:              runID,
			TraceID:            traceID,
			WorkflowType:       StoryGraphBondGenerationWorkflowType,
			TemporalWorkflowID: temporalWorkflowID,
			ActorUserID:        actorUserID,
			RequestID:          requestID,
			GraphID:            graphID,
			NodeCount:          len(nodeIDs),
			HasFocus:           focus != "",
			Status:             "queued",
		})
		if err != nil {
			if ErrorCode(err) == "WORKFLOW_ADMISSION_FAILED" {
				return StoryGraphBondGenerationRun{}, err
			}
			return StoryGraphBondGenerationRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
		}
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 2 * time.Hour,
		WorkflowRunTimeout:       2 * time.Hour,
	}, StoryGraphBondGenerationWorkflowName, payload)
	if err != nil {
		return StoryGraphBondGenerationRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("failed to start story_graph_bond_generation workflow: %v", err),
		}
	}
	return StoryGraphBondGenerationRun{
		RunID:        runID,
		ProjectID:    projectID,
		WorkflowType: StoryGraphBondGenerationWorkflowType,
		Status:       "queued",
	}, nil
}

func NormalizeStoryGraphBondNodeIDs(nodeIDs []string) []string {
	normalized := make([]string, 0, len(nodeIDs))
	seen := map[string]bool{}
	for _, nodeID := range nodeIDs {
		nodeID = strings.TrimSpace(nodeID)
		if nodeID == "" || seen[nodeID] {
			continue
		}
		seen[nodeID] = true
		normalized = append(normalized, nodeID)
	}
	return normalized
}

func sanitizeStoryGraphBondGenerationOptions(options map[string]any) map[string]any {
	sanitized := map[string]any{}
	for key, value := range options {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if normalizedKey == "" || storyGraphBondGenerationOptionKeySensitive(normalizedKey) {
			continue
		}
		sanitized[key] = sanitizeStoryGraphBondGenerationValue(value)
	}
	return sanitized
}

func sanitizeStoryGraphBondGenerationValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeStoryGraphBondGenerationOptions(typed)
	case []any:
		sanitized := make([]any, 0, len(typed))
		for _, item := range typed {
			sanitized = append(sanitized, sanitizeStoryGraphBondGenerationValue(item))
		}
		return sanitized
	default:
		return value
	}
}

func storyGraphBondGenerationOptionKeySensitive(key string) bool {
	switch key {
	case "api_key", "body", "candidate_body", "content", "credential_ref", "draft", "encrypted_api_key", "evidence_text", "manuscript", "prompt", "raw_content", "raw_text", "response", "seed_analysis_body", "snippet", "source_text", "text":
		return true
	default:
		return false
	}
}
