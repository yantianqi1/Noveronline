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
	autoEvolutionLiveAppRole     = "mirofish_auto_evolution_live_app"
	autoEvolutionLiveAppPassword = "mirofish_auto_evolution_live_password"
)

type autoEvolutionCountingTemporalClient struct {
	mu      sync.Mutex
	options []client.StartWorkflowOptions
	err     error
}

func TestWorldlineAutoEvolutionAdmissionLiveSerializesOverlapAndReusesRequest(t *testing.T) {
	adminDB, appDB := openAutoEvolutionLiveDatabases(t)
	defer adminDB.Close()
	defer appDB.Close()

	tenantID := newUUID()
	userID := newUUID()
	projectID := newUUID()
	sessionRunID := newUUID()
	sessionID := newUUID()
	prepareAutoEvolutionLiveSession(t, adminDB, tenantID, userID, projectID, sessionRunID, sessionID)
	defer cleanupAutoEvolutionLiveSession(t, adminDB, tenantID, userID)

	temporalClient := &autoEvolutionCountingTemporalClient{}
	starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{
		Store:  NewSQLAutoEvolutionAdmissionStore(appDB),
		Client: temporalClient,
	})
	requests := []StartAutoEvolutionInput{
		{TenantID: tenantID, ProjectID: projectID, SessionID: sessionID, ActorUserID: userID, RequestID: "req-auto-a", MaxSteps: 5},
		{TenantID: tenantID, ProjectID: projectID, SessionID: sessionID, ActorUserID: userID, RequestID: "req-auto-b", MaxSteps: 8},
	}
	runs := make([]AutoEvolutionRun, len(requests))
	errs := make([]error, len(requests))
	start := make(chan struct{})
	var wait sync.WaitGroup
	for index := range requests {
		wait.Add(1)
		go func(index int) {
			defer wait.Done()
			<-start
			runs[index], errs[index] = starter.StartAutoEvolution(context.Background(), requests[index])
		}(index)
	}
	close(start)
	wait.Wait()

	winner := -1
	for index, admissionErr := range errs {
		if admissionErr == nil {
			if winner != -1 {
				t.Fatalf("two concurrent auto-evolutions were admitted: runs=%#v errors=%#v", runs, errs)
			}
			winner = index
			continue
		}
		if ErrorCode(admissionErr) != "WORLDLINE_AUTO_EVOLUTION_ACTIVE" ||
			admissionErr.Error() != "worldline session already has an active auto-evolution" {
			t.Fatalf("unexpected overlap error at %d: code=%s err=%v", index, ErrorCode(admissionErr), admissionErr)
		}
	}
	if winner == -1 {
		t.Fatalf("no concurrent auto-evolution was admitted: %#v", errs)
	}
	if temporalClient.callCount() != 1 {
		t.Fatalf("expected one Temporal start, got %d", temporalClient.callCount())
	}

	replayed, err := starter.StartAutoEvolution(context.Background(), requests[winner])
	if err != nil {
		t.Fatalf("replay winning request: %v", err)
	}
	if replayed.RunID != runs[winner].RunID || replayed.MaxSteps != requests[winner].MaxSteps {
		t.Fatalf("idempotent replay returned a different run: original=%#v replay=%#v", runs[winner], replayed)
	}
	if temporalClient.callCount() != 1 {
		t.Fatalf("idempotent replay started Temporal again: %d", temporalClient.callCount())
	}

	assertAutoEvolutionLiveAdmission(
		t,
		adminDB,
		tenantID,
		projectID,
		sessionID,
		runs[winner].RunID,
		requests[winner].RequestID,
		requests[winner].MaxSteps,
	)
}

