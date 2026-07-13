package characterconsole

import (
	"context"
	"database/sql"
	"errors"
	"net/url"
	"os"
	"sync"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	proposalLiveTenantID      = "91111111-1111-4111-8111-111111111111"
	proposalLiveUserID        = "92222222-2222-4222-8222-222222222222"
	proposalLiveProjectID     = "93333333-3333-4333-8333-333333333333"
	proposalLiveRunID         = "94444444-4444-4444-8444-444444444444"
	proposalLiveSessionID     = "95555555-5555-4555-8555-555555555555"
	proposalLiveInteraction   = "96666666-6666-4666-8666-666666666666"
	proposalLiveMemoryAsset   = "97111111-1111-4711-8711-111111111111"
	proposalLiveRelationAsset = "97222222-2222-4722-8722-222222222222"
	proposalLiveWorldAsset    = "97333333-3333-4733-8733-333333333333"
	proposalLiveRaceAsset     = "97444444-4444-4744-8744-444444444444"
	proposalLiveMemoryID      = "98111111-1111-4811-8811-111111111111"
	proposalLiveWorldEventID  = "98222222-2222-4822-8822-222222222222"
	proposalLiveRole          = "mirofish_character_proposal_live_app"
	proposalLivePassword      = "mirofish_character_proposal_live_password"
)

func TestLiveCharacterProposalAdoptionMaterializesDomainTargetsAtomically(t *testing.T) {
	adminURL := os.Getenv("MIROFISH_CHARACTER_PROPOSAL_LIVE_DATABASE_URL")
	if adminURL == "" {
		t.Skip("set MIROFISH_CHARACTER_PROPOSAL_LIVE_DATABASE_URL to run Character proposal live test")
	}
	admin := openProposalLiveDB(t, adminURL)
	cleanupProposalLive(t, admin)
	prepareProposalLive(t, admin)
	t.Cleanup(func() {
		cleanupProposalLive(t, admin)
		admin.Close()
	})

	app := openProposalLiveDB(t, proposalLiveAppURL(t, adminURL))
	store := NewSQLProposalStore(app, 100)
	ctx := context.Background()
	proposals, err := store.ListProposals(ctx, ListProposalsInput{
		TenantID: proposalLiveTenantID, ProjectID: proposalLiveProjectID,
		InteractionID: proposalLiveInteraction, ActorUserID: proposalLiveUserID,
	})
	if err != nil || len(proposals) != 4 {
		t.Fatalf("list live proposals: count=%d err=%v", len(proposals), err)
	}

	for _, assetID := range []string{proposalLiveMemoryAsset, proposalLiveRelationAsset, proposalLiveWorldAsset} {
		result, err := store.AdoptProposal(ctx, AdoptProposalInput{
			TenantID: proposalLiveTenantID, ProjectID: proposalLiveProjectID,
			InteractionID: proposalLiveInteraction, AssetID: assetID,
			ActorUserID: proposalLiveUserID, RequestID: "proposal-live-" + assetID,
			Note: "accepted in live verification",
		})
		if err != nil || result.Status != "adopted" || result.TargetID == "" {
			t.Fatalf("adopt proposal %s: result=%#v err=%v", assetID, result, err)
		}
	}
	if _, err := store.AdoptProposal(ctx, AdoptProposalInput{
		TenantID: proposalLiveTenantID, ProjectID: proposalLiveProjectID,
		InteractionID: "99999999-9999-4999-8999-999999999999", AssetID: proposalLiveRaceAsset,
		ActorUserID: proposalLiveUserID,
	}); ErrorCode(err) != "NOT_FOUND" {
		t.Fatalf("cross-interaction proposal lookup must fail closed, got %v", err)
	}

	results := make(chan error, 2)
	var wg sync.WaitGroup
	for index := 0; index < 2; index++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := store.AdoptProposal(ctx, AdoptProposalInput{
				TenantID: proposalLiveTenantID, ProjectID: proposalLiveProjectID,
				InteractionID: proposalLiveInteraction, AssetID: proposalLiveRaceAsset,
				ActorUserID: proposalLiveUserID, RequestID: "proposal-live-race",
			})
			results <- err
		}()
	}
	wg.Wait()
	close(results)
	successes, conflicts := 0, 0
	for err := range results {
		if err == nil {
			successes++
		} else if ErrorCode(err) == "CHARACTER_PROPOSAL_ALREADY_ADOPTED" {
			conflicts++
		} else {
			t.Fatalf("unexpected concurrent adoption error: %v", err)
		}
	}
	if successes != 1 || conflicts != 1 {
		t.Fatalf("expected one adoption and one conflict, got success=%d conflict=%d", successes, conflicts)
	}
	app.Close()

	assertProposalLiveState(t, admin)
}

