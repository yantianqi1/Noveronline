package writerworkspace

import (
	"context"
	"database/sql"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"sync"
	"testing"

	"mirofish-novel/apps/api/internal/testschema"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const liveTenant = "a1111111-1111-4111-8111-111111111111"
const liveOtherTenant = "a2222222-2222-4222-8222-222222222222"
const liveProject = "a3333333-3333-4333-8333-333333333333"
const liveOtherProject = "a4444444-4444-4444-8444-444444444444"
const liveUser = "a5555555-5555-4555-8555-555555555555"
const liveUserEmail = "writer-workspace-live@example.test"
const liveRun = "a6666666-6666-4666-8666-666666666666"
const liveRole = "mirofish_writer_workspace_live"
const livePassword = "mirofish_writer_workspace_live_password"

func TestLiveWriterWorkspaceAppRoleLifecycle(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WRITER_WORKSPACE_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WRITER_WORKSPACE_LIVE_DATABASE_URL to run app-role Writer Workspace E2E")
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
		if _, err := admin.Exec(`DELETE FROM tenants WHERE tenant_id IN ($1,$2)`, liveTenant, liveOtherTenant); err != nil {
			t.Errorf("cleanup writer workspace live tenants: %v", err)
		}
		if _, err := admin.Exec(`DELETE FROM users WHERE user_id = $1 AND email = $2`, liveUser, liveUserEmail); err != nil {
			t.Errorf("cleanup writer workspace live user: %v", err)
		}
		_, _ = admin.Exec(`DROP ROLE IF EXISTS ` + liveRole)
	})
	prepareLive(t, admin)
	app, err := sql.Open("pgx", appURL(t, adminURL))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = app.Close() })
	store := NewSQLStore(app)
	ctx := context.Background()
	scope := Scope{TenantID: liveTenant, ProjectID: liveProject, ActorUserID: liveUser}
	c1, err := store.CreateChapter(ctx, CreateChapterInput{Scope: scope, Title: "One", Brief: "private brief", Content: "private chapter"})
	if err != nil {
		t.Fatalf("create chapter: %s %v", ErrorCode(err), err)
	}
	c2, err := store.CreateChapter(ctx, CreateChapterInput{Scope: scope, Title: "Two"})
	if err != nil {
		t.Fatal(err)
	}
	chapterOwner, err := store.LookupResourceOwner(ctx, OwnerLookupInput{TenantID: liveTenant, ActorUserID: liveUser, Kind: ResourceChapter, ResourceID: c1.ChapterID})
	if err != nil || chapterOwner.ProjectID != liveProject || chapterOwner.TenantScoped {
		t.Fatalf("tenant-scoped chapter owner lookup: %#v %v", chapterOwner, err)
	}
	private, err := store.GetChapter(ctx, scope, c1.ChapterID, true)
	if err != nil || private.Private == nil || private.Private.Content != "private chapter" {
		t.Fatalf("authorized private read failed: %#v %v", private, err)
	}
	newContent := "updated chapter"
	updated, err := store.UpdateChapter(ctx, scope, c1.ChapterID, ChapterPatch{ExpectedVersion: 1, Content: &newContent})
	if err != nil || updated.Version != 2 {
		t.Fatalf("update chapter: %#v %v", updated, err)
	}
	if _, err = store.UpdateChapter(ctx, scope, c1.ChapterID, ChapterPatch{ExpectedVersion: 1, Content: &newContent}); ErrorCode(err) != CodeConflict {
		t.Fatalf("stale update did not conflict: %v", err)
	}
	versions, err := store.ListChapterVersions(ctx, scope, c1.ChapterID, true)
	if err != nil || len(versions) != 1 || versions[0].Private == nil || versions[0].Private.Content != "private chapter" {
		t.Fatalf("immutable chapter history failed: %#v %v", versions, err)
	}
	s1, err := store.CreateScene(ctx, CreateSceneInput{Scope: scope, ChapterID: c1.ChapterID, Title: "Scene one", Content: "scene private"})
	if err != nil {
		t.Fatal(err)
	}
	s2, err := store.CreateScene(ctx, CreateSceneInput{Scope: scope, ChapterID: c1.ChapterID, Title: "Scene two"})
	if err != nil {
		t.Fatal(err)
	}
	sceneContent := "scene updated"
	if _, err = store.UpdateScene(ctx, scope, s1.SceneID, ScenePatch{ExpectedVersion: 1, Content: &sceneContent}); err != nil {
		t.Fatal(err)
	}
	if err = store.ReorderScenes(ctx, scope, c1.ChapterID, []string{s2.SceneID, s1.SceneID}); err != nil {
		t.Fatalf("scene reorder: %v", err)
	}
	if err = store.ReorderScenes(ctx, scope, c1.ChapterID, []string{s1.SceneID}); ErrorCode(err) != CodeReorderInvalid {
		t.Fatalf("incomplete reorder accepted: %v", err)
	}
	scenes, _ := store.ListScenes(ctx, scope, c1.ChapterID)
	if len(scenes) != 2 || scenes[0].SceneID != s2.SceneID {
		t.Fatalf("failed reorder changed committed order: %#v", scenes)
	}
	if err = store.ReorderChapters(ctx, scope, []string{c2.ChapterID, c1.ChapterID}); err != nil {
		t.Fatal(err)
	}
	if err = store.DeleteScene(ctx, scope, s2.SceneID, 1); err != nil {
		t.Fatalf("delete scene: %v", err)
	}
	if _, err = store.GetScene(ctx, scope, s2.SceneID, false); ErrorCode(err) != CodeNotFound {
		t.Fatalf("deleted scene remained readable: %v", err)
	}
	reusedSceneOrder := 0
	reusedScene, err := store.CreateScene(ctx, CreateSceneInput{Scope: scope, ChapterID: c1.ChapterID, Title: "Reused scene order", Order: &reusedSceneOrder})
	if err != nil || reusedScene.Order != reusedSceneOrder {
		t.Fatalf("reuse archived scene order: %#v %v", reusedScene, err)
	}
	if err = store.ReorderScenes(ctx, scope, c1.ChapterID, []string{s1.SceneID, reusedScene.SceneID}); err != nil {
		t.Fatalf("scene reorder after archive/reuse: %v", err)
	}
	if err = store.DeleteChapter(ctx, scope, c2.ChapterID, 1); err != nil {
		t.Fatalf("delete chapter: %v", err)
	}
	reusedChapterOrder := 0
	reusedChapter, err := store.CreateChapter(ctx, CreateChapterInput{Scope: scope, Title: "Reused chapter order", Order: &reusedChapterOrder})
	if err != nil || reusedChapter.Order != reusedChapterOrder {
		t.Fatalf("reuse archived chapter order: %#v %v", reusedChapter, err)
	}
	if err = store.ReorderChapters(ctx, scope, []string{c1.ChapterID, reusedChapter.ChapterID}); err != nil {
		t.Fatalf("chapter reorder after archive/reuse: %v", err)
	}
	outline, err := store.CreateOutline(ctx, CreateOutlineInput{Scope: scope, ScopeType: "project", Lifecycle: "active", Title: "Outline", OutlineText: "v1"})
	if err != nil {
		t.Fatal(err)
	}
	restored, err := store.RestoreOutline(ctx, scope, outline.OutlineVersionID)
	if err != nil || restored.RestoredFromVersionID != outline.OutlineVersionID || restored.Version != 2 {
		t.Fatalf("outline restore: %#v %v", restored, err)
	}
	candidate, err := store.CreateOutline(ctx, CreateOutlineInput{Scope: scope, ScopeType: "project", Lifecycle: "candidate", Title: "Candidate", OutlineText: "v3"})
	if err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	results := make(chan error, 2)
	for range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, e := store.RestoreOutline(ctx, scope, candidate.OutlineVersionID)
			results <- e
		}()
	}
	wg.Wait()
	close(results)
	conflicts, successes := 0, 0
	for e := range results {
		if e == nil {
			successes++
		} else if ErrorCode(e) == CodeConflict {
			conflicts++
		}
	}
	if conflicts != 1 || successes != 1 {
		t.Fatalf("concurrent restore was not single-winner: successes=%d conflicts=%d", successes, conflicts)
	}
	plan, err := store.CreateBookPlan(ctx, scope, BookPlan{Title: "Book plan", PlanningJSON: `{"acts":3}`})
	if err != nil {
		t.Fatal(err)
	}
	active := "active"
	plan, err = store.UpdateBookPlan(ctx, scope, plan.BookPlanID, BookPlanPatch{ExpectedVersion: 1, Status: &active})
	if err != nil || plan.Version != 2 {
		t.Fatalf("update plan: %#v %v", plan, err)
	}
	if _, err = store.UpdateBookPlan(ctx, scope, plan.BookPlanID, BookPlanPatch{ExpectedVersion: 1, Status: &active}); ErrorCode(err) != CodeConflict {
		t.Fatalf("stale plan update accepted: %v", err)
	}
	admission, err := store.AdmitBookRun(ctx, scope, plan.BookPlanID, AdmitBookRunInput{ExpectedVersion: 2, RunID: liveRun, Status: "queued", ItemCount: 2})
	if err != nil || admission.Plan.LastRunID != liveRun || admission.Plan.Version != 3 || admission.Event.EventType != "planning.admitted" {
		t.Fatalf("book run admission: %#v %v", admission, err)
	}
	if _, err = store.AdmitBookRun(ctx, scope, plan.BookPlanID, AdmitBookRunInput{ExpectedVersion: 2, RunID: liveRun, Status: "queued"}); ErrorCode(err) != CodeConflict {
		t.Fatalf("stale run admission accepted: %v", err)
	}
	if _, err = store.AppendBookRunEvent(ctx, scope, BookRunEvent{BookPlanID: plan.BookPlanID, EventType: "planning.started", Status: "running", ItemCount: 2}); err != nil {
		t.Fatal(err)
	}
	events, err := store.ListBookRunEvents(ctx, scope, plan.BookPlanID, 0)
	if err != nil || len(events) != 2 || events[0].EventType != "planning.admitted" || events[1].ItemCount != 2 {
		t.Fatalf("count-only replay: %#v %v", events, err)
	}
	preset, err := store.UpsertPreset(ctx, scope, WriterPreset{Name: "Default", SettingsJSON: `{"tone":"tense"}`, Enabled: true})
	if err != nil {
		t.Fatal(err)
	}
	preset.Description = "Updated"
	if _, err = store.UpsertPreset(ctx, scope, preset); err != nil {
		t.Fatal(err)
	}
	if got, e := store.GetPreset(ctx, scope, preset.PresetID); e != nil || got.Description != "Updated" {
		t.Fatalf("preset read/update: %#v %v", got, e)
	}
	tenantPreset, err := store.UpsertPreset(ctx, scope, WriterPreset{Scope: "tenant", Name: "Tenant default", SettingsJSON: `{"tone":"neutral"}`, Enabled: true})
	if err != nil || tenantPreset.Scope != "tenant" || tenantPreset.ProjectID != "" {
		t.Fatalf("tenant preset scope: %#v %v", tenantPreset, err)
	}
	tenantPresetOwner, err := store.LookupResourceOwner(ctx, OwnerLookupInput{TenantID: liveTenant, ActorUserID: liveUser, Kind: ResourceWriterPreset, ResourceID: tenantPreset.PresetID})
	if err != nil || !tenantPresetOwner.TenantScoped || tenantPresetOwner.ProjectID != "" {
		t.Fatalf("tenant preset owner lookup: %#v %v", tenantPresetOwner, err)
	}
	if _, err = store.UpsertPreset(ctx, scope, WriterPreset{Name: "Unsafe", SettingsJSON: `{"provider":"secret"}`, Enabled: true}); ErrorCode(err) != CodeValidationFailed {
		t.Fatalf("unsafe preset accepted: %v", err)
	}
	lex, err := store.UpsertLexicon(ctx, scope, ForbiddenEntry{Term: "bad", Category: "style", Severity: "warning", ReplacementGuidance: "replace", Enabled: true})
	if err != nil {
		t.Fatal(err)
	}
	lex.ReplacementGuidance = "updated"
	if _, err = store.UpsertLexicon(ctx, scope, lex); err != nil {
		t.Fatal(err)
	}
	if got, e := store.GetLexicon(ctx, scope, lex.EntryID); e != nil || got.ReplacementGuidance != "updated" {
		t.Fatalf("lexicon read/update: %#v %v", got, e)
	}
	before, _ := store.ListChapters(ctx, scope)
	handler := NewHandler(HandlerConfig{Store: store, Actors: staticActors{Actor{UserID: liveUser, TenantID: liveTenant, ProjectID: liveProject}}, Authorizer: &testAuthorizer{err: errors.New("viewer denied driver prompt api_key")}})
	req := httptest.NewRequest(http.MethodPost, "/v1/projects/"+liveProject+"/chapters", strings.NewReader(`{"title":"viewer write"}`))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	after, _ := store.ListChapters(ctx, scope)
	if rec.Code != http.StatusForbidden || len(after) != len(before) {
		t.Fatalf("viewer mutation reached app-role store: status=%d before=%d after=%d", rec.Code, len(before), len(after))
	}
	if err = store.DeletePreset(ctx, scope, preset.PresetID); err != nil {
		t.Fatal(err)
	}
	if err = store.DeletePreset(ctx, scope, tenantPreset.PresetID); err != nil {
		t.Fatal(err)
	}
	if err = store.DeleteLexicon(ctx, scope, lex.EntryID); err != nil {
		t.Fatal(err)
	}
	other := scope
	other.TenantID = liveOtherTenant
	other.ProjectID = liveOtherProject
	list, err := store.ListChapters(ctx, other)
	if err != nil || len(list) != 0 {
		t.Fatalf("cross tenant rows visible: %#v %v", list, err)
	}
	if _, err = store.GetChapter(ctx, other, c1.ChapterID, true); ErrorCode(err) != CodeNotFound {
		t.Fatalf("cross tenant private read visible: %v", err)
	}
	assertAppRoleImmutable(t, app, `UPDATE chapter_versions SET content_text='tamper' WHERE tenant_id=$1`, liveTenant)
	assertAppRoleImmutable(t, app, `UPDATE outline_versions SET outline_text='tamper' WHERE tenant_id=$1`, liveTenant)
	assertAppRoleImmutable(t, app, `DELETE FROM book_run_events WHERE tenant_id=$1`, liveTenant)
	closed, _ := sql.Open("pgx", appURL(t, adminURL))
	closed.Close()
	_, err = NewSQLStore(closed).ListChapters(ctx, scope)
	if ErrorCode(err) != CodeQueryFailed || strings.Contains(err.Error(), "closed") {
		t.Fatalf("driver error not sanitized: %v", err)
	}
}

