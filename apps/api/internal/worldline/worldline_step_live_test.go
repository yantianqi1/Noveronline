package worldline

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"testing"

	"mirofish-novel/apps/api/internal/testschema"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
	"go.temporal.io/sdk/client"
)

const (
	worldlineLiveAppRole     = "mirofish_worldline_live_app"
	worldlineLiveAppPassword = "mirofish_worldline_live_password"
)

type countingWorldlineTemporalClient struct {
	mu      sync.Mutex
	options []client.StartWorkflowOptions
	err     error
}

type capturingWorldlineStepExecer struct {
	inner   *SQLDBQueryer
	lastErr error
}

func (e *capturingWorldlineStepExecer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	result, err := e.inner.ExecContext(ctx, query, args...)
	e.lastErr = err
	return result, err
}

func (e *capturingWorldlineStepExecer) ExecTenantActorContext(
	ctx context.Context,
	tenantID string,
	actorUserID string,
	query string,
	args ...any,
) (sql.Result, error) {
	result, err := e.inner.ExecTenantActorContext(ctx, tenantID, actorUserID, query, args...)
	e.lastErr = err
	return result, err
}

func (e *capturingWorldlineStepExecer) AdmitWorldlineStep(
	ctx context.Context,
	input StartStepInput,
	proposed StepRun,
	eventID string,
	temporalWorkflowID string,
	traceID string,
	mode string,
) (StepRun, bool, error) {
	run, idempotent, err := e.inner.AdmitWorldlineStep(
		ctx, input, proposed, eventID, temporalWorkflowID, traceID, mode,
	)
	e.lastErr = err
	return run, idempotent, err
}

func (c *countingWorldlineTemporalClient) ExecuteWorkflow(
	_ context.Context,
	options client.StartWorkflowOptions,
	_ any,
	_ ...any,
) (client.WorkflowRun, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.options = append(c.options, options)
	return nil, c.err
}

func TestWorldlineStepAdmissionLiveCompensatesTemporalStartFailure(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WORLDLINE_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WORLDLINE_LIVE_DATABASE_URL to run the live Worldline compensation E2E")
	}
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin database: %v", err)
	}
	defer adminDB.Close()
	applyWorldlineLiveSchema(t, adminDB)
	ensureWorldlineLiveAppRole(t, adminDB)

	tenantID := newUUID()
	userID := newUUID()
	projectID := newUUID()
	sessionRunID := newUUID()
	sessionID := newUUID()
	prepareWorldlineLiveSession(t, adminDB, tenantID, userID, projectID, sessionRunID, sessionID)
	defer cleanupWorldlineLiveSession(t, adminDB, tenantID, userID)

	appConfig, err := pgx.ParseConfig(adminURL)
	if err != nil {
		t.Fatalf("parse admin database URL: %v", err)
	}
	appConfig.User = worldlineLiveAppRole
	appConfig.Password = worldlineLiveAppPassword
	appDB := stdlib.OpenDB(*appConfig)
	defer appDB.Close()
	temporalClient := &countingWorldlineTemporalClient{err: errors.New("private temporal provider failure")}
	execer := &capturingWorldlineStepExecer{inner: NewSQLDBQueryer(appDB)}
	starter := NewSQLStepStarter(SQLStepStarterConfig{Execer: execer, Client: temporalClient})

	_, startErr := starter.StartStep(context.Background(), StartStepInput{
		TenantID: tenantID, ProjectID: projectID, SessionID: sessionID,
		ActorUserID: userID, RequestID: "req-live-compensation", Mode: "director",
	})
	if ErrorCode(startErr) != "WORKFLOW_FAILED" || startErr.Error() != "failed to start worldline step workflow" {
		t.Fatalf("unexpected public start error: code=%s err=%v postgres=%v", ErrorCode(startErr), startErr, execer.lastErr)
	}

	var runStatus, sessionStatus, eventType, errorCode, errorMessage string
	err = adminDB.QueryRow(`SELECT
  workflow_run.status,
  session.status,
  event.event_type,
  COALESCE(workflow_run.error_code, ''),
  COALESCE(workflow_run.error_message, '')
FROM workflow_runs AS workflow_run
JOIN workflow_events AS event
  ON event.tenant_id = workflow_run.tenant_id
 AND event.run_id = workflow_run.run_id
 AND event.event_type = 'workflow.start_failed'
JOIN worldline_sessions AS session
  ON session.tenant_id = workflow_run.tenant_id
 AND session.project_id = workflow_run.project_id
WHERE workflow_run.tenant_id = $1
  AND workflow_run.project_id = $2
  AND workflow_run.workflow_type = 'worldline_step'`, tenantID, projectID).Scan(
		&runStatus, &sessionStatus, &eventType, &errorCode, &errorMessage,
	)
	if err != nil {
		t.Fatalf("read compensation state: %v", err)
	}
	if runStatus != "failed" || sessionStatus != "paused" || eventType != "workflow.start_failed" ||
		errorCode != "WORKFLOW_FAILED" || errorMessage != "failed to start worldline step workflow" {
		t.Fatalf("unexpected compensation state: run=%s session=%s event=%s code=%s message=%s", runStatus, sessionStatus, eventType, errorCode, errorMessage)
	}
}

