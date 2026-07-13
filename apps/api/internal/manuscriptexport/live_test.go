package manuscriptexport

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/manuscriptworkspace"
	"mirofish-novel/apps/api/internal/workflows"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const liveTenantID = "91111111-1111-4111-8111-111111111111"
const liveUserID = "92222222-2222-4222-8222-222222222222"
const liveProjectID = "93333333-3333-4333-8333-333333333333"
const liveRunID = "94444444-4444-4444-8444-444444444444"
const liveDraftID = "95555555-5555-4555-8555-555555555555"
const liveAppRole = "mirofish_writer_export_live_app"
const liveAppPassword = "mirofish_writer_export_live_password"

func TestLiveExplicitAdoptionThenAuthorizedArtifactDownload(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WRITER_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WRITER_LIVE_DATABASE_URL to run Writer adoption/export live E2E")
	}
	adminDB, appDB := prepareLiveDatabase(t, adminURL)
	defer adminDB.Close()
	defer appDB.Close()
	t.Cleanup(func() { _, _ = adminDB.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveTenantID) })

	exporter := workflows.NewSQLManuscriptArtifactExporter(workflows.SQLManuscriptArtifactExporterConfig{
		Queryer: workflows.NewSQLDBWriterEventQueryer(appDB),
	})
	handler := NewHandler(Config{
		Exporter:      exporter,
		Authorizer:    &recordingAuthorizer{},
		ActorResolver: staticActorResolver{actor: liveUserID},
	})

	before := downloadLiveArtifact(handler)
	if before.Code != http.StatusConflict || !strings.Contains(before.Body.String(), "MANUSCRIPT_EMPTY") {
		t.Fatalf("candidate draft was exportable before explicit adoption: status=%d body=%s", before.Code, before.Body.String())
	}

	adoptionStore := workflows.NewSQLDraftAdoptionStore(workflows.SQLDraftAdoptionStoreConfig{
		Queryer: workflows.NewSQLDBWriterDraftAdoptionQueryer(appDB),
	})
	adopted, err := adoptionStore.AdoptDraft(context.Background(), workflows.DraftAdoptionInput{
		TenantID:    liveTenantID,
		DraftID:     liveDraftID,
		ActorUserID: liveUserID,
		RequestID:   "req-writer-live-adopt",
		BlockOrder:  1,
	})
	if err != nil {
		t.Fatalf("explicit draft adoption failed: code=%s err=%v", workflows.ErrorCode(err), err)
	}
	if adopted.DraftID != liveDraftID || adopted.Status != "adopted" || adopted.BlockID == "" {
		t.Fatalf("unexpected adoption result: %#v", adopted)
	}

	after := downloadLiveArtifact(handler)
	if after.Code != http.StatusOK {
		t.Fatalf("artifact download failed: status=%d body=%s", after.Code, after.Body.String())
	}
	if after.Body.String() != "第一章\n\n雨夜里，门终于打开。\n" {
		t.Fatalf("download did not contain adopted manuscript prose: %q", after.Body.String())
	}
	if !strings.HasPrefix(after.Header().Get("Content-Disposition"), "attachment;") || after.Header().Get("X-Content-SHA256") == "" {
		t.Fatalf("artifact response missing download/integrity headers: %#v", after.Header())
	}

	workspaceStore := manuscriptworkspace.NewSQLStore(appDB)
	artifactFiles, err := NewFileArtifactStore(t.TempDir())
	if err != nil {
		t.Fatalf("create private artifact store: %v", err)
	}
	generator := NewGenerator(GeneratorConfig{States: workspaceStore, Exporter: exporter, Artifacts: artifactFiles})
	exportRecord, replay, err := generator.GenerateExport(context.Background(), manuscriptworkspace.CreateExportInput{
		Scope:  manuscriptworkspace.Scope{TenantID: liveTenantID, ProjectID: liveProjectID, ActorUserID: liveUserID, RequestID: "req-writer-live-workspace-export"},
		Format: "txt",
	})
	if err != nil || replay || exportRecord.Status != "completed" || exportRecord.ArtifactSHA256 == "" || exportRecord.ArtifactSizeBytes <= 0 {
		t.Fatalf("workspace artifact generation failed: record=%#v replay=%v err=%v", exportRecord, replay, err)
	}
	storedHandler := NewHandler(Config{
		States: workspaceStore, Artifacts: artifactFiles,
		Authorizer: &recordingAuthorizer{}, ActorResolver: staticActorResolver{actor: liveUserID},
	})
	storedRequest := httptest.NewRequest(http.MethodGet, "/v1/projects/"+liveProjectID+"/manuscript/exports/"+exportRecord.ExportID+"/download", nil)
	storedRequest.Header.Set("X-Tenant-Id", liveTenantID)
	storedResponse := httptest.NewRecorder()
	storedHandler.ServeHTTP(storedResponse, storedRequest)
	if storedResponse.Code != http.StatusOK || storedResponse.Body.String() != after.Body.String() || storedResponse.Header().Get("X-Content-SHA256") != exportRecord.ArtifactSHA256 {
		t.Fatalf("stored artifact download mismatch: status=%d headers=%#v body=%q", storedResponse.Code, storedResponse.Header(), storedResponse.Body.String())
	}

	deniedExporter := &recordingExporter{}
	denied := NewHandler(Config{
		Exporter:      deniedExporter,
		Authorizer:    &recordingAuthorizer{err: context.Canceled},
		ActorResolver: staticActorResolver{actor: liveUserID},
	})
	deniedResponse := downloadLiveArtifact(denied)
	if deniedResponse.Code != http.StatusForbidden || deniedExporter.calls != 0 {
		t.Fatalf("denied download reached exporter: status=%d calls=%d", deniedResponse.Code, deniedExporter.calls)
	}
}