func TestWorldlineAutoEvolutionAdmissionLiveCompensatesAndRequiresCurrentWorld(t *testing.T) {
	adminDB, appDB := openAutoEvolutionLiveDatabases(t)
	defer adminDB.Close()
	defer appDB.Close()

	tenantID := newUUID()
	userID := newUUID()
	projectID := newUUID()
	sessionRunID := newUUID()
	sessionID := newUUID()
	prepareAutoEvolutionLiveSession(t, adminDB, tenantID, userID, projectID, sessionRunID, sessionID)
	defer cleanupAutoEvolutionLiveSession(t, adminDB, tenantID, userID)

	starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{
		Store: NewSQLAutoEvolutionAdmissionStore(appDB),
		Client: &autoEvolutionCountingTemporalClient{
			err: errors.New("private Temporal start failure"),
		},
	})
	input := StartAutoEvolutionInput{
		TenantID: tenantID, ProjectID: projectID, SessionID: sessionID,
		ActorUserID: userID, RequestID: "req-auto-compensation", MaxSteps: 3,
	}

	_, startErr := starter.StartAutoEvolution(context.Background(), input)
	if ErrorCode(startErr) != "WORKFLOW_FAILED" || startErr.Error() != "failed to start worldline auto-evolution workflow" {
		t.Fatalf("unexpected public start failure: code=%s err=%v", ErrorCode(startErr), startErr)
	}

	var runStatus, sessionStatus, errorCode, errorMessage string
	var queuedCount, failedCount, candidateEventCount int
	err := adminDB.QueryRow(`SELECT
  workflow_run.status,
  session.status,
  workflow_run.error_code,
  workflow_run.error_message,
  (SELECT COUNT(*) FROM workflow_events AS event
    WHERE event.tenant_id = workflow_run.tenant_id AND event.run_id = workflow_run.run_id
      AND event.event_type = 'workflow.queued'),
  (SELECT COUNT(*) FROM workflow_events AS event
    WHERE event.tenant_id = workflow_run.tenant_id AND event.run_id = workflow_run.run_id
      AND event.event_type = 'workflow.start_failed'),
  (SELECT COUNT(*) FROM worldline_events AS event
    WHERE event.tenant_id = workflow_run.tenant_id AND event.project_id = workflow_run.project_id
      AND event.session_id = session.session_id)
FROM workflow_runs AS workflow_run
JOIN worldline_sessions AS session
  ON session.tenant_id = workflow_run.tenant_id
 AND session.project_id = workflow_run.project_id
WHERE workflow_run.tenant_id = $1
  AND workflow_run.project_id = $2
  AND workflow_run.workflow_type = 'worldline_auto_evolution'`, tenantID, projectID).Scan(
		&runStatus,
		&sessionStatus,
		&errorCode,
		&errorMessage,
		&queuedCount,
		&failedCount,
		&candidateEventCount,
	)
	if err != nil {
		t.Fatalf("read compensated auto-evolution: %v", err)
	}
	if runStatus != "failed" || sessionStatus != "paused" || errorCode != "WORKFLOW_FAILED" ||
		errorMessage != "failed to start worldline auto-evolution workflow" ||
		queuedCount != 1 || failedCount != 1 || candidateEventCount != 0 {
		t.Fatalf(
			"unexpected compensation: run=%s session=%s code=%s message=%s queued=%d failed=%d candidates=%d",
			runStatus,
			sessionStatus,
			errorCode,
			errorMessage,
			queuedCount,
			failedCount,
			candidateEventCount,
		)
	}

	if _, err := adminDB.Exec(`UPDATE worldline_sessions SET lifecycle = 'archived' WHERE tenant_id = $1 AND session_id = $2`, tenantID, sessionID); err != nil {
		t.Fatalf("archive live session: %v", err)
	}
	input.RequestID = "req-auto-archived"
	_, archivedErr := starter.StartAutoEvolution(context.Background(), input)
	if ErrorCode(archivedErr) != "CURRENT_WORLD_REQUIRED" ||
		archivedErr.Error() != "worldline auto-evolution requires the active current_world session" {
		t.Fatalf("unexpected archived-world error: code=%s err=%v", ErrorCode(archivedErr), archivedErr)
	}
	var runCount int
	if err := adminDB.QueryRow(`SELECT COUNT(*) FROM workflow_runs
WHERE tenant_id = $1 AND project_id = $2 AND workflow_type = 'worldline_auto_evolution'`, tenantID, projectID).Scan(&runCount); err != nil {
		t.Fatalf("count auto-evolutions after archived rejection: %v", err)
	}
	if runCount != 1 {
		t.Fatalf("archived world admitted another workflow run: %d", runCount)
	}

	if _, err := adminDB.Exec(`UPDATE worldline_sessions
SET lifecycle = 'active', status = 'completed'
WHERE tenant_id = $1 AND session_id = $2`, tenantID, sessionID); err != nil {
		t.Fatalf("complete live session: %v", err)
	}
	input.RequestID = "req-auto-terminal"
	_, terminalErr := starter.StartAutoEvolution(context.Background(), input)
	if ErrorCode(terminalErr) != "WORLDLINE_SESSION_NOT_ACTIVE" ||
		terminalErr.Error() != "worldline session is not active" {
		t.Fatalf("unexpected terminal-session error: code=%s err=%v", ErrorCode(terminalErr), terminalErr)
	}
	if err := adminDB.QueryRow(`SELECT COUNT(*) FROM workflow_runs
WHERE tenant_id = $1 AND project_id = $2 AND workflow_type = 'worldline_auto_evolution'`, tenantID, projectID).Scan(&runCount); err != nil {
		t.Fatalf("count auto-evolutions after terminal rejection: %v", err)
	}
	if runCount != 1 {
		t.Fatalf("terminal session admitted another workflow run: %d", runCount)
	}
}

