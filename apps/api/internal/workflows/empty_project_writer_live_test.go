package workflows

import (
	"context"
	"database/sql"
	"net/url"
	"os"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/testschema"
	"mirofish-novel/apps/api/internal/writerworkspace"

	_ "github.com/jackc/pgx/v5/stdlib"
)

// Empty-project Writer live path (doc 28 Z0):
// zero source/segment/seed rows -> book plan -> chapter/scene -> writer run/draft -> adoption -> manuscript.

const (
	emptyProjectLiveTenant   = "c1111111-1111-4111-8111-111111111111"
	emptyProjectLiveUser     = "c2222222-2222-4222-8222-222222222222"
	emptyProjectLiveProject  = "c3333333-3333-4333-8333-333333333333"
	emptyProjectLiveUserMail = "empty-project-writer-live@example.test"
	emptyProjectLiveRole     = "mirofish_empty_project_writer_live"
	emptyProjectLivePassword = "mirofish_empty_project_writer_live_password"
	emptyProjectLiveRun      = "c4444444-4444-4444-8444-444444444444"
	emptyProjectLiveDraft    = "c5555555-5555-4555-8555-555555555555"
)

func TestLiveEmptyProjectWriterPathWithoutSeedArtifacts(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_EMPTY_PROJECT_WRITER_LIVE_DATABASE_URL"))
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_WRITER_WORKSPACE_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_EMPTY_PROJECT_WRITER_LIVE_DATABASE_URL to run empty-project Writer live path")
	}

	admin, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = admin.Close() })
	if err := testschema.RequireDisposableLiveDatabase(context.Background(), admin); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if _, err := admin.Exec(`DELETE FROM tenants WHERE tenant_id = $1`, emptyProjectLiveTenant); err != nil {
			t.Errorf("cleanup empty-project live tenant: %v", err)
		}
		if _, err := admin.Exec(`DELETE FROM users WHERE user_id = $1 AND email = $2`, emptyProjectLiveUser, emptyProjectLiveUserMail); err != nil {
			t.Errorf("cleanup empty-project live user: %v", err)
		}
		_, _ = admin.Exec(`DROP ROLE IF EXISTS ` + emptyProjectLiveRole)
	})
	prepareEmptyProjectLive(t, admin)

	app, err := sql.Open("pgx", emptyProjectLiveAppURL(t, adminURL))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = app.Close() })

	ctx := context.Background()
	assertEmptyProjectHasZeroSeedRows(t, admin)

	workspace := writerworkspace.NewSQLStore(app)
	scope := writerworkspace.Scope{
		TenantID:    emptyProjectLiveTenant,
		ProjectID:   emptyProjectLiveProject,
		ActorUserID: emptyProjectLiveUser,
	}

	targetChapters := 12
	plan, err := workspace.CreateBookPlan(ctx, scope, writerworkspace.BookPlan{
		Title:              "从零开始的故事",
		Premise:            "一座海边小镇上，失踪的灯塔看守人留下了未完成的日记。",
		PlanningJSON:       `{"bootstrap":true,"entry":"idea_first"}`,
		TargetChapterCount: &targetChapters,
	})
	if err != nil {
		t.Fatalf("create book plan on empty project: %s %v", writerworkspace.ErrorCode(err), err)
	}
	if plan.BookPlanID == "" || plan.Premise == "" {
		t.Fatalf("unexpected book plan: %#v", plan)
	}

	chapter, err := workspace.CreateChapter(ctx, writerworkspace.CreateChapterInput{
		Scope:   scope,
		Title:   "第一章 灯塔",
		Brief:   "开篇建立小镇与失踪事件",
		Content: "章节纲要：从码头到灯塔的夜路。",
	})
	if err != nil {
		t.Fatalf("create chapter on empty project: %s %v", writerworkspace.ErrorCode(err), err)
	}
	scene, err := workspace.CreateScene(ctx, writerworkspace.CreateSceneInput{
		Scope:     scope,
		ChapterID: chapter.ChapterID,
		Title:     "码头夜色",
		Brief:     "主角抵达码头",
		Content:   "场景焦点：风雨、汽笛、日记第一页。",
	})
	if err != nil {
		t.Fatalf("create scene on empty project: %s %v", writerworkspace.ErrorCode(err), err)
	}

	// Simulate a completed Writer run + candidate draft without Seed inputs.
	if _, err := admin.Exec(`INSERT INTO workflow_runs(tenant_id,run_id,workflow_type,project_id,status,started_by)
VALUES($1,$2,'writer_run',$3,'completed',$4)`, emptyProjectLiveTenant, emptyProjectLiveRun, emptyProjectLiveProject, emptyProjectLiveUser); err != nil {
		t.Fatalf("insert writer workflow run: %v", err)
	}
	if _, err := admin.Exec(`INSERT INTO writer_runs(tenant_id,run_id,workflow_run_id,project_id,chapter_id,scene_id,mode,status,module_key,instruction,created_by)
VALUES($1,$2,$2,$3,$4,$5,'draft','completed','writer_composer','写开篇第一段',$6)`,
		emptyProjectLiveTenant, emptyProjectLiveRun, emptyProjectLiveProject, chapter.ChapterID, scene.SceneID, emptyProjectLiveUser); err != nil {
		t.Fatalf("insert writer run: %v", err)
	}
	if _, err := admin.Exec(`INSERT INTO writer_drafts(tenant_id,draft_id,run_id,project_id,chapter_id,scene_id,content_text,word_count,status)
VALUES($1,$2,$3,$4,$5,$6,$7,18,'candidate')`,
		emptyProjectLiveTenant, emptyProjectLiveDraft, emptyProjectLiveRun, emptyProjectLiveProject, chapter.ChapterID, scene.SceneID,
		"雨把码头的木板洗得发亮。灯塔仍是黑的，日记却湿漉漉地摊在栏杆上。"); err != nil {
		t.Fatalf("insert candidate draft: %v", err)
	}

	adoption := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{
		Queryer: NewSQLDBWriterDraftAdoptionQueryer(app),
	})
	adopted, err := adoption.AdoptDraft(ctx, DraftAdoptionInput{
		TenantID:    emptyProjectLiveTenant,
		DraftID:     emptyProjectLiveDraft,
		ActorUserID: emptyProjectLiveUser,
		RequestID:   "empty-project-live-adopt",
		ChapterID:   chapter.ChapterID,
		BlockOrder:  1,
	})
	if err != nil {
		t.Fatalf("adopt draft on empty project: %s %v", ErrorCode(err), err)
	}
	if adopted.Status != "adopted" || adopted.BlockID == "" || adopted.ProjectID != emptyProjectLiveProject {
		t.Fatalf("unexpected adoption: %#v", adopted)
	}
	if adopted.ChapterID != chapter.ChapterID {
		t.Fatalf("adoption chapter mismatch: %#v", adopted)
	}

	var blockCount int
	var content string
	if err := admin.QueryRow(`SELECT count(*), coalesce(max(content_text),'')
FROM manuscript_blocks
WHERE tenant_id=$1 AND project_id=$2 AND status='active'`, emptyProjectLiveTenant, emptyProjectLiveProject).Scan(&blockCount, &content); err != nil {
		t.Fatalf("read manuscript blocks: %v", err)
	}
	if blockCount != 1 || !strings.Contains(content, "灯塔") {
		t.Fatalf("expected one adopted manuscript block, got count=%d content=%q", blockCount, content)
	}

	// Idempotent replay must not create a second block or Seed artifacts.
	replay, err := adoption.AdoptDraft(ctx, DraftAdoptionInput{
		TenantID:  emptyProjectLiveTenant,
		DraftID:   emptyProjectLiveDraft,
		RequestID: "empty-project-live-adopt-replay",
	})
	if err != nil {
		t.Fatalf("adoption replay: %s %v", ErrorCode(err), err)
	}
	if replay.BlockID != adopted.BlockID {
		t.Fatalf("adoption replay created a different block: first=%#v replay=%#v", adopted, replay)
	}

	assertEmptyProjectHasZeroSeedRows(t, admin)
	if err := admin.QueryRow(`SELECT count(*) FROM manuscript_blocks WHERE tenant_id=$1 AND project_id=$2`, emptyProjectLiveTenant, emptyProjectLiveProject).Scan(&blockCount); err != nil {
		t.Fatalf("recount manuscript blocks: %v", err)
	}
	if blockCount != 1 {
		t.Fatalf("adoption replay duplicated manuscript: %d", blockCount)
	}
}

