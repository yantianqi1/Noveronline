package workflows

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"strings"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
	"go.temporal.io/sdk/client"
)

func TestWriterReviewCrossServiceAdmissionLive(t *testing.T) {
	databaseURL := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_APP_DATABASE_URL")
	temporalAddress := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_TEMPORAL_ADDRESS")
	tenantID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_TENANT_ID")
	projectID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_PROJECT_ID")
	draftID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_DRAFT_ID")
	actorID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_ACTOR_ID")
	otherTenantID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_OTHER_TENANT_ID")
	otherProjectID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_OTHER_PROJECT_ID")
	otherActorID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_OTHER_ACTOR_ID")
	taskQueue := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_TASK_QUEUE")

	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatalf("open app-role database: %v", err)
	}
	defer db.Close()
	temporalClient, err := client.Dial(client.Options{
		HostPort:  temporalAddress,
		Namespace: strings.TrimSpace(os.Getenv("MIROFISH_WRITER_REVIEW_LIVE_TEMPORAL_NAMESPACE")),
	})
	if err != nil {
		t.Fatalf("connect Temporal: %v", err)
	}
	defer temporalClient.Close()
	runtimeStore := NewSQLDraftReviewRuntimeStore(db)
	ownerProjectID, err := runtimeStore.LookupDraftReviewProject(context.Background(), DraftReviewOwnerLookupInput{
		TenantID: tenantID, DraftID: draftID, ActorUserID: actorID,
	})
	if err != nil || ownerProjectID != projectID {
		t.Fatalf("owner lookup failed: project=%q err=%v", ownerProjectID, err)
	}
	if _, err := runtimeStore.LookupDraftReviewProject(context.Background(), DraftReviewOwnerLookupInput{
		TenantID: otherTenantID, DraftID: draftID, ActorUserID: otherActorID,
	}); ErrorCode(err) != "NOT_FOUND" {
		t.Fatalf("cross-tenant owner lookup was not hidden: %v", err)
	}
	starter := NewTemporalDraftReviewStarter(TemporalDraftReviewConfig{
		Client: temporalClient, TaskQueue: taskQueue, AdmissionStore: runtimeStore,
	})
	input := StartDraftReviewInput{
		TenantID: tenantID, ProjectID: projectID, DraftID: draftID, ActorUserID: actorID,
		RequestID: "writer-review-live-request", ModuleKey: WriterReviewerModuleKey,
		Options: map[string]any{"severity_floor": "low", "prompt": "must not persist"},
	}
	first, err := starter.StartDraftReview(context.Background(), input)
	if err != nil {
		t.Fatalf("start live writer review: %v", err)
	}
	replayed, err := starter.StartDraftReview(context.Background(), input)
	if err != nil || replayed.ReviewID != first.ReviewID || replayed.RunID != first.RunID {
		t.Fatalf("request replay changed admission: first=%#v replay=%#v err=%v", first, replayed, err)
	}
	conflict := input
	conflict.Options = map[string]any{"severity_floor": "high"}
	if _, err := starter.StartDraftReview(context.Background(), conflict); ErrorCode(err) != "IDEMPOTENCY_CONFLICT" {
		t.Fatalf("expected payload conflict, got %v", err)
	}
	crossTenant := input
	crossTenant.TenantID = otherTenantID
	crossTenant.ProjectID = otherProjectID
	crossTenant.ActorUserID = otherActorID
	crossTenant.RequestID = "writer-review-cross-tenant"
	if _, err := starter.StartDraftReview(context.Background(), crossTenant); ErrorCode(err) != "NOT_FOUND" {
		t.Fatalf("cross-tenant draft was not hidden: %v", err)
	}
	var temporalID string
	err = withWriterReviewLiveContext(context.Background(), db, tenantID, actorID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), `SELECT temporal_workflow_id
FROM workflow_runs WHERE tenant_id::text = $1 AND project_id::text = $2 AND run_id::text = $3`,
			tenantID, projectID, first.RunID).Scan(&temporalID)
	})
	if err != nil || temporalID != "writer_review_"+first.ReviewID {
		t.Fatalf("stable Temporal id was not persisted: id=%q err=%v", temporalID, err)
	}
}

