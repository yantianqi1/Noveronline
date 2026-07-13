package llm

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

type ModelSyncInput struct {
	TenantID  string
	ChannelID string
}

type ModelSyncResult struct {
	Channel ChannelRecord `json:"channel"`
	Models  []ModelRecord `json:"models"`
}

type ProviderListModelsInput struct {
	Provider              string
	BaseURL               string
	APIKey                string
	ExternalProviderOptIn bool
}

type ProviderModel struct {
	ModelID string `json:"model_id"`
	OwnedBy string `json:"owned_by,omitempty"`
}

type ModelProvider interface {
	ListModels(context.Context, ProviderListModelsInput) ([]ProviderModel, error)
}

type ModelSyncer interface {
	SyncModels(context.Context, ModelSyncInput) (ModelSyncResult, error)
}

type DisabledModelSyncer struct{}

func NewDisabledModelSyncer() DisabledModelSyncer {
	return DisabledModelSyncer{}
}

func (DisabledModelSyncer) SyncModels(context.Context, ModelSyncInput) (ModelSyncResult, error) {
	return ModelSyncResult{}, &AppError{
		Code:    "LLM_MODEL_SYNC_BACKEND_UNCONFIGURED",
		Message: "LLM model sync backend is not configured",
	}
}

type SQLModelSyncerConfig struct {
	Queryer               SQLQueryer
	CredentialKeyMaterial string
	Provider              ModelProvider
}

type SQLModelSyncer struct {
	queryer  SQLQueryer
	key      []byte
	keyErr   error
	provider ModelProvider
}

func NewSQLModelSyncer(config SQLModelSyncerConfig) *SQLModelSyncer {
	key, err := parseCredentialKey(config.CredentialKeyMaterial)
	provider := config.Provider
	if provider == nil {
		provider = NewOpenAICompatibleModelProvider(nil)
	}
	return &SQLModelSyncer{
		queryer:  config.Queryer,
		key:      key,
		keyErr:   err,
		provider: provider,
	}
}

type syncChannelCredential struct {
	channel      ChannelRecord
	encryptedKey string
}

func (s *SQLModelSyncer) SyncModels(ctx context.Context, input ModelSyncInput) (ModelSyncResult, error) {
	if err := validateModelSyncInput(input); err != nil {
		return ModelSyncResult{}, err
	}
	if s.queryer == nil {
		return ModelSyncResult{}, &AppError{
			Code:    "LLM_MODEL_SYNC_BACKEND_UNCONFIGURED",
			Message: "LLM model sync backend is not configured",
		}
	}
	if s.keyErr != nil {
		return ModelSyncResult{}, s.keyErr
	}
	if len(s.key) != 32 {
		return ModelSyncResult{}, &AppError{
			Code:    "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED",
			Message: "LLM credential encryption key is not configured",
		}
	}
	if s.provider == nil {
		return ModelSyncResult{}, &AppError{
			Code:    "LLM_MODEL_PROVIDER_UNCONFIGURED",
			Message: "LLM model provider is not configured",
		}
	}
	channel, err := s.loadTenantChannelCredential(ctx, input)
	if err != nil {
		return ModelSyncResult{}, err
	}
	apiKey, err := decryptCredentialEnvelope(channel.encryptedKey, s.key)
	if err != nil {
		return ModelSyncResult{}, err
	}
	models, err := s.provider.ListModels(ctx, ProviderListModelsInput{
		Provider:              channel.channel.Provider,
		BaseURL:               channel.channel.BaseURL,
		APIKey:                apiKey,
		ExternalProviderOptIn: channel.channel.ExternalProviderOptIn,
	})
	if err != nil {
		status := "failed:" + modelSyncErrorCode(err)
		if _, statusErr := s.recordFailure(ctx, input, status); statusErr != nil {
			return ModelSyncResult{}, statusErr
		}
		return ModelSyncResult{}, normalizeProviderError(err)
	}
	return s.upsertModels(ctx, input, models)
}

