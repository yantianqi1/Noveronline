package manuscriptworkspace

import (
	"context"
	"database/sql"
	"errors"
	"net/url"
	"os"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveTenantID  = "b1111111-1111-4111-8111-111111111111"
	liveUserID    = "b2222222-2222-4222-8222-222222222222"
	liveProjectID = "b3333333-3333-4333-8333-333333333333"
	liveChapter1  = "b4111111-1111-4111-8111-111111111111"
	liveChapter2  = "b4222222-2222-4222-8222-222222222222"
	liveScene1    = "b5111111-1111-4111-8111-111111111111"
	liveScene2    = "b5222222-2222-4222-8222-222222222222"
	liveSourceRun = "b6111111-1111-4111-8111-111111111111"
	liveDraft1    = "b7111111-1111-4111-8111-111111111111"
	liveDraft2    = "b7222222-2222-4222-8222-222222222222"
	liveBlock1    = "b8111111-1111-4111-8111-111111111111"
	liveBlock2    = "b8222222-2222-4222-8222-222222222222"
	liveLexicon   = "b9111111-1111-4111-8111-111111111111"
	liveRole      = "mirofish_manuscript_workspace_live"
	livePassword  = "mirofish_manuscript_workspace_live_password"
)

func TestLiveManuscriptWorkspaceAppRoleLifecycle(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_MANUSCRIPT_WORKSPACE_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_MANUSCRIPT_WORKSPACE_LIVE_DATABASE_URL to run app-role Manuscript Workspace live test")
	}
	admin := openLiveDB(t, adminURL)
	prepareManuscriptLive(t, admin)
	t.Cleanup(func() {
		cleanupManuscriptLive(t, admin)
		admin.Close()
	})
	app := openLiveDB(t, manuscriptLiveAppURL(t, adminURL))
	defer app.Close()
	store := NewSQLStore(app)
	ctx := context.Background()
	scope := liveScope("lifecycle-1")
	assertLiveBlockVisible(t, app)

	original, err := store.GetPrivateBlock(ctx, scope, liveBlock1)
	if err != nil || original.ContentText != "Original forbidden prose" || original.SourceDraftID != liveDraft1 {
		t.Fatalf("adopted block read: %#v err=%v", original, err)
	}
	newContent := "Updated forbidden prose"
	updated, err := store.UpdateBlock(ctx, UpdateBlockInput{
		Scope: scope, BlockID: liveBlock1, ExpectedVersion: 1, ContentText: &newContent,
	})
	if err != nil || updated.Version != 2 || updated.WordCount == 0 {
		t.Fatalf("update block: %#v err=%v", updated, err)
	}
	if _, err := store.UpdateBlock(ctx, UpdateBlockInput{
		Scope: liveScope("stale"), BlockID: liveBlock1, ExpectedVersion: 1, ContentText: &newContent,
	}); ErrorCode(err) != "OPTIMISTIC_CONFLICT" {
		t.Fatalf("stale update must conflict: %v", err)
	}
	versions, err := store.ListVersions(ctx, scope, liveBlock1)
	if err != nil || len(versions) != 2 {
		t.Fatalf("immutable versions: %#v err=%v", versions, err)
	}
	assertImmutableVersionTrigger(t, app)

	assertConcurrentBlockConflict(t, store)
	blocks, err := store.ListBlocks(ctx, scope, false)
	if err != nil || len(blocks) != 2 {
		t.Fatalf("list active blocks: %#v err=%v", blocks, err)
	}
	items := []ReorderItem{
		{BlockID: liveBlock2, ExpectedVersion: versionFor(blocks, liveBlock2)},
		{BlockID: liveBlock1, ExpectedVersion: versionFor(blocks, liveBlock1)},
	}
	moved, err := store.MoveBlock(ctx, MoveBlockInput{
		Scope: liveScope("move"), BlockID: liveBlock1,
		ExpectedVersion: versionFor(blocks, liveBlock1), ChapterID: liveChapter2, Items: items,
	})
	if err != nil || moved[0].BlockID != liveBlock2 || blockFor(moved, liveBlock1).ChapterID != liveChapter2 {
		t.Fatalf("atomic move/reorder: %#v err=%v", moved, err)
	}
	badItems := append([]ReorderItem(nil), items[:1]...)
	if _, err := store.ReorderBlocks(ctx, ReorderBlocksInput{Scope: liveScope("bad-reorder"), Items: badItems}); ErrorCode(err) != "MANUSCRIPT_REORDER_SET_MISMATCH" {
		t.Fatalf("incomplete reorder accepted: %v", err)
	}
	unchanged, _ := store.ListBlocks(ctx, scope, false)
	if unchanged[0].BlockID != liveBlock2 {
		t.Fatalf("failed reorder changed state: %#v", unchanged)
	}
	tags := []string{"climax", "review"}
	current := blockFor(unchanged, liveBlock1)
	taggedMetadata, err := store.TagBlock(ctx, TagBlockInput{
		Scope: liveScope("tag"), BlockID: liveBlock1, ExpectedVersion: current.Version, Tags: tags,
	})
	if err != nil || len(taggedMetadata.Tags) != 2 {
		t.Fatalf("tag block: %#v err=%v", taggedMetadata, err)
	}
	tagged, err := store.GetPrivateBlock(ctx, scope, liveBlock1)
	if err != nil {
		t.Fatal(err)
	}
	originalVersion := versionNumber(versions, 1)
	restored, err := store.RestoreVersion(ctx, RestoreBlockInput{
		Scope: liveScope("restore"), BlockID: liveBlock1,
		VersionID: originalVersion.VersionID, ExpectedVersion: tagged.Version,
	})
	if err != nil || restored.ContentText != "Original forbidden prose" || restored.Version <= tagged.Version {
		t.Fatalf("restore creates new state: %#v err=%v", restored, err)
	}
	afterRestoreVersions, _ := store.ListVersions(ctx, scope, liveBlock1)
	if len(afterRestoreVersions) < 5 || afterRestoreVersions[0].RestoredFromVersionID != originalVersion.VersionID {
		t.Fatalf("restore lineage missing: %#v", afterRestoreVersions)
	}

	block2 := blockFor(unchanged, liveBlock2)
	deleted, err := store.DeleteBlock(ctx, DeleteBlockInput{
		Scope: liveScope("delete"), BlockID: liveBlock2, ExpectedVersion: block2.Version,
	})
	if err != nil || deleted.Status != "deleted" {
		t.Fatalf("soft delete: %#v err=%v", deleted, err)
	}
	active, _ := store.ListBlocks(ctx, scope, false)
	all, _ := store.ListBlocks(ctx, scope, true)
	if len(active) != 1 || len(all) != 2 || blockFor(all, liveBlock2).SourceDraftID != liveDraft2 {
		t.Fatalf("delete provenance boundary active=%#v all=%#v", active, all)
	}

	starter := &liveStarter{db: app}
	assertLexiconQueryWorks(t, app)
	commands := NewCommandService(store, starter, starter)
	outline, err := commands.Admit(ctx, CommandInput{
		Scope: liveScope("outline-command"), CommandType: CommandCompleteOutline, TargetChapterID: liveChapter1,
	})
	if err != nil || outline.Run.Status != "queued" || outline.Run.CandidateKind != "outline" || starter.workflowCalls != 1 {
		t.Fatalf("outline admission: %#v err=%v", outline, err)
	}
	replay, err := commands.Admit(ctx, CommandInput{
		Scope: liveScope("outline-command"), CommandType: CommandCompleteOutline, TargetChapterID: liveChapter1,
	})
	if err != nil || !replay.Replay || starter.workflowCalls != 1 {
		t.Fatalf("command replay started twice: %#v calls=%d err=%v", replay, starter.workflowCalls, err)
	}
	continued, err := commands.Admit(ctx, CommandInput{
		Scope: liveScope("continue-command"), CommandType: CommandContinueChapter, TargetChapterID: liveChapter1,
	})
	if err != nil || continued.Run.CandidateKind != "draft" || starter.writerCalls != 1 {
		t.Fatalf("continue admission: %#v err=%v starter=%v", continued, err, starter.lastError)
	}
	aligned, err := commands.Admit(ctx, CommandInput{
		Scope: liveScope("align-command"), CommandType: CommandAlignWords,
		TargetBlockID: liveBlock1, Options: map[string]any{"target_words": 1200},
	})
	if err != nil || aligned.Run.CandidateKind != "prose" || starter.writerCalls != 2 {
		t.Fatalf("align admission: %#v err=%v", aligned, err)
	}
	relations, err := commands.Admit(ctx, CommandInput{
		Scope: liveScope("relationships-command"), CommandType: CommandFillRelationships, TargetChapterID: liveChapter1,
	})
	if err != nil || relations.Run.CandidateKind != "relationship" || starter.workflowCalls != 2 {
		t.Fatalf("relationship admission: %#v err=%v", relations, err)
	}
	scan, err := commands.Admit(ctx, CommandInput{Scope: liveScope("scan-command"), CommandType: CommandScanLexicon})
	if err != nil || scan.Run.Status != "completed" || scan.Run.MatchCount != 1 || len(scan.Matches) != 1 {
		t.Fatalf("deterministic lexicon scan: %#v err=%v cause=%v", scan, err, errors.Unwrap(err))
	}
	failing := NewCommandService(store, &liveStarter{db: app, fail: true}, nil)
	if _, err := failing.Admit(ctx, CommandInput{
		Scope: liveScope("failed-command"), CommandType: CommandContinueChapter, TargetChapterID: liveChapter1,
	}); ErrorCode(err) != "COMMAND_START_FAILED" {
		t.Fatalf("failed start was not surfaced: %v", err)
	}
	failed := commandByRequest(t, admin, "failed-command")
	if failed != "failed" {
		t.Fatalf("failed start left command status %q", failed)
	}
	assertNoAutomaticAdoption(t, admin)

	export, replayExport, err := store.CreateExport(ctx, CreateExportInput{Scope: liveScope("export-1"), Format: "txt"})
	if err != nil || replayExport || export.Status != "queued" || export.ArtifactSHA256 != "" {
		t.Fatalf("queued export state: %#v replay=%v err=%v", export, replayExport, err)
	}
	if _, err := store.CompleteExport(ctx, CompleteExportInput{
		Scope: liveScope("export-complete-bad"), ExportID: export.ExportID,
	}); ErrorCode(err) != "VALIDATION_FAILED" {
		t.Fatalf("artifact-less export completed: %v", err)
	}
	completed, err := store.CompleteExport(ctx, CompleteExportInput{
		Scope: liveScope("export-complete"), ExportID: export.ExportID,
		ArtifactSHA256: strings.Repeat("a", 64), ArtifactSizeBytes: 128,
		ArtifactObjectRef: "manuscripts/live/export.txt", BlockCount: 1,
	})
	if err != nil || completed.Status != "completed" || completed.ArtifactObjectRef == "" {
		t.Fatalf("real artifact completion: %#v err=%v", completed, err)
	}

	pattern, replayPattern, err := store.CreateDedupCandidate(ctx, CreateDedupCandidateInput{
		Scope: scope, PatternText: "At that exact moment", PatternKind: "transition", OccurrenceCount: 3,
		SourceCommandRunID: outline.Run.CommandRunID, SourceWorkflowRunID: outline.Run.WorkflowRunID,
	})
	if err != nil || replayPattern || pattern.Lifecycle != "candidate" || pattern.Enabled {
		t.Fatalf("dedup candidate boundary: %#v replay=%v err=%v", pattern, replayPattern, err)
	}
	accepted, err := store.ReviewDedupPattern(ctx, ReviewDedupPatternInput{
		Scope: liveScope("dedup-accept"), PatternID: pattern.PatternID, Decision: "accepted",
	})
	if err != nil || accepted.Lifecycle != "accepted" || !accepted.Enabled {
		t.Fatalf("explicit dedup accept: %#v err=%v", accepted, err)
	}

	crossTenant := Scope{TenantID: "b0000000-0000-4000-8000-000000000000", ProjectID: liveProjectID, ActorUserID: liveUserID}
	visible, err := store.ListBlocks(ctx, crossTenant, true)
	if err != nil || len(visible) != 0 {
		t.Fatalf("cross-tenant rows visible: %#v err=%v", visible, err)
	}
}

