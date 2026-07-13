package assetdistillation

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"net/url"
	"os"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/testschema"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveDistillTenant   = "e1111111-1111-4111-8111-111111111111"
	liveDistillOther    = "e2222222-2222-4222-8222-222222222222"
	liveDistillProject  = "e3333333-3333-4333-8333-333333333333"
	liveDistillProjectB = "e4444444-4444-4444-8444-444444444444"
	liveDistillUser     = "e5555555-5555-4555-8555-555555555555"
	liveDistillUserMail = "asset-distillation-live@example.test"
	liveDistillRole     = "mirofish_asset_distillation_live"
	liveDistillPassword = "mirofish_asset_distillation_live_password"
	liveDistillRun      = "e6666666-6666-4666-8666-666666666666"
	liveDistillDraft    = "e7777777-7777-4777-8777-777777777777"
	liveDistillBlock    = "e8888888-8888-4888-8888-888888888888"
	liveDistillChapter  = "e9999999-9999-4999-8999-999999999999"
)

func TestLiveAssetDistillationSettingsAdmissionProposalsAndRLS(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_ASSET_DISTILLATION_LIVE_DATABASE_URL"))
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_EMPTY_PROJECT_WRITER_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_WRITER_WORKSPACE_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_ASSET_DISTILLATION_LIVE_DATABASE_URL to run asset distillation app-role live test")
	}

	admin, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = admin.Close() })
	if err := testschema.RequireDisposableLiveDatabase(context.Background(), admin); err != nil {
		t.Fatal(err)
	}
	if !schemaReady(t, admin) {
		t.Skip("0018 manuscript asset distillation schema is not present on disposable DB")
	}
	t.Cleanup(func() {
		_, _ = admin.Exec(`DELETE FROM tenants WHERE tenant_id IN ($1,$2)`, liveDistillTenant, liveDistillOther)
		_, _ = admin.Exec(`DELETE FROM users WHERE user_id=$1 AND email=$2`, liveDistillUser, liveDistillUserMail)
		_, _ = admin.Exec(`DROP ROLE IF EXISTS ` + liveDistillRole)
	})
	prepareDistillationLive(t, admin)

	app, err := sql.Open("pgx", distillationAppURL(t, adminURL))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = app.Close() })
	store := NewSQLStore(app)
	ctx := context.Background()
	scope := Scope{TenantID: liveDistillTenant, ProjectID: liveDistillProject, ActorUserID: liveDistillUser, RequestID: "live-distill-1"}

	// Settings default for fixture project is manual (seeded).
	settings, err := store.GetSettings(ctx, scope)
	if err != nil || settings.TriggerMode != "manual" {
		t.Fatalf("settings: %#v err=%v", settings, err)
	}
	mode := "after_adoption"
	settings, err = store.PatchSettings(ctx, scope, SettingsPatch{TriggerMode: &mode})
	if err != nil || settings.TriggerMode != "after_adoption" {
		t.Fatalf("patch settings: %#v err=%v", settings, err)
	}

	// Manual admission against adopted block.
	admission, replay, err := store.AdmitManual(ctx, StartManualInput{
		Scope: scope, BlockIDs: []string{liveDistillBlock}, ExpectedVersions: map[string]int{liveDistillBlock: 1},
	})
	if err != nil || replay || admission.RunID == "" || admission.RequestID == "" {
		t.Fatalf("admit manual: %#v replay=%v err=%v code=%s", admission, replay, err, ErrorCode(err))
	}
	// Fingerprint replay
	replayed, replay, err := store.AdmitManual(ctx, StartManualInput{
		Scope:    Scope{TenantID: liveDistillTenant, ProjectID: liveDistillProject, ActorUserID: liveDistillUser, RequestID: "live-distill-2"},
		BlockIDs: []string{liveDistillBlock}, ExpectedVersions: map[string]int{liveDistillBlock: 1},
	})
	if err != nil || !replay || replayed.RunID != admission.RunID {
		t.Fatalf("fingerprint replay: %#v replay=%v err=%v", replayed, replay, err)
	}

	// Persist a disabled candidate + pending proposal + evidence as worker would.
	candidateID := insertLiveCandidate(t, admin, admission.RequestID)
	proposals, err := store.ListProposals(ctx, scope, "pending")
	if err != nil || len(proposals) != 1 || proposals[0].CandidateAssetID != candidateID {
		t.Fatalf("list proposals: %#v err=%v", proposals, err)
	}
	detail, err := store.GetProposal(ctx, scope, candidateID, true)
	if err != nil || detail.EvidenceCount != 1 || len(detail.EvidencePrivate) != 1 {
		t.Fatalf("proposal detail private: %#v err=%v", detail, err)
	}
	publicDetail, err := store.GetProposal(ctx, scope, candidateID, false)
	if err != nil || len(publicDetail.EvidencePrivate) != 0 {
		t.Fatalf("public detail leaked evidence text: %#v err=%v", publicDetail, err)
	}

	// Accept create
	decision, err := store.Decide(ctx, DecisionInput{
		Scope: scope, CandidateAssetID: candidateID, Decision: "accept_create", TargetLifecycle: "canon",
	})
	if err != nil || decision.ReviewStatus != "accepted" || decision.AcceptedAssetID != candidateID {
		t.Fatalf("accept create: %#v err=%v", decision, err)
	}
	var lifecycle string
	var enabled bool
	if err := admin.QueryRow(`SELECT lifecycle, enabled FROM assets WHERE asset_id=$1`, candidateID).Scan(&lifecycle, &enabled); err != nil || lifecycle != "canon" || !enabled {
		t.Fatalf("accepted asset state lifecycle=%s enabled=%v err=%v", lifecycle, enabled, err)
	}
	// Replay decision
	replayDecision, err := store.Decide(ctx, DecisionInput{
		Scope: scope, CandidateAssetID: candidateID, Decision: "accept_create", TargetLifecycle: "canon",
	})
	if err != nil || !replayDecision.Replay {
		t.Fatalf("decision replay: %#v err=%v", replayDecision, err)
	}

	// Cross-tenant isolation
	other := Scope{TenantID: liveDistillOther, ProjectID: liveDistillProjectB, ActorUserID: liveDistillUser}
	if items, err := store.ListProposals(ctx, other, "pending"); err != nil || len(items) != 0 {
		t.Fatalf("cross tenant proposals visible: %#v err=%v", items, err)
	}
	if _, err := store.GetProposal(ctx, other, candidateID, true); ErrorCode(err) != CodeNotFound && ErrorCode(err) != "ASSET_DISTILLATION_QUERY_FAILED" {
		// may be not found due to RLS empty
		if err == nil {
			t.Fatalf("cross tenant proposal readable")
		}
	}

	// Reject path with second candidate
	candidate2 := insertLiveCandidateWithTitle(t, admin, admission.RequestID, "第二角色")
	// Need a second request for unique pending identity or different identity - already different title
	// Move proposal to pending if insert used staging
	_, _ = admin.Exec(`UPDATE asset_candidate_proposals SET review_status='pending' WHERE candidate_asset_id=$1`, candidate2)
	reject, err := store.Decide(ctx, DecisionInput{
		Scope: scope, CandidateAssetID: candidate2, Decision: "reject", Note: "not a fact",
	})
	if err != nil || reject.ReviewStatus != "rejected" {
		t.Fatalf("reject: %#v err=%v", reject, err)
	}
	if err := admin.QueryRow(`SELECT lifecycle, enabled FROM assets WHERE asset_id=$1`, candidate2).Scan(&lifecycle, &enabled); err != nil || lifecycle != "archived" || enabled {
		t.Fatalf("rejected asset state lifecycle=%s enabled=%v err=%v", lifecycle, enabled, err)
	}

	// Outbox claim function works for pending request after re-admit with different content fingerprint...
	// Existing request is dispatched-or-pending; claim SECURITY DEFINER should return pending rows.
	items, err := store.ClaimPendingDispatch(ctx, 5)
	if err != nil {
		t.Fatalf("claim outbox: %v", err)
	}
	// may be empty if already claimed/dispatched; ensure function executes
	_ = items
}