func (s *SQLModelSyncer) loadTenantChannelCredential(ctx context.Context, input ModelSyncInput) (syncChannelCredential, error) {
	query := `SELECT
  channel_id::text,
  name,
  provider,
  base_url,
  encrypted_api_key,
  max_concurrency,
  external_provider_opt_in,
  enabled,
  created_at::text,
  updated_at::text
FROM llm_channels
WHERE tenant_id::text = $1
  AND channel_id::text = $2
  AND enabled = TRUE
LIMIT 1`
	rows, err := s.queryTenantRows(ctx, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ChannelID))
	if err != nil {
		return syncChannelCredential{}, &AppError{Code: "LLM_MODEL_SYNC_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return syncChannelCredential{}, &AppError{Code: "LLM_MODEL_SYNC_QUERY_FAILED", Message: err.Error()}
		}
		return syncChannelCredential{}, &AppError{Code: "LLM_CHANNEL_NOT_FOUND", Message: "channel is not available for model sync"}
	}
	var record syncChannelCredential
	if err := rows.Scan(
		&record.channel.ChannelID,
		&record.channel.Name,
		&record.channel.Provider,
		&record.channel.BaseURL,
		&record.encryptedKey,
		&record.channel.MaxConcurrency,
		&record.channel.ExternalProviderOptIn,
		&record.channel.Enabled,
		&record.channel.CreatedAt,
		&record.channel.UpdatedAt,
	); err != nil {
		return syncChannelCredential{}, &AppError{Code: "LLM_MODEL_SYNC_QUERY_FAILED", Message: err.Error()}
	}
	record.channel.Scope = "tenant"
	if err := rows.Err(); err != nil {
		return syncChannelCredential{}, &AppError{Code: "LLM_MODEL_SYNC_QUERY_FAILED", Message: err.Error()}
	}
	return record, nil
}

func (s *SQLModelSyncer) upsertModels(ctx context.Context, input ModelSyncInput, models []ProviderModel) (ModelSyncResult, error) {
	modelsJSON, err := json.Marshal(sanitizeProviderModels(models))
	if err != nil {
		return ModelSyncResult{}, &AppError{Code: "LLM_MODEL_SYNC_FAILED", Message: "provider models must be JSON serializable"}
	}
	status := fmt.Sprintf("ok:%d", len(models))
	query := `WITH incoming AS (
  SELECT model_id, owned_by
  FROM jsonb_to_recordset($3::jsonb) AS model(model_id TEXT, owned_by TEXT)
), upserted AS (
  INSERT INTO llm_models (
    tenant_id, channel_id, model_id, owned_by, updated_at
  )
  SELECT $1::uuid, c.channel_id, incoming.model_id, NULLIF(incoming.owned_by, ''), now()
  FROM llm_channels c
  JOIN incoming ON incoming.model_id IS NOT NULL AND incoming.model_id <> ''
  WHERE c.tenant_id = $1::uuid
    AND c.channel_id = $2::uuid
  ON CONFLICT (channel_id, model_id) DO UPDATE SET
    owned_by = EXCLUDED.owned_by,
    updated_at = now()
  RETURNING
    model_id,
    COALESCE(owned_by, '') AS owned_by,
    COALESCE(context_window, 0) AS context_window,
    supports_tools,
    supports_json,
    COALESCE(input_cost, 0)::float8 AS input_cost,
    COALESCE(output_cost, 0)::float8 AS output_cost,
    created_at::text,
    updated_at::text
), marked AS (
  UPDATE llm_channels
  SET last_sync_at = now(),
      last_sync_status = $4,
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND channel_id = $2::uuid
  RETURNING
    channel_id::text,
    name,
    provider,
    base_url,
    max_concurrency,
    external_provider_opt_in,
    enabled,
    COALESCE(last_sync_at::text, '') AS last_sync_at,
    COALESCE(last_sync_status, '') AS last_sync_status,
    'tenant' AS scope,
    created_at::text,
    updated_at::text
)
SELECT
  marked.channel_id,
  marked.name,
  marked.provider,
  marked.base_url,
  marked.max_concurrency,
  marked.external_provider_opt_in,
  marked.enabled,
  marked.last_sync_at,
  marked.last_sync_status,
  marked.scope,
  marked.created_at,
  marked.updated_at,
  COALESCE(upserted.model_id, ''),
  COALESCE(upserted.owned_by, ''),
  COALESCE(upserted.context_window, 0),
  COALESCE(upserted.supports_tools, false),
  COALESCE(upserted.supports_json, false),
  COALESCE(upserted.input_cost, 0)::float8,
  COALESCE(upserted.output_cost, 0)::float8,
  COALESCE(upserted.created_at, ''),
  COALESCE(upserted.updated_at, '')
FROM marked
LEFT JOIN upserted ON TRUE
ORDER BY upserted.model_id ASC`
	rows, err := s.queryTenantWriteRows(ctx, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ChannelID), string(modelsJSON), status)
	if err != nil {
		return ModelSyncResult{}, &AppError{Code: "LLM_MODEL_SYNC_FAILED", Message: err.Error()}
	}
	result, scanErr := scanModelSyncRows(rows)
	closeErr := rows.Close()
	if scanErr != nil {
		return ModelSyncResult{}, scanErr
	}
	if closeErr != nil {
		return ModelSyncResult{}, &AppError{Code: "LLM_MODEL_SYNC_FAILED", Message: closeErr.Error()}
	}
	return result, nil
}