func assertLexiconQueryWorks(t *testing.T, db *sql.DB) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec("SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", liveTenantID, liveUserID); err != nil {
		t.Fatal(err)
	}
	var entryID, blockID, term string
	var count int
	err = tx.QueryRow(`SELECT lexicon.lexicon_entry_id::text, block.block_id::text, lexicon.term,
  (length(lower(block.content_text)) - length(replace(lower(block.content_text), lower(lexicon.term), ''))) / NULLIF(length(lexicon.term), 0)
FROM forbidden_lexicon_entries AS lexicon
JOIN manuscript_blocks AS block ON block.tenant_id = lexicon.tenant_id AND block.project_id = lexicon.project_id
WHERE lexicon.tenant_id = $1 AND lexicon.project_id = $2 AND lexicon.enabled = TRUE
  AND block.status = 'active' AND position(lower(lexicon.term) in lower(block.content_text)) > 0
LIMIT 1`, liveTenantID, liveProjectID).Scan(&entryID, &blockID, &term, &count)
	if err != nil || count != 1 {
		t.Fatalf("raw lexicon query failed count=%d err=%v", count, err)
	}
}

func assertLiveBlockVisible(t *testing.T, db *sql.DB) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec("SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", liveTenantID, liveUserID); err != nil {
		t.Fatalf("set live tenant context: %v", err)
	}
	var count int
	if err := tx.QueryRow(`SELECT count(*) FROM manuscript_blocks WHERE tenant_id = $1 AND project_id = $2`, liveTenantID, liveProjectID).Scan(&count); err != nil {
		t.Fatalf("count live manuscript blocks: %v", err)
	}
	if count != 2 {
		t.Fatalf("app role sees %d manuscript blocks, want 2", count)
	}
}