func prepareEmptyProjectLive(t *testing.T, db *sql.DB) {
	t.Helper()
	_, _ = db.Exec(`DELETE FROM tenants WHERE tenant_id = $1`, emptyProjectLiveTenant)
	if _, err := db.Exec(`DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '` + emptyProjectLiveRole + `') THEN
    CREATE ROLE ` + emptyProjectLiveRole + ` LOGIN PASSWORD '` + emptyProjectLivePassword + `' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE ` + emptyProjectLiveRole + ` WITH LOGIN PASSWORD '` + emptyProjectLivePassword + `';
  END IF;
END $$; GRANT mirofish_app TO ` + emptyProjectLiveRole); err != nil {
		t.Fatalf("ensure empty-project app role: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO users(user_id,email,display_name)
VALUES($1,$2,'Empty Project Writer Live')
ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email, display_name=EXCLUDED.display_name`,
		emptyProjectLiveUser, emptyProjectLiveUserMail); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO tenants(tenant_id,slug,name,tenant_type)
VALUES($1,'empty-project-writer-live','Empty Project Writer','personal')`, emptyProjectLiveTenant); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO projects(tenant_id,project_id,title,created_by)
VALUES($1,$2,'Empty Idea Project',$3)`, emptyProjectLiveTenant, emptyProjectLiveProject, emptyProjectLiveUser); err != nil {
		t.Fatal(err)
	}
}

func assertEmptyProjectHasZeroSeedRows(t *testing.T, db *sql.DB) {
	t.Helper()
	checks := []struct {
		label string
		query string
	}{
		{"source_files", `SELECT count(*) FROM source_files WHERE tenant_id=$1 AND project_id=$2`},
		{"text_segments", `SELECT count(*) FROM text_segments WHERE tenant_id=$1 AND project_id=$2`},
		{"seed workflow_runs", `SELECT count(*) FROM workflow_runs WHERE tenant_id=$1 AND project_id=$2 AND workflow_type LIKE 'seed%'`},
	}
	for _, check := range checks {
		var count int
		if err := db.QueryRow(check.query, emptyProjectLiveTenant, emptyProjectLiveProject).Scan(&count); err != nil {
			// text_segments may not exist in all disposable fixtures; treat missing relation as zero for this contract.
			if strings.Contains(err.Error(), "does not exist") {
				continue
			}
			t.Fatalf("count %s: %v", check.label, err)
		}
		if count != 0 {
			t.Fatalf("empty project must have zero %s, got %d", check.label, count)
		}
	}
}

func emptyProjectLiveAppURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatal(err)
	}
	parsed.User = url.UserPassword(emptyProjectLiveRole, emptyProjectLivePassword)
	return parsed.String()
}