func openProposalLiveDB(t *testing.T, databaseURL string) *sql.DB {
	t.Helper()
	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatalf("open proposal live database: %v", err)
	}
	if err := db.Ping(); err != nil {
		db.Close()
		t.Fatalf("ping proposal live database: %v", err)
	}
	return db
}

func proposalLiveAppURL(t *testing.T, databaseURL string) string {
	t.Helper()
	parsed, err := url.Parse(databaseURL)
	if err != nil {
		t.Fatalf("parse proposal live database URL: %v", err)
	}
	parsed.User = url.UserPassword(proposalLiveRole, proposalLivePassword)
	return parsed.String()
}

func prepareProposalLive(t *testing.T, db *sql.DB) {
	t.Helper()
	statements := []string{
		`DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_character_proposal_live_app') THEN
    CREATE ROLE mirofish_character_proposal_live_app LOGIN PASSWORD 'mirofish_character_proposal_live_password' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE mirofish_character_proposal_live_app WITH LOGIN PASSWORD 'mirofish_character_proposal_live_password';
    GRANT mirofish_app TO mirofish_character_proposal_live_app;
  END IF;
END $$`,
		`INSERT INTO users (user_id, email, display_name) VALUES ('` + proposalLiveUserID + `', 'proposal-live@example.invalid', 'Proposal Live')`,
		`INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES ('` + proposalLiveTenantID + `', 'proposal-live', 'Proposal Live', 'personal')`,
		`INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES ('` + proposalLiveTenantID + `', '` + proposalLiveUserID + `', 'owner')`,
		`INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES ('` + proposalLiveTenantID + `', '` + proposalLiveProjectID + `', 'Proposal Live', '` + proposalLiveUserID + `')`,
		`INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES ('` + proposalLiveTenantID + `', '` + proposalLiveProjectID + `', '` + proposalLiveUserID + `', 'project_owner')`,
		`INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, started_by) VALUES ('` + proposalLiveTenantID + `', '` + proposalLiveRunID + `', 'character_dialogue', '` + proposalLiveProjectID + `', 'completed', '` + proposalLiveUserID + `')`,
		`INSERT INTO worldline_sessions (tenant_id, session_id, project_id, run_id, status, lifecycle, created_by) VALUES ('` + proposalLiveTenantID + `', '` + proposalLiveSessionID + `', '` + proposalLiveProjectID + `', '` + proposalLiveRunID + `', 'paused', 'active', '` + proposalLiveUserID + `')`,
		`INSERT INTO character_interaction_sessions (tenant_id, interaction_id, project_id, worldline_session_id, mode, status, title, created_by) VALUES ('` + proposalLiveTenantID + `', '` + proposalLiveInteraction + `', '` + proposalLiveProjectID + `', '` + proposalLiveSessionID + `', 'dialogue', 'active', 'Proposal interaction', '` + proposalLiveUserID + `')`,
	}
	for _, statement := range statements {
		if _, err := db.Exec(statement); err != nil {
			t.Fatalf("prepare proposal live fixture: %v", err)
		}
	}
	insertProposalLiveAssets(t, db)
}

