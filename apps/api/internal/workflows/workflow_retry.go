package workflows

import "context"

type RetryWorkflowRunInput struct {
	TenantID    string
	RunID       string
	ActorUserID string
	RequestID   string
}

type WorkflowRunRetry struct {
	RunID  string
	Status string
}

type WorkflowRetrier interface {
	RetryWorkflowRun(context.Context, RetryWorkflowRunInput) (WorkflowRunRetry, error)
}

type DisabledWorkflowRetrier struct{}

func NewDisabledWorkflowRetrier() *DisabledWorkflowRetrier {
	return &DisabledWorkflowRetrier{}
}

func (r *DisabledWorkflowRetrier) RetryWorkflowRun(_ context.Context, _ RetryWorkflowRunInput) (WorkflowRunRetry, error) {
	return WorkflowRunRetry{}, &AppError{
		Code:    "WORKFLOW_RETRY_BACKEND_UNCONFIGURED",
		Message: "workflow retry backend is not configured",
	}
}