func TestWriterReviewStartCompensationLive(t *testing.T) {
	databaseURL := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_APP_DATABASE_URL")
	tenantID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_TENANT_ID")
	projectID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_PROJECT_ID")
	draftID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_DRAFT_ID")
	actorID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_ACTOR_ID")
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	temporal := &failingWriterReviewTemporalClient{err: errors.New("private Temporal failure")}
	starter := NewTemporalDraftReviewStarter(TemporalDraftReviewConfig{
		Client: temporal, AdmissionStore: NewSQLDraftReviewRuntimeStore(db),
	})
	_, err = starter.StartDraftReview(context.Background(), StartDraftReviewInput{
		TenantID: tenantID, ProjectID: projectID, DraftID: draftID, ActorUserID: actorID,
		RequestID: "writer-review-live-compensation", ModuleKey: WriterReviewerModuleKey,
	})
	if ErrorCode(err) != "WORKFLOW_FAILED" {
		t.Fatalf("unexpected compensation error: %v", err)
	}
	var reviewStatus, workflowStatus, eventType string
	err = withWriterReviewLiveContext(context.Background(), db, tenantID, actorID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), `SELECT review.status, workflow.status, event.event_type
FROM draft_reviews review
JOIN workflow_runs workflow ON workflow.tenant_id = review.tenant_id AND workflow.run_id = review.run_id
JOIN workflow_events event ON event.tenant_id = workflow.tenant_id AND event.run_id = workflow.run_id
 AND event.event_type = 'workflow.start_failed'
WHERE review.tenant_id::text = $1 AND review.project_id::text = $2
  AND workflow.workflow_type = 'writer_review'
  AND EXISTS (SELECT 1 FROM workflow_events queued WHERE queued.tenant_id = workflow.tenant_id
    AND queued.run_id = workflow.run_id AND queued.event_type = 'workflow.queued'
    AND queued.payload_jsonb->>'request_id' = 'writer-review-live-compensation')`, tenantID, projectID).Scan(
			&reviewStatus, &workflowStatus, &eventType,
		)
	})
	if err != nil || reviewStatus != "failed" || workflowStatus != "failed" || eventType != "workflow.start_failed" {
		t.Fatalf("compensation was not terminal: review=%s workflow=%s event=%s err=%v", reviewStatus, workflowStatus, eventType, err)
	}
}

type failingWriterReviewTemporalClient struct{ err error }

func (c *failingWriterReviewTemporalClient) ExecuteWorkflow(context.Context, client.StartWorkflowOptions, any, ...any) (client.WorkflowRun, error) {
	return nil, c.err
}

func (c *failingWriterReviewTemporalClient) CancelWorkflow(context.Context, string, string) error {
	return nil
}

func TestWriterReviewIssueMutationLive(t *testing.T) {
	databaseURL := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_APP_DATABASE_URL")
	tenantID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_TENANT_ID")
	projectID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_PROJECT_ID")
	actorID := writerReviewLiveEnv(t, "MIROFISH_WRITER_REVIEW_LIVE_ACTOR_ID")
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	type issueVersion struct{ id, version string }
	issues := []issueVersion{}
	err = withWriterReviewLiveContext(context.Background(), db, tenantID, actorID, func(tx *sql.Tx) error {
		rows, queryErr := tx.QueryContext(context.Background(), `SELECT issue_id::text, updated_at::text
FROM draft_review_issues WHERE tenant_id::text = $1 AND project_id::text = $2 AND status = 'open'
ORDER BY created_at LIMIT 3`, tenantID, projectID)
		if queryErr != nil {
			return queryErr
		}
		defer rows.Close()
		for rows.Next() {
			var issue issueVersion
			if err := rows.Scan(&issue.id, &issue.version); err != nil {
				return err
			}
			issues = append(issues, issue)
		}
		return rows.Err()
	})
	if err != nil || len(issues) != 3 {
		t.Fatalf("expected three live issues, got %#v err=%v", issues, err)
	}
	runtimeStore := NewSQLDraftReviewRuntimeStore(db)
	ownerProjectID, err := runtimeStore.LookupDraftReviewProject(context.Background(), DraftReviewOwnerLookupInput{
		TenantID: tenantID, IssueID: issues[0].id, ActorUserID: actorID,
	})
	if err != nil || ownerProjectID != projectID {
		t.Fatalf("issue owner lookup failed: project=%q err=%v", ownerProjectID, err)
	}
	store := NewSQLDraftReviewIssueStore(db)
	statuses := []string{"accepted", "dismissed", "resolved"}
	for index, status := range statuses {
		input := UpdateDraftReviewIssueInput{
			TenantID: tenantID, ProjectID: projectID, IssueID: issues[index].id,
			ActorUserID: actorID, RequestID: "writer-review-issue-" + status,
			Status: status, Version: issues[index].version,
		}
		result, updateErr := store.UpdateIssueStatus(context.Background(), input)
		if updateErr != nil || result.Status != status || result.Version == input.Version {
			t.Fatalf("update %s failed: %#v %v", status, result, updateErr)
		}
		replayed, replayErr := store.UpdateIssueStatus(context.Background(), input)
		if replayErr != nil || replayed.Status != status || replayed.Version != result.Version {
			t.Fatalf("idempotent %s replay failed: %#v %v", status, replayed, replayErr)
		}
		conflict := input
		conflict.Status = statuses[(index+1)%len(statuses)]
		if _, conflictErr := store.UpdateIssueStatus(context.Background(), conflict); ErrorCode(conflictErr) != "WRITER_REVIEW_ISSUE_CONFLICT" {
			t.Fatalf("different terminal action did not conflict: %v", conflictErr)
		}
	}
}

func withWriterReviewLiveContext(ctx context.Context, db *sql.DB, tenantID, actorID string, operation func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", tenantID, actorID); err != nil {
		return err
	}
	if err := operation(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func writerReviewLiveEnv(t *testing.T, key string) string {
	t.Helper()
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		t.Skip("set " + key + " to run Writer reviewer live tests")
	}
	return value
}
