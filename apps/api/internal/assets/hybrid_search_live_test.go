package assets

import (
	"context"
	"database/sql"
	"os"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveTenantA       = "81000000-0000-4000-8000-000000000001"
	liveTenantB       = "81000000-0000-4000-8000-000000000002"
	liveProjectA      = "82000000-0000-4000-8000-000000000001"
	liveProjectB      = "82000000-0000-4000-8000-000000000002"
	liveUser          = "83000000-0000-4000-8000-000000000001"
	liveAssetMoon     = "85000000-0000-4000-8000-000000000001"
	liveAssetFire     = "85000000-0000-4000-8000-000000000002"
	liveAssetDisabled = "85000000-0000-4000-8000-000000000003"
	liveAssetForeign  = "85000000-0000-4000-8000-000000000004"
)

func TestSQLReaderLivePostgresKeywordVectorHybridIsolationAndDisabledExclusion(t *testing.T) {
	adminURL := os.Getenv("MIROFISH_ASSET_SEARCH_LIVE_ADMIN_DATABASE_URL")
	appURL := os.Getenv("MIROFISH_ASSET_SEARCH_LIVE_DATABASE_URL")
	if adminURL == "" || appURL == "" {
		t.Skip("asset search live PostgreSQL URLs are not configured")
	}
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin database: %v", err)
	}
	defer adminDB.Close()
	cleanupLiveAssetSearch(t, adminDB)
	defer cleanupLiveAssetSearch(t, adminDB)
	seedLiveAssetSearch(t, adminDB)

	appDB, err := sql.Open("pgx", appURL)
	if err != nil {
		t.Fatalf("open app database: %v", err)
	}
	defer appDB.Close()
	reader := NewSQLReader(SQLReaderConfig{Queryer: NewSQLDBQueryer(appDB), Limit: 20})

	keyword, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: liveTenantA, ProjectID: liveProjectA, Query: "Moon", Mode: "keyword",
	})
	if err != nil {
		t.Fatalf("keyword search: %v", err)
	}
	if len(keyword) != 1 || keyword[0].SourceRef != liveAssetMoon || keyword[0].Ranking.Mode != "keyword" {
		t.Fatalf("unexpected keyword result: %#v", keyword)
	}

	vector, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: liveTenantA, ProjectID: liveProjectA, Query: "semantic rule", Mode: "vector",
		QueryEmbedding: []float64{1, 0, 0}, EmbeddingModel: "live-embedding-model",
	})
	if err != nil {
		t.Fatalf("vector search: %v", err)
	}
	if len(vector) != 2 || vector[0].SourceRef != liveAssetMoon || vector[0].Ranking.VectorScore <= vector[1].Ranking.VectorScore {
		t.Fatalf("unexpected vector ranking: %#v", vector)
	}
	for _, item := range vector {
		if item.SourceRef == liveAssetDisabled || item.SourceRef == liveAssetForeign {
			t.Fatalf("vector search exposed disabled or foreign asset: %#v", item)
		}
	}

	hybrid, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: liveTenantA, ProjectID: liveProjectA, Query: "Fire", Mode: "hybrid",
		QueryEmbedding: []float64{1, 0, 0}, EmbeddingModel: "live-embedding-model",
	})
	if err != nil {
		t.Fatalf("hybrid search: %v", err)
	}
	if len(hybrid) != 2 || hybrid[0].Ranking.Rank != 1 || hybrid[0].Ranking.FinalScore < hybrid[1].Ranking.FinalScore {
		t.Fatalf("unexpected hybrid ranking: %#v", hybrid)
	}
	if hybrid[0].Ranking.KeywordScore == 0 && hybrid[0].Ranking.VectorScore == 0 {
		t.Fatalf("hybrid ranking metadata omitted score components: %#v", hybrid[0].Ranking)
	}

	pinned := false
	filtered, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: liveTenantA, ProjectID: liveProjectA, Query: "rule", Mode: "hybrid",
		QueryEmbedding: []float64{1, 0, 0}, EmbeddingModel: "live-embedding-model",
		Filters: SearchFilters{AssetTypes: []string{"world_rule"}, Categories: []string{"world"}, Lifecycles: []string{"material"}, Sources: []string{"manual"}, Tags: []string{"fire"}, Pinned: &pinned},
	})
	if err != nil {
		t.Fatalf("filtered hybrid search: %v", err)
	}
	if len(filtered) != 1 || filtered[0].SourceRef != liveAssetFire {
		t.Fatalf("filters did not isolate the expected asset: %#v", filtered)
	}

	crossTenant, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: liveTenantA, ProjectID: liveProjectB, Query: "Foreign", Mode: "keyword",
	})
	if err != nil {
		t.Fatalf("cross-tenant search: %v", err)
	}
	if len(crossTenant) != 0 {
		t.Fatalf("tenant A read tenant B search documents: %#v", crossTenant)
	}
}

