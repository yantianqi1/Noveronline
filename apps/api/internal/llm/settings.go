package llm

import (
	"context"
	"strings"
)

type SettingsInput struct {
	TenantID string
}

type SettingsSnapshot struct {
	Modules        []ModuleRecord        `json:"modules"`
	Channels       []ChannelRecord       `json:"channels"`
	TenantBindings []ModuleBindingRecord `json:"tenant_bindings"`
}

type SettingsReader interface {
	GetSettings(context.Context, SettingsInput) (SettingsSnapshot, error)
}

type DisabledSettingsReader struct{}

func NewDisabledSettingsReader() DisabledSettingsReader {
	return DisabledSettingsReader{}
}

func (DisabledSettingsReader) GetSettings(context.Context, SettingsInput) (SettingsSnapshot, error) {
	return SettingsSnapshot{}, &AppError{
		Code:    "LLM_SETTINGS_BACKEND_UNCONFIGURED",
		Message: "LLM settings backend is not configured",
	}
}

type SQLSettingsReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLSettingsReader struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLSettingsReader(config SQLSettingsReaderConfig) *SQLSettingsReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLSettingsReader{queryer: config.Queryer, limit: limit}
}

func (r *SQLSettingsReader) GetSettings(ctx context.Context, input SettingsInput) (SettingsSnapshot, error) {
	if strings.TrimSpace(input.TenantID) == "" {
		return SettingsSnapshot{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id is required"}
	}
	if r.queryer == nil {
		return SettingsSnapshot{}, &AppError{
			Code:    "LLM_SETTINGS_BACKEND_UNCONFIGURED",
			Message: "LLM settings backend is not configured",
		}
	}
	tenantQueryer, ok := r.queryer.(SQLTenantQueryer)
	if !ok {
		return SettingsSnapshot{}, &AppError{
			Code:    "LLM_SETTINGS_BACKEND_UNCONFIGURED",
			Message: "LLM settings backend does not support tenant-scoped queries",
		}
	}
	channels, err := r.listSettingsChannels(ctx, tenantQueryer, input)
	if err != nil {
		return SettingsSnapshot{}, err
	}
	bindings, err := r.listTenantBindings(ctx, tenantQueryer, input)
	if err != nil {
		return SettingsSnapshot{}, err
	}
	return SettingsSnapshot{
		Modules:        documentedModules(),
		Channels:       channels,
		TenantBindings: bindings,
	}, nil
}

func (r *SQLSettingsReader) listSettingsChannels(ctx context.Context, queryer SQLTenantQueryer, input SettingsInput) ([]ChannelRecord, error) {
	query := `SELECT
  channel_id::text,
  name,
  provider,
  base_url,
  max_concurrency,
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
	rows, err := queryer.QueryTenantContext(ctx, tenantID, query, tenantID, r.limit)
	if err != nil {
		return nil, &AppError{Code: "LLM_SETTINGS_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	records := []ChannelRecord{}
	for rows.Next() {
		var record ChannelRecord
		if err := rows.Scan(
			&record.ChannelID,
			&record.Name,
			&record.Provider,
			&record.BaseURL,
			&record.MaxConcurrency,
			&record.Enabled,
			&record.LastSyncAt,
			&record.LastSyncStatus,
			&record.Scope,
			&record.CreatedAt,
			&record.UpdatedAt,
		); err != nil {
			return nil, &AppError{Code: "LLM_SETTINGS_QUERY_FAILED", Message: err.Error()}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "LLM_SETTINGS_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func (r *SQLSettingsReader) listTenantBindings(ctx context.Context, queryer SQLTenantQueryer, input SettingsInput) ([]ModuleBindingRecord, error) {
	query := `SELECT
  b.module_key,
  c.channel_id::text,
  c.name,
  c.provider,
  c.base_url,
  b.model_id,
  m.supports_tools,
  m.supports_json,
  b.settings_jsonb::text,
  'tenant' AS scope,
  b.updated_at::text
FROM llm_module_bindings b
JOIN llm_channels c
  ON c.channel_id = b.channel_id
JOIN llm_models m
  ON m.channel_id = b.channel_id
 AND m.model_id = b.model_id
WHERE b.tenant_id::text = $1
  AND b.project_id IS NULL
ORDER BY b.module_key ASC
LIMIT $2`
	tenantID := strings.TrimSpace(input.TenantID)
	rows, err := queryer.QueryTenantContext(ctx, tenantID, query, tenantID, r.limit)
	if err != nil {
		return nil, &AppError{Code: "LLM_SETTINGS_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	records := []ModuleBindingRecord{}
	for rows.Next() {
		var record ModuleBindingRecord
		var settingsJSON string
		if err := rows.Scan(
			&record.ModuleKey,
			&record.ChannelID,
			&record.ChannelName,
			&record.Provider,
			&record.BaseURL,
			&record.ModelID,
			&record.SupportsTools,
			&record.SupportsJSON,
			&settingsJSON,
			&record.Scope,
			&record.UpdatedAt,
		); err != nil {
			return nil, &AppError{Code: "LLM_SETTINGS_QUERY_FAILED", Message: err.Error()}
		}
		record.Settings = sanitizePublicSettings(decodeSettingsJSON(settingsJSON))
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "LLM_SETTINGS_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func sanitizePublicSettings(settings map[string]any) map[string]any {
	if len(settings) == 0 {
		return map[string]any{}
	}
	sanitized := make(map[string]any, len(settings))
	for key, value := range settings {
		if isSensitiveSettingsKey(key) {
			continue
		}
		sanitized[key] = value
	}
	return sanitized
}

func isSensitiveSettingsKey(key string) bool {
	normalized := strings.ToLower(strings.TrimSpace(key))
	if normalized == "" {
		return true
	}
	// Operational generation budgets are public binding metadata, not credentials.
	// Without this allowlist, keys like max_tokens would match the broad "token" filter.
	switch normalized {
	case "max_tokens", "max_concurrency", "temperature", "top_p", "top_k",
		"presence_penalty", "frequency_penalty", "embedding_dimensions":
		return false
	}
	return strings.Contains(normalized, "api_key") ||
		strings.Contains(normalized, "credential") ||
		strings.Contains(normalized, "secret") ||
		strings.Contains(normalized, "token") ||
		normalized == "prompt" ||
		normalized == "system_prompt" ||
		normalized == "body" ||
		normalized == "content"
}
