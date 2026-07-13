package workflows

import (
	"context"
	"database/sql"
	"net/url"
	"os"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/testschema"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const liveWriterExportTenantID = "91111111-1111-4111-8111-111111111111"
const liveWriterExportProjectID = "92222222-2222-4222-8222-222222222222"
const liveWriterExportUserID = "93333333-3333-4333-8333-333333333333"
const liveWriterExportUserEmail = "writer-export-go-live@example.test"
const liveWriterExportRunID = "94444444-4444-4444-8444-444444444444"
const liveWriterExportDraftID = "95555555-5555-4555-8555-555555555555"
const liveWriterExportAppRole = "mirofish_writer_export_live_app"
const liveWriterExportAppPassword = "mirofish_writer_export_live_password"

func TestLiveWriterExplicitAdoptionAndContentArtifactWithAppRole(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WRITER_EXPORT_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WRITER_EXPORT_LIVE_DATABASE_URL to run Writer adoption/export app-role E2E")
	}
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin db: %v", err)
	}
	t.Cleanup(func() { _ = adminDB.Close() })
	if err := testschema.RequireDisposableLiveDatabase(context.Background(), adminDB); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if _, err := adminDB.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveWriterExportTenantID); err != nil {
			t.Errorf("cleanup writer export live tenant: %v", err)
		}
		if _, err := adminDB.Exec("DELETE FROM users WHERE user_id = $1 AND email = $2", liveWriterExportUserID, liveWriterExportUserEmail); err != nil {
			t.Errorf("cleanup writer export live user: %v", err)
		}
	})
	prepareLiveWriterExportFixture(t, adminDB)

	appDB, err := sql.Open("pgx", liveWriterExportAppURL(t, adminURL))
	if err != nil {
		t.Fatalf("open writer app-role db: %v", err)
	}
	t.Cleanup(func() { _ = appDB.Close() })

	adoptionStore := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{
		Queryer: NewSQLDBWriterDraftAdoptionQueryer(appDB),
	})
	input := DraftAdoptionInput{
		TenantID: liveWriterExportTenantID, DraftID: liveWriterExportDraftID,
		ActorUserID: liveWriterExportUserID, RequestID: "writer-export-live-adopt",
	}
	first, err := adoptionStore.AdoptDraft(context.Background(), input)
	if err != nil {
		t.Fatalf("adopt candidate draft: code=%s err=%v", ErrorCode(err), err)
	}
	second, err := adoptionStore.AdoptDraft(context.Background(), input)
	if err != nil {
		t.Fatalf("retry explicit adoption: code=%s err=%v", ErrorCode(err), err)
	}
	if first.BlockID == "" || second.BlockID != first.BlockID || second.BlockOrder != first.BlockOrder {
		t.Fatalf("adoption retry created a different manuscript block: first=%#v second=%#v", first, second)
	}

	exporter := NewSQLManuscriptArtifactExporter(SQLManuscriptArtifactExporterConfig{
		Queryer: NewSQLDBWriterEventQueryer(appDB),
	})
	artifact, err := exporter.ExportManuscriptArtifact(context.Background(), ExportManuscriptArtifactInput{
		TenantID: liveWriterExportTenantID, ProjectID: liveWriterExportProjectID, Format: "txt",
	})
	if err != nil {
		t.Fatalf("export adopted manuscript content: code=%s err=%v", ErrorCode(err), err)
	}
	if artifact.BlockCount != 1 || string(artifact.Content) != "真实正文导出内容。\n" || artifact.SizeBytes != int64(len(artifact.Content)) || artifact.SHA256 == "" {
		t.Fatalf("unexpected real manuscript artifact: %#v", artifact)
	}

	var blockCount int
	var auditCount int
	if err := adminDB.QueryRow(`SELECT COUNT(*) FROM manuscript_blocks WHERE tenant_id = $1 AND project_id = $2 AND source_draft_id = $3`, liveWriterExportTenantID, liveWriterExportProjectID, liveWriterExportDraftID).Scan(&blockCount); err != nil {
		t.Fatalf("count adopted blocks: %v", err)
	}
	if err := adminDB.QueryRow(`SELECT COUNT(*) FROM audit_logs WHERE tenant_id = $1 AND resource_id = $2 AND action = 'writer.draft_adopted'`, liveWriterExportTenantID, liveWriterExportDraftID).Scan(&auditCount); err != nil {
		t.Fatalf("count adoption audit: %v", err)
	}
	if blockCount != 1 || auditCount != 1 {
		t.Fatalf("explicit adoption was not idempotent/audited: blocks=%d audits=%d", blockCount, auditCount)
	}

	if _, err := adminDB.Exec(`INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT
  $1, $2, 'writer_run', $3,
  CASE WHEN sequence = 102 THEN 'writer.run.completed' ELSE 'writer.token' END,
  sequence,
  CASE WHEN sequence = 102 THEN '{"status":"completed"}'::jsonb ELSE jsonb_build_object('token_index', sequence) END
FROM generate_series(1, 102) AS sequence`, liveWriterExportTenantID, liveWriterExportRunID, liveWriterExportProjectID); err != nil {
		t.Fatalf("seed persisted writer replay events: %v", err)
	}
	eventReader := NewSQLWriterEventReader(SQLWriterEventReaderConfig{
		Queryer: NewSQLDBWriterEventQueryer(appDB), Limit: 100,
	})
	firstPage, err := eventReader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID: liveWriterExportTenantID, RunID: liveWriterExportRunID,
	})
	if err != nil || len(firstPage) != 100 {
		t.Fatalf("read first persisted replay page: events=%d code=%s err=%v", len(firstPage), ErrorCode(err), err)
	}
	secondPage, err := eventReader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID: liveWriterExportTenantID, RunID: liveWriterExportRunID, AfterEventID: firstPage[99].EventID,
	})
	if err != nil || len(secondPage) != 2 || secondPage[1].EventType != "writer.run.completed" {
		t.Fatalf("resume replay lost terminal event: events=%#v code=%s err=%v", secondPage, ErrorCode(err), err)
	}
	replayedPage, err := eventReader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID: liveWriterExportTenantID, RunID: liveWriterExportRunID, AfterEventID: firstPage[99].EventID,
	})
	if err != nil || len(replayedPage) != 2 || replayedPage[0].EventID != secondPage[0].EventID || replayedPage[1].EventID != secondPage[1].EventID {
		t.Fatalf("same reconnect cursor was not deterministic: second=%#v replay=%#v err=%v", secondPage, replayedPage, err)
	}
	runReader := NewSQLWriterReader(SQLWriterReaderConfig{Queryer: NewSQLDBWriterEventQueryer(appDB)})
	recoveredRun, err := runReader.GetWriterRun(context.Background(), GetWriterRunInput{
		TenantID: liveWriterExportTenantID, RunID: liveWriterExportRunID,
	})
	if err != nil || recoveredRun.Status != "completed" {
		t.Fatalf("refresh recovery did not reload persisted writer run: run=%#v code=%s err=%v", recoveredRun, ErrorCode(err), err)
	}
}

