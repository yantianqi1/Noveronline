package assets

import (
	"bytes"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"io"
	"math"
	"net/http"
	"strings"
	"time"
)

const AssetSearchEmbeddingModuleKey = "asset_search_embedding"

type QueryEmbeddingBinding struct {
	ModuleKey string
	ModelID   string
	Provider  string
	BaseURL   string
	APIKey    string
	Settings  map[string]any
}

type QueryEmbeddingResolver interface {
	ResolveQueryEmbedding(context.Context, string, string) (QueryEmbeddingBinding, error)
}

type QueryEmbeddingProvider interface {
	EmbedQuery(context.Context, QueryEmbeddingRequest) ([]float64, error)
}

type QueryEmbeddingRequest struct {
	TenantID  string
	ProjectID string
	Query     string
	Binding   QueryEmbeddingBinding
}

type SearchIndexChecker interface {
	HasSearchIndex(context.Context, SearchIndexInput) (bool, error)
}

type SearchIndexInput struct {
	TenantID       string
	ProjectID      string
	EmbeddingModel string
	Dimensions     int
}

type PublicSearchReaderConfig struct {
	Base     Reader
	Resolver QueryEmbeddingResolver
	Provider QueryEmbeddingProvider
	Index    SearchIndexChecker
}

type PublicSearchReader struct {
	base     Reader
	resolver QueryEmbeddingResolver
	provider QueryEmbeddingProvider
	index    SearchIndexChecker
}

func NewPublicSearchReader(config PublicSearchReaderConfig) *PublicSearchReader {
	return &PublicSearchReader{
		base:     config.Base,
		resolver: config.Resolver,
		provider: config.Provider,
		index:    config.Index,
	}
}

func (r *PublicSearchReader) ListAssets(ctx context.Context, input ListAssetsInput) (AssetPage, error) {
	if r.base == nil {
		return AssetPage{}, searchBackendUnconfigured()
	}
	return r.base.ListAssets(ctx, input)
}

func (r *PublicSearchReader) GetAsset(ctx context.Context, input GetAssetInput) (Record, error) {
	if r.base == nil {
		return Record{}, searchBackendUnconfigured()
	}
	return r.base.GetAsset(ctx, input)
}

func (r *PublicSearchReader) ListFacets(ctx context.Context, input ListFacetsInput) (Facets, error) {
	if r.base == nil {
		return Facets{}, searchBackendUnconfigured()
	}
	return r.base.ListFacets(ctx, input)
}

func (r *PublicSearchReader) SearchAssets(ctx context.Context, input SearchAssetsInput) ([]SearchRecord, error) {
	if r.base == nil {
		return nil, searchBackendUnconfigured()
	}
	mode := strings.ToLower(strings.TrimSpace(input.Mode))
	if mode == "" {
		mode = "keyword"
	}
	if mode != "keyword" && mode != "vector" && mode != "hybrid" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "search mode must be keyword, vector, or hybrid"}
	}
	if len(input.QueryEmbedding) != 0 || strings.TrimSpace(input.EmbeddingModel) != "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "client-supplied query embeddings are not accepted"}
	}
	input.Mode = mode
	if mode == "keyword" {
		return r.base.SearchAssets(ctx, input)
	}
	if r.resolver == nil || r.provider == nil {
		return nil, &AppError{Code: "ASSET_QUERY_EMBEDDING_PROVIDER_UNCONFIGURED", Message: "asset query embedding provider is not configured"}
	}
	if r.index == nil {
		return nil, &AppError{Code: "ASSET_SEARCH_INDEX_UNAVAILABLE", Message: "asset vector search index is not available"}
	}
	binding, err := r.resolver.ResolveQueryEmbedding(ctx, input.TenantID, input.ProjectID)
	if err != nil {
		return nil, normalizeQueryEmbeddingError(err)
	}
	if err := validateQueryEmbeddingBinding(binding); err != nil {
		return nil, err
	}
	embedding, err := r.provider.EmbedQuery(ctx, QueryEmbeddingRequest{
		TenantID:  strings.TrimSpace(input.TenantID),
		ProjectID: strings.TrimSpace(input.ProjectID),
		Query:     strings.TrimSpace(input.Query),
		Binding:   binding,
	})
	if err != nil {
		return nil, normalizeQueryEmbeddingError(err)
	}
	if err := validateEmbedding(embedding); err != nil {
		return nil, err
	}
	hasIndex, err := r.index.HasSearchIndex(ctx, SearchIndexInput{
		TenantID:       input.TenantID,
		ProjectID:      input.ProjectID,
		EmbeddingModel: binding.ModelID,
		Dimensions:     len(embedding),
	})
	if err != nil {
		return nil, &AppError{Code: "ASSET_SEARCH_INDEX_QUERY_FAILED", Message: "asset vector search index check failed"}
	}
	if !hasIndex {
		return nil, &AppError{Code: "ASSET_SEARCH_INDEX_UNAVAILABLE", Message: "asset vector search index is not available for the resolved model"}
	}
	input.QueryEmbedding = append([]float64(nil), embedding...)
	input.EmbeddingModel = binding.ModelID
	return r.base.SearchAssets(ctx, input)
}