func (s *SQLModelSyncer) recordFailure(ctx context.Context, input ModelSyncInput, status string) (ChannelRecord, error) {
	query := `UPDATE llm_channels
SET last_sync_at = now(),
    last_sync_status = $3,
    updated_at = now()
WHERE tenant_id = $1::uuid
  AND channel_id = $2::uuid
RETURNING
  channel_id::text,
  name,
  provider,
  base_url,
  max_concurrency,
  external_provider_opt_in,
  enabled,
  COALESCE(last_sync_at::text, ''),
  COALESCE(last_sync_status, ''),
  'tenant' AS scope,
  created_at::text,
  updated_at::text`
	rows, err := s.queryTenantWriteRows(ctx, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ChannelID), status)
	if err != nil {
		return ChannelRecord{}, &AppError{Code: "LLM_MODEL_SYNC_STATUS_FAILED", Message: err.Error()}
	}
	result, scanErr := scanSingleChannel(rows, "LLM_MODEL_SYNC_STATUS_FAILED", "channel sync status was not updated")
	closeErr := rows.Close()
	if scanErr != nil {
		return ChannelRecord{}, scanErr
	}
	if closeErr != nil {
		return ChannelRecord{}, &AppError{Code: "LLM_MODEL_SYNC_STATUS_FAILED", Message: closeErr.Error()}
	}
	return result, nil
}

func (s *SQLModelSyncer) queryTenantRows(ctx context.Context, tenantID, query string, args ...any) (SQLRows, error) {
	if queryer, ok := s.queryer.(SQLTenantQueryer); ok {
		return queryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return s.queryer.QueryContext(ctx, query, args...)
}

func (s *SQLModelSyncer) queryTenantWriteRows(ctx context.Context, tenantID, query string, args ...any) (SQLRows, error) {
	if queryer, ok := s.queryer.(SQLTenantWriteQueryer); ok {
		return queryer.QueryTenantWriteContext(ctx, tenantID, query, args...)
	}
	return s.queryer.QueryContext(ctx, query, args...)
}

func scanModelSyncRows(rows SQLRows) (ModelSyncResult, error) {
	result := ModelSyncResult{Models: []ModelRecord{}}
	for rows.Next() {
		var channel ChannelRecord
		var model ModelRecord
		if err := rows.Scan(
			&channel.ChannelID,
			&channel.Name,
			&channel.Provider,
			&channel.BaseURL,
			&channel.MaxConcurrency,
			&channel.ExternalProviderOptIn,
			&channel.Enabled,
			&channel.LastSyncAt,
			&channel.LastSyncStatus,
			&channel.Scope,
			&channel.CreatedAt,
			&channel.UpdatedAt,
			&model.ModelID,
			&model.OwnedBy,
			&model.ContextWindow,
			&model.SupportsTools,
			&model.SupportsJSON,
			&model.InputCost,
			&model.OutputCost,
			&model.CreatedAt,
			&model.UpdatedAt,
		); err != nil {
			return ModelSyncResult{}, &AppError{Code: "LLM_MODEL_SYNC_FAILED", Message: err.Error()}
		}
		if result.Channel.ChannelID == "" {
			result.Channel = channel
		}
		if strings.TrimSpace(model.ModelID) != "" {
			result.Models = append(result.Models, model)
		}
	}
	if err := rows.Err(); err != nil {
		return ModelSyncResult{}, &AppError{Code: "LLM_MODEL_SYNC_FAILED", Message: err.Error()}
	}
	if result.Channel.ChannelID == "" {
		return ModelSyncResult{}, &AppError{Code: "LLM_MODEL_SYNC_FAILED", Message: "channel sync result was empty"}
	}
	return result, nil
}

func validateModelSyncInput(input ModelSyncInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ChannelID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and channel_id are required"}
	}
	return nil
}