func prepareLiveWriterExportFixture(t *testing.T, db *sql.DB) {
	t.Helper()
	if _, err := db.Exec("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_writer_export_live_app') THEN CREATE ROLE mirofish_writer_export_live_app LOGIN PASSWORD 'mirofish_writer_export_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_writer_export_live_app WITH LOGIN PASSWORD 'mirofish_writer_export_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_writer_export_live_app;"); err != nil {
		t.Fatalf("ensure writer app role: %v", err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveWriterExportTenantID); err != nil {
		t.Fatalf("cleanup old writer live tenant: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO users (user_id, email, display_name)
	VALUES ($1, $2, 'Writer Export Live')
	ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, display_name = EXCLUDED.display_name`, liveWriterExportUserID, liveWriterExportUserEmail); err != nil {
		t.Fatalf("seed writer live user: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO tenants (tenant_id, slug, name, tenant_type)
VALUES ($1, 'writer-export-live', 'Writer Export Live', 'personal')`, liveWriterExportTenantID); err != nil {
		t.Fatalf("seed writer live tenant: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO projects (tenant_id, project_id, title, created_by)
VALUES ($1, $2, 'Writer Export Live Project', $3)`, liveWriterExportTenantID, liveWriterExportProjectID, liveWriterExportUserID); err != nil {
		t.Fatalf("seed writer live project: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, started_by)
VALUES ($1, $2, 'writer_run', $3, 'completed', $4)`, liveWriterExportTenantID, liveWriterExportRunID, liveWriterExportProjectID, liveWriterExportUserID); err != nil {
		t.Fatalf("seed writer live workflow run: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO writer_runs (tenant_id, run_id, workflow_run_id, project_id, mode, status, module_key, instruction, created_by)
VALUES ($1, $2, $2, $3, 'draft', 'completed', 'writer_composer', 'live export', $4)`, liveWriterExportTenantID, liveWriterExportRunID, liveWriterExportProjectID, liveWriterExportUserID); err != nil {
		t.Fatalf("seed writer live run: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO writer_drafts (tenant_id, draft_id, run_id, project_id, content_text, word_count, status)
VALUES ($1, $2, $3, $4, '真实正文导出内容。', 10, 'candidate')`, liveWriterExportTenantID, liveWriterExportDraftID, liveWriterExportRunID, liveWriterExportProjectID); err != nil {
		t.Fatalf("seed writer live candidate draft: %v", err)
	}
}

func liveWriterExportAppURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatalf("parse writer live database URL: %v", err)
	}
	parsed.User = url.UserPassword(liveWriterExportAppRole, liveWriterExportAppPassword)
	return parsed.String()
}