func searchBackendUnconfigured() error {
	return &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
}

func validateQueryEmbeddingBinding(binding QueryEmbeddingBinding) error {
	if strings.TrimSpace(binding.ModuleKey) != AssetSearchEmbeddingModuleKey {
		return &AppError{Code: "LLM_MODULE_UNBOUND", Message: "asset_search_embedding module is not bound"}
	}
	if strings.TrimSpace(binding.ModelID) == "" || strings.TrimSpace(binding.BaseURL) == "" {
		return &AppError{Code: "ASSET_QUERY_EMBEDDING_PROVIDER_UNCONFIGURED", Message: "asset query embedding provider is incomplete"}
	}
	if strings.TrimSpace(binding.APIKey) == "" {
		return &AppError{Code: "LLM_CREDENTIAL_UNAVAILABLE", Message: "asset query embedding credential is unavailable"}
	}
	provider := strings.ToLower(strings.TrimSpace(binding.Provider))
	if provider != "openai" && provider != "openai-compatible" {
		return &AppError{Code: "ASSET_QUERY_EMBEDDING_PROVIDER_UNSUPPORTED", Message: "asset query embedding provider is unsupported"}
	}
	return nil
}

func validateEmbedding(embedding []float64) error {
	if len(embedding) == 0 {
		return &AppError{Code: "ASSET_QUERY_EMBEDDING_INVALID", Message: "asset query embedding was empty"}
	}
	nonZero := false
	for _, component := range embedding {
		if math.IsNaN(component) || math.IsInf(component, 0) {
			return &AppError{Code: "ASSET_QUERY_EMBEDDING_INVALID", Message: "asset query embedding was invalid"}
		}
		if component != 0 {
			nonZero = true
		}
	}
	if !nonZero {
		return &AppError{Code: "ASSET_QUERY_EMBEDDING_INVALID", Message: "asset query embedding was invalid"}
	}
	return nil
}

func normalizeQueryEmbeddingError(err error) error {
	if code := ErrorCode(err); code != "ASSET_ERROR" {
		return err
	}
	return &AppError{Code: "LLM_PROVIDER_ERROR", Message: "asset query embedding failed"}
}

type SQLQueryEmbeddingResolverConfig struct {
	Queryer               SQLQueryer
	CredentialKeyMaterial string
}

type SQLQueryEmbeddingResolver struct {
	queryer SQLQueryer
	key     []byte
	keyErr  error
}

func NewSQLQueryEmbeddingResolver(config SQLQueryEmbeddingResolverConfig) *SQLQueryEmbeddingResolver {
	key, err := parseQueryCredentialKey(config.CredentialKeyMaterial)
	return &SQLQueryEmbeddingResolver{queryer: config.Queryer, key: key, keyErr: err}
}

