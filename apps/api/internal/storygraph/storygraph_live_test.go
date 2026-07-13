package storygraph

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"mirofish-novel/apps/api/internal/testschema"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveGraphTenantID            = "c9dc019b-e533-4d4a-b58e-c0c484af170a"
	liveGraphProjectID           = "4e45d5ca-8fb0-4ddd-9f16-e5f7aaab9e34"
	liveGraphUserID              = "7ecfdb14-8ad1-471c-9b1f-e53632ca073c"
	liveGraphUserEmail           = "graph-go-live@example.test"
	liveGraphBondRunID           = "10d6a2f6-ae86-485b-bcbd-d56910e59ce2"
	liveGraphRelationshipAssetID = "17b924de-7237-4898-b606-4c48c755b5fb"
	liveGraphThreadAssetID       = "f87fd81d-d935-4fe7-bcc2-ae45c67ee4f6"
	liveGraphAppRole             = "mirofish_graph_go_live_app"
	liveGraphAppPassword         = "mirofish_graph_go_live_password"
)

func TestLiveSQLCandidateAdoptionRequiresExplicitAction(t *testing.T) {
	adminURL := os.Getenv("MIROFISH_GRAPH_LIVE_DATABASE_URL")
	if adminURL == "" {
		t.Skip("set MIROFISH_GRAPH_LIVE_DATABASE_URL to run live Story Graph adoption E2E")
	}
	adminDB := openLiveGraphDB(t, adminURL)
	t.Cleanup(func() { _ = adminDB.Close() })
	if err := testschema.RequireDisposableLiveDatabase(context.Background(), adminDB); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if _, err := adminDB.Exec(`DELETE FROM tenants WHERE tenant_id = $1`, liveGraphTenantID); err != nil {
			t.Errorf("cleanup live graph tenant: %v", err)
		}
		if _, err := adminDB.Exec(`DELETE FROM users WHERE user_id = $1 AND email = $2`, liveGraphUserID, liveGraphUserEmail); err != nil {
			t.Errorf("cleanup live graph user: %v", err)
		}
	})
	prepareLiveGraphAdoptionFixture(t, adminDB)
	appDB := openLiveGraphDB(t, liveGraphAppURL(t, adminURL))
	t.Cleanup(func() { _ = appDB.Close() })
	store := NewSQLCandidateAdoptionStore(SQLCandidateAdoptionStoreConfig{
		Queryer: NewSQLDBQueryer(appDB),
	})

	assertLiveGraphAssetLifecycle(t, adminDB, liveGraphRelationshipAssetID, "candidate")
	assertLiveGraphAssetLifecycle(t, adminDB, liveGraphThreadAssetID, "candidate")
	relationship, err := store.AdoptCandidate(context.Background(), AdoptCandidateInput{
		TenantID:   liveGraphTenantID,
		ProjectID:  liveGraphProjectID,
		AssetID:    liveGraphRelationshipAssetID,
		ActorID:    liveGraphUserID,
		RequestID:  "req-live-graph-relationship-adoption",
		TargetKind: "relationship",
	})
	if err != nil {
		t.Fatalf("adopt live relationship candidate: code=%s err=%v", ErrorCode(err), err)
	}
	thread, err := store.AdoptCandidate(context.Background(), AdoptCandidateInput{
		TenantID:   liveGraphTenantID,
		ProjectID:  liveGraphProjectID,
		AssetID:    liveGraphThreadAssetID,
		ActorID:    liveGraphUserID,
		RequestID:  "req-live-graph-thread-adoption",
		TargetKind: "plot_thread",
	})
	if err != nil {
		t.Fatalf("adopt live plot thread candidate: code=%s err=%v", ErrorCode(err), err)
	}
	if relationship.Status != "adopted" || relationship.TargetKind != "relationship" || relationship.TargetID == "" {
		t.Fatalf("unexpected relationship adoption result: %#v", relationship)
	}
	if thread.Status != "adopted" || thread.TargetKind != "plot_thread" || thread.TargetID == "" {
		t.Fatalf("unexpected plot thread adoption result: %#v", thread)
	}
	assertLiveGraphAssetLifecycle(t, adminDB, liveGraphRelationshipAssetID, "canon")
	assertLiveGraphAssetLifecycle(t, adminDB, liveGraphThreadAssetID, "canon")
	assertLiveGraphCanonAndAuditCounts(t, adminDB)

	if _, err := store.AdoptCandidate(context.Background(), AdoptCandidateInput{
		TenantID:   liveGraphTenantID,
		ProjectID:  liveGraphProjectID,
		AssetID:    liveGraphRelationshipAssetID,
		ActorID:    liveGraphUserID,
		RequestID:  "req-live-graph-repeat-adoption",
		TargetKind: "relationship",
	}); ErrorCode(err) != "NOT_FOUND" {
		t.Fatalf("expected repeated explicit adoption to fail closed, got code=%s err=%v", ErrorCode(err), err)
	}
}