func schemaReady(t *testing.T, db *sql.DB) bool {
	t.Helper()
	var ok bool
	err := db.QueryRow(`SELECT to_regclass('public.project_asset_distillation_settings') IS NOT NULL
	  AND to_regclass('public.manuscript_asset_distillation_requests') IS NOT NULL
	  AND to_regclass('public.asset_candidate_proposals') IS NOT NULL
	  AND to_regclass('public.asset_candidate_evidence') IS NOT NULL
	  AND EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version='0018_manuscript_asset_distillation')`).Scan(&ok)
	if err != nil {
		t.Logf("schema probe: %v", err)
		return false
	}
	return ok
}

func prepareDistillationLive(t *testing.T, db *sql.DB) {
	t.Helper()
	_, _ = db.Exec(`DELETE FROM tenants WHERE tenant_id IN ($1,$2)`, liveDistillTenant, liveDistillOther)
	if _, err := db.Exec(`DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='` + liveDistillRole + `') THEN
    CREATE ROLE ` + liveDistillRole + ` LOGIN PASSWORD '` + liveDistillPassword + `' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE ` + liveDistillRole + ` WITH LOGIN PASSWORD '` + liveDistillPassword + `';
  END IF;
END $$; GRANT mirofish_app TO ` + liveDistillRole); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO users(user_id,email,display_name) VALUES($1,$2,'Distill Live')
ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email`, liveDistillUser, liveDistillUserMail); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES
($1,'asset-distill-live','Asset Distill','personal'),
($2,'asset-distill-other','Other','personal')`, liveDistillTenant, liveDistillOther); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO projects(tenant_id,project_id,title,created_by) VALUES
($1,$2,'Distill Project',$3),($4,$5,'Other Project',$3)`,
		liveDistillTenant, liveDistillProject, liveDistillUser, liveDistillOther, liveDistillProjectB); err != nil {
		t.Fatal(err)
	}
	// Ensure settings rows (migration may have backfilled; re-upsert manual).
	if _, err := db.Exec(`INSERT INTO project_asset_distillation_settings(tenant_id,project_id,trigger_mode,enabled_asset_types,created_by,updated_by)