func assertAppRoleImmutable(t *testing.T, db *sql.DB, statement, tenantID string) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	if _, err = tx.Exec(`SELECT app_set_tenant_context($1::uuid,$2::uuid,false)`, tenantID, liveUser); err != nil {
		t.Fatal(err)
	}
	if _, err = tx.Exec(statement, tenantID); err == nil {
		t.Fatalf("app role mutated immutable writer snapshot")
	}
}

func prepareLive(t *testing.T, db *sql.DB) {
	t.Helper()
	_, _ = db.Exec(`DELETE FROM tenants WHERE tenant_id IN ($1,$2)`, liveTenant, liveOtherTenant)
	_, err := db.Exec(`DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='` + liveRole + `') THEN CREATE ROLE ` + liveRole + ` LOGIN PASSWORD '` + livePassword + `' IN ROLE mirofish_app; END IF; END $$`)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(`INSERT INTO users(user_id,email,display_name) VALUES($1,$2,'Writer Workspace Live') ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email, display_name=EXCLUDED.display_name`, liveUser, liveUserEmail); err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(`INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES($1,'writer-workspace-live','Writer Workspace','personal'),($2,'writer-workspace-other','Other','personal')`, liveTenant, liveOtherTenant); err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(`INSERT INTO projects(tenant_id,project_id,title,created_by) VALUES($1,$2,'Writer Workspace',$3),($4,$5,'Other',$3)`, liveTenant, liveProject, liveUser, liveOtherTenant, liveOtherProject); err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(`INSERT INTO workflow_runs(tenant_id,run_id,workflow_type,project_id,status,started_by) VALUES($1,$2,'book_planning',$3,'queued',$4)`, liveTenant, liveRun, liveProject, liveUser); err != nil {
		t.Fatal(err)
	}
}
func appURL(t *testing.T, raw string) string {
	u, e := url.Parse(raw)
	if e != nil {
		t.Fatal(e)
	}
	u.User = url.UserPassword(liveRole, livePassword)
	return u.String()
}
