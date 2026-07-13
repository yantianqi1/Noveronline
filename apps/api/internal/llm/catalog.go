package llm

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"strings"
)

type CatalogQueryInput struct {
	TenantID  string
	ProjectID string
}

type ModelQueryInput struct {
	TenantID  string
	ProjectID string
	ChannelID string
}

type ChannelRecord struct {
	ChannelID             string `json:"channel_id"`
	Name                  string `json:"name"`
	Provider              string `json:"provider"`
	BaseURL               string `json:"base_url"`
	MaxConcurrency        int    `json:"max_concurrency"`
	ExternalProviderOptIn bool   `json:"external_provider_opt_in"`
	Enabled               bool   `json:"enabled"`
	LastSyncAt            string `json:"last_sync_at,omitempty"`
	LastSyncStatus        string `json:"last_sync_status,omitempty"`
	Scope                 string `json:"scope"`
	CreatedAt             string `json:"created_at"`
	UpdatedAt             string `json:"updated_at"`
}

type ModelRecord struct {
	ModelID       string  `json:"model_id"`
	OwnedBy       string  `json:"owned_by,omitempty"`
	ContextWindow int     `json:"context_window,omitempty"`
	SupportsTools bool    `json:"supports_tools"`
	SupportsJSON  bool    `json:"supports_json"`
	InputCost     float64 `json:"input_cost,omitempty"`
	OutputCost    float64 `json:"output_cost,omitempty"`
	CreatedAt     string  `json:"created_at"`
	UpdatedAt     string  `json:"updated_at"`
}

type CreateChannelInput struct {
	TenantID              string
	Name                  string
	Provider              string
	BaseURL               string
	APIKey                string
	MaxConcurrency        int
	ExternalProviderOptIn bool
	Enabled               bool
}

type UpdateChannelInput struct {
	TenantID              string
	ChannelID             string
	Name                  string
	BaseURL               string
	APIKey                string
	MaxConcurrency        int
	ExternalProviderOptIn bool
	Enabled               bool
}

type DeleteChannelInput struct {
	TenantID  string
	ChannelID string
}

type UpdateModelInput struct {
	TenantID      string
	ChannelID     string
	ModelID       string
	ContextWindow *int
	SupportsTools bool
	SupportsJSON  bool
	InputCost     *float64
	OutputCost    *float64
}

type CatalogReader interface {
	ListChannels(context.Context, CatalogQueryInput) ([]ChannelRecord, error)
	ListModels(context.Context, ModelQueryInput) ([]ModelRecord, error)
}

type ChannelStore interface {
	CreateChannel(context.Context, CreateChannelInput) (ChannelRecord, error)
	UpdateChannel(context.Context, UpdateChannelInput) (ChannelRecord, error)
	DeleteChannel(context.Context, DeleteChannelInput) (ChannelRecord, error)
}

type ModelStore interface {
	UpdateModel(context.Context, UpdateModelInput) (ModelRecord, error)
}

type DisabledCatalogReader struct{}

func NewDisabledCatalogReader() DisabledCatalogReader {
	return DisabledCatalogReader{}
}

func (DisabledCatalogReader) ListChannels(context.Context, CatalogQueryInput) ([]ChannelRecord, error) {
	return nil, &AppError{
		Code:    "LLM_CATALOG_BACKEND_UNCONFIGURED",
		Message: "LLM catalog backend is not configured",
	}
}

func (DisabledCatalogReader) ListModels(context.Context, ModelQueryInput) ([]ModelRecord, error) {
	return nil, &AppError{
		Code:    "LLM_CATALOG_BACKEND_UNCONFIGURED",
		Message: "LLM catalog backend is not configured",
	}
}

type DisabledChannelStore struct{}

func NewDisabledChannelStore() DisabledChannelStore {
	return DisabledChannelStore{}
}

func (DisabledChannelStore) CreateChannel(context.Context, CreateChannelInput) (ChannelRecord, error) {
	return ChannelRecord{}, &AppError{
		Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
		Message: "LLM channel backend is not configured",
	}
}

type DisabledModelStore struct{}

func NewDisabledModelStore() DisabledModelStore {
	return DisabledModelStore{}
}

func (DisabledModelStore) UpdateModel(context.Context, UpdateModelInput) (ModelRecord, error) {
	return ModelRecord{}, &AppError{
		Code:    "LLM_MODEL_BACKEND_UNCONFIGURED",
		Message: "LLM model backend is not configured",
	}
}

func (DisabledChannelStore) UpdateChannel(context.Context, UpdateChannelInput) (ChannelRecord, error) {
	return ChannelRecord{}, &AppError{
		Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
		Message: "LLM channel backend is not configured",
	}
}

