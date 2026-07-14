package llm

import (
	"context"
	"encoding/json"
	"strings"
)

type ModuleBindingRecord struct {
	ModuleKey     string         `json:"module_key"`
	Scope         string         `json:"scope"`
	ChannelID     string         `json:"channel_id"`
	ChannelName   string         `json:"channel_name"`
	ModelID       string         `json:"model_id"`
	Provider      string         `json:"provider"`
	BaseURL       string         `json:"base_url"`
	SupportsTools bool           `json:"supports_tools"`
	SupportsJSON  bool           `json:"supports_json"`
	Settings      map[string]any `json:"settings"`
	UpdatedAt     string         `json:"updated_at"`
}

type ListModuleBindingsInput struct {
	TenantID  string
	ProjectID string
}

type UpsertProjectModuleBindingInput struct {
	TenantID  string
	ProjectID string
	ActorID   string
	ModuleKey string
	ChannelID string
	ModelID   string
	Settings  map[string]any
}

type DeleteProjectModuleBindingInput struct {
	TenantID  string
	ProjectID string
	ModuleKey string
}

type BindingStore interface {
	ListModuleBindings(context.Context, ListModuleBindingsInput) ([]ModuleBindingRecord, error)
	UpsertProjectModuleBinding(context.Context, UpsertProjectModuleBindingInput) (ModuleBindingRecord, error)
	DeleteProjectModuleBinding(context.Context, DeleteProjectModuleBindingInput) (ModuleBindingRecord, error)
}

type DisabledBindingStore struct{}

func NewDisabledBindingStore() DisabledBindingStore {
	return DisabledBindingStore{}
}

func (DisabledBindingStore) ListModuleBindings(context.Context, ListModuleBindingsInput) ([]ModuleBindingRecord, error) {
	return nil, &AppError{
		Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
		Message: "LLM binding backend is not configured",
	}
}

func (DisabledBindingStore) UpsertProjectModuleBinding(context.Context, UpsertProjectModuleBindingInput) (ModuleBindingRecord, error) {
	return ModuleBindingRecord{}, &AppError{
		Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
		Message: "LLM binding backend is not configured",
	}
}

func (DisabledBindingStore) DeleteProjectModuleBinding(context.Context, DeleteProjectModuleBindingInput) (ModuleBindingRecord, error) {
	return ModuleBindingRecord{}, &AppError{
		Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
		Message: "LLM binding backend is not configured",
	}
}

type SQLResolverConfig struct {
	Queryer SQLQueryer
}

type SQLResolver struct {
	queryer SQLQueryer
}

func NewSQLResolver(config SQLResolverConfig) *SQLResolver {
	return &SQLResolver{queryer: config.Queryer}
}