func insertProposalLiveAssets(t *testing.T, db *sql.DB) {
	t.Helper()
	assets := []struct{ id, assetType, proposalType, title, summary, targetID, payload string }{
		{proposalLiveMemoryAsset, "character_memory_proposal", "memory", "Memory", "Remember the gate", proposalLiveMemoryID, `"memory_type":"interaction"`},
		{proposalLiveRelationAsset, "character_relation_proposal", "relation", "Relation", "Gatekeeper distrusts visitor", "", `"source_entity_name":"Gatekeeper","target_entity_name":"Visitor","relationship_type":"distrusts"`},
		{proposalLiveWorldAsset, "character_world_state_proposal", "world_state", "World", "The inner lock changed", proposalLiveWorldEventID, `"state_changes":{"inner_lock":"changed"}`},
		{proposalLiveRaceAsset, "character_relation_proposal", "relation", "Race relation", "Gatekeeper distrusts visitor", "", `"source_entity_name":"Gatekeeper","target_entity_name":"Visitor","relationship_type":"distrusts"`},
	}
	for _, asset := range assets {
		payload := `{"interaction_id":"` + proposalLiveInteraction + `","proposal_type":"` + asset.proposalType + `","target_id":"` + asset.targetID + `","source_run_id":"` + proposalLiveRunID + `",` + asset.payload + `}`
		_, err := db.Exec(`INSERT INTO assets (
  tenant_id, asset_id, project_id, scope, asset_type, category, lifecycle,
  title, summary, payload_jsonb, source_kind, source_ref, created_by
) VALUES ($1, $2, $3, 'project', $4, 'character', 'candidate', $5, $6, $7::jsonb, 'character_dialogue', $8, $9)`,
			proposalLiveTenantID, asset.id, proposalLiveProjectID, asset.assetType,
			asset.title, asset.summary, payload, "proposal-live:"+asset.id, proposalLiveUserID)
		if err != nil {
			t.Fatalf("insert proposal live asset: %v", err)
		}
	}
	if _, err := db.Exec(`INSERT INTO archive_memories (
  tenant_id, memory_id, asset_id, project_id, memory_type, status, summary,
  source_kind, source_ref, created_by
) VALUES ($1, $2, $3, $4, 'interaction', 'candidate', 'Remember the gate', 'character_dialogue', 'proposal-live-memory', $5)`,
		proposalLiveTenantID, proposalLiveMemoryID, proposalLiveMemoryAsset, proposalLiveProjectID, proposalLiveUserID); err != nil {
		t.Fatalf("insert proposal live memory: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO worldline_events (
  tenant_id, event_id, session_id, project_id, step, title, summary, kind,
  status, lifecycle, source_run_id, created_by
) VALUES ($1, $2, $3, $4, 1, 'World', 'The inner lock changed', 'character_dialogue', 'candidate', 'simulation', $5, $6)`,
		proposalLiveTenantID, proposalLiveWorldEventID, proposalLiveSessionID, proposalLiveProjectID, proposalLiveRunID, proposalLiveUserID); err != nil {
		t.Fatalf("insert proposal live world event: %v", err)
	}
}

func assertProposalLiveState(t *testing.T, db *sql.DB) {
	t.Helper()
	assertCount := func(query string, expected int) {
		t.Helper()
		var count int
		if err := db.QueryRow(query, proposalLiveTenantID).Scan(&count); err != nil {
			t.Fatalf("read proposal live state: %v", err)
		}
		if count != expected {
			t.Fatalf("unexpected proposal live count: got %d want %d for %s", count, expected, query)
		}
	}
	assertCount(`SELECT count(*) FROM assets WHERE tenant_id = $1 AND lifecycle = 'canon'`, 4)
	assertCount(`SELECT count(*) FROM archive_memories WHERE tenant_id = $1 AND status = 'canon'`, 1)
	assertCount(`SELECT count(*) FROM archive_memory_events WHERE tenant_id = $1 AND status = 'accepted'`, 1)
	assertCount(`SELECT count(*) FROM worldline_events WHERE tenant_id = $1 AND status = 'canon' AND lifecycle = 'canon_reference'`, 1)
	assertCount(`SELECT count(*) FROM worldline_event_adoptions WHERE tenant_id = $1`, 1)
	assertCount(`SELECT count(*) FROM relationships WHERE tenant_id = $1`, 1)
	assertCount(`SELECT count(*) FROM audit_logs WHERE tenant_id = $1 AND action = 'character.proposal.adopt'`, 4)
}

func cleanupProposalLive(t *testing.T, db *sql.DB) {
	t.Helper()
	if _, err := db.Exec(`DELETE FROM tenants WHERE tenant_id = $1`, proposalLiveTenantID); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("cleanup proposal live tenant: %v", err)
	}
	if _, err := db.Exec(`DELETE FROM users WHERE user_id = $1`, proposalLiveUserID); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("cleanup proposal live user: %v", err)
	}
}