func prepareLiveGraphAdoptionFixture(t *testing.T, db *sql.DB) {
	t.Helper()
	if err := testschema.EnsureLiveSchema(context.Background(), db, liveGraphMigrationPath(t),
		"tenants", "projects", "assets", "graph_nodes", "graph_edges", "graph_evidence",
	); err != nil {
		t.Fatalf("ensure live Story Graph schema: %v", err)
	}
	roleSQL := fmt.Sprintf(`DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '%s') THEN
    CREATE ROLE %s LOGIN PASSWORD '%s' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE %s WITH LOGIN PASSWORD '%s';
    GRANT mirofish_app TO %s;
  END IF;
END $$`, liveGraphAppRole, liveGraphAppRole, liveGraphAppPassword, liveGraphAppRole, liveGraphAppPassword, liveGraphAppRole)
	if _, err := db.Exec(roleSQL); err != nil {
		t.Fatalf("prepare app login role: %v", err)
	}
	statements := []struct {
		query string
		args  []any
	}{
		{`DELETE FROM tenants WHERE tenant_id = $1`, []any{liveGraphTenantID}},
		{`INSERT INTO users (user_id, email, display_name)
	       VALUES ($1, $2, 'Graph Go Live')
	       ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, display_name = EXCLUDED.display_name`, []any{liveGraphUserID, liveGraphUserEmail}},
		{`INSERT INTO tenants (tenant_id, slug, name, tenant_type)
       VALUES ($1, 'graph-go-live-disposable', 'Graph Go Live Disposable', 'personal')`, []any{liveGraphTenantID}},
		{`INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES ($1, $2, 'owner')`, []any{liveGraphTenantID, liveGraphUserID}},
		{`INSERT INTO projects (tenant_id, project_id, title, created_by)
       VALUES ($1, $2, 'Graph Go Live Disposable', $3)`, []any{liveGraphTenantID, liveGraphProjectID, liveGraphUserID}},
		{`INSERT INTO project_members (tenant_id, project_id, user_id, role)
       VALUES ($1, $2, $3, 'project_owner')`, []any{liveGraphTenantID, liveGraphProjectID, liveGraphUserID}},
		{`INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
       VALUES ($1, $2, 'story_graph_bond_generation', $3, 'completed', 100, $4)`, []any{liveGraphTenantID, liveGraphBondRunID, liveGraphProjectID, liveGraphUserID}},
		{`INSERT INTO assets (
         tenant_id, asset_id, project_id, scope, asset_type, category, lifecycle,
         title, summary, content_text, payload_jsonb, tags_jsonb, source_kind,
         source_ref, enabled, pinned, created_by
       ) VALUES (
         $1, $2, $3, 'project', 'graph_bond', 'relationship', 'candidate',
         'Live explicit alliance', 'Public relationship candidate summary', NULL,
         jsonb_build_object(
           'source_run_id', $4::text,
           'source_entity_name', '林澈',
           'target_entity_name', '白塔会',
           'relationship_type', 'opposes',
           'confidence', 0.82
         ), '[]'::jsonb, 'graph_bond_generation', $5, true, false, $6
       )`, []any{liveGraphTenantID, liveGraphRelationshipAssetID, liveGraphProjectID, liveGraphBondRunID, "graph-bond:" + liveGraphBondRunID + ":1", liveGraphUserID}},
		{`INSERT INTO assets (
         tenant_id, asset_id, project_id, scope, asset_type, category, lifecycle,
         title, summary, content_text, payload_jsonb, tags_jsonb, source_kind,
         source_ref, enabled, pinned, created_by
       ) VALUES (
         $1, $2, $3, 'project', 'plot_thread', 'plot', 'candidate',
         'Live unresolved treaty', 'Public plot thread candidate summary', NULL,
         jsonb_build_object('source_run_id', $4::text, 'thread_type', 'mystery', 'status', 'open'),
         '[]'::jsonb, 'graph_bond_generation', $5, true, false, $6
       )`, []any{liveGraphTenantID, liveGraphThreadAssetID, liveGraphProjectID, liveGraphBondRunID, "graph-bond:" + liveGraphBondRunID + ":2", liveGraphUserID}},
	}
	for _, statement := range statements {
		if _, err := db.Exec(statement.query, statement.args...); err != nil {
			t.Fatalf("prepare live graph fixture: %v", err)
		}
	}
}

