package workflows

import (
	"context"
	"database/sql"
	"errors"
	"net/url"
	"os"
	"strings"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveAssetReindexTenantA  = "a7111111-1111-4111-8111-111111111111"
	liveAssetReindexTenantB  = "b7111111-1111-4111-8111-111111111111"
	liveAssetReindexUserA    = "a7222222-2222-4222-8222-222222222222"
	liveAssetReindexUserB    = "b7222222-2222-4222-8222-222222222222"
	liveAssetReindexProjectA = "a7333333-3333-4333-8333-333333333333"
	liveAssetReindexProjectB = "b7333333-3333-4333-8333-333333333333"
	liveAssetReindexRunA     = "a7444444-4444-4444-8444-444444444444"

	liveAssetReindexRole     = "mirofish_asset_reindex_live_app"
	liveAssetReindexPassword = "mirofish_asset_reindex_live_password"
)

func TestLiveAssetReindexAdmissionAndCompensationUseAppRoleForceRLS(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_ASSET_REINDEX_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_ASSET_REINDEX_LIVE_DATABASE_URL to run Asset reindex app-role admission live test")
	}
	adminDB := openLiveAssetReindexDB(t, adminURL)
	defer adminDB.Close()
	prepareLiveAssetReindexFixture(t, adminDB)
	defer cleanupLiveAssetReindexFixture(t, adminDB)

	appDB := openLiveAssetReindexDB(t, liveAssetReindexAppURL(t, adminURL))
	defer appDB.Close()
	assertLiveAssetReindexRoleAndRLS(t, adminDB, appDB)
	store := NewSQLAssetReindexAdmissionStore(SQLAssetReindexAdmissionStoreConfig{
		Execer: NewSQLDBWriterAdmissionExecer(appDB),
	})
	input := AssetReindexAdmissionInput{
		TenantID:           liveAssetReindexTenantA,
		ProjectID:          liveAssetReindexProjectA,
		RunID:              liveAssetReindexRunA,
		TraceID:            "trace_" + liveAssetReindexRunA,
		WorkflowType:       AssetReindexWorkflowType,
		TemporalWorkflowID: "asset_reindex_" + liveAssetReindexRunA,
		ActorUserID:        liveAssetReindexUserA,
		RequestID:          "req-live-asset-reindex-admission",
		Scope:              "project",
		Mode:               "hybrid",
		Status:             "queued",
	}

	if err := store.AdmitAssetReindexRun(context.Background(), input); err != nil {
		t.Fatalf("admit asset reindex through app role: code=%s err=%v", ErrorCode(err), err)
	}
	assertLiveAssetReindexRun(t, adminDB, input.RunID, "queued", "", 1)
	assertLiveAssetReindexNoContextVisibility(t, appDB)

	foreign := input
	foreign.TenantID = liveAssetReindexTenantB
	foreign.ProjectID = liveAssetReindexProjectB
	foreign.ActorUserID = liveAssetReindexUserB
	if err := store.RecordAssetReindexStartFailure(context.Background(), foreign); ErrorCode(err) != "WORKFLOW_FAILED" {
		t.Fatalf("foreign compensation must fail closed: code=%s err=%v", ErrorCode(err), err)
	}
	assertLiveAssetReindexRun(t, adminDB, input.RunID, "queued", "", 1)

	if err := store.RecordAssetReindexStartFailure(context.Background(), input); err != nil {
		t.Fatalf("compensate asset reindex through app role: code=%s err=%v", ErrorCode(err), err)
	}
	assertLiveAssetReindexRun(t, adminDB, input.RunID, "failed", "WORKFLOW_START_FAILED", 2)
	if err := store.RecordAssetReindexStartFailure(context.Background(), input); ErrorCode(err) != "WORKFLOW_FAILED" {
		t.Fatalf("repeat compensation must report that no queued run changed: code=%s err=%v", ErrorCode(err), err)
	}
	assertLiveAssetReindexRun(t, adminDB, input.RunID, "failed", "WORKFLOW_START_FAILED", 2)

	temporalClient := &recordingSeedTemporalClient{
		err: errors.New("Temporal prompt=private api_key=sk-private credential_ref=secret raw_content=novel"),
	}
	starter := NewTemporalAssetReindexStarter(TemporalAssetReindexConfig{
		Client:         temporalClient,
		AdmissionStore: store,
	})
	_, err := starter.StartAssetReindex(context.Background(), StartAssetReindexInput{
		TenantID:    liveAssetReindexTenantA,
		ProjectID:   liveAssetReindexProjectA,
		ActorUserID: liveAssetReindexUserA,
		RequestID:   "req-live-asset-reindex-start-failure",
		Scope:       "project",
		Mode:        "hybrid",
	})
	if ErrorCode(err) != "WORKFLOW_FAILED" || err.Error() != assetReindexStartFailedMessage {
		t.Fatalf("expected stable compensated start failure, code=%s err=%v", ErrorCode(err), err)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-private", "credential_ref", "secret", "raw_content", "novel"} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("live asset reindex error leaked %q: %v", forbidden, err)
		}
	}
	dynamicRunID := strings.TrimPrefix(temporalClient.options.ID, "asset_reindex_")
	if dynamicRunID == "" || dynamicRunID == temporalClient.options.ID {
		t.Fatalf("Temporal start did not receive stable asset reindex workflow id: %#v", temporalClient.options)
	}
	assertLiveAssetReindexRun(t, adminDB, dynamicRunID, "failed", "WORKFLOW_START_FAILED", 2)
}