func (r *SQLResolver) ResolveModuleBinding(ctx context.Context, input ResolveModuleInput) (ModuleResolution, error) {
	if err := validateResolveInput(input); err != nil {
		return ModuleResolution{}, err
	}
	if r.queryer == nil {
		return ModuleResolution{}, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend is not configured",
		}
	}
	query := `SELECT
  tenant_id,
  project_id,
  module_key,
  channel_id,
  model_id,
  provider,
  base_url,
  supports_tools,
  supports_json,
  settings_jsonb
FROM (
  SELECT
    b.tenant_id::text AS tenant_id,
    COALESCE(b.project_id::text, '') AS project_id,
    b.module_key,
    b.channel_id::text AS channel_id,
    b.model_id,
    c.provider,
    c.base_url,
    COALESCE(m.supports_tools, false) AS supports_tools,
    COALESCE(m.supports_json, false) AS supports_json,
    b.settings_jsonb::text AS settings_jsonb,
    CASE WHEN b.project_id::text = $2 THEN 0 ELSE 1 END AS binding_rank
  FROM llm_module_bindings b
  JOIN llm_channels c
    ON c.channel_id = b.channel_id
   AND c.enabled = TRUE
   AND (c.tenant_id = b.tenant_id OR c.tenant_id IS NULL)
  JOIN llm_models m
    ON m.channel_id = b.channel_id
   AND m.model_id = b.model_id
   AND (m.tenant_id = b.tenant_id OR m.tenant_id IS NULL)
   AND m.enabled = TRUE
  WHERE b.tenant_id::text = $1
    AND (b.project_id::text = $2 OR b.project_id IS NULL)
    AND b.module_key = $3
  UNION ALL
  SELECT
    $1::text AS tenant_id,
    ''::text AS project_id,
    p.module_key,
    p.channel_id::text AS channel_id,
    p.model_id,
    c.provider,
    c.base_url,
    COALESCE(m.supports_tools, false) AS supports_tools,
    COALESCE(m.supports_json, false) AS supports_json,
    p.settings_jsonb::text AS settings_jsonb,
    2 AS binding_rank
  FROM llm_platform_module_defaults p
  JOIN llm_channels c
    ON c.channel_id = p.channel_id
   AND c.tenant_id IS NULL
   AND c.enabled = TRUE
  JOIN llm_models m
    ON m.channel_id = p.channel_id
   AND m.model_id = p.model_id
   AND m.tenant_id IS NULL
   AND m.enabled = TRUE
  WHERE p.module_key = $3
) ranked_bindings
ORDER BY binding_rank, module_key
LIMIT 1`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := r.queryRows(
		ctx,
		tenantID,
		query,
		tenantID,
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.ModuleKey),
	)
	if err != nil {
		if ErrorCode(err) == "LLM_BINDING_BACKEND_UNCONFIGURED" {
			return ModuleResolution{}, err
		}
		return ModuleResolution{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
	}
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return ModuleResolution{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
		}
		if err := rows.Close(); err != nil {
			return ModuleResolution{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
		}
		return ModuleResolution{}, &AppError{
			Code:    "LLM_MODULE_UNBOUND",
			Message: strings.TrimSpace(input.ModuleKey) + " module is not bound",
		}
	}
	var resolution ModuleResolution
	var settingsJSON string
	if err := rows.Scan(
		&resolution.TenantID,
		&resolution.ProjectID,
		&resolution.ModuleKey,
		&resolution.ChannelID,
		&resolution.ModelID,
		&resolution.Provider,
		&resolution.BaseURL,
		&resolution.SupportsTools,
		&resolution.SupportsJSON,
		&settingsJSON,
	); err != nil {
		_ = rows.Close()
		return ModuleResolution{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
	}
	if rows.Next() {
		_ = rows.Close()
		return ModuleResolution{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: "module resolution returned multiple rows"}
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return ModuleResolution{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
	}
	if err := rows.Close(); err != nil {
		return ModuleResolution{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
	}
	resolution.CredentialRef = resolution.ChannelID
	resolution.Settings = decodeSettingsJSON(settingsJSON)
	// Catalog rows often keep supports_json=false after model sync. OR in
	// documented chat-model defaults so Seed/Writer do not hard-fail before call.
	caps := inferModelCapabilities(resolution.ModelID)
	resolution.SupportsJSON = resolution.SupportsJSON || caps.SupportsJSON
	resolution.SupportsTools = resolution.SupportsTools || caps.SupportsTools
	return resolution, nil
}

func (r *SQLResolver) queryRows(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	tenantQueryer, ok := r.queryer.(SQLTenantQueryer)
	if !ok {
		return nil, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend does not support tenant-scoped queries",
		}
	}
	return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
}

type SQLBindingStoreConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLBindingStore struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLBindingStore(config SQLBindingStoreConfig) *SQLBindingStore {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLBindingStore{queryer: config.Queryer, limit: limit}
}

func (s *SQLBindingStore) ListModuleBindings(ctx context.Context, input ListModuleBindingsInput) ([]ModuleBindingRecord, error) {
	if err := validateBindingListInput(input); err != nil {
		return nil, err
	}
	if s.queryer == nil {
		return nil, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend is not configured",
		}
	}
	tenantQueryer, ok := s.queryer.(SQLTenantQueryer)
	if !ok {
		return nil, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend does not support tenant-scoped queries",
		}
	}
	query := `SELECT DISTINCT ON (module_key)
  module_key,
  scope,
  channel_id,
  channel_name,
  model_id,
  provider,
  base_url,
  supports_tools,
  supports_json,
  settings_jsonb,
  updated_at
FROM (
  SELECT
    b.module_key,
    CASE WHEN b.project_id IS NULL THEN 'tenant' ELSE 'project' END AS scope,
    b.channel_id::text AS channel_id,
    c.name AS channel_name,
    b.model_id,
    c.provider,
    c.base_url,
    COALESCE(m.supports_tools, false) AS supports_tools,
    COALESCE(m.supports_json, false) AS supports_json,
    b.settings_jsonb::text AS settings_jsonb,
    b.updated_at::text AS updated_at,
    CASE WHEN b.project_id::text = $2 THEN 0 ELSE 1 END AS binding_rank
  FROM llm_module_bindings b
  JOIN llm_channels c
    ON c.channel_id = b.channel_id
   AND (c.tenant_id = b.tenant_id OR c.tenant_id IS NULL)
  JOIN llm_models m
    ON m.channel_id = b.channel_id
   AND m.model_id = b.model_id
   AND (m.tenant_id = b.tenant_id OR m.tenant_id IS NULL)
   AND m.enabled = TRUE
  WHERE b.tenant_id::text = $1
    AND (b.project_id::text = $2 OR b.project_id IS NULL)
  UNION ALL
  SELECT
    p.module_key,
    'platform' AS scope,
    p.channel_id::text AS channel_id,
    c.name AS channel_name,
    p.model_id,
    c.provider,
    c.base_url,
    COALESCE(m.supports_tools, false) AS supports_tools,
    COALESCE(m.supports_json, false) AS supports_json,
    p.settings_jsonb::text AS settings_jsonb,
    p.updated_at::text AS updated_at,
    2 AS binding_rank
  FROM llm_platform_module_defaults p
  JOIN llm_channels c
    ON c.channel_id = p.channel_id
   AND c.tenant_id IS NULL
   AND c.enabled = TRUE
  JOIN llm_models m
    ON m.channel_id = p.channel_id
   AND m.model_id = p.model_id
   AND m.tenant_id IS NULL
   AND m.enabled = TRUE
) ranked_bindings
ORDER BY module_key, binding_rank
LIMIT $3`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantQueryer.QueryTenantContext(ctx, tenantID, query, tenantID, strings.TrimSpace(input.ProjectID), s.limit)
	if err != nil {
		return nil, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
	}
	records, scanErr := scanModuleBindingRecords(rows)
	closeErr := rows.Close()
	if scanErr != nil {
		return nil, scanErr
	}
	if closeErr != nil {
		return nil, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: closeErr.Error()}
	}
	return records, nil
}