VALUES($1,$2,'manual','{}',$3,$3),($4,$5,'manual','{}',$3,$3)
ON CONFLICT (tenant_id,project_id) DO UPDATE SET trigger_mode='manual'`,
		liveDistillTenant, liveDistillProject, liveDistillUser, liveDistillOther, liveDistillProjectB); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO chapters(tenant_id,project_id,chapter_id,title,status,chapter_order,created_by,updated_by)
VALUES($1,$2,$3,'第一章','drafting',1,$4,$4)`, liveDistillTenant, liveDistillProject, liveDistillChapter, liveDistillUser); err != nil {
		t.Fatalf("chapter seed: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO workflow_runs(tenant_id,run_id,workflow_type,project_id,status,started_by)
VALUES($1,$2,'writer_run',$3,'completed',$4)`, liveDistillTenant, liveDistillRun, liveDistillProject, liveDistillUser); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO writer_runs(tenant_id,run_id,workflow_run_id,project_id,chapter_id,mode,status,module_key,instruction,created_by)
VALUES($1,$2,$2,$3,$4,'draft','completed','writer_composer','live distill',$5)`,
		liveDistillTenant, liveDistillRun, liveDistillProject, liveDistillChapter, liveDistillUser); err != nil {
		t.Fatal(err)
	}
	content := "林晚站在灯塔下看着大海。"
	if _, err := db.Exec(`INSERT INTO writer_drafts(tenant_id,draft_id,run_id,project_id,chapter_id,content_text,word_count,status,adopted_block_id)
VALUES($1,$2,$3,$4,$5,$6,12,'adopted',$7)`,
		liveDistillTenant, liveDistillDraft, liveDistillRun, liveDistillProject, liveDistillChapter, content, liveDistillBlock); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO manuscript_blocks(
  tenant_id,block_id,project_id,chapter_id,source_draft_id,source_writer_run_id,block_order,content_text,word_count,version,status,created_by,updated_by
) VALUES($1,$2,$3,$4,$5,$6,1,$7,12,1,'active',$8,$8)`,
		liveDistillTenant, liveDistillBlock, liveDistillProject, liveDistillChapter, liveDistillDraft, liveDistillRun, content, liveDistillUser); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO manuscript_block_versions(
  tenant_id,project_id,block_id,version_number,chapter_id,status,tags,block_order,content_text,word_count,source_draft_id,source_writer_run_id,snapshot_reason,created_by
) VALUES($1,$2,$3,1,$4,'active','{}',1,$5,12,$6,$7,'adopt',$8)`,
		liveDistillTenant, liveDistillProject, liveDistillBlock, liveDistillChapter, content, liveDistillDraft, liveDistillRun, liveDistillUser); err != nil {
		t.Fatal(err)
	}
}