func openLiveAssetReindexDB(t *testing.T, databaseURL string) *sql.DB {
	t.Helper()
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatalf("open Asset reindex live database: %v", err)
	}
	if err := db.PingContext(context.Background()); err != nil {
		db.Close()
		t.Fatalf("ping Asset reindex live database: %v", err)
	}
	return db
}

func prepareLiveAssetReindexFixture(t *testing.T, db *sql.DB) {
	t.Helper()
	_, err := db.Exec(`DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_asset_reindex_live_app') THEN
    CREATE ROLE mirofish_asset_reindex_live_app LOGIN PASSWORD 'mirofish_asset_reindex_live_password' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE mirofish_asset_reindex_live_app WITH LOGIN PASSWORD 'mirofish_asset_reindex_live_password' NOSUPERUSER NOBYPASSRLS;
  END IF;
END
$$;
GRANT mirofish_app TO mirofish_asset_reindex_live_app;`)
	if err != nil {
		t.Fatalf("ensure Asset reindex app role: %v", err)
	}
	cleanupLiveAssetReindexFixture(t, db)
	_, err = db.Exec(`INSERT INTO users (user_id, email, display_name) VALUES
  ($1, 'asset-reindex-a@example.test', 'Asset Reindex A'),
  ($2, 'asset-reindex-b@example.test', 'Asset Reindex B')
ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name`,
		liveAssetReindexUserA,
		liveAssetReindexUserB,
	)
	if err != nil {
		t.Fatalf("seed Asset reindex live users: %v", err)
	}
	_, err = db.Exec(`INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES
  ($1, 'asset-reindex-live-a', 'Asset Reindex Live A', 'personal'),
  ($2, 'asset-reindex-live-b', 'Asset Reindex Live B', 'personal')`,
		liveAssetReindexTenantA,
		liveAssetReindexTenantB,
	)
	if err != nil {
		t.Fatalf("seed Asset reindex live tenants: %v", err)
	}
	_, err = db.Exec(`INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES
  ($1, $2, 'Asset Reindex Project A', $3),
  ($4, $5, 'Asset Reindex Project B', $6)`,
		liveAssetReindexTenantA,
		liveAssetReindexProjectA,
		liveAssetReindexUserA,
		liveAssetReindexTenantB,
		liveAssetReindexProjectB,
		liveAssetReindexUserB,
	)
	if err != nil {
		t.Fatalf("seed Asset reindex live projects: %v", err)
	}
}

func cleanupLiveAssetReindexFixture(t *testing.T, db *sql.DB) {
	t.Helper()
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id IN ($1, $2)", liveAssetReindexTenantA, liveAssetReindexTenantB); err != nil {
		t.Fatalf("cleanup Asset reindex tenants: %v", err)
	}
	if _, err := db.Exec("DELETE FROM users WHERE user_id IN ($1, $2)", liveAssetReindexUserA, liveAssetReindexUserB); err != nil {
		t.Fatalf("cleanup Asset reindex users: %v", err)
	}
}

func liveAssetReindexAppURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatalf("parse Asset reindex live database URL: %v", err)
	}
	parsed.User = url.UserPassword(liveAssetReindexRole, liveAssetReindexPassword)
	return parsed.String()
}