type liveStarter struct {
	db            *sql.DB
	fail          bool
	mu            sync.Mutex
	writerCalls   int
	workflowCalls int
	lastError     error
}

func (s *liveStarter) StartWriter(ctx context.Context, input WriterStartInput) (StartedRun, error) {
	s.mu.Lock()
	s.writerCalls++
	s.mu.Unlock()
	if s.fail {
		return StartedRun{}, errors.New("private writer start error")
	}
	runID := uuid.NewString()
	tx, err := s.scopedTx(ctx, input)
	if err != nil {
		s.lastError = err
		return StartedRun{}, err
	}
	defer tx.Rollback()
	mode := "continue"
	if input.CommandType == CommandAlignWords {
		mode = "draft"
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO writer_runs (
  tenant_id, run_id, project_id, chapter_id, scene_id, mode, status,
  instruction, options_jsonb, created_by
) VALUES ($1::uuid, $2::uuid, $3::uuid, NULLIF($4, '')::uuid, NULLIF($5, '')::uuid,
  $6, 'queued', 'candidate-only one-click command', jsonb_build_object('candidate_only', true, 'command_run_id', $7::text), $8::uuid)`,
		input.TenantID, runID, input.ProjectID, input.TargetChapterID, input.TargetSceneID,
		mode, input.CommandRunID, input.ActorUserID)
	if err != nil {
		s.lastError = err
		return StartedRun{}, err
	}
	if err := tx.Commit(); err != nil {
		s.lastError = err
		return StartedRun{}, err
	}
	return StartedRun{RunID: runID}, nil
}

func (s *liveStarter) StartWorkflow(ctx context.Context, input WorkflowStartInput) (StartedRun, error) {
	s.mu.Lock()
	s.workflowCalls++
	s.mu.Unlock()
	if s.fail {
		return StartedRun{}, errors.New("private workflow start error")
	}
	runID := uuid.NewString()
	tx, err := s.scopedTx(ctx, input)
	if err != nil {
		return StartedRun{}, err
	}
	defer tx.Rollback()
	_, err = tx.ExecContext(ctx, `INSERT INTO workflow_runs (
  tenant_id, run_id, workflow_type, project_id, status, progress, message, started_by
) VALUES ($1::uuid, $2::uuid, $3, $4::uuid, 'queued', 0, 'candidate-only one-click command', $5::uuid)`,
		input.TenantID, runID, "writer_"+input.CandidateKind+"_candidate", input.ProjectID, input.ActorUserID)
	if err != nil {
		return StartedRun{}, err
	}
	if err := tx.Commit(); err != nil {
		return StartedRun{}, err
	}
	return StartedRun{RunID: runID}, nil
}

func (s *liveStarter) scopedTx(ctx context.Context, input WriterStartInput) (*sql.Tx, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		tx.Rollback()
		return nil, err
	}
	return tx, nil
}

func prepareManuscriptLive(t *testing.T, db *sql.DB) {
	t.Helper()
	cleanupManuscriptLive(t, db)
	statements := []string{
		`DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '` + liveRole + `') THEN CREATE ROLE ` + liveRole + ` LOGIN PASSWORD '` + livePassword + `' IN ROLE mirofish_app; ELSE ALTER ROLE ` + liveRole + ` WITH LOGIN PASSWORD '` + livePassword + `'; GRANT mirofish_app TO ` + liveRole + `; END IF; END $$`,
		`INSERT INTO users (user_id, email, display_name) VALUES ('` + liveUserID + `', 'manuscript-workspace-live@example.invalid', 'Manuscript Live')`,
		`INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES ('` + liveTenantID + `', 'manuscript-workspace-live', 'Manuscript Live', 'personal')`,
		`INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES ('` + liveTenantID + `', '` + liveProjectID + `', 'Manuscript Live', '` + liveUserID + `')`,
		`INSERT INTO chapters (tenant_id, project_id, chapter_id, chapter_order, title, created_by) VALUES ('` + liveTenantID + `', '` + liveProjectID + `', '` + liveChapter1 + `', 1, 'Chapter One', '` + liveUserID + `'), ('` + liveTenantID + `', '` + liveProjectID + `', '` + liveChapter2 + `', 2, 'Chapter Two', '` + liveUserID + `')`,
		`INSERT INTO scenes (tenant_id, project_id, scene_id, chapter_id, scene_order, title, created_by) VALUES ('` + liveTenantID + `', '` + liveProjectID + `', '` + liveScene1 + `', '` + liveChapter1 + `', 1, 'Scene One', '` + liveUserID + `'), ('` + liveTenantID + `', '` + liveProjectID + `', '` + liveScene2 + `', '` + liveChapter1 + `', 2, 'Scene Two', '` + liveUserID + `')`,
		`INSERT INTO writer_runs (tenant_id, run_id, project_id, chapter_id, mode, status, instruction, created_by) VALUES ('` + liveTenantID + `', '` + liveSourceRun + `', '` + liveProjectID + `', '` + liveChapter1 + `', 'draft', 'completed', 'fixture', '` + liveUserID + `')`,
		`INSERT INTO writer_drafts (tenant_id, draft_id, run_id, project_id, chapter_id, scene_id, content_text, word_count, status) VALUES ('` + liveTenantID + `', '` + liveDraft1 + `', '` + liveSourceRun + `', '` + liveProjectID + `', '` + liveChapter1 + `', '` + liveScene1 + `', 'Original forbidden prose', 3, 'candidate'), ('` + liveTenantID + `', '` + liveDraft2 + `', '` + liveSourceRun + `', '` + liveProjectID + `', '` + liveChapter1 + `', '` + liveScene2 + `', 'Second block', 2, 'candidate')`,
		`INSERT INTO manuscript_blocks (tenant_id, block_id, project_id, chapter_id, scene_id, source_draft_id, source_writer_run_id, block_order, content_text, word_count, created_by, updated_by) VALUES ('` + liveTenantID + `', '` + liveBlock1 + `', '` + liveProjectID + `', '` + liveChapter1 + `', '` + liveScene1 + `', '` + liveDraft1 + `', '` + liveSourceRun + `', 1, 'Original forbidden prose', 3, '` + liveUserID + `', '` + liveUserID + `'), ('` + liveTenantID + `', '` + liveBlock2 + `', '` + liveProjectID + `', '` + liveChapter1 + `', '` + liveScene2 + `', '` + liveDraft2 + `', '` + liveSourceRun + `', 2, 'Second block', 2, '` + liveUserID + `', '` + liveUserID + `')`,
		`UPDATE writer_drafts SET status = 'adopted', adopted_block_id = CASE draft_id WHEN '` + liveDraft1 + `' THEN '` + liveBlock1 + `'::uuid ELSE '` + liveBlock2 + `'::uuid END WHERE tenant_id = '` + liveTenantID + `'::uuid`,
		`INSERT INTO forbidden_lexicon_entries (tenant_id, project_id, lexicon_entry_id, term, category, severity, enabled, created_by) VALUES ('` + liveTenantID + `', '` + liveProjectID + `', '` + liveLexicon + `', 'forbidden', 'style', 'warning', true, '` + liveUserID + `')`,
	}
	for _, statement := range statements {
		if _, err := db.Exec(statement); err != nil {
			t.Fatalf("prepare manuscript live fixture: %v", err)
		}
	}
}

func cleanupManuscriptLive(t *testing.T, db *sql.DB) {
	t.Helper()
	_, _ = db.Exec(`DELETE FROM tenants WHERE tenant_id = $1`, liveTenantID)
	_, _ = db.Exec(`DELETE FROM users WHERE user_id = $1`, liveUserID)
}

func openLiveDB(t *testing.T, databaseURL string) *sql.DB {
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

func manuscriptLiveAppURL(t *testing.T, raw string) string {
	t.Helper()
	parsed, err := url.Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	parsed.User = url.UserPassword(liveRole, livePassword)
	return parsed.String()
}

func liveScope(requestID string) Scope {
	return Scope{TenantID: liveTenantID, ProjectID: liveProjectID, ActorUserID: liveUserID, RequestID: requestID}
}

func versionFor(blocks []BlockMetadata, blockID string) int { return blockFor(blocks, blockID).Version }
func blockFor(blocks []BlockMetadata, blockID string) BlockMetadata {
	for _, block := range blocks {
		if block.BlockID == blockID {
			return block
		}
	}
	return BlockMetadata{}
}
func versionNumber(versions []BlockVersion, number int) BlockVersion {
	for _, version := range versions {
		if version.VersionNumber == number {
			return version
		}
	}
	return BlockVersion{}
}

func assertConcurrentBlockConflict(t *testing.T, store *SQLStore) {
	t.Helper()
	results := make(chan error, 2)
	var wg sync.WaitGroup
	for index := range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			content := "concurrent content"
			_, err := store.UpdateBlock(context.Background(), UpdateBlockInput{
				Scope: liveScope("concurrent-" + string(rune('a'+index))), BlockID: liveBlock2,
				ExpectedVersion: 1, ContentText: &content,
			})
			results <- err
		}()
	}
	wg.Wait()
	close(results)
	success, conflict := 0, 0
	for err := range results {
		if err == nil {
			success++
		} else if ErrorCode(err) == "OPTIMISTIC_CONFLICT" {
			conflict++
		} else {
			t.Fatalf("unexpected concurrent error: %v", err)
		}
	}
	if success != 1 || conflict != 1 {
		t.Fatalf("concurrent result success=%d conflict=%d", success, conflict)
	}
}

func assertImmutableVersionTrigger(t *testing.T, db *sql.DB) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec("SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", liveTenantID, liveUserID); err != nil {
		t.Fatal(err)
	}
	if _, err := tx.Exec(`UPDATE manuscript_block_versions SET word_count = word_count + 1 WHERE tenant_id = $1 AND block_id = $2`, liveTenantID, liveBlock1); err == nil {
		t.Fatal("immutable version update succeeded")
	}
}

func commandByRequest(t *testing.T, db *sql.DB, requestID string) string {
	t.Helper()
	var status string
	if err := db.QueryRow(`SELECT status FROM writer_command_runs WHERE tenant_id = $1 AND request_id = $2`, liveTenantID, requestID).Scan(&status); err != nil {
		t.Fatal(err)
	}
	return status
}

func assertNoAutomaticAdoption(t *testing.T, db *sql.DB) {
	t.Helper()
	var drafts, blocks, canonAssets int
	if err := db.QueryRow(`SELECT count(*) FROM writer_drafts WHERE tenant_id = $1`, liveTenantID).Scan(&drafts); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM manuscript_blocks WHERE tenant_id = $1`, liveTenantID).Scan(&blocks); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM assets WHERE tenant_id = $1 AND lifecycle = 'canon'`, liveTenantID).Scan(&canonAssets); err != nil {
		t.Fatal(err)
	}
	if drafts != 2 || blocks != 2 || canonAssets != 0 {
		t.Fatalf("command auto-adopted state drafts=%d blocks=%d canon=%d", drafts, blocks, canonAssets)
	}
}
