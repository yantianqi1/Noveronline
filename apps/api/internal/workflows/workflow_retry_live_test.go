package workflows

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"

	"go.temporal.io/sdk/client"
)

const (
	liveSeedRetrySegmentOneID = "85555555-5555-4555-8555-555555555555"
	liveSeedRetrySegmentTwoID = "86666666-6666-4666-8666-666666666666"
)

func TestLiveSQLSeedSegmentRetrierRejectsRequestedAndRunningOverlap(t *testing.T) {
	fixture := prepareLiveSeedSegmentRetryGuardFixture(t)
	temporalClient := &countingSeedSegmentRetryTemporalClient{}
	execer := &capturingSeedSegmentRetryExecer{inner: NewSQLDBWriterAdmissionExecer(fixture.AppDB)}
	retrier := NewSQLSeedSegmentRetrier(SQLSeedSegmentRetrierConfig{
		Execer:    execer,
		Client:    temporalClient,
		TaskQueue: "seed-retry-live-test",
	})
	input := RetrySeedSegmentsInput{
		TenantID:    liveSeedTenantID,
		ProjectID:   liveSeedProjectID,
		RunID:       liveSeedRunID,
		SegmentIDs:  []string{liveSeedRetrySegmentOneID, liveSeedRetrySegmentTwoID},
		ActorUserID: liveSeedUserID,
		RequestID:   "req-live-seed-segments-first",
	}

	retried, err := retrier.RetrySeedSegments(context.Background(), input)
	if err != nil {
		t.Fatalf("admit first seed segment retry: code=%s err=%v postgres=%v", ErrorCode(err), err, execer.lastErr)
	}
	if retried.Status != "retry_requested" || retried.RequestedCount != 2 {
		t.Fatalf("unexpected first retry result: %#v", retried)
	}
	if temporalClient.starts != 1 {
		t.Fatalf("expected one Temporal start, got %d", temporalClient.starts)
	}
	retryAttemptID := temporalClient.retryAttemptID(t)
	assertLiveSeedSegmentRetryGuardState(
		t,
		fixture.AdminDB,
		"requested",
		"req-live-seed-segments-first",
		retryAttemptID,
	)

	input.RequestID = "req-live-seed-segments-overlap-requested"
	if _, err := retrier.RetrySeedSegments(context.Background(), input); ErrorCode(err) != "SEED_SEGMENT_RETRY_FAILED" {
		t.Fatalf("expected requested overlap to fail closed, got code=%s err=%v", ErrorCode(err), err)
	}
	if temporalClient.starts != 1 {
		t.Fatalf("requested overlap started another Temporal workflow: %d", temporalClient.starts)
	}
	assertLiveSeedSegmentRetryGuardState(
		t,
		fixture.AdminDB,
		"requested",
		"req-live-seed-segments-first",
		retryAttemptID,
	)

	if _, err := fixture.AdminDB.Exec(`UPDATE seed_segment_retry_requests
SET status = 'running', updated_at = now()
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3`, liveSeedTenantID, liveSeedProjectID, liveSeedRunID); err != nil {
		t.Fatalf("advance retry rows to running: %v", err)
	}
	input.RequestID = "req-live-seed-segments-overlap-running"
	if _, err := retrier.RetrySeedSegments(context.Background(), input); ErrorCode(err) != "SEED_SEGMENT_RETRY_FAILED" {
		t.Fatalf("expected running overlap to fail closed, got code=%s err=%v", ErrorCode(err), err)
	}
	if temporalClient.starts != 1 {
		t.Fatalf("running overlap started another Temporal workflow: %d", temporalClient.starts)
	}
	assertLiveSeedSegmentRetryGuardState(
		t,
		fixture.AdminDB,
		"running",
		"req-live-seed-segments-first",
		retryAttemptID,
	)
}

type capturingSeedSegmentRetryExecer struct {
	inner   WriterAdmissionSQLExecer
	lastErr error
}

func (e *capturingSeedSegmentRetryExecer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	result, err := e.inner.ExecContext(ctx, query, args...)
	e.lastErr = err
	return result, err
}

func (e *capturingSeedSegmentRetryExecer) ExecTenantContext(
	ctx context.Context,
	tenantID string,
	projectID string,
	query string,
	args ...any,
) (sql.Result, error) {
	tenantExecer, ok := e.inner.(WriterAdmissionSQLTenantExecer)
	if !ok {
		return e.ExecContext(ctx, query, args...)
	}
	result, err := tenantExecer.ExecTenantContext(ctx, tenantID, projectID, query, args...)
	e.lastErr = err
	return result, err
}

type liveSeedSegmentRetryGuardFixture struct {
	AdminDB *sql.DB
	AppDB   *sql.DB
}