func (r *SQLQueryEmbeddingResolver) ResolveQueryEmbedding(ctx context.Context, tenantID, projectID string) (QueryEmbeddingBinding, error) {
	if err := validateProjectInput(tenantID, projectID); err != nil {
		return QueryEmbeddingBinding{}, err
	}
	if r.queryer == nil {
		return QueryEmbeddingBinding{}, &AppError{Code: "LLM_BINDING_BACKEND_UNCONFIGURED", Message: "LLM binding backend is not configured"}
	}
	if r.keyErr != nil || len(r.key) != 32 {
		return QueryEmbeddingBinding{}, &AppError{Code: "LLM_CREDENTIAL_KEY_UNCONFIGURED", Message: "LLM credential encryption key is not configured"}
	}
	query := `SELECT
  binding.module_key,
  binding.model_id,
  channel.provider,
  channel.base_url,
  channel.encrypted_api_key,
  binding.settings_jsonb::text
FROM llm_module_bindings binding
JOIN llm_channels channel
  ON channel.channel_id = binding.channel_id
 AND channel.enabled = TRUE
 AND (channel.tenant_id = binding.tenant_id OR channel.tenant_id IS NULL)
JOIN llm_models model
  ON model.channel_id = binding.channel_id
 AND model.model_id = binding.model_id
 AND (model.tenant_id = binding.tenant_id OR model.tenant_id IS NULL)
WHERE binding.tenant_id::text = $1
  AND (binding.project_id::text = $2 OR binding.project_id IS NULL)
  AND binding.module_key = $3
ORDER BY CASE WHEN binding.project_id::text = $2 THEN 0 ELSE 1 END
LIMIT 1`
	rows, err := queryWithTenantContext(ctx, r.queryer, tenantID, query,
		strings.TrimSpace(tenantID), strings.TrimSpace(projectID), AssetSearchEmbeddingModuleKey)
	if err != nil {
		return QueryEmbeddingBinding{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: "asset query embedding binding query failed"}
	}
	defer rows.Close()
	if !rows.Next() {
		if rows.Err() != nil {
			return QueryEmbeddingBinding{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: "asset query embedding binding query failed"}
		}
		return QueryEmbeddingBinding{}, &AppError{Code: "LLM_MODULE_UNBOUND", Message: "asset_search_embedding module is not bound"}
	}
	var binding QueryEmbeddingBinding
	var encryptedKey string
	var settingsJSON string
	if err := rows.Scan(&binding.ModuleKey, &binding.ModelID, &binding.Provider, &binding.BaseURL, &encryptedKey, &settingsJSON); err != nil {
		return QueryEmbeddingBinding{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: "asset query embedding binding query failed"}
	}
	apiKey, err := decryptQueryCredential(encryptedKey, r.key)
	if err != nil {
		return QueryEmbeddingBinding{}, err
	}
	binding.APIKey = apiKey
	binding.Settings = decodeSearchSettings(settingsJSON)
	return binding, nil
}

func (r *SQLReader) HasSearchIndex(ctx context.Context, input SearchIndexInput) (bool, error) {
	if err := validateProjectInput(input.TenantID, input.ProjectID); err != nil {
		return false, err
	}
	if strings.TrimSpace(input.EmbeddingModel) == "" || input.Dimensions <= 0 {
		return false, &AppError{Code: "VALIDATION_FAILED", Message: "embedding model and dimensions are required"}
	}
	if r.queryer == nil {
		return false, searchBackendUnconfigured()
	}
	query := `SELECT EXISTS (
  SELECT 1
  FROM asset_embeddings embedding
  JOIN assets asset
    ON asset.tenant_id = embedding.tenant_id
   AND asset.project_id = embedding.project_id
   AND asset.asset_id = embedding.asset_id
   AND asset.enabled = TRUE
  JOIN global_search_index search_doc
    ON search_doc.tenant_id = asset.tenant_id
   AND search_doc.project_id = asset.project_id
   AND search_doc.source = 'asset'
   AND search_doc.source_ref = asset.asset_id::text
  WHERE embedding.tenant_id::text = $1
    AND embedding.project_id::text = $2
    AND embedding.embedding_model = $3
    AND embedding.dimensions = $4
)`
	rows, err := queryWithTenantContext(ctx, r.queryer, input.TenantID, query,
		strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), strings.TrimSpace(input.EmbeddingModel), input.Dimensions)
	if err != nil {
		return false, err
	}
	defer rows.Close()
	if !rows.Next() {
		return false, rows.Err()
	}
	var exists bool
	if err := rows.Scan(&exists); err != nil {
		return false, err
	}
	return exists, rows.Err()
}

type OpenAICompatibleQueryEmbeddingProvider struct {
	client *http.Client
}

func NewOpenAICompatibleQueryEmbeddingProvider(client *http.Client) *OpenAICompatibleQueryEmbeddingProvider {
	if client == nil {
		client = &http.Client{Timeout: 20 * time.Second}
	}
	return &OpenAICompatibleQueryEmbeddingProvider{client: client}
}