func openAutoEvolutionLiveDatabases(t *testing.T) (*sql.DB, *sql.DB) {
	t.Helper()
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WORLDLINE_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WORLDLINE_LIVE_DATABASE_URL to run the live Worldline auto-evolution E2E")
	}
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin database: %v", err)
	}
	applyAutoEvolutionLiveSchema(t, adminDB)
	ensureAutoEvolutionLiveAppRole(t, adminDB)
	appConfig, err := pgx.ParseConfig(adminURL)
	if err != nil {
		adminDB.Close()
		t.Fatalf("parse admin database URL: %v", err)
	}
	appConfig.User = autoEvolutionLiveAppRole
	appConfig.Password = autoEvolutionLiveAppPassword
	return adminDB, stdlib.OpenDB(*appConfig)
}

func (c *autoEvolutionCountingTemporalClient) ExecuteWorkflow(
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

func (c *autoEvolutionCountingTemporalClient) callCount() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.options)
}

func applyAutoEvolutionLiveSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	if err := testschema.EnsureLiveSchema(context.Background(), db,
		"../../../../infra/postgres/migrations/0001_core_saas.sql",
		"tenants", "projects", "workflow_runs", "worldline_sessions", "workflow_events",
	); err != nil {
		t.Fatalf("ensure live auto-evolution schema: %v", err)
	}
}

func ensureAutoEvolutionLiveAppRole(t *testing.T, db *sql.DB) {
	t.Helper()
	query := fmt.Sprintf(`DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '%s') THEN
    CREATE ROLE %s LOGIN PASSWORD '%s' IN ROLE mirofish_app;
  END IF;
END $$;
ALTER ROLE %s WITH LOGIN PASSWORD '%s';
GRANT mirofish_app TO %s`,
		autoEvolutionLiveAppRole,
		autoEvolutionLiveAppRole,
		autoEvolutionLiveAppPassword,
		autoEvolutionLiveAppRole,
		autoEvolutionLiveAppPassword,
		autoEvolutionLiveAppRole,
	)
	if _, err := db.Exec(query); err != nil {
		t.Fatalf("ensure auto-evolution live app role: %v", err)
	}
}

