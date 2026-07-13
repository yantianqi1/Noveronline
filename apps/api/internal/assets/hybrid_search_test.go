package assets

import (
	"context"
	"encoding/json"
	"math"
	"reflect"
	"strings"
	"testing"
)

func hybridSearchRow(mode, model string) []any {
	return []any{
		"doc-1",
		"asset",
		"asset-1",
		"project-123",
		"world_rule",
		"灵气规则",
		`["世界"]`,
		`{"asset_id":"asset-1"}`,
		0,
		0,
		"",
		`[]`,
		"2026-07-04T00:00:00Z",
		"2026-07-04T00:00:00Z",
		mode,
		0.4,
		0.9,
		0.03,
		0.08,
		0.05,
		0.835,
		1,
		model,
	}
}

func TestSQLReaderVectorSearchRequiresExplicitQueryEmbedding(t *testing.T) {
	queryer := &recordingSQLQueryer{}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	_, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Query:     "师门规则",
		Mode:      "vector",
	})

	if ErrorCode(err) != "ASSET_QUERY_EMBEDDING_REQUIRED" {
		t.Fatalf("expected query embedding error, got %v", err)
	}
	if queryer.query != "" {
		t.Fatalf("vector search silently reached keyword query path: %s", queryer.query)
	}
}

func TestSQLReaderHybridSearchRejectsInvalidEmbeddingsBeforeDatabase(t *testing.T) {
	tests := []struct {
		name      string
		embedding []float64
	}{
		{name: "zero", embedding: []float64{0, 0, 0}},
		{name: "nan", embedding: []float64{math.NaN(), 0, 1}},
		{name: "infinite", embedding: []float64{math.Inf(1), 0, 1}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			queryer := &recordingSQLQueryer{}
			reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

			_, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
				TenantID:       "tenant-123",
				ProjectID:      "project-123",
				Query:          "师门规则",
				Mode:           "hybrid",
				QueryEmbedding: test.embedding,
				EmbeddingModel: "embedding-model-1",
			})

			if ErrorCode(err) != "VALIDATION_FAILED" {
				t.Fatalf("expected validation failure, got %v", err)
			}
			if queryer.query != "" {
				t.Fatalf("invalid embedding reached database: %s", queryer.query)
			}
		})
	}
}

func TestSQLReaderHybridSearchUsesVectorRankingAndReturnsStableMetadata(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{values: [][]any{hybridSearchRow("hybrid", "embedding-model-1")}},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer, Limit: 25})

	items, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID:       "tenant-123",
		ProjectID:      "project-123",
		Query:          "师门规则",
		Mode:           "hybrid",
		QueryEmbedding: []float64{1, 0.25, -0.5},
		EmbeddingModel: "embedding-model-1",
	})

	if err != nil {
		t.Fatalf("hybrid search: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected one result, got %#v", items)
	}
	ranking := items[0].Ranking
	if ranking.Mode != "hybrid" || ranking.EmbeddingModel != "embedding-model-1" || ranking.Rank != 1 {
		t.Fatalf("unexpected ranking metadata: %#v", ranking)
	}
	if ranking.KeywordScore != 0.4 || ranking.VectorScore != 0.9 || ranking.FinalScore != 0.835 {
		t.Fatalf("unexpected score components: %#v", ranking)
	}
	for _, fragment := range []string{
		"LEFT JOIN asset_embeddings",
		"embedding.embedding <=> input.query_embedding",
		"asset.enabled = true",
		"embedding.embedding_model = input.embedding_model",
		"embedding.dimensions = vector_dims(input.query_embedding)",
		"(0.45 * boosted.keyword_score) + (0.55 * boosted.vector_score)",
		"row_number() OVER",
	} {
		if !strings.Contains(queryer.query, fragment) {
			t.Fatalf("hybrid SQL missing %q: %s", fragment, queryer.query)
		}
	}
	expectedArgs := []any{
		"tenant-123",
		"project-123",
		"师门规则",
		"%师门规则%",
		"hybrid",
		"[1,0.25,-0.5]",
		"embedding-model-1",
		[]string{},
		[]string{},
		[]string{},
		[]string{},
		[]string{},
		(*bool)(nil),
		25,
	}
	if !reflect.DeepEqual(queryer.args, expectedArgs) {
		t.Fatalf("unexpected hybrid args: %#v", queryer.args)
	}
	raw, err := json.Marshal(items[0])
	if err != nil {
		t.Fatalf("marshal result: %v", err)
	}
	for _, forbidden := range []string{"query_embedding", `"embedding":`, "content_text", "body_text"} {
		if strings.Contains(string(raw), forbidden) {
			t.Fatalf("public result leaked %q: %s", forbidden, raw)
		}
	}
}

func TestSQLReaderHybridSearchAppliesParameterizedFiltersAndExplainsWeights(t *testing.T) {
	pinned := true
	queryer := &recordingSQLQueryer{rows: &fakeSQLRows{values: [][]any{hybridSearchRow("hybrid", "embedding-model-1")}}}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer, Limit: 25})

	items, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: "tenant-123", ProjectID: "project-123", Query: "师门规则", Mode: "hybrid",
		QueryEmbedding: []float64{1, 0.25, -0.5}, EmbeddingModel: "embedding-model-1",
		Filters: SearchFilters{
			AssetTypes: []string{" world_rule ", "world_rule"},
			Categories: []string{"world"},
			Lifecycles: []string{"canon", "material"},
			Sources:    []string{"seed_pipeline"},
			Tags:       []string{"师门"},
			Pinned:     &pinned,
		},
	})
	if err != nil || len(items) != 1 {
		t.Fatalf("filtered hybrid search: items=%#v err=%v", items, err)
	}
	for _, fragment := range []string{
		"asset.asset_type = ANY(input.asset_types)",
		"asset.category = ANY(input.categories)",
		"asset.lifecycle = ANY(input.lifecycles)",
		"asset.source_kind = ANY(input.sources)",
		"asset.tags_jsonb ?| input.tags",
		"asset.pinned = input.pinned",
	} {
		if !strings.Contains(queryer.query, fragment) {
			t.Fatalf("filter SQL missing %q: %s", fragment, queryer.query)
		}
	}
	wantFilterArgs := []any{
		[]string{"world_rule"}, []string{"world"}, []string{"canon", "material"},
		[]string{"seed_pipeline"}, []string{"师门"}, &pinned,
	}
	if !reflect.DeepEqual(queryer.args[7:13], wantFilterArgs) {
		t.Fatalf("unexpected filter args: %#v", queryer.args[7:13])
	}
	ranking := items[0].Ranking
	if ranking.KeywordWeight != 0.45 || ranking.VectorWeight != 0.55 || math.Abs(ranking.KeywordContribution-0.18) > 1e-9 || math.Abs(ranking.VectorContribution-0.495) > 1e-9 {
		t.Fatalf("unexpected hybrid contribution explanation: %#v", ranking)
	}
	if !strings.Contains(ranking.Explanation, "45% keyword") {
		t.Fatalf("missing public ranking explanation: %#v", ranking)
	}
}