func assertLiveGraphAssetLifecycle(t *testing.T, db *sql.DB, assetID string, expected string) {
	t.Helper()
	var lifecycle string
	if err := db.QueryRow(`SELECT lifecycle FROM assets WHERE tenant_id = $1 AND project_id = $2 AND asset_id = $3`, liveGraphTenantID, liveGraphProjectID, assetID).Scan(&lifecycle); err != nil {
		t.Fatalf("read live graph candidate lifecycle: %v", err)
	}
	if lifecycle != expected {
		t.Fatalf("expected candidate lifecycle %q, got %q", expected, lifecycle)
	}
}

func assertLiveGraphCanonAndAuditCounts(t *testing.T, db *sql.DB) {
	t.Helper()
	var relationships, threads, audits int
	if err := db.QueryRow(`SELECT count(*) FROM relationships WHERE tenant_id = $1 AND project_id = $2`, liveGraphTenantID, liveGraphProjectID).Scan(&relationships); err != nil {
		t.Fatalf("count adopted relationships: %v", err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM plot_threads WHERE tenant_id = $1 AND project_id = $2`, liveGraphTenantID, liveGraphProjectID).Scan(&threads); err != nil {
		t.Fatalf("count adopted plot threads: %v", err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM audit_logs WHERE tenant_id = $1 AND project_id = $2 AND action = 'story_graph.candidate_adopt'`, liveGraphTenantID, liveGraphProjectID).Scan(&audits); err != nil {
		t.Fatalf("count graph adoption audits: %v", err)
	}
	if relationships != 1 || threads != 1 || audits != 2 {
		t.Fatalf("unexpected explicit adoption state: relationships=%d threads=%d audits=%d", relationships, threads, audits)
	}
}

func openLiveGraphDB(t *testing.T, databaseURL string) *sql.DB {
	t.Helper()
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatalf("open live graph database: %v", err)
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		t.Fatalf("ping live graph database: %v", err)
	}
	return db
}

func liveGraphAppURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatalf("parse live graph database URL: %v", err)
	}
	parsed.User = url.UserPassword(liveGraphAppRole, liveGraphAppPassword)
	return parsed.String()
}

func liveGraphMigrationPath(t *testing.T) string {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve story graph live test path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "..", "..", "..", "infra", "postgres", "migrations", "0001_core_saas.sql"))
}
