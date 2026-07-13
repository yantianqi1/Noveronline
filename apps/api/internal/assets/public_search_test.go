package assets

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
)

type recordingAssetReader struct {
	searchInput SearchAssetsInput
	searches    int
	items       []SearchRecord
}

func (r *recordingAssetReader) ListAssets(context.Context, ListAssetsInput) ([]Record, error) {
	return nil, nil
}

func (r *recordingAssetReader) GetAsset(context.Context, GetAssetInput) (Record, error) {
	return Record{}, nil
}

func (r *recordingAssetReader) ListFacets(context.Context, ListFacetsInput) (Facets, error) {
	return Facets{}, nil
}

func (r *recordingAssetReader) SearchAssets(_ context.Context, input SearchAssetsInput) ([]SearchRecord, error) {
	r.searches++
	r.searchInput = input
	return r.items, nil
}

type recordingQueryEmbeddingResolver struct {
	binding QueryEmbeddingBinding
	err     error
	calls   int
}

func (r *recordingQueryEmbeddingResolver) ResolveQueryEmbedding(context.Context, string, string) (QueryEmbeddingBinding, error) {
	r.calls++
	return r.binding, r.err
}

type recordingQueryEmbeddingProvider struct {
	request   QueryEmbeddingRequest
	embedding []float64
	err       error
	calls     int
}

func (p *recordingQueryEmbeddingProvider) EmbedQuery(_ context.Context, input QueryEmbeddingRequest) ([]float64, error) {
	p.calls++
	p.request = input
	return p.embedding, p.err
}

type recordingSearchIndexChecker struct {
	input  SearchIndexInput
	exists bool
	err    error
	calls  int
}

func (c *recordingSearchIndexChecker) HasSearchIndex(_ context.Context, input SearchIndexInput) (bool, error) {
	c.calls++
	c.input = input
	return c.exists, c.err
}

func validQueryEmbeddingBinding() QueryEmbeddingBinding {
	return QueryEmbeddingBinding{
		ModuleKey: AssetSearchEmbeddingModuleKey,
		ModelID:   "embedding-model-1",
		Provider:  "openai-compatible",
		BaseURL:   "https://provider.example/v1",
		APIKey:    "private-key",
		Settings:  map[string]any{"embedding_dimensions": float64(3)},
	}
}

func TestPublicSearchReaderBuildsTrustedHybridInput(t *testing.T) {
	base := &recordingAssetReader{items: []SearchRecord{{SearchDocumentID: "doc-1"}}}
	resolver := &recordingQueryEmbeddingResolver{binding: validQueryEmbeddingBinding()}
	provider := &recordingQueryEmbeddingProvider{embedding: []float64{0.1, 0.2, 0.3}}
	index := &recordingSearchIndexChecker{exists: true}
	reader := NewPublicSearchReader(PublicSearchReaderConfig{Base: base, Resolver: resolver, Provider: provider, Index: index})

	items, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: "tenant-123", ProjectID: "project-123", Query: "月光规则", Mode: "hybrid",
		Filters: SearchFilters{AssetTypes: []string{"world_rule"}, Tags: []string{"moon"}},
	})
	if err != nil {
		t.Fatalf("hybrid search: %v", err)
	}
	if len(items) != 1 || resolver.calls != 1 || provider.calls != 1 || index.calls != 1 || base.searches != 1 {
		t.Fatalf("hybrid chain did not complete: items=%#v resolver=%d provider=%d index=%d base=%d", items, resolver.calls, provider.calls, index.calls, base.searches)
	}
	if provider.request.Query != "月光规则" || provider.request.Binding.APIKey != "private-key" {
		t.Fatalf("provider lost server-resolved query binding: %#v", provider.request)
	}
	if index.input.EmbeddingModel != "embedding-model-1" || index.input.Dimensions != 3 {
		t.Fatalf("index check did not bind model and dimensions: %#v", index.input)
	}
	if base.searchInput.Mode != "hybrid" || base.searchInput.EmbeddingModel != "embedding-model-1" || !reflect.DeepEqual(base.searchInput.QueryEmbedding, []float64{0.1, 0.2, 0.3}) {
		t.Fatalf("base reader did not receive trusted vector input: %#v", base.searchInput)
	}
	if !reflect.DeepEqual(base.searchInput.Filters, SearchFilters{AssetTypes: []string{"world_rule"}, Tags: []string{"moon"}}) {
		t.Fatalf("public reader dropped server-side filters: %#v", base.searchInput.Filters)
	}
}