func (s *SQLBindingStore) UpsertProjectModuleBinding(ctx context.Context, input UpsertProjectModuleBindingInput) (ModuleBindingRecord, error) {
	if err := validateBindingUpsertInput(input); err != nil {
		return ModuleBindingRecord{}, err
	}
	if s.queryer == nil {
		return ModuleBindingRecord{}, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend is not configured",
		}
	}
	tenantWriteQueryer, ok := s.queryer.(SQLTenantWriteQueryer)
	if !ok {
		return ModuleBindingRecord{}, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend does not support tenant-scoped writes",
		}
	}
	settingsJSON, err := json.Marshal(input.Settings)
	if err != nil {
		return ModuleBindingRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "settings must be JSON serializable"}
	}
	query := `WITH target AS (
  SELECT c.channel_id, m.model_id
  FROM llm_channels c
  JOIN llm_models m
    ON m.channel_id = c.channel_id
   AND m.model_id = $5
   AND (m.tenant_id::text = $1 OR m.tenant_id IS NULL)
   AND m.enabled = TRUE
  WHERE c.channel_id::text = $4
    AND c.enabled = TRUE
    AND (c.tenant_id::text = $1 OR c.tenant_id IS NULL)
  LIMIT 1
), upserted AS (
  INSERT INTO llm_module_bindings (
    tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by, updated_at
  )
  SELECT $1::uuid, $2::uuid, $3, target.channel_id, target.model_id, $6::jsonb, NULLIF($7, '')::uuid, now()
  FROM target
  ON CONFLICT (tenant_id, project_id, module_key) DO UPDATE SET
    channel_id = EXCLUDED.channel_id,
    model_id = EXCLUDED.model_id,
    settings_jsonb = EXCLUDED.settings_jsonb,
    updated_by = EXCLUDED.updated_by,
    updated_at = now()
  RETURNING module_key, channel_id, model_id, settings_jsonb, updated_at
)
SELECT
  upserted.module_key,
  'project' AS scope,
  upserted.channel_id::text,
  c.name,
  upserted.model_id,
  c.provider,
  c.base_url,
  COALESCE(m.supports_tools, false),
  COALESCE(m.supports_json, false),
  upserted.settings_jsonb::text,
  upserted.updated_at::text
FROM upserted
JOIN llm_channels c
  ON c.channel_id = upserted.channel_id
JOIN llm_models m
  ON m.channel_id = upserted.channel_id
 AND m.model_id = upserted.model_id`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantWriteQueryer.QueryTenantWriteContext(
		ctx,
		tenantID,
		query,
		tenantID,
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.ModuleKey),
		strings.TrimSpace(input.ChannelID),
		strings.TrimSpace(input.ModelID),
		string(settingsJSON),
		strings.TrimSpace(input.ActorID),
	)
	if err != nil {
		return ModuleBindingRecord{}, &AppError{Code: "LLM_BINDING_UPDATE_FAILED", Message: err.Error()}
	}
	return finishBindingWrite(
		rows,
		"LLM_BINDING_UPDATE_FAILED",
		"LLM_BINDING_TARGET_NOT_FOUND",
		"target channel/model is not available for this tenant",
	)
}