func sanitizeProviderModels(models []ProviderModel) []ProviderModel {
	sanitized := make([]ProviderModel, 0, len(models))
	seen := map[string]bool{}
	for _, model := range models {
		modelID := strings.TrimSpace(model.ModelID)
		if modelID == "" || seen[modelID] {
			continue
		}
		seen[modelID] = true
		sanitized = append(sanitized, ProviderModel{
			ModelID: modelID,
			OwnedBy: strings.TrimSpace(model.OwnedBy),
		})
	}
	return sanitized
}

func decryptCredentialEnvelope(envelope string, key []byte) (string, error) {
	parts := strings.Split(strings.TrimSpace(envelope), ":")
	if len(parts) != 5 || parts[0] != "aes-256-gcm" || parts[1] != "v1" {
		return "", &AppError{Code: "LLM_CREDENTIAL_DECRYPTION_FAILED", Message: "unsupported credential envelope"}
	}
	iv, err := base64.StdEncoding.DecodeString(parts[2])
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_DECRYPTION_FAILED", Message: "invalid credential nonce"}
	}
	tag, err := base64.StdEncoding.DecodeString(parts[3])
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_DECRYPTION_FAILED", Message: "invalid credential tag"}
	}
	ciphertext, err := base64.StdEncoding.DecodeString(parts[4])
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_DECRYPTION_FAILED", Message: "invalid credential ciphertext"}
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_DECRYPTION_FAILED", Message: err.Error()}
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_DECRYPTION_FAILED", Message: err.Error()}
	}
	sealed := append(append([]byte{}, ciphertext...), tag...)
	plaintext, err := gcm.Open(nil, iv, sealed, nil)
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_DECRYPTION_FAILED", Message: "credential decrypt failed"}
	}
	return string(plaintext), nil
}

func modelSyncErrorCode(err error) string {
	code := ErrorCode(err)
	if code == "" {
		return "LLM_PROVIDER_ERROR"
	}
	return code
}

func normalizeProviderError(err error) error {
	if code := ErrorCode(err); code != "" {
		return err
	}
	return &AppError{Code: "LLM_PROVIDER_ERROR", Message: err.Error()}
}

type OpenAICompatibleModelProvider struct {
	client *http.Client
}

func NewOpenAICompatibleModelProvider(client *http.Client) *OpenAICompatibleModelProvider {
	if client == nil {
		client = &http.Client{Timeout: 20 * time.Second}
	}
	return &OpenAICompatibleModelProvider{client: client}
}

func (p *OpenAICompatibleModelProvider) ListModels(ctx context.Context, input ProviderListModelsInput) ([]ProviderModel, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(input.BaseURL), "/")
	if baseURL == "" || strings.TrimSpace(input.APIKey) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "base_url and api_key are required"}
	}
	endpoint, err := validateProviderEndpoint(baseURL, "/models", input.ExternalProviderOptIn)
	if err != nil {
		return nil, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, &AppError{Code: "LLM_PROVIDER_REQUEST_INVALID", Message: "LLM provider request is invalid"}
	}
	request.Header.Set("Authorization", "Bearer "+strings.TrimSpace(input.APIKey))
	request.Header.Set("Accept", "application/json")
	response, err := p.client.Do(request)
	if err != nil {
		return nil, stableProviderContextError(err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, providerStatusError(response.StatusCode)
	}
	var payload struct {
		Data []struct {
			ID      string `json:"id"`
			OwnedBy string `json:"owned_by"`
		} `json:"data"`
	}
	decoder := json.NewDecoder(response.Body)
	if err := decoder.Decode(&payload); err != nil {
		return nil, &AppError{Code: "LLM_PROVIDER_ERROR", Message: "model catalog response was not valid JSON"}
	}
	models := make([]ProviderModel, 0, len(payload.Data))
	for _, item := range payload.Data {
		models = append(models, ProviderModel{ModelID: item.ID, OwnedBy: item.OwnedBy})
	}
	return sanitizeProviderModels(models), nil
}