func TestPublicSearchReaderRejectsClientVectorBeforeProvider(t *testing.T) {
	base := &recordingAssetReader{}
	resolver := &recordingQueryEmbeddingResolver{binding: validQueryEmbeddingBinding()}
	provider := &recordingQueryEmbeddingProvider{embedding: []float64{1}}
	reader := NewPublicSearchReader(PublicSearchReaderConfig{Base: base, Resolver: resolver, Provider: provider, Index: &recordingSearchIndexChecker{exists: true}})

	_, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: "tenant-123", ProjectID: "project-123", Query: "rules", Mode: "vector",
		QueryEmbedding: []float64{1}, EmbeddingModel: "client-model",
	})
	if ErrorCode(err) != "VALIDATION_FAILED" {
		t.Fatalf("expected client vector rejection, got %v", err)
	}
	if resolver.calls != 0 || provider.calls != 0 || base.searches != 0 {
		t.Fatal("client vector reached trusted embedding chain")
	}
}

func TestPublicSearchReaderFailsClosedWithoutBindingProviderOrIndex(t *testing.T) {
	cases := []struct {
		name     string
		resolver QueryEmbeddingResolver
		provider QueryEmbeddingProvider
		index    SearchIndexChecker
		want     string
	}{
		{name: "binding", resolver: &recordingQueryEmbeddingResolver{err: &AppError{Code: "LLM_MODULE_UNBOUND", Message: "private binding detail"}}, provider: &recordingQueryEmbeddingProvider{}, index: &recordingSearchIndexChecker{exists: true}, want: "LLM_MODULE_UNBOUND"},
		{name: "provider", resolver: &recordingQueryEmbeddingResolver{binding: validQueryEmbeddingBinding()}, index: &recordingSearchIndexChecker{exists: true}, want: "ASSET_QUERY_EMBEDDING_PROVIDER_UNCONFIGURED"},
		{name: "index", resolver: &recordingQueryEmbeddingResolver{binding: validQueryEmbeddingBinding()}, provider: &recordingQueryEmbeddingProvider{embedding: []float64{1, 2}}, index: &recordingSearchIndexChecker{exists: false}, want: "ASSET_SEARCH_INDEX_UNAVAILABLE"},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			base := &recordingAssetReader{}
			reader := NewPublicSearchReader(PublicSearchReaderConfig{Base: base, Resolver: test.resolver, Provider: test.provider, Index: test.index})
			_, err := reader.SearchAssets(context.Background(), SearchAssetsInput{TenantID: "tenant-123", ProjectID: "project-123", Query: "private query", Mode: "hybrid"})
			if ErrorCode(err) != test.want {
				t.Fatalf("expected %s, got %v", test.want, err)
			}
			if base.searches != 0 {
				t.Fatal("failed hybrid preparation silently fell back to keyword/base search")
			}
			if strings.Contains(err.Error(), "private query") {
				t.Fatalf("public error leaked query: %v", err)
			}
		})
	}
}

func TestPublicSearchReaderKeywordDoesNotCallEmbeddingDependencies(t *testing.T) {
	base := &recordingAssetReader{}
	reader := NewPublicSearchReader(PublicSearchReaderConfig{Base: base})
	_, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID: "tenant-123", ProjectID: "project-123", Query: "rules", Mode: "keyword",
	})
	if err != nil || base.searches != 1 || base.searchInput.Mode != "keyword" {
		t.Fatalf("keyword search changed unexpectedly: input=%#v err=%v", base.searchInput, err)
	}
}

