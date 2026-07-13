package llmadmin

import (
	"context"
	"strings"

	"mirofish-novel/apps/api/internal/llm"
)

type SQLHealthCredentialResolverConfig struct {
	Queryer               llm.SQLQueryer
	CredentialKeyMaterial string
}

type SQLHealthCredentialResolver struct {
	queryer   llm.SQLTenantQueryer
	decryptor *llm.CredentialDecryptor
}

func NewSQLHealthCredentialResolver(config SQLHealthCredentialResolverConfig) (*SQLHealthCredentialResolver, error) {
	queryer, ok := config.Queryer.(llm.SQLTenantQueryer)
	if !ok || queryer == nil {
		return nil, &AppError{Code: "LLM_PROVIDER_HEALTH_UNCONFIGURED", Message: "LLM provider health check is not configured"}
	}
	decryptor, err := llm.NewCredentialDecryptor(config.CredentialKeyMaterial)
	if err != nil {
		code := llm.ErrorCode(err)
		if code == "" {
			code = "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED"
		}
		return nil, &AppError{Code: code, Message: credentialConfigurationMessage(code)}
	}
	return &SQLHealthCredentialResolver{queryer: queryer, decryptor: decryptor}, nil
}

func (r *SQLHealthCredentialResolver) ResolveHealthTarget(
	ctx context.Context,
	tenantID string,
	projectID string,
	channelID string,
	modelID string,
) (HealthTarget, error) {
	tenantID = strings.TrimSpace(tenantID)
	projectID = strings.TrimSpace(projectID)
	channelID = strings.TrimSpace(channelID)
	modelID = strings.TrimSpace(modelID)
	if r == nil || r.queryer == nil || r.decryptor == nil {
		return HealthTarget{}, healthTargetUnavailable()
	}
	if tenantID == "" || projectID == "" || channelID == "" || modelID == "" {
		return HealthTarget{}, validationError()
	}

	rows, err := r.queryer.QueryTenantContext(ctx, tenantID, healthTargetQuery, tenantID, projectID, channelID, modelID)
	if err != nil {
		return HealthTarget{}, healthTargetUnavailable()
	}
	if rows == nil {
		return HealthTarget{}, healthTargetUnavailable()
	}
	defer rows.Close()
	if !rows.Next() {
		return HealthTarget{}, healthTargetUnavailable()
	}
	var target HealthTarget
	var encryptedAPIKey string
	if err := rows.Scan(
		&target.ChannelID,
		&target.ModelID,
		&target.BaseURL,
		&encryptedAPIKey,
		&target.ExternalProviderOptIn,
		&target.SupportsTools,
		&target.SupportsJSON,
	); err != nil {
		return HealthTarget{}, healthTargetUnavailable()
	}
	if rows.Next() || rows.Err() != nil {
		return HealthTarget{}, healthTargetUnavailable()
	}
	if target.ChannelID != channelID || target.ModelID != modelID || strings.TrimSpace(target.BaseURL) == "" {
		return HealthTarget{}, healthTargetUnavailable()
	}
	apiKey, err := r.decryptor.Decrypt(encryptedAPIKey)
	if err != nil || strings.TrimSpace(apiKey) == "" {
		return HealthTarget{}, healthTargetUnavailable()
	}
	target.APIKey = apiKey
	return target, nil
}

func credentialConfigurationMessage(code string) string {
	if code == "LLM_CREDENTIAL_KEY_INVALID" {
		return "LLM credential encryption key is invalid"
	}
	return "LLM credential encryption key is not configured"
}

func healthTargetUnavailable() error {
	return &AppError{Code: "LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE", Message: "LLM provider health target is unavailable"}
}

const healthTargetQuery = `SELECT
  c.channel_id::text,
  m.model_id,
  c.base_url,
  c.encrypted_api_key,
  c.external_provider_opt_in,
  m.supports_tools,
  m.supports_json
FROM llm_channels c
JOIN llm_models m
  ON m.tenant_id = c.tenant_id
 AND m.channel_id = c.channel_id
JOIN projects p
  ON p.tenant_id = c.tenant_id
WHERE c.tenant_id::text = $1
  AND p.project_id::text = $2
  AND c.channel_id::text = $3
  AND m.model_id = $4
  AND c.enabled
  AND m.enabled
  AND p.status = 'active'
LIMIT 2`
