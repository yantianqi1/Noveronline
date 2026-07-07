package workflows

import (
	"context"
	"errors"
	"testing"

	"go.temporal.io/sdk/client"
)

func TestDisabledHelloAgentStarterFailsExplicitly(t *testing.T) {
	starter := NewDisabledHelloAgentStarter()

	_, err := starter.StartHelloAgent(context.Background(), StartHelloAgentInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit unconfigured workflow backend, got %s (%v)", code, err)
	}
}

func TestTemporalHelloAgentStarterExecutesHelloWorkflowWithContext(t *testing.T) {
	temporalClient := &recordingTemporalClient{}
	starter := NewTemporalHelloAgentStarter(TemporalHelloAgentConfig{
		Client:    temporalClient,
		TaskQueue: HelloAgentTaskQueue,
	})

	run, err := starter.StartHelloAgent(context.Background(), StartHelloAgentInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
	})

	if err != nil {
		t.Fatalf("start hello agent: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-1" || run.WorkflowType != HelloAgentWorkflowType || run.Status != "completed" {
		t.Fatalf("unexpected run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if temporalClient.options.TaskQueue != HelloAgentTaskQueue {
		t.Fatalf("unexpected task queue: %#v", temporalClient.options)
	}
	if temporalClient.workflow != HelloAgentWorkflowName {
		t.Fatalf("unexpected workflow type: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected context payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != "tenant-1" || payload["project_id"] != "project-1" || payload["actor_user_id"] != "user-1" {
		t.Fatalf("lost runtime context payload: %#v", payload)
	}
	if payload["workflow_type"] != HelloAgentWorkflowType || payload["run_id"] != run.RunID || payload["trace_id"] == "" {
		t.Fatalf("lost run/trace payload: %#v", payload)
	}
	permissions := payload["permissions"].(map[string][]string)
	if got := permissions["hello_agent"][0]; got != "run" {
		t.Fatalf("expected hello permission, got %#v", permissions)
	}
}

func TestTemporalHelloAgentStarterSurfacesWorkflowFailure(t *testing.T) {
	temporalClient := &recordingTemporalClient{getErr: errors.New("activity failed")}
	starter := NewTemporalHelloAgentStarter(TemporalHelloAgentConfig{
		Client:    temporalClient,
		TaskQueue: HelloAgentTaskQueue,
	})

	_, err := starter.StartHelloAgent(context.Background(), StartHelloAgentInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_FAILED" {
		t.Fatalf("expected workflow failure, got %s (%v)", code, err)
	}
}

type recordingTemporalClient struct {
	options  client.StartWorkflowOptions
	workflow any
	args     []any
	getErr   error
}

func (c *recordingTemporalClient) ExecuteWorkflow(ctx context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.options = options
	c.workflow = workflow
	c.args = args
	return &recordingWorkflowRun{workflowID: options.ID, getErr: c.getErr}, nil
}

func (c *recordingTemporalClient) CancelWorkflow(context.Context, string, string) error {
	return nil
}

type recordingWorkflowRun struct {
	workflowID string
	getErr     error
}

func (r *recordingWorkflowRun) GetID() string    { return r.workflowID }
func (r *recordingWorkflowRun) GetRunID() string { return "temporal-run-id" }
func (r *recordingWorkflowRun) Get(ctx context.Context, valuePtr any) error {
	if r.getErr != nil {
		return r.getErr
	}
	result := valuePtr.(*map[string]any)
	*result = map[string]any{
		"status": "completed",
	}
	return nil
}
func (r *recordingWorkflowRun) GetWithOptions(ctx context.Context, valuePtr any, _ client.WorkflowRunGetOptions) error {
	return r.Get(ctx, valuePtr)
}