func cleanupLiveAssetSearch(t *testing.T, db *sql.DB) {
	t.Helper()
	if _, err := db.Exec(`DELETE FROM tenants WHERE tenant_id IN ($1::uuid, $2::uuid)`, liveTenantA, liveTenantB); err != nil {
		t.Fatalf("cleanup tenants: %v", err)
	}
	if _, err := db.Exec(`DELETE FROM users WHERE user_id = $1::uuid`, liveUser); err != nil {
		t.Fatalf("cleanup user: %v", err)
	}
}

func seedLiveAssetSearch(t *testing.T, db *sql.DB) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatalf("begin live seed: %v", err)
	}
	defer tx.Rollback()
	statements := []struct {
		query string
		args  []any
	}{
		{`INSERT INTO users (user_id, email, display_name) VALUES ($1::uuid, 'asset-go-live@example.invalid', 'Asset Go Live')`, []any{liveUser}},
		{`INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES ($1::uuid, 'asset-go-live-a', 'Asset Go A', 'organization'), ($2::uuid, 'asset-go-live-b', 'Asset Go B', 'organization')`, []any{liveTenantA, liveTenantB}},
		{`INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES ($1::uuid, $2::uuid, 'Asset Go A', $3::uuid), ($4::uuid, $5::uuid, 'Asset Go B', $3::uuid)`, []any{liveTenantA, liveProjectA, liveUser, liveTenantB, liveProjectB}},
		{`INSERT INTO assets (tenant_id, asset_id, project_id, scope, asset_type, category, lifecycle, title, summary, tags_jsonb, source_kind, source_ref, enabled, pinned, created_by) VALUES
	       ($1::uuid, $2::uuid, $3::uuid, 'project', 'world_rule', 'world', 'canon', 'Moon rule', 'Moon semantic rule', '["moon"]'::jsonb, 'manual', 'moon', true, true, $4::uuid),
	       ($1::uuid, $5::uuid, $3::uuid, 'project', 'world_rule', 'world', 'material', 'Fire rule', 'Fire semantic rule', '["fire"]'::jsonb, 'manual', 'fire', true, false, $4::uuid),
	       ($1::uuid, $6::uuid, $3::uuid, 'project', 'world_rule', 'world', 'canon', 'Disabled rule', 'Disabled semantic rule', '[]'::jsonb, 'manual', 'disabled', false, false, $4::uuid),
	       ($7::uuid, $8::uuid, $9::uuid, 'project', 'world_rule', 'world', 'canon', 'Foreign rule', 'Foreign semantic rule', '[]'::jsonb, 'manual', 'foreign', true, false, $4::uuid)`, []any{liveTenantA, liveAssetMoon, liveProjectA, liveUser, liveAssetFire, liveAssetDisabled, liveTenantB, liveAssetForeign, liveProjectB}},
		{`INSERT INTO global_search_index (tenant_id, source, source_ref, project_id, entity_type, title, body) VALUES
       ($1::uuid, 'asset', $2, $3::uuid, 'world_rule', 'Moon rule', 'Moon semantic rule'),
       ($1::uuid, 'asset', $4, $3::uuid, 'world_rule', 'Fire rule', 'Fire semantic rule'),
       ($1::uuid, 'asset', $5, $3::uuid, 'world_rule', 'Disabled rule', 'Disabled semantic rule'),
       ($6::uuid, 'asset', $7, $8::uuid, 'world_rule', 'Foreign rule', 'Foreign semantic rule')`, []any{liveTenantA, liveAssetMoon, liveProjectA, liveAssetFire, liveAssetDisabled, liveTenantB, liveAssetForeign, liveProjectB}},
		{`INSERT INTO asset_embeddings (tenant_id, asset_id, project_id, embedding_model, dimensions, embedding, content_sha256, reindex_batch_id, source_updated_at) VALUES
       ($1::uuid, $2::uuid, $3::uuid, 'live-embedding-model', 3, '[1,0,0]'::vector, repeat('a', 64), 'live-go', now()),
       ($1::uuid, $4::uuid, $3::uuid, 'live-embedding-model', 3, '[0,1,0]'::vector, repeat('b', 64), 'live-go', now()),
       ($1::uuid, $5::uuid, $3::uuid, 'live-embedding-model', 3, '[0,0,1]'::vector, repeat('c', 64), 'live-go', now()),
       ($6::uuid, $7::uuid, $8::uuid, 'live-embedding-model', 3, '[1,0,0]'::vector, repeat('d', 64), 'live-go', now())`, []any{liveTenantA, liveAssetMoon, liveProjectA, liveAssetFire, liveAssetDisabled, liveTenantB, liveAssetForeign, liveProjectB}},
	}
	for _, statement := range statements {
		if _, err := tx.Exec(statement.query, statement.args...); err != nil {
			t.Fatalf("seed live search: %v", err)
		}
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit live seed: %v", err)
	}
}