func TestOpenAICompatibleQueryEmbeddingProviderUsesBoundModelAndSanitizesFailure(t *testing.T) {
	var requestBody map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/v1/embeddings" || request.Header.Get("Authorization") != "Bearer private-key" || request.Header.Get("X-MiroFish-Module-Key") != AssetSearchEmbeddingModuleKey {
			t.Fatalf("unexpected provider request: path=%s headers=%v", request.URL.Path, request.Header)
		}
		if err := json.NewDecoder(request.Body).Decode(&requestBody); err != nil {
			t.Fatalf("decode provider request: %v", err)
		}
		response.Header().Set("Content-Type", "application/json")
		_, _ = response.Write([]byte(`{"data":[{"index":0,"embedding":[0.5,0.25,0.125]}]}`))
	}))
	defer server.Close()

	provider := NewOpenAICompatibleQueryEmbeddingProvider(server.Client())
	embedding, err := provider.EmbedQuery(context.Background(), QueryEmbeddingRequest{
		TenantID: "tenant-123", ProjectID: "project-123", Query: "private query",
		Binding: QueryEmbeddingBinding{ModelID: "embedding-model-1", BaseURL: server.URL + "/v1", APIKey: "private-key", Settings: map[string]any{"embedding_dimensions": float64(3)}},
	})
	if err != nil || !reflect.DeepEqual(embedding, []float64{0.5, 0.25, 0.125}) {
		t.Fatalf("embed query: embedding=%v err=%v", embedding, err)
	}
	if requestBody["model"] != "embedding-model-1" || requestBody["dimensions"] != float64(3) {
		t.Fatalf("provider request did not use binding: %#v", requestBody)
	}
	inputs, ok := requestBody["input"].([]any)
	if !ok || len(inputs) != 1 || inputs[0] != "private query" {
		t.Fatalf("provider request input mismatch: %#v", requestBody)
	}
}

func TestOpenAICompatibleQueryEmbeddingProviderDoesNotExposeRawErrorBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		response.WriteHeader(http.StatusBadGateway)
		_, _ = response.Write([]byte(`{"error":"api_key=sk-secret query=private"}`))
	}))
	defer server.Close()
	provider := NewOpenAICompatibleQueryEmbeddingProvider(server.Client())
	_, err := provider.EmbedQuery(context.Background(), QueryEmbeddingRequest{
		TenantID: "tenant-123", ProjectID: "project-123", Query: "private",
		Binding: QueryEmbeddingBinding{ModelID: "model", BaseURL: server.URL, APIKey: "sk-secret"},
	})
	if ErrorCode(err) != "LLM_PROVIDER_ERROR" || strings.Contains(err.Error(), "sk-secret") || strings.Contains(err.Error(), "private") {
		t.Fatalf("provider error was not sanitized: %v", err)
	}
}

func TestSQLQueryEmbeddingResolverUsesFixedModuleAndTenantContext(t *testing.T) {
	queryer := &recordingSQLQueryer{rows: &fakeSQLRows{values: [][]any{{
		AssetSearchEmbeddingModuleKey,
		"embedding-model-1",
		"openai-compatible",
		"https://provider.example/v1",
		"invalid-envelope",
		`{"embedding_dimensions":3}`,
	}}}}
	resolver := NewSQLQueryEmbeddingResolver(SQLQueryEmbeddingResolverConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: base64.StdEncoding.EncodeToString(make([]byte, 32)),
	})

	_, err := resolver.ResolveQueryEmbedding(context.Background(), "tenant-123", "project-123")
	if ErrorCode(err) != "LLM_CREDENTIAL_UNAVAILABLE" {
		t.Fatalf("expected encrypted credential failure, got %v", err)
	}
	if !strings.Contains(queryer.query, "binding.module_key = $3") || strings.Contains(queryer.query, "query_text") {
		t.Fatalf("binding query is not fixed or leaked search text: %s", queryer.query)
	}
	wantArgs := []any{"tenant-123", "project-123", AssetSearchEmbeddingModuleKey}
	if !reflect.DeepEqual(queryer.args, wantArgs) {
		t.Fatalf("unexpected binding args: got %#v want %#v", queryer.args, wantArgs)
	}
}

func TestSQLReaderSearchIndexCheckRequiresEnabledAssetAndSearchDocument(t *testing.T) {
	queryer := &recordingSQLQueryer{rows: &fakeSQLRows{values: [][]any{{true}}}}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})
	exists, err := reader.HasSearchIndex(context.Background(), SearchIndexInput{
		TenantID: "tenant-123", ProjectID: "project-123", EmbeddingModel: "embedding-model-1", Dimensions: 3,
	})
	if err != nil || !exists {
		t.Fatalf("search index check: exists=%v err=%v", exists, err)
	}
	for _, fragment := range []string{"asset.enabled = TRUE", "global_search_index", "embedding.embedding_model = $3", "embedding.dimensions = $4"} {
		if !strings.Contains(queryer.query, fragment) {
			t.Fatalf("search index check missing %q: %s", fragment, queryer.query)
		}
	}
}