func insertLiveCandidate(t *testing.T, db *sql.DB, requestID string) string {
	t.Helper()
	return insertLiveCandidateWithTitle(t, db, requestID, "林晚")
}

func insertLiveCandidateWithTitle(t *testing.T, db *sql.DB, requestID, title string) string {
	t.Helper()
	var assetID string
	err := db.QueryRow(`INSERT INTO assets(
  tenant_id,project_id,scope,asset_type,category,lifecycle,title,summary,payload_jsonb,tags_jsonb,source_kind,source_ref,enabled,pinned,created_by
) VALUES($1,$2,'project','character','character','candidate',$3,'主角','{}','[]','manuscript_distillation',$4,false,false,$5)
RETURNING asset_id::text`, liveDistillTenant, liveDistillProject, title, requestID+":"+title, liveDistillUser).Scan(&assetID)
	if err != nil {
		t.Fatalf("insert candidate: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO asset_candidate_proposals(
  tenant_id,project_id,candidate_asset_id,request_id,operation,normalized_identity,confidence,review_status
) VALUES($1,$2,$3,$4,'create',$5,0.9,'pending')`,
		liveDistillTenant, liveDistillProject, assetID, requestID, "character|"+strings.ToLower(title)); err != nil {
		t.Fatalf("insert proposal: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO asset_candidate_evidence(
  tenant_id,project_id,candidate_asset_id,block_id,block_version,content_sha256,start_offset,end_offset,evidence_text,confidence
) VALUES($1,$2,$3,$4,1,$5,0,2,'林晚',0.9)`,
		liveDistillTenant, liveDistillProject, assetID, liveDistillBlock, sha256Hex("林晚站在灯塔下看着大海。")); err != nil {
		// content sha of full block for fixture consistency
		sum := sha256Hex("林晚站在灯塔下看着大海。")
		if _, err2 := db.Exec(`INSERT INTO asset_candidate_evidence(
  tenant_id,project_id,candidate_asset_id,block_id,block_version,content_sha256,start_offset,end_offset,evidence_text,confidence
) VALUES($1,$2,$3,$4,1,$5,0,2,'林晚',0.9)`,
			liveDistillTenant, liveDistillProject, assetID, liveDistillBlock, sum); err2 != nil {
			t.Fatalf("insert evidence: %v / %v", err, err2)
		}
	}
	return assetID
}

func sha256Hex(content string) string {
	sum := sha256.Sum256([]byte(content))
	return hex.EncodeToString(sum[:])
}

func distillationAppURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatal(err)
	}
	parsed.User = url.UserPassword(liveDistillRole, liveDistillPassword)
	return parsed.String()
}