func (c *countingWorldlineTemporalClient) callCount() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.options)
}

func TestWorldlineStepAdmissionLiveSerializesOverlapAndReusesRequest(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WORLDLINE_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WORLDLINE_LIVE_DATABASE_URL to run the live Worldline admission guard E2E")
	}
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin database: %v", err)
	}
	defer adminDB.Close()
	applyWorldlineLiveSchema(t, adminDB)
	ensureWorldlineLiveAppRole(t, adminDB)

	tenantID := newUUID()
	userID := newUUID()
	projectID := newUUID()
	sessionRunID := newUUID()
	sessionID := newUUID()
	prepareWorldlineLiveSession(t, adminDB, tenantID, userID, projectID, sessionRunID, sessionID)
	defer cleanupWorldlineLiveSession(t, adminDB, tenantID, userID)

	appConfig, err := pgx.ParseConfig(adminURL)
	if err != nil {
		t.Fatalf("parse admin database URL: %v", err)
	}
	appConfig.User = worldlineLiveAppRole
	appConfig.Password = worldlineLiveAppPassword
	appDB := stdlib.OpenDB(*appConfig)
	defer appDB.Close()
	queryer := NewSQLDBQueryer(appDB)
	temporalClient := &countingWorldlineTemporalClient{}
	starter := NewSQLStepStarter(SQLStepStarterConfig{Execer: queryer, Client: temporalClient})

	requests := []string{"req-live-a", "req-live-b"}
	runs := make([]StepRun, len(requests))
	errs := make([]error, len(requests))
	var wait sync.WaitGroup
	start := make(chan struct{})
	for index, requestID := range requests {
		wait.Add(1)
		go func(index int, requestID string) {
			defer wait.Done()
			<-start
			runs[index], errs[index] = starter.StartStep(context.Background(), StartStepInput{
				TenantID: tenantID, ProjectID: projectID, SessionID: sessionID,
				ActorUserID: userID, RequestID: requestID, Mode: "director",
			})
		}(index, requestID)
	}
	close(start)
	wait.Wait()

	winner := -1
	for index, admissionErr := range errs {
		if admissionErr == nil {
			if winner != -1 {
				t.Fatalf("two concurrent steps were admitted: runs=%#v errors=%#v", runs, errs)
			}
			winner = index
			continue
		}
		if ErrorCode(admissionErr) != "WORLDLINE_STEP_ACTIVE" || admissionErr.Error() != "worldline session already has an active step" {
			t.Fatalf("unexpected overlap error at %d: code=%s err=%v", index, ErrorCode(admissionErr), admissionErr)
		}
	}
	if winner == -1 {
		t.Fatalf("no concurrent step was admitted: %#v", errs)
	}
	if temporalClient.callCount() != 1 {
		t.Fatalf("expected one Temporal start, got %d", temporalClient.callCount())
	}

	replayed, err := starter.StartStep(context.Background(), StartStepInput{
		TenantID: tenantID, ProjectID: projectID, SessionID: sessionID,
		ActorUserID: userID, RequestID: requests[winner], Mode: "director",
	})
	if err != nil {
		t.Fatalf("replay same request: %v", err)
	}
	if replayed.RunID != runs[winner].RunID || replayed.Status != "queued" {
		t.Fatalf("idempotent request did not return original run: original=%#v replay=%#v", runs[winner], replayed)
	}
	if temporalClient.callCount() != 1 {
		t.Fatalf("idempotent replay started Temporal again: %d", temporalClient.callCount())
	}

	assertWorldlineLiveAdmissionState(t, adminDB, tenantID, projectID, sessionID, runs[winner].RunID, requests[winner])
}

func applyWorldlineLiveSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	if err := testschema.EnsureLiveSchema(context.Background(), db,
		"../../../../infra/postgres/migrations/0001_core_saas.sql",
		"tenants", "projects", "workflow_runs", "worldline_sessions", "worldline_events", "workflow_events",
	); err != nil {
		t.Fatalf("ensure live Worldline schema: %v", err)
	}
}

func ensureWorldlineLiveAppRole(t *testing.T, db *sql.DB) {
	t.Helper()
	query := fmt.Sprintf(`DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '%s') THEN
    CREATE ROLE %s LOGIN PASSWORD '%s' IN ROLE mirofish_app;
  END IF;
END $$;
ALTER ROLE %s WITH LOGIN PASSWORD '%s';
GRANT mirofish_app TO %s`,
		worldlineLiveAppRole, worldlineLiveAppRole, worldlineLiveAppPassword,
		worldlineLiveAppRole, worldlineLiveAppPassword, worldlineLiveAppRole,
	)
	if _, err := db.Exec(query); err != nil {
		t.Fatalf("ensure live app role: %v", err)
	}
}

func prepareWorldlineLiveSession(t *testing.T, db *sql.DB, tenantID, userID, projectID, sessionRunID, sessionID string) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatalf("begin live fixture: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	statements := []struct {
		query string
		args  []any
	}{
		{`INSERT INTO users (user_id, email, display_name) VALUES ($1, $2, 'Worldline Live')`, []any{userID, "worldline-" + userID + "@example.test"}},
		{`INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES ($1, $2, 'Worldline Live', 'personal')`, []any{tenantID, "worldline-" + tenantID}},
		{`INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES ($1, $2, 'owner')`, []any{tenantID, userID}},
		{`INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES ($1, $2, 'Worldline Live', $3)`, []any{tenantID, projectID, userID}},
		{`INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES ($1, $2, $3, 'project_owner')`, []any{tenantID, projectID, userID}},
		{`INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by) VALUES ($1, $2, 'worldline_session', $3, 'completed', 100, $4)`, []any{tenantID, sessionRunID, projectID, userID}},
		{`INSERT INTO worldline_sessions (tenant_id, session_id, project_id, run_id, status, lifecycle, goal_summary, created_by) VALUES ($1, $2, $3, $4, 'paused', 'active', 'Live admission guard', $5)`, []any{tenantID, sessionID, projectID, sessionRunID, userID}},
	}
	for _, statement := range statements {
		if _, err := tx.Exec(statement.query, statement.args...); err != nil {
			t.Fatalf("prepare live fixture: %v", err)
		}
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit live fixture: %v", err)
	}
}

func assertWorldlineLiveAdmissionState(t *testing.T, db *sql.DB, tenantID, projectID, sessionID, runID, requestID string) {
	t.Helper()
	var runCount, queuedEventCount int
	var sessionStatus, persistedRequestID string
	err := db.QueryRow(`SELECT
  (SELECT COUNT(*) FROM workflow_runs WHERE tenant_id = $1 AND project_id = $2 AND workflow_type = 'worldline_step'),
  (SELECT COUNT(*) FROM workflow_events WHERE tenant_id = $1 AND project_id = $2 AND event_type = 'workflow.queued'),
  (SELECT status FROM worldline_sessions WHERE tenant_id = $1 AND project_id = $2 AND session_id = $3),
  (SELECT payload_jsonb->>'request_id' FROM workflow_events WHERE tenant_id = $1 AND project_id = $2 AND run_id = $4 AND event_type = 'workflow.queued')`,
		tenantID, projectID, sessionID, runID,
	).Scan(&runCount, &queuedEventCount, &sessionStatus, &persistedRequestID)
	if err != nil {
		t.Fatalf("read live admission state: %v", err)
	}
	if runCount != 1 || queuedEventCount != 1 || sessionStatus != "running" || persistedRequestID != requestID {
		t.Fatalf("unexpected all-or-nothing admission state: runs=%d events=%d session=%s request=%s", runCount, queuedEventCount, sessionStatus, persistedRequestID)
	}
}

func cleanupWorldlineLiveSession(t *testing.T, db *sql.DB, tenantID, userID string) {
	t.Helper()
	if _, err := db.Exec(`DELETE FROM tenants WHERE tenant_id = $1`, tenantID); err != nil {
		t.Errorf("cleanup live tenant: %v", err)
	}
	if _, err := db.Exec(`DELETE FROM users WHERE user_id = $1`, userID); err != nil {
		t.Errorf("cleanup live user: %v", err)
	}
}