func (p *OpenAICompatibleQueryEmbeddingProvider) EmbedQuery(ctx context.Context, input QueryEmbeddingRequest) ([]float64, error) {
	if p == nil || p.client == nil {
		return nil, &AppError{Code: "ASSET_QUERY_EMBEDDING_PROVIDER_UNCONFIGURED", Message: "asset query embedding provider is not configured"}
	}
	if strings.TrimSpace(input.Query) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "query is required"}
	}
	body := map[string]any{"model": input.Binding.ModelID, "input": []string{input.Query}}
	if dimensions, ok := positiveSettingInt(input.Binding.Settings["embedding_dimensions"]); ok {
		body["dimensions"] = dimensions
	}
	encoded, err := json.Marshal(body)
	if err != nil {
		return nil, &AppError{Code: "LLM_PROVIDER_ERROR", Message: "asset query embedding request failed"}
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, embeddingsURL(input.Binding.BaseURL), bytes.NewReader(encoded))
	if err != nil {
		return nil, &AppError{Code: "LLM_PROVIDER_ERROR", Message: "asset query embedding request failed"}
	}
	request.Header.Set("Authorization", "Bearer "+input.Binding.APIKey)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-MiroFish-Tenant-Id", input.TenantID)
	request.Header.Set("X-MiroFish-Project-Id", input.ProjectID)
	request.Header.Set("X-MiroFish-Module-Key", AssetSearchEmbeddingModuleKey)
	response, err := p.client.Do(request)
	if err != nil {
		return nil, &AppError{Code: "LLM_PROVIDER_ERROR", Message: "asset query embedding provider request failed"}
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
		return nil, &AppError{Code: "LLM_PROVIDER_ERROR", Message: "asset query embedding provider request failed"}
	}
	limited := io.LimitReader(response.Body, 8<<20)
	var payload struct {
		Data []struct {
			Index     int       `json:"index"`
			Embedding []float64 `json:"embedding"`
		} `json:"data"`
	}
	decoder := json.NewDecoder(limited)
	if err := decoder.Decode(&payload); err != nil || len(payload.Data) != 1 || payload.Data[0].Index != 0 {
		return nil, &AppError{Code: "ASSET_QUERY_EMBEDDING_INVALID", Message: "asset query embedding provider returned an invalid response"}
	}
	return append([]float64(nil), payload.Data[0].Embedding...), nil
}

func embeddingsURL(baseURL string) string {
	normalized := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if strings.HasSuffix(normalized, "/embeddings") {
		return normalized
	}
	return normalized + "/embeddings"
}

func positiveSettingInt(value any) (int, bool) {
	switch typed := value.(type) {
	case float64:
		if typed > 0 && typed == math.Trunc(typed) {
			return int(typed), true
		}
	case int:
		return typed, typed > 0
	}
	return 0, false
}

func decodeSearchSettings(raw string) map[string]any {
	settings := map[string]any{}
	if json.Unmarshal([]byte(raw), &settings) != nil {
		return map[string]any{}
	}
	return settings
}

func parseQueryCredentialKey(keyMaterial string) ([]byte, error) {
	trimmed := strings.TrimSpace(keyMaterial)
	if trimmed == "" {
		return nil, nil
	}
	if len(trimmed) == 64 {
		if key, err := hex.DecodeString(trimmed); err == nil && len(key) == 32 {
			return key, nil
		}
	}
	key, err := base64.StdEncoding.DecodeString(trimmed)
	if err != nil || len(key) != 32 {
		return nil, &AppError{Code: "LLM_CREDENTIAL_KEY_INVALID", Message: "expected 32-byte AES key material"}
	}
	return key, nil
}

func decryptQueryCredential(envelope string, key []byte) (string, error) {
	parts := strings.Split(strings.TrimSpace(envelope), ":")
	if len(parts) != 5 || parts[0] != "aes-256-gcm" || parts[1] != "v1" {
		return "", &AppError{Code: "LLM_CREDENTIAL_UNAVAILABLE", Message: "asset query embedding credential is unavailable"}
	}
	iv, ivErr := base64.StdEncoding.DecodeString(parts[2])
	tag, tagErr := base64.StdEncoding.DecodeString(parts[3])
	ciphertext, ciphertextErr := base64.StdEncoding.DecodeString(parts[4])
	if ivErr != nil || tagErr != nil || ciphertextErr != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_UNAVAILABLE", Message: "asset query embedding credential is unavailable"}
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_UNAVAILABLE", Message: "asset query embedding credential is unavailable"}
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_UNAVAILABLE", Message: "asset query embedding credential is unavailable"}
	}
	plaintext, err := gcm.Open(nil, iv, append(ciphertext, tag...), nil)
	if err != nil || strings.TrimSpace(string(plaintext)) == "" {
		return "", &AppError{Code: "LLM_CREDENTIAL_UNAVAILABLE", Message: "asset query embedding credential is unavailable"}
	}
	return strings.TrimSpace(string(plaintext)), nil
}
