package workflows

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	HelloAgentWorkflowType = "hello_agent"
	HelloAgentWorkflowName = "HelloAgentWorkflow"
	HelloAgentTaskQueue    = "maintenance"
)

type StartHelloAgentInput struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	RequestID   string
}

type HelloAgentRun struct {
	RunID        string
	ProjectID    string
	WorkflowType string
	Status       string
}

type AgentHelloStarter interface {
	StartHelloAgent(context.Context, StartHelloAgentInput) (HelloAgentRun, error)
}

type DisabledHelloAgentStarter struct{}

func NewDisabledHelloAgentStarter() *DisabledHelloAgentStarter {
	return &DisabledHelloAgentStarter{}
}

func (s *DisabledHelloAgentStarter) StartHelloAgent(_ context.Context, _ StartHelloAgentInput) (HelloAgentRun, error) {
	return HelloAgentRun{}, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "Temporal workflow backend is not configured for hello_agent",
	}
}

type TemporalWorkflowClient interface {
	ExecuteWorkflow(context.Context, client.StartWorkflowOptions, any, ...any) (client.WorkflowRun, error)
	CancelWorkflow(context.Context, string, string) error
}

type TemporalHelloAgentConfig struct {
	Client    TemporalWorkflowClient
	TaskQueue string
}

type TemporalHelloAgentStarter struct {
	client    TemporalWorkflowClient
	taskQueue string
}

func NewTemporalHelloAgentStarter(config TemporalHelloAgentConfig) *TemporalHelloAgentStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = HelloAgentTaskQueue
	}
	return &TemporalHelloAgentStarter{client: config.Client, taskQueue: taskQueue}
}


func (s *TemporalHelloAgentStarter) StartHelloAgent(ctx context.Context, input StartHelloAgentInput) (HelloAgentRun, error) {
	if input.TenantID == "" || input.ProjectID == "" {
		return HelloAgentRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and project_id are required",
		}
	}
	if s.client == nil {
		return HelloAgentRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for hello_agent",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return HelloAgentRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate hello agent run id",
		}
	}
	payload := map[string]any{
		"tenant_id":     input.TenantID,
		"project_id":    input.ProjectID,
		"run_id":        runID,
		"workflow_type": HelloAgentWorkflowType,
		"actor_user_id": strings.TrimSpace(input.ActorUserID),
		"trace_id":      "trace_" + strings.TrimPrefix(runID, "run_"),
		"permissions": map[string][]string{
			"hello_agent": {"run"},
		},
	}
	workflowRun, err := s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       "hello_agent_" + runID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: time.Minute,
		WorkflowRunTimeout:       time.Minute,
	}, HelloAgentWorkflowName, payload)
	if err != nil {
		return HelloAgentRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("failed to start hello_agent workflow: %v", err),
		}
	}
	var result map[string]any
	if err := workflowRun.Get(ctx, &result); err != nil {
		return HelloAgentRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("hello_agent workflow failed: %v", err),
		}
	}
	status, _ := result["status"].(string)
	if status != "completed" {
		return HelloAgentRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("hello_agent workflow returned status %q", status),
		}
	}
	return HelloAgentRun{
		RunID:        runID,
		ProjectID:    input.ProjectID,
		WorkflowType: HelloAgentWorkflowType,
		Status:       status,
	}, nil
}