func downloadLiveArtifact(handler http.Handler) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/"+liveProjectID+"/manuscript/export?format=txt", nil)
	request.Header.Set("X-Tenant-Id", liveTenantID)
	request.Header.Set("X-Request-Id", "req-writer-live-export")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func prepareLiveDatabase(t *testing.T, adminURL string) (*sql.DB, *sql.DB) {
	t.Helper()
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open Writer live admin DB: %v", err)
	}
	var schemaReady bool
	if err := adminDB.QueryRow(`SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL
		AND to_regclass('public.manuscript_blocks') IS NOT NULL
		AND EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version = '0008_writer_manuscript_hardening')`).Scan(&schemaReady); err != nil || !schemaReady {
		adminDB.Close()
		t.Fatalf("Writer live database must be prepared through 0008_writer_manuscript_hardening: %v", err)
	}
	roleSQL := "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '" + liveAppRole + "') THEN CREATE ROLE " + liveAppRole + " LOGIN PASSWORD '" + liveAppPassword + "' IN ROLE mirofish_app; ELSE ALTER ROLE " + liveAppRole + " WITH LOGIN PASSWORD '" + liveAppPassword + "'; END IF; END $$; GRANT mirofish_app TO " + liveAppRole
	if _, err := adminDB.Exec(roleSQL); err != nil {
		adminDB.Close()
		t.Fatalf("ensure Writer live app role: %v", err)
	}
	_, _ = adminDB.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveTenantID)
	_, _ = adminDB.Exec("DELETE FROM users WHERE user_id = $1 OR email = 'writer-export-live@example.test'", liveUserID)
	if _, err := adminDB.Exec(`INSERT INTO users (user_id, email, display_name)
VALUES ($1, 'writer-export-live@example.test', 'Writer Export Live')
ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email`, liveUserID); err != nil {
		adminDB.Close()
		t.Fatalf("seed Writer live user: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO tenants (tenant_id, slug, name, tenant_type)
VALUES ($1, 'writer-export-live', 'Writer Export Live', 'personal')`, liveTenantID); err != nil {
		adminDB.Close()
		t.Fatalf("seed Writer live tenant: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO projects (tenant_id, project_id, title, created_by)
VALUES ($1, $2, 'Writer Export Live Project', $3)`, liveTenantID, liveProjectID, liveUserID); err != nil {
		adminDB.Close()
		t.Fatalf("seed Writer live project: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
VALUES ($1, $2, 'writer_run', $3, 'completed', 100, $4)`, liveTenantID, liveRunID, liveProjectID, liveUserID); err != nil {
		adminDB.Close()
		t.Fatalf("seed Writer live workflow run: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO writer_runs (tenant_id, run_id, workflow_run_id, project_id, mode, status, module_key, instruction, created_by)
VALUES ($1, $2, $2, $3, 'draft', 'completed', 'writer_composer', 'private live instruction', $4)`, liveTenantID, liveRunID, liveProjectID, liveUserID); err != nil {
		adminDB.Close()
		t.Fatalf("seed Writer live run: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO writer_drafts (tenant_id, draft_id, run_id, project_id, content_text, word_count, status)
VALUES ($1, $2, $3, $4, $5, 12, 'candidate')`, liveTenantID, liveDraftID, liveRunID, liveProjectID, "第一章\n\n雨夜里，门终于打开。"); err != nil {
		adminDB.Close()
		t.Fatalf("seed Writer live candidate: %v", err)
	}

	parsed, err := url.Parse(adminURL)
	if err != nil {
		adminDB.Close()
		t.Fatalf("parse Writer live DB URL: %v", err)
	}
	parsed.User = url.UserPassword(liveAppRole, liveAppPassword)
	appDB, err := sql.Open("pgx", parsed.String())
	if err != nil {
		adminDB.Close()
		t.Fatalf("open Writer live app DB: %v", err)
	}
	return adminDB, appDB
}