func assertLiveAssetReindexRoleAndRLS(t *testing.T, adminDB *sql.DB, appDB *sql.DB) {
	t.Helper()
	var currentUser string
	if err := appDB.QueryRow("SELECT current_user").Scan(&currentUser); err != nil {
		t.Fatalf("read Asset reindex current user: %v", err)
	}
	if currentUser != liveAssetReindexRole {
		t.Fatalf("Asset reindex live path is not using app role: %q", currentUser)
	}
	var superuser, bypassRLS bool
	if err := adminDB.QueryRow("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = $1", liveAssetReindexRole).Scan(&superuser, &bypassRLS); err != nil {
		t.Fatalf("read Asset reindex role flags: %v", err)
	}
	if superuser || bypassRLS {
		t.Fatalf("Asset reindex role bypasses RLS: superuser=%v bypass_rls=%v", superuser, bypassRLS)
	}
	for _, table := range []string{"workflow_runs", "workflow_events"} {
		var forced bool
		if err := adminDB.QueryRow("SELECT relforcerowsecurity FROM pg_class WHERE oid = $1::regclass", table).Scan(&forced); err != nil {
			t.Fatalf("read FORCE RLS flag for %s: %v", table, err)
		}
		if !forced {
			t.Fatalf("expected FORCE RLS on %s", table)
		}
	}
}

func assertLiveAssetReindexNoContextVisibility(t *testing.T, appDB *sql.DB) {
	t.Helper()
	var count int
	if err := appDB.QueryRow("SELECT COUNT(*) FROM workflow_runs WHERE run_id = $1", liveAssetReindexRunA).Scan(&count); err != nil {
		t.Fatalf("query Asset reindex run without tenant context: %v", err)
	}
	if count != 0 {
		t.Fatalf("app role read Asset reindex run without tenant context: %d", count)
	}
}

func assertLiveAssetReindexRun(t *testing.T, db *sql.DB, runID string, wantStatus string, wantErrorCode string, wantEvents int) {
	t.Helper()
	var status, errorCode, errorMessage, startedBy, temporalWorkflowID string
	err := db.QueryRow(`SELECT status, COALESCE(error_code, ''), COALESCE(error_message, ''),
  COALESCE(started_by::text, ''), COALESCE(temporal_workflow_id, '')
FROM workflow_runs
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3 AND workflow_type = 'asset_reindex'`,
		liveAssetReindexTenantA,
		liveAssetReindexProjectA,
		runID,
	).Scan(&status, &errorCode, &errorMessage, &startedBy, &temporalWorkflowID)
	if err != nil {
		t.Fatalf("read Asset reindex run %s: %v", runID, err)
	}
	if status != wantStatus || errorCode != wantErrorCode {
		t.Fatalf("unexpected Asset reindex run state: status=%q error_code=%q", status, errorCode)
	}
	if startedBy != liveAssetReindexUserA || temporalWorkflowID != "asset_reindex_"+runID {
		t.Fatalf("Asset reindex admission lost actor/Temporal identity: actor=%q workflow=%q", startedBy, temporalWorkflowID)
	}
	if wantStatus == "failed" && errorMessage != assetReindexStartFailedMessage {
		t.Fatalf("unexpected stable Asset reindex failure message: %q", errorMessage)
	}
	var eventCount int
	if err := db.QueryRow("SELECT COUNT(*) FROM workflow_events WHERE tenant_id = $1 AND run_id = $2", liveAssetReindexTenantA, runID).Scan(&eventCount); err != nil {
		t.Fatalf("count Asset reindex events: %v", err)
	}
	if eventCount != wantEvents {
		t.Fatalf("unexpected Asset reindex event count: got=%d want=%d", eventCount, wantEvents)
	}
	if wantEvents == 2 {
		var eventType, payload string
		if err := db.QueryRow(`SELECT event_type, payload_jsonb::text FROM workflow_events
WHERE tenant_id = $1 AND run_id = $2 ORDER BY sequence DESC LIMIT 1`, liveAssetReindexTenantA, runID).Scan(&eventType, &payload); err != nil {
			t.Fatalf("read Asset reindex failure event: %v", err)
		}
		if eventType != "workflow.start_failed" || !strings.Contains(payload, "WORKFLOW_START_FAILED") || strings.Contains(payload, "api_key") || strings.Contains(payload, "credential_ref") {
			t.Fatalf("unexpected Asset reindex failure event: type=%q payload=%s", eventType, payload)
		}
	}
}