func prepareLiveSeedSegmentRetryGuardFixture(t *testing.T) liveSeedSegmentRetryGuardFixture {
	t.Helper()
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_SEED_RETRY_LIVE_DATABASE_URL"))
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_SEED_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_SEED_RETRY_LIVE_DATABASE_URL to run live Seed segment retry guard E2E")
	}
	prepareLiveSeedGoDatabase(t, adminURL)

	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open live seed retry admin db: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO workflow_runs (
  tenant_id, run_id, workflow_type, project_id, status, started_by, temporal_workflow_id
) VALUES ($1, $2, 'seed_pipeline', $3, 'failed', $4, $5)`,
		liveSeedTenantID,
		liveSeedRunID,
		liveSeedProjectID,
		liveSeedUserID,
		"seed_run_"+liveSeedRunID,
	); err != nil {
		adminDB.Close()
		t.Fatalf("seed failed workflow run: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO text_segments (
  tenant_id, segment_id, project_id, run_id, segment_order, content_excerpt
) VALUES
  ($1, $2, $3, $4, 0, 'live retry segment one'),
  ($1, $5, $3, $4, 1, 'live retry segment two')`,
		liveSeedTenantID,
		liveSeedRetrySegmentOneID,
		liveSeedProjectID,
		liveSeedRunID,
		liveSeedRetrySegmentTwoID,
	); err != nil {
		adminDB.Close()
		t.Fatalf("seed text segments: %v", err)
	}

	appDB, err := sql.Open("pgx", liveSeedAppDatabaseURL(t, adminURL))
	if err != nil {
		adminDB.Close()
		t.Fatalf("open live seed retry app db: %v", err)
	}
	t.Cleanup(func() {
		_ = appDB.Close()
		_, _ = adminDB.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveSeedTenantID)
		_ = adminDB.Close()
	})
	return liveSeedSegmentRetryGuardFixture{AdminDB: adminDB, AppDB: appDB}
}

func assertLiveSeedSegmentRetryGuardState(
	t *testing.T,
	db *sql.DB,
	expectedStatus string,
	expectedRequestID string,
	expectedAttemptID string,
) {
	t.Helper()
	rows, err := db.Query(`SELECT status, request_id, retry_attempt_id::text
FROM seed_segment_retry_requests
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
ORDER BY segment_id`, liveSeedTenantID, liveSeedProjectID, liveSeedRunID)
	if err != nil {
		t.Fatalf("read live seed retry rows: %v", err)
	}
	defer rows.Close()
	rowCount := 0
	for rows.Next() {
		var status string
		var requestID sql.NullString
		var retryAttemptID string
		if err := rows.Scan(&status, &requestID, &retryAttemptID); err != nil {
			t.Fatalf("scan live seed retry row: %v", err)
		}
		rowCount++
		if status != expectedStatus || requestID.String != expectedRequestID || retryAttemptID != expectedAttemptID {
			t.Fatalf("retry guard mutated active row: status=%q request_id=%q retry_attempt_id=%q", status, requestID.String, retryAttemptID)
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate live seed retry rows: %v", err)
	}
	if rowCount != 2 {
		t.Fatalf("expected exactly two retry rows, got %d", rowCount)
	}

	var eventCount int
	var eventType string
	if err := db.QueryRow(`SELECT COUNT(*), COALESCE(MAX(event_type), '')
FROM workflow_events
WHERE tenant_id = $1 AND run_id = $2`, liveSeedTenantID, liveSeedRunID).Scan(&eventCount, &eventType); err != nil {
		t.Fatalf("read live seed retry events: %v", err)
	}
	if eventCount != 1 || eventType != "seed.segments.retry_requested" {
		t.Fatalf("retry guard wrote unexpected events: count=%d type=%q", eventCount, eventType)
	}
}

type countingSeedSegmentRetryTemporalClient struct {
	recordingRetryTemporalClient
	starts int
}

func (c *countingSeedSegmentRetryTemporalClient) ExecuteWorkflow(
	ctx context.Context,
	options client.StartWorkflowOptions,
	workflow any,
	args ...any,
) (client.WorkflowRun, error) {
	c.starts++
	return c.recordingRetryTemporalClient.ExecuteWorkflow(ctx, options, workflow, args...)
}

func (c *countingSeedSegmentRetryTemporalClient) retryAttemptID(t *testing.T) string {
	t.Helper()
	if len(c.args) != 1 {
		t.Fatalf("expected one Temporal payload, got %#v", c.args)
	}
	payload, ok := c.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected map Temporal payload, got %#v", c.args[0])
	}
	retryAttemptID, ok := payload["retry_attempt_id"].(string)
	if !ok || strings.TrimSpace(retryAttemptID) == "" {
		t.Fatalf("Temporal payload missing retry_attempt_id: %#v", payload)
	}
	return retryAttemptID
}
