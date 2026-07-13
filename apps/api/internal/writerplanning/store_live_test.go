package writerplanning

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	livePlanningTenant  = "d1000000-0000-4000-8000-000000000001"
	livePlanningProject = "d1000000-0000-4000-8000-000000000002"
	livePlanningUser    = "d1000000-0000-4000-8000-000000000003"
	livePlanningPlan    = "d1000000-0000-4000-8000-000000000004"
	livePlanningWriter  = "d1000000-0000-4000-8000-000000000005"
	livePlanningDraft   = "d1000000-0000-4000-8000-000000000006"
	livePlanningBlock   = "d1000000-0000-4000-8000-000000000007"
	livePlanningBookRun = "d1000000-0000-4000-8000-000000000008"
	livePlanningDedup   = "d1000000-0000-4000-8000-000000000009"
)

func TestLiveSQLStoreAdmitReplayAndCompensate(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WRITER_PLANNING_LIVE_ADMIN_DATABASE_URL"))
	appURL := strings.TrimSpace(os.Getenv("MIROFISH_WRITER_PLANNING_LIVE_APP_DATABASE_URL"))
	if adminURL == "" || appURL == "" {
		t.Skip("set writer planning live admin and app database URLs")
	}
	admin := openPlanningLiveDB(t, adminURL)
	defer admin.Close()
	preparePlanningLiveFixture(t, admin)
	defer cleanupPlanningLiveFixture(admin)

	app := openPlanningLiveDB(t, appURL)
	defer app.Close()
	store := NewSQLStore(app)

	bookInput := StartInput{
		TenantID: livePlanningTenant, ProjectID: livePlanningProject, ActorUserID: livePlanningUser,
		RequestID: "live-book-request", Kind: KindBookPlan, BookPlanID: livePlanningPlan, ExpectedVersion: 1,
	}
	book := Admission{RunID: livePlanningBookRun, ProjectID: livePlanningProject, WorkflowType: WorkflowType(KindBookPlan), ModuleKey: BookPlanModuleKey, Status: "queued", BookPlanID: livePlanningPlan}
	assertPlanningAdmissionLifecycle(t, store, bookInput, book, "writer-book-live", "book-hash")

	dedupInput := StartInput{
		TenantID: livePlanningTenant, ProjectID: livePlanningProject, ActorUserID: livePlanningUser,
		RequestID: "live-dedup-request", Kind: KindDedup, BlockIDs: []string{livePlanningBlock},
	}
	dedup := Admission{RunID: livePlanningDedup, ProjectID: livePlanningProject, WorkflowType: WorkflowType(KindDedup), ModuleKey: DedupModuleKey, Status: "queued"}
	assertPlanningAdmissionLifecycle(t, store, dedupInput, dedup, "writer-dedup-live", "dedup-hash")
}

func assertPlanningAdmissionLifecycle(t *testing.T, store *SQLStore, input StartInput, proposed Admission, temporalID, payloadHash string) {
	t.Helper()
	ctx := context.Background()
	admitted, replay, err := store.Admit(ctx, input, proposed, temporalID, payloadHash)
	if err != nil || replay || admitted.RunID != proposed.RunID {
		t.Fatalf("admit %s: admitted=%#v replay=%v code=%s err=%v", input.Kind, admitted, replay, ErrorCode(err), err)
	}
	replayed, replay, err := store.Admit(ctx, input, Admission{RunID: "d1000000-0000-4000-8000-000000000010"}, temporalID+"-ignored", payloadHash)
	if err != nil || !replay || replayed.RunID != proposed.RunID {
		t.Fatalf("replay %s: admitted=%#v replay=%v code=%s err=%v", input.Kind, replayed, replay, ErrorCode(err), err)
	}
	if err := store.Compensate(ctx, input, admitted); err != nil {
		t.Fatalf("compensate %s: code=%s err=%v", input.Kind, ErrorCode(err), err)
	}
}

func openPlanningLiveDB(t *testing.T, databaseURL string) *sql.DB {
	t.Helper()
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	if err := db.Ping(); err != nil {
		db.Close()
		t.Fatal(err)
	}
	return db
}

func preparePlanningLiveFixture(t *testing.T, db *sql.DB) {
	t.Helper()
	cleanupPlanningLiveFixture(db)
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	statements := []struct {
		query string
		args  []any
	}{
		{`INSERT INTO users (user_id,email,display_name) VALUES ($1,'writer-planning-live@example.test','Writer Planning Live')`, []any{livePlanningUser}},
		{`INSERT INTO tenants (tenant_id,slug,name,tenant_type) VALUES ($1,'writer-planning-live','Writer Planning Live','personal')`, []any{livePlanningTenant}},
		{`INSERT INTO tenant_memberships (tenant_id,user_id,role) VALUES ($1,$2,'owner')`, []any{livePlanningTenant, livePlanningUser}},
		{`INSERT INTO projects (tenant_id,project_id,title,created_by) VALUES ($1,$2,'Writer Planning Live',$3)`, []any{livePlanningTenant, livePlanningProject, livePlanningUser}},
		{`INSERT INTO project_members (tenant_id,project_id,user_id,role) VALUES ($1,$2,$3,'project_owner')`, []any{livePlanningTenant, livePlanningProject, livePlanningUser}},
		{`INSERT INTO book_plans (tenant_id,project_id,book_plan_id,title,status,premise,planning_jsonb,created_by,updated_by)
VALUES ($1,$2,$3,'Live plan','draft','Private premise','{}',$4,$4)`, []any{livePlanningTenant, livePlanningProject, livePlanningPlan, livePlanningUser}},
		{`INSERT INTO writer_runs (tenant_id,run_id,project_id,mode,status,module_key,instruction,created_by)
VALUES ($1,$2,$3,'draft','completed','writer_composer','Private instruction',$4)`, []any{livePlanningTenant, livePlanningWriter, livePlanningProject, livePlanningUser}},
		{`INSERT INTO writer_drafts (tenant_id,draft_id,run_id,project_id,content_text,status)
VALUES ($1,$2,$3,$4,'Private adopted draft','adopted')`, []any{livePlanningTenant, livePlanningDraft, livePlanningWriter, livePlanningProject}},
		{`INSERT INTO manuscript_blocks (tenant_id,block_id,project_id,source_draft_id,block_order,content_text,status,created_by,updated_by)
VALUES ($1,$2,$3,$4,1,'Private adopted manuscript','active',$5,$5)`, []any{livePlanningTenant, livePlanningBlock, livePlanningProject, livePlanningDraft, livePlanningUser}},
	}
	for _, statement := range statements {
		if _, err := tx.Exec(statement.query, statement.args...); err != nil {
			t.Fatalf("prepare writer planning live fixture: %v", err)
		}
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit writer planning live fixture: %v", err)
	}
}

func cleanupPlanningLiveFixture(db *sql.DB) {
	_, _ = db.Exec(`DELETE FROM tenants WHERE tenant_id=$1`, livePlanningTenant)
	_, _ = db.Exec(`DELETE FROM users WHERE user_id=$1`, livePlanningUser)
}