func (DisabledChannelStore) DeleteChannel(context.Context, DeleteChannelInput) (ChannelRecord, error) {
	return ChannelRecord{}, &AppError{
		Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
		Message: "LLM channel backend is not configured",
	}
}

type SQLCatalogConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLCatalogReader struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLCatalogReader(config SQLCatalogConfig) *SQLCatalogReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLCatalogReader{queryer: config.Queryer, limit: limit}
}

type SQLChannelStoreConfig struct {
	Queryer               SQLQueryer
	CredentialKeyMaterial string
}

type SQLChannelStore struct {
	queryer SQLQueryer
	key     []byte
}

func NewSQLChannelStore(config SQLChannelStoreConfig) *SQLChannelStore {
	key, _ := parseCredentialKey(config.CredentialKeyMaterial)
	return &SQLChannelStore{queryer: config.Queryer, key: key}
}

func (r *SQLCatalogReader) ListChannels(ctx context.Context, input CatalogQueryInput) ([]ChannelRecord, error) {
	if err := validateCatalogInput(input); err != nil {
		return nil, err
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "LLM_CATALOG_BACKEND_UNCONFIGURED",
			Message: "LLM catalog backend is not configured",
		}
	}
	tenantQueryer, ok := r.queryer.(SQLTenantQueryer)
	if !ok {
		return nil, &AppError{
			Code:    "LLM_CATALOG_BACKEND_UNCONFIGURED",
			Message: "LLM catalog backend does not support tenant-scoped queries",
		}
	}
	query := `SELECT
  channel_id::text,
  name,
  provider,
  base_url,
  max_concurrency,
  external_provider_opt_in,
  enabled,
  COALESCE(last_sync_at::text, ''),
  COALESCE(last_sync_status, ''),
  CASE WHEN tenant_id IS NULL THEN 'platform' ELSE 'tenant' END AS scope,
  created_at::text,
  updated_at::text
FROM llm_channels
WHERE (tenant_id::text = $1 OR tenant_id IS NULL)
ORDER BY scope DESC, name ASC, channel_id::text ASC
LIMIT $2`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantQueryer.QueryTenantContext(ctx, tenantID, query, tenantID, r.limit)
	if err != nil {
		return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
	}

	records := []ChannelRecord{}
	for rows.Next() {
		var record ChannelRecord
		if err := rows.Scan(
			&record.ChannelID,
			&record.Name,
			&record.Provider,
			&record.BaseURL,
			&record.MaxConcurrency,
			&record.ExternalProviderOptIn,
			&record.Enabled,
			&record.LastSyncAt,
			&record.LastSyncStatus,
			&record.Scope,
			&record.CreatedAt,
			&record.UpdatedAt,
		); err != nil {
			_ = rows.Close()
			return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
	}
	if err := rows.Close(); err != nil {
		return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func (r *SQLCatalogReader) ListModels(ctx context.Context, input ModelQueryInput) ([]ModelRecord, error) {
	if err := validateModelQueryInput(input); err != nil {
		return nil, err
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "LLM_CATALOG_BACKEND_UNCONFIGURED",
			Message: "LLM catalog backend is not configured",
		}
	}
	tenantQueryer, ok := r.queryer.(SQLTenantQueryer)
	if !ok {
		return nil, &AppError{
			Code:    "LLM_CATALOG_BACKEND_UNCONFIGURED",
			Message: "LLM catalog backend does not support tenant-scoped queries",
		}
	}
	query := `SELECT
  m.model_id,
  COALESCE(m.owned_by, ''),
  COALESCE(m.context_window, 0),
  m.supports_tools,
  m.supports_json,
  COALESCE(m.input_cost, 0)::float8,
  COALESCE(m.output_cost, 0)::float8,
  m.created_at::text,
  m.updated_at::text
FROM llm_models m
JOIN llm_channels c
  ON c.channel_id = m.channel_id
WHERE (c.tenant_id::text = $1 OR c.tenant_id IS NULL)
  AND (m.tenant_id::text = $1 OR m.tenant_id IS NULL)
  AND c.channel_id::text = $2
ORDER BY m.model_id ASC
LIMIT $3`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantQueryer.QueryTenantContext(ctx, tenantID, query, tenantID, strings.TrimSpace(input.ChannelID), r.limit)
	if err != nil {
		return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
	}

	records := []ModelRecord{}
	for rows.Next() {
		var record ModelRecord
		if err := rows.Scan(
			&record.ModelID,
			&record.OwnedBy,
			&record.ContextWindow,
			&record.SupportsTools,
			&record.SupportsJSON,
			&record.InputCost,
			&record.OutputCost,
			&record.CreatedAt,
			&record.UpdatedAt,
		); err != nil {
			_ = rows.Close()
			return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
	}
	if err := rows.Close(); err != nil {
		return nil, &AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func (s *SQLChannelStore) CreateChannel(ctx context.Context, input CreateChannelInput) (ChannelRecord, error) {
	if err := validateCreateChannelInput(input); err != nil {
		return ChannelRecord{}, err
	}
	if s.queryer == nil {
		return ChannelRecord{}, &AppError{
			Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
			Message: "LLM channel backend is not configured",
		}
	}
	tenantWriteQueryer, ok := s.queryer.(SQLTenantWriteQueryer)
	if !ok {
		return ChannelRecord{}, &AppError{
			Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
			Message: "LLM channel backend does not support tenant-scoped writes",
		}
	}
	encryptedAPIKey, err := s.encryptCredential(strings.TrimSpace(input.APIKey))
	if err != nil {
		return ChannelRecord{}, err
	}
	query := `INSERT INTO llm_channels (
  tenant_id, name, provider, base_url, encrypted_api_key, max_concurrency, external_provider_opt_in, enabled, updated_at
) VALUES (
  $1, $2, $3, $4, $5, $6, $7, $8, now()
) RETURNING
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
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantWriteQueryer.QueryTenantWriteContext(
		ctx,
		tenantID,
		query,
		tenantID,
		strings.TrimSpace(input.Name),
		strings.TrimSpace(input.Provider),
		strings.TrimSpace(input.BaseURL),
		encryptedAPIKey,
		input.MaxConcurrency,
		input.ExternalProviderOptIn,
		input.Enabled,
	)
	if err != nil {
		return ChannelRecord{}, &AppError{Code: "LLM_CHANNEL_UPDATE_FAILED", Message: err.Error()}
	}
	return finishChannelWrite(rows, "channel was not created")
}

func (s *SQLChannelStore) UpdateChannel(ctx context.Context, input UpdateChannelInput) (ChannelRecord, error) {
	if err := validateUpdateChannelInput(input); err != nil {
		return ChannelRecord{}, err
	}
	if s.queryer == nil {
		return ChannelRecord{}, &AppError{
			Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
			Message: "LLM channel backend is not configured",
		}
	}
	tenantWriteQueryer, ok := s.queryer.(SQLTenantWriteQueryer)
	if !ok {
		return ChannelRecord{}, &AppError{
			Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
			Message: "LLM channel backend does not support tenant-scoped writes",
		}
	}
	encryptedAPIKey := ""
	if strings.TrimSpace(input.APIKey) != "" {
		var err error
		encryptedAPIKey, err = s.encryptCredential(strings.TrimSpace(input.APIKey))
		if err != nil {
			return ChannelRecord{}, err
		}
	}
	query := `UPDATE llm_channels
SET name = $3,
    base_url = $4,
    max_concurrency = $5,
    encrypted_api_key = COALESCE(NULLIF($6, ''), encrypted_api_key),
    external_provider_opt_in = $7,
    enabled = $8,
    updated_at = now()
WHERE tenant_id::text = $1
  AND channel_id::text = $2
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
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantWriteQueryer.QueryTenantWriteContext(
		ctx,
		tenantID,
		query,
		tenantID,
		strings.TrimSpace(input.ChannelID),
		strings.TrimSpace(input.Name),
		strings.TrimSpace(input.BaseURL),
		input.MaxConcurrency,
		encryptedAPIKey,
		input.ExternalProviderOptIn,
		input.Enabled,
	)
	if err != nil {
		return ChannelRecord{}, &AppError{Code: "LLM_CHANNEL_UPDATE_FAILED", Message: err.Error()}
	}
	return finishChannelWrite(rows, "channel was not updated")
}

func (s *SQLChannelStore) UpdateModel(ctx context.Context, input UpdateModelInput) (ModelRecord, error) {
	if err := validateUpdateModelInput(input); err != nil {
		return ModelRecord{}, err
	}
	if s.queryer == nil {
		return ModelRecord{}, &AppError{
			Code:    "LLM_MODEL_BACKEND_UNCONFIGURED",
			Message: "LLM model backend is not configured",
		}
	}
	tenantWriteQueryer, ok := s.queryer.(SQLTenantWriteQueryer)
	if !ok {
		return ModelRecord{}, &AppError{
			Code:    "LLM_MODEL_BACKEND_UNCONFIGURED",
			Message: "LLM model backend does not support tenant-scoped writes",
		}
	}
	// Tenant-owned models only. Platform catalog rows (tenant_id IS NULL) stay read-only.
	query := `UPDATE llm_models AS model
SET context_window = $4,
    supports_tools = $5,
    supports_json = $6,
    input_cost = $7,
    output_cost = $8,
    updated_at = now()
WHERE model.tenant_id::text = $1
  AND model.channel_id::text = $2
  AND model.model_id = $3
RETURNING
  model.model_id,
  COALESCE(model.owned_by, ''),
  COALESCE(model.context_window, 0),
  model.supports_tools,
  model.supports_json,
  COALESCE(model.input_cost, 0)::float8,
  COALESCE(model.output_cost, 0)::float8,
  model.created_at::text,
  model.updated_at::text`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantWriteQueryer.QueryTenantWriteContext(
		ctx,
		tenantID,
		query,
		tenantID,
		strings.TrimSpace(input.ChannelID),
		strings.TrimSpace(input.ModelID),
		nullablePositiveInt(input.ContextWindow),
		input.SupportsTools,
		input.SupportsJSON,
		nullableNonNegativeFloat(input.InputCost),
		nullableNonNegativeFloat(input.OutputCost),
	)
	if err != nil {
		return ModelRecord{}, &AppError{Code: "LLM_MODEL_UPDATE_FAILED", Message: err.Error()}
	}
	return finishModelWrite(rows, "model was not updated")
}

func (s *SQLChannelStore) DeleteChannel(ctx context.Context, input DeleteChannelInput) (ChannelRecord, error) {
	if err := validateDeleteChannelInput(input); err != nil {
		return ChannelRecord{}, err
	}
	if s.queryer == nil {
		return ChannelRecord{}, &AppError{
			Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
			Message: "LLM channel backend is not configured",
		}
	}
	tenantWriteQueryer, ok := s.queryer.(SQLTenantWriteQueryer)
	if !ok {
		return ChannelRecord{}, &AppError{
			Code:    "LLM_CHANNEL_BACKEND_UNCONFIGURED",
			Message: "LLM channel backend does not support tenant-scoped writes",
		}
	}
	query := `UPDATE llm_channels
SET enabled = FALSE,
    updated_at = now()
WHERE tenant_id::text = $1
  AND channel_id::text = $2
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
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantWriteQueryer.QueryTenantWriteContext(ctx, tenantID, query, tenantID, strings.TrimSpace(input.ChannelID))
	if err != nil {
		return ChannelRecord{}, &AppError{Code: "LLM_CHANNEL_UPDATE_FAILED", Message: err.Error()}
	}
	return finishChannelWrite(rows, "channel was not disabled")
}

func finishChannelWrite(rows SQLRows, missingMessage string) (ChannelRecord, error) {
	record, scanErr := scanSingleChannel(rows, "LLM_CHANNEL_UPDATE_FAILED", missingMessage)
	closeErr := rows.Close()
	if scanErr != nil {
		return ChannelRecord{}, scanErr
	}
	if closeErr != nil {
		return ChannelRecord{}, &AppError{Code: "LLM_CHANNEL_UPDATE_FAILED", Message: closeErr.Error()}
	}
	return record, nil
}

func (s *SQLChannelStore) encryptCredential(apiKey string) (string, error) {
	if len(s.key) != 32 {
		return "", &AppError{
			Code:    "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED",
			Message: "LLM credential encryption key is not configured",
		}
	}
	block, err := aes.NewCipher(s.key)
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_ENCRYPTION_FAILED", Message: err.Error()}
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_ENCRYPTION_FAILED", Message: err.Error()}
	}
	iv := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, iv); err != nil {
		return "", &AppError{Code: "LLM_CREDENTIAL_ENCRYPTION_FAILED", Message: err.Error()}
	}
	sealed := gcm.Seal(nil, iv, []byte(apiKey), nil)
	tagStart := len(sealed) - gcm.Overhead()
	ciphertext := sealed[:tagStart]
	tag := sealed[tagStart:]
	return fmt.Sprintf(
		"aes-256-gcm:v1:%s:%s:%s",
		base64.StdEncoding.EncodeToString(iv),
		base64.StdEncoding.EncodeToString(tag),
		base64.StdEncoding.EncodeToString(ciphertext),
	), nil
}

func validateCatalogInput(input CatalogQueryInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	return nil
}

func validateModelQueryInput(input ModelQueryInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.ChannelID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and channel_id are required"}
	}
	return nil
}

func validateCreateChannelInput(input CreateChannelInput) error {
	if strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.Name) == "" ||
		strings.TrimSpace(input.Provider) == "" ||
		strings.TrimSpace(input.BaseURL) == "" ||
		strings.TrimSpace(input.APIKey) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, name, provider, base_url, and api_key are required"}
	}
	if input.MaxConcurrency <= 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "max_concurrency must be greater than zero"}
	}
	if _, err := validateProviderEndpoint(input.BaseURL, "", input.ExternalProviderOptIn); err != nil {
		return err
	}
	return nil
}

func validateUpdateChannelInput(input UpdateChannelInput) error {
	if strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ChannelID) == "" ||
		strings.TrimSpace(input.Name) == "" ||
		strings.TrimSpace(input.BaseURL) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, channel_id, name, and base_url are required"}
	}
	if input.MaxConcurrency <= 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "max_concurrency must be greater than zero"}
	}
	if _, err := validateProviderEndpoint(input.BaseURL, "", input.ExternalProviderOptIn); err != nil {
		return err
	}
	return nil
}

func validateDeleteChannelInput(input DeleteChannelInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ChannelID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and channel_id are required"}
	}
	return nil
}

func validateUpdateModelInput(input UpdateModelInput) error {
	if strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ChannelID) == "" ||
		strings.TrimSpace(input.ModelID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, channel_id, and model_id are required"}
	}
	if input.ContextWindow != nil && *input.ContextWindow <= 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "context_window must be greater than zero when set"}
	}
	if input.InputCost != nil && *input.InputCost < 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "input_cost must be non-negative when set"}
	}
	if input.OutputCost != nil && *input.OutputCost < 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "output_cost must be non-negative when set"}
	}
	return nil
}

func nullablePositiveInt(value *int) any {
	if value == nil {
		return nil
	}
	return *value
}

func nullableNonNegativeFloat(value *float64) any {
	if value == nil {
		return nil
	}
	return *value
}

func finishModelWrite(rows SQLRows, missingMessage string) (ModelRecord, error) {
	record, scanErr := scanSingleModel(rows, "LLM_MODEL_UPDATE_FAILED", missingMessage)
	closeErr := rows.Close()
	if scanErr != nil {
		return ModelRecord{}, scanErr
	}
	if closeErr != nil {
		return ModelRecord{}, &AppError{Code: "LLM_MODEL_UPDATE_FAILED", Message: closeErr.Error()}
	}
	return record, nil
}

func scanSingleModel(rows SQLRows, code string, missingMessage string) (ModelRecord, error) {
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return ModelRecord{}, &AppError{Code: code, Message: err.Error()}
		}
		return ModelRecord{}, &AppError{Code: "LLM_MODEL_NOT_FOUND", Message: missingMessage}
	}
	var record ModelRecord
	if err := rows.Scan(
		&record.ModelID,
		&record.OwnedBy,
		&record.ContextWindow,
		&record.SupportsTools,
		&record.SupportsJSON,
		&record.InputCost,
		&record.OutputCost,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return ModelRecord{}, &AppError{Code: code, Message: err.Error()}
	}
	if rows.Next() {
		return ModelRecord{}, &AppError{Code: code, Message: "model mutation returned multiple rows"}
	}
	if err := rows.Err(); err != nil {
		return ModelRecord{}, &AppError{Code: code, Message: err.Error()}
	}
	return record, nil
}

func scanSingleChannel(rows SQLRows, code string, missingMessage string) (ChannelRecord, error) {
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return ChannelRecord{}, &AppError{Code: code, Message: err.Error()}
		}
		return ChannelRecord{}, &AppError{Code: "LLM_CHANNEL_NOT_FOUND", Message: missingMessage}
	}
	record, err := scanChannelRecord(rows)
	if err != nil {
		return ChannelRecord{}, &AppError{Code: code, Message: err.Error()}
	}
	if rows.Next() {
		return ChannelRecord{}, &AppError{Code: code, Message: "channel mutation returned multiple rows"}
	}
	if err := rows.Err(); err != nil {
		return ChannelRecord{}, &AppError{Code: code, Message: err.Error()}
	}
	return record, nil
}

func scanChannelRecord(rows SQLRows) (ChannelRecord, error) {
	var record ChannelRecord
	if err := rows.Scan(
		&record.ChannelID,
		&record.Name,
		&record.Provider,
		&record.BaseURL,
		&record.MaxConcurrency,
		&record.ExternalProviderOptIn,
		&record.Enabled,
		&record.LastSyncAt,
		&record.LastSyncStatus,
		&record.Scope,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return ChannelRecord{}, err
	}
	return record, nil
}

func parseCredentialKey(keyMaterial string) ([]byte, error) {
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
