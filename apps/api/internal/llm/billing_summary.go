package llm

import (
	"context"
	"fmt"
	"strings"
	"time"
)

type BillingUsageQuery struct {
	TenantID   string
	ProjectID  string
	ModuleKey  string
	ModelID    string
	PeriodFrom time.Time
	PeriodTo   time.Time
}

type BillingUsageRecord struct {
	TenantID      string `json:"tenant_id"`
	ProjectID     string `json:"project_id,omitempty"`
	ModuleKey     string `json:"module_key,omitempty"`
	ModelID       string `json:"model_id,omitempty"`
	ProviderCalls int    `json:"provider_calls"`
	Tokens        int64  `json:"tokens"`
	CostMicros    *int64 `json:"cost_micros,omitempty"`
	BillingStatus string `json:"billing_status"`
}

func (r *SQLTelemetryReader) BillingUsage(ctx context.Context, input BillingUsageQuery) ([]BillingUsageRecord, error) {
	if strings.TrimSpace(input.TenantID) == "" ||
		!input.PeriodFrom.IsZero() && !input.PeriodTo.IsZero() && !input.PeriodFrom.Before(input.PeriodTo) {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "billing usage query is invalid"}
	}
	if r == nil || r.queryer == nil {
		return nil, &AppError{Code: "LLM_ACTIVITY_BACKEND_UNCONFIGURED", Message: "LLM usage backend is not configured"}
	}
	where, args := billingUsageWhere(input)
	query := fmt.Sprintf(`WITH call_usage AS (
  SELECT tenant_id, project_id, module_key,
    NULLIF(BTRIM(metadata_jsonb->>'model_id'), '') AS model_id,
    NULLIF(BTRIM(metadata_jsonb->>'provider_call_id'), '') AS provider_call_id,
    MAX(quantity) FILTER (WHERE usage_type = 'llm_tokens')::bigint AS tokens,
    MAX(quantity) FILTER (WHERE usage_type = 'llm_cost_micros')::bigint AS cost_micros
  FROM usage_events
  WHERE %s AND usage_type IN ('llm_tokens', 'llm_cost_micros')
  GROUP BY tenant_id, project_id, module_key,
    NULLIF(BTRIM(metadata_jsonb->>'model_id'), ''),
    NULLIF(BTRIM(metadata_jsonb->>'provider_call_id'), '')
)
SELECT COALESCE(project_id::text, ''), COALESCE(module_key, ''), COALESCE(model_id, ''),
  COUNT(*) FILTER (WHERE provider_call_id IS NOT NULL)::int,
  COALESCE(SUM(tokens), 0)::bigint,
  CASE WHEN COUNT(*) FILTER (WHERE tokens IS NOT NULL) = COUNT(*) FILTER (WHERE provider_call_id IS NOT NULL)
         AND COUNT(*) FILTER (WHERE cost_micros IS NOT NULL) = COUNT(*) FILTER (WHERE provider_call_id IS NOT NULL)
       THEN COALESCE(SUM(cost_micros), 0)::bigint ELSE NULL END,
  CASE
    WHEN COUNT(*) FILTER (WHERE provider_call_id IS NULL OR model_id IS NULL OR tokens IS NULL) > 0 THEN 'unavailable'
    WHEN COUNT(*) FILTER (WHERE cost_micros IS NULL) > 0 THEN 'pricing_unavailable'
    ELSE 'billing_ready'
  END
FROM call_usage
GROUP BY project_id, module_key, model_id
ORDER BY project_id, module_key, model_id`, where)
	rows, err := r.queryRows(ctx, input.TenantID, query, args...)
	if err != nil {
		return nil, &AppError{Code: "LLM_BILLING_USAGE_QUERY_FAILED", Message: "LLM billing usage query failed"}
	}
	records := []BillingUsageRecord{}
	for rows.Next() {
		record := BillingUsageRecord{TenantID: strings.TrimSpace(input.TenantID)}
		if err := rows.Scan(&record.ProjectID, &record.ModuleKey, &record.ModelID, &record.ProviderCalls,
			&record.Tokens, &record.CostMicros, &record.BillingStatus); err != nil {
			_ = rows.Close()
			return nil, &AppError{Code: "LLM_BILLING_USAGE_QUERY_FAILED", Message: "LLM billing usage query failed"}
		}
		if record.ProviderCalls < 0 || record.Tokens < 0 || record.CostMicros != nil && *record.CostMicros < 0 {
			_ = rows.Close()
			return nil, &AppError{Code: "LLM_USAGE_DATA_INVALID", Message: "LLM usage data is invalid"}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, &AppError{Code: "LLM_BILLING_USAGE_QUERY_FAILED", Message: "LLM billing usage query failed"}
	}
	if err := rows.Close(); err != nil {
		return nil, &AppError{Code: "LLM_BILLING_USAGE_QUERY_FAILED", Message: "LLM billing usage query failed"}
	}
	return records, nil
}

func billingUsageWhere(input BillingUsageQuery) (string, []any) {
	clauses := []string{"tenant_id::text = $1"}
	args := []any{strings.TrimSpace(input.TenantID)}
	add := func(format string, value any) {
		args = append(args, value)
		clauses = append(clauses, fmt.Sprintf(format, len(args)))
	}
	if value := strings.TrimSpace(input.ProjectID); value != "" {
		add("project_id::text = $%d", value)
	}
	if value := strings.TrimSpace(input.ModuleKey); value != "" {
		add("module_key = $%d", value)
	}
	if value := strings.TrimSpace(input.ModelID); value != "" {
		add("metadata_jsonb->>'model_id' = $%d", value)
	}
	if !input.PeriodFrom.IsZero() {
		add("created_at >= $%d", input.PeriodFrom.UTC())
	}
	if !input.PeriodTo.IsZero() {
		add("created_at < $%d", input.PeriodTo.UTC())
	}
	return strings.Join(clauses, " AND "), args
}