func (s *SQLBindingStore) DeleteProjectModuleBinding(ctx context.Context, input DeleteProjectModuleBindingInput) (ModuleBindingRecord, error) {
	if err := validateBindingDeleteInput(input); err != nil {
		return ModuleBindingRecord{}, err
	}
	if s.queryer == nil {
		return ModuleBindingRecord{}, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend is not configured",
		}
	}
	tenantWriteQueryer, ok := s.queryer.(SQLTenantWriteQueryer)
	if !ok {
		return ModuleBindingRecord{}, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend does not support tenant-scoped writes",
		}
	}
	query := `WITH deleted AS (
  DELETE FROM llm_module_bindings
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND module_key = $3
  RETURNING module_key, channel_id, model_id, settings_jsonb, updated_at
)
SELECT
  deleted.module_key,
  'project' AS scope,
  deleted.channel_id::text,
  c.name,
  deleted.model_id,
  c.provider,
  c.base_url,
  COALESCE(m.supports_tools, false),
  COALESCE(m.supports_json, false),
  deleted.settings_jsonb::text,
  deleted.updated_at::text
FROM deleted
JOIN llm_channels c
  ON c.channel_id = deleted.channel_id
JOIN llm_models m
  ON m.channel_id = deleted.channel_id
 AND m.model_id = deleted.model_id`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := tenantWriteQueryer.QueryTenantWriteContext(
		ctx,
		tenantID,
		query,
		tenantID,
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.ModuleKey),
	)
	if err != nil {
		return ModuleBindingRecord{}, &AppError{Code: "LLM_BINDING_DELETE_FAILED", Message: err.Error()}
	}
	return finishBindingWrite(
		rows,
		"LLM_BINDING_DELETE_FAILED",
		"LLM_BINDING_NOT_FOUND",
		"project module binding override was not found",
	)
}

func finishBindingWrite(rows SQLRows, failureCode, missingCode, missingMessage string) (ModuleBindingRecord, error) {
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return ModuleBindingRecord{}, &AppError{Code: failureCode, Message: err.Error()}
		}
		if err := rows.Close(); err != nil {
			return ModuleBindingRecord{}, &AppError{Code: failureCode, Message: err.Error()}
		}
		return ModuleBindingRecord{}, &AppError{
			Code:    missingCode,
			Message: missingMessage,
		}
	}
	record, err := scanModuleBindingRecord(rows)
	if err != nil {
		_ = rows.Close()
		return ModuleBindingRecord{}, &AppError{Code: failureCode, Message: err.Error()}
	}
	if rows.Next() {
		_ = rows.Close()
		return ModuleBindingRecord{}, &AppError{Code: failureCode, Message: "binding mutation returned multiple rows"}
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return ModuleBindingRecord{}, &AppError{Code: failureCode, Message: err.Error()}
	}
	if err := rows.Close(); err != nil {
		return ModuleBindingRecord{}, &AppError{Code: failureCode, Message: err.Error()}
	}
	return record, nil
}

func scanModuleBindingRecords(rows SQLRows) ([]ModuleBindingRecord, error) {
	records := []ModuleBindingRecord{}
	for rows.Next() {
		record, err := scanModuleBindingRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func scanModuleBindingRecord(rows SQLRows) (ModuleBindingRecord, error) {
	var record ModuleBindingRecord
	var settingsJSON string
	if err := rows.Scan(
		&record.ModuleKey,
		&record.Scope,
		&record.ChannelID,
		&record.ChannelName,
		&record.ModelID,
		&record.Provider,
		&record.BaseURL,
		&record.SupportsTools,
		&record.SupportsJSON,
		&settingsJSON,
		&record.UpdatedAt,
	); err != nil {
		return ModuleBindingRecord{}, &AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: err.Error()}
	}
	record.Settings = decodeSettingsJSON(settingsJSON)
	return record, nil
}

func validateResolveInput(input ResolveModuleInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ModuleKey) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and module_key are required"}
	}
	return nil
}

func validateBindingListInput(input ListModuleBindingsInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	return nil
}

func validateBindingUpsertInput(input UpsertProjectModuleBindingInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.ModuleKey) == "" || strings.TrimSpace(input.ChannelID) == "" || strings.TrimSpace(input.ModelID) == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, module_key, channel_id, and model_id are required",
		}
	}
	return nil
}

func validateBindingDeleteInput(input DeleteProjectModuleBindingInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.ModuleKey) == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and module_key are required",
		}
	}
	return nil
}

func decodeSettingsJSON(raw string) map[string]any {
	raw = strings.TrimSpace(raw)
	if raw == "" || raw == "null" {
		return map[string]any{}
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return map[string]any{}
	}
	if decoded == nil {
		return map[string]any{}
	}
	return decoded
}
