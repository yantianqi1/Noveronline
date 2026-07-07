package workflows

import (
	"context"
	"testing"
)

func TestDisabledWorkflowRetrierFailsClosed(t *testing.T) {
	retrier := NewDisabledWorkflowRetrier()

	_, err := retrier.RetryWorkflowRun(context.Background(), RetryWorkflowRunInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_RETRY_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected retry backend to fail closed, got %s (%v)", code, err)
	}
}