func prepareAutoEvolutionLiveSession(
	t *testing.T,
	db *sql.DB,
	tenantID string,
	userID string,
	projectID string,
	sessionRunID string,
	sessionID string,
) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatalf("begin auto-evolution live fixture: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	statements := []struct {
		query string
		args  []any
	}{
		{`INSERT INTO users (user_id, email, display_name) VALUES ($1, $2, 'Auto Evolution Live')`, []any{userID, "auto-evolution-" + userID + "@example.test"}},
		{`INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES ($1, $2, 'Auto Evolution Live', 'personal')`, []any{tenantID, "auto-evolution-" + tenantID}},
		{`INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES ($1, $2, 'owner')`, []any{tenantID, userID}},
		{`INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES ($1, $2, 'Auto Evolution Live', $3)`, []any{tenantID, projectID, userID}},
		{`INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES ($1, $2, $3, 'project_owner')`, []any{tenantID, projectID, userID}},
		{`INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by) VALUES ($1, $2, 'worldline_session', $3, 'completed', 100, $4)`, []any{tenantID, sessionRunID, projectID, userID}},
		{`INSERT INTO worldline_sessions (tenant_id, session_id, project_id, run_id, status, lifecycle, goal_summary, created_by) VALUES ($1, $2, $3, $4, 'paused', 'active', 'Auto evolution live guard', $5)`, []any{tenantID, sessionID, projectID, sessionRunID, userID}},
	}
	for _, statement := range statements {
		if _, err := tx.Exec(statement.query, statement.args...); err != nil {
			t.Fatalf("prepare auto-evolution live fixture: %v", err)
		}
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit auto-evolution live fixture: %v", err)
	}
}

func cleanupAutoEvolutionLiveSession(t *testing.T, db *sql.DB, tenantID string, userID string) {
	t.Helper()
	if _, err := db.Exec(`DELETE FROM tenants WHERE tenant_id = $1`, tenantID); err != nil {
		t.Errorf("cleanup auto-evolution live tenant: %v", err)
	}
	if _, err := db.Exec(`DELETE FROM users WHERE user_id = $1`, userID); err != nil {
		t.Errorf("cleanup auto-evolution live user: %v", err)
	}
}

func assertAutoEvolutionLiveAdmission(
	t *testing.T,
	db *sql.DB,
	tenantID string,
	projectID string,
	sessionID string,
	runID string,
	requestID string,
	maxSteps int,
) {
	t.Helper()
	var runCount, queuedCount, payloadKeyCount, candidateEventCount int
	var sessionStatus, persistedRequestID, worldScope string
	err := db.QueryRow(`SELECT
  (SELECT COUNT(*) FROM workflow_runs
    WHERE tenant_id = $1 AND project_id = $2 AND workflow_type = 'worldline_auto_evolution'),
  (SELECT COUNT(*) FROM workflow_events
    WHERE tenant_id = $1 AND project_id = $2 AND workflow_type = 'worldline_auto_evolution'
      AND event_type = 'workflow.queued'),
  (SELECT status FROM worldline_sessions
    WHERE tenant_id = $1 AND project_id = $2 AND session_id = $3),
  queued.payload_jsonb->>'request_id',
  queued.payload_jsonb->>'world_scope',
  (SELECT COUNT(*) FROM jsonb_object_keys(queued.payload_jsonb)),
  (SELECT COUNT(*) FROM worldline_events
    WHERE tenant_id = $1 AND project_id = $2 AND session_id = $3)
FROM workflow_events AS queued
WHERE queued.tenant_id = $1
  AND queued.project_id = $2
  AND queued.run_id = $4
  AND queued.workflow_type = 'worldline_auto_evolution'
  AND queued.event_type = 'workflow.queued'
  AND (queued.payload_jsonb->>'max_steps')::integer = $5
  AND NOT (queued.payload_jsonb ?| ARRAY['options', 'goal_text', 'branch_id', 'branch_ids', 'prompt', 'response'])`,
		tenantID,
		projectID,
		sessionID,
		runID,
		maxSteps,
	).Scan(
		&runCount,
		&queuedCount,
		&sessionStatus,
		&persistedRequestID,
		&worldScope,
		&payloadKeyCount,
		&candidateEventCount,
	)
	if err != nil {
		t.Fatalf("read auto-evolution admission: %v", err)
	}
	if runCount != 1 || queuedCount != 1 || sessionStatus != "running" ||
		persistedRequestID != requestID || worldScope != "current_world" ||
		payloadKeyCount != 7 || candidateEventCount != 0 {
		t.Fatalf(
			"unexpected admission: runs=%d queued=%d session=%s request=%s scope=%s keys=%d candidates=%d",
			runCount,
			queuedCount,
			sessionStatus,
			persistedRequestID,
			worldScope,
			payloadKeyCount,
			candidateEventCount,
		)
	}
}
