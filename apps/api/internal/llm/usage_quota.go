package llm

import (
	"context"
	"fmt"
	"math"
	"sort"
	"strings"
	"time"
)

const LLMTokenUsageType = "llm_tokens"

type UsageAggregateQueryInput struct {
	TenantID   string
	ProjectID  string
	RunID      string
	ModuleKey  string
	PeriodFrom time.Time
	PeriodTo   time.Time
}

type UsageAggregateRecord struct {
	TenantID           string  `json:"tenant_id"`
	ProjectID          string  `json:"project_id,omitempty"`
	ModuleKey          string  `json:"module_key,omitempty"`
	RunID              string  `json:"run_id,omitempty"`
	Quantity           float64 `json:"quantity"`
	Unit               string  `json:"unit"`
	ProviderCalls      int     `json:"provider_calls"`
	UnidentifiedEvents int     `json:"unidentified_events"`
	CallIdentityStatus string  `json:"call_identity_status"`
}

func (r *SQLTelemetryReader) AggregateUsage(ctx context.Context, input UsageAggregateQueryInput) ([]UsageAggregateRecord, error) {
	if strings.TrimSpace(input.TenantID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id is required"}
	}
	if !input.PeriodFrom.IsZero() && !input.PeriodTo.IsZero() && !input.PeriodFrom.Before(input.PeriodTo) {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "usage period is invalid"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "LLM_ACTIVITY_BACKEND_UNCONFIGURED", Message: "LLM usage backend is not configured"}
	}

	where, args := usageAggregationWhere(input)
	query := fmt.Sprintf(`WITH normalized_usage AS (
  SELECT
    tenant_id,
    project_id,
    run_id,
    module_key,
    quantity,
    unit,
    NULLIF(BTRIM(metadata_jsonb->>'provider_call_id'), '') AS provider_call_id,
    created_at,
    usage_event_id
  FROM usage_events
  WHERE %s
),
conflicting_calls AS (
  SELECT project_id, run_id, module_key, provider_call_id
  FROM normalized_usage
  WHERE provider_call_id IS NOT NULL
  GROUP BY project_id, run_id, module_key, provider_call_id
  HAVING MIN(quantity) <> MAX(quantity) OR MIN(unit) <> MAX(unit)
),
deduplicated_usage AS (
  SELECT DISTINCT ON (
    tenant_id,
    project_id,
    run_id,
    module_key,
    unit,
    COALESCE(provider_call_id, usage_event_id::text)
  )
    project_id,
    run_id,
    module_key,
    quantity,
    unit,
    provider_call_id,
    created_at,
    usage_event_id
  FROM normalized_usage
  ORDER BY
    tenant_id,
    project_id,
    run_id,
    module_key,
    unit,
    COALESCE(provider_call_id, usage_event_id::text),
    created_at,
    usage_event_id
)
SELECT
  COALESCE(project_id::text, ''),
  COALESCE(module_key, ''),
  COALESCE(run_id::text, ''),
  COALESCE(SUM(quantity), 0)::float8,
  unit,
  COUNT(*) FILTER (WHERE provider_call_id IS NOT NULL)::int,
  COUNT(*) FILTER (WHERE provider_call_id IS NULL)::int,
  (SELECT COUNT(*)::int FROM conflicting_calls)
FROM deduplicated_usage
GROUP BY project_id, module_key, run_id, unit
ORDER BY project_id, module_key, run_id, unit`, where)

	rows, err := r.queryRows(ctx, input.TenantID, query, args...)
	if err != nil {
		return nil, usageQueryError()
	}

	records := []UsageAggregateRecord{}
	for rows.Next() {
		record := UsageAggregateRecord{TenantID: strings.TrimSpace(input.TenantID)}
		var conflictingCalls int
		if err := rows.Scan(
			&record.ProjectID,
			&record.ModuleKey,
			&record.RunID,
			&record.Quantity,
			&record.Unit,
			&record.ProviderCalls,
			&record.UnidentifiedEvents,
			&conflictingCalls,
		); err != nil {
			_ = rows.Close()
			return nil, usageQueryError()
		}
		if conflictingCalls > 0 || !finiteNonNegative(record.Quantity) || record.Unit != "tokens" {
			_ = rows.Close()
			return nil, &AppError{Code: "LLM_USAGE_DATA_INVALID", Message: "LLM usage data is invalid"}
		}
		record.CallIdentityStatus = callIdentityStatus(record.ProviderCalls, record.UnidentifiedEvents)
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, usageQueryError()
	}
	if err := rows.Close(); err != nil {
		return nil, usageQueryError()
	}
	return records, nil
}

func usageAggregationWhere(input UsageAggregateQueryInput) (string, []any) {
	clauses := []string{"tenant_id::text = $1", "usage_type = 'llm_tokens'"}
	args := []any{strings.TrimSpace(input.TenantID)}
	add := func(clause string, value any) {
		args = append(args, value)
		clauses = append(clauses, fmt.Sprintf(clause, len(args)))
	}
	if value := strings.TrimSpace(input.ProjectID); value != "" {
		add("project_id::text = $%d", value)
	}
	if value := strings.TrimSpace(input.RunID); value != "" {
		add("run_id::text = $%d", value)
	}
	if value := strings.TrimSpace(input.ModuleKey); value != "" {
		add("module_key = $%d", value)
	}
	if !input.PeriodFrom.IsZero() {
		add("created_at >= $%d", input.PeriodFrom.UTC())
	}
	if !input.PeriodTo.IsZero() {
		add("created_at < $%d", input.PeriodTo.UTC())
	}
	return strings.Join(clauses, " AND "), args
}

func callIdentityStatus(providerCalls int, unidentifiedEvents int) string {
	switch {
	case providerCalls > 0 && unidentifiedEvents == 0:
		return "complete"
	case providerCalls > 0:
		return "partial"
	default:
		return "unavailable"
	}
}

func usageQueryError() error {
	return &AppError{Code: "LLM_USAGE_QUERY_FAILED", Message: "LLM usage query failed"}
}

type TokenUsageMeter interface {
	MeasureTokens(context.Context, UsageAggregateQueryInput) (TokenUsageMeasurement, error)
}

type TokenUsageMeasurement struct {
	Used   float64 `json:"used"`
	Status string  `json:"status"`
}

func (r *SQLTelemetryReader) MeasureTokens(ctx context.Context, input UsageAggregateQueryInput) (TokenUsageMeasurement, error) {
	usage, err := r.AggregateUsage(ctx, input)
	if err != nil {
		return TokenUsageMeasurement{}, err
	}
	var total float64
	for _, record := range usage {
		if record.Unit != "tokens" {
			return TokenUsageMeasurement{}, &AppError{Code: "LLM_USAGE_UNIT_INVALID", Message: "LLM usage unit is invalid"}
		}
		total += record.Quantity
	}
	activity, err := r.AggregateActivity(ctx, input)
	if err != nil {
		return TokenUsageMeasurement{}, err
	}
	reconciled := ReconcileTelemetry(activity, usage)
	if len(reconciled) == 0 {
		return TokenUsageMeasurement{Used: 0, Status: "zero_truth"}, nil
	}
	for _, record := range reconciled {
		if record.Status != "matched" {
			return TokenUsageMeasurement{Used: total, Status: "unavailable"}, nil
		}
	}
	return TokenUsageMeasurement{Used: total, Status: "available"}, nil
}

type QuotaMode string

const (
	QuotaModeEnforced  QuotaMode = "enforced"
	QuotaModeUnlimited QuotaMode = "unlimited"
)

type QuotaPolicy struct {
	Mode  QuotaMode
	Limit float64
	Scope UsageAggregateQueryInput
}

type QuotaDecision struct {
	Status    string  `json:"status"`
	Used      float64 `json:"used"`
	Limit     float64 `json:"limit,omitempty"`
	Remaining float64 `json:"remaining,omitempty"`
	Unit      string  `json:"unit"`
}

type QuotaEnforcer struct {
	meter TokenUsageMeter
}

func NewQuotaEnforcer(meter TokenUsageMeter) *QuotaEnforcer {
	return &QuotaEnforcer{meter: meter}
}

func (e *QuotaEnforcer) CheckBeforeProviderCall(ctx context.Context, policy QuotaPolicy) (QuotaDecision, error) {
	if policy.Mode == QuotaModeUnlimited {
		return QuotaDecision{Status: "unlimited", Unit: "tokens"}, nil
	}
	if policy.Mode != QuotaModeEnforced {
		return QuotaDecision{}, &AppError{Code: "LLM_QUOTA_POLICY_UNAVAILABLE", Message: "LLM quota policy is unavailable"}
	}
	if strings.TrimSpace(policy.Scope.TenantID) == "" {
		return QuotaDecision{}, &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota tenant scope is required"}
	}
	if !finiteNonNegative(policy.Limit) {
		return QuotaDecision{}, &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota limit must be finite and non-negative"}
	}
	if e == nil || e.meter == nil {
		return QuotaDecision{}, &AppError{Code: "LLM_QUOTA_CHECK_FAILED", Message: "LLM quota check failed"}
	}
	measurement, err := e.meter.MeasureTokens(ctx, policy.Scope)
	if err != nil {
		return QuotaDecision{}, &AppError{Code: "LLM_QUOTA_CHECK_FAILED", Message: "LLM quota check failed"}
	}
	if measurement.Status != "available" && measurement.Status != "zero_truth" {
		return QuotaDecision{}, &AppError{Code: "LLM_QUOTA_USAGE_UNAVAILABLE", Message: "LLM quota usage is unavailable"}
	}
	used := measurement.Used
	if !finiteNonNegative(used) {
		return QuotaDecision{}, &AppError{Code: "LLM_QUOTA_USAGE_UNAVAILABLE", Message: "LLM quota usage is unavailable"}
	}
	remaining := policy.Limit - used
	if remaining < 0 {
		remaining = 0
	}
	decision := QuotaDecision{Status: "allowed", Used: used, Limit: policy.Limit, Remaining: remaining, Unit: "tokens"}
	if used >= policy.Limit {
		decision.Status = "exceeded"
		return decision, &AppError{Code: "LLM_QUOTA_EXCEEDED", Message: "LLM token quota exceeded"}
	}
	return decision, nil
}

type TelemetryReconciliation struct {
	ProjectID          string  `json:"project_id,omitempty"`
	ModuleKey          string  `json:"module_key,omitempty"`
	RunID              string  `json:"run_id,omitempty"`
	ActivityCalls      int     `json:"activity_calls"`
	ActivityTokens     float64 `json:"activity_tokens"`
	UsageTokens        float64 `json:"usage_tokens"`
	CallIdentityStatus string  `json:"call_identity_status"`
	Status             string  `json:"status"`
}

type ActivityAggregateRecord struct {
	TenantID              string  `json:"tenant_id"`
	ProjectID             string  `json:"project_id,omitempty"`
	ModuleKey             string  `json:"module_key,omitempty"`
	RunID                 string  `json:"run_id,omitempty"`
	CompletedCalls        int     `json:"completed_calls"`
	TokenReportedCalls    int     `json:"token_reported_calls"`
	TokenUnavailableCalls int     `json:"token_unavailable_calls"`
	Tokens                float64 `json:"tokens"`
}

func (r *SQLTelemetryReader) AggregateActivity(ctx context.Context, input UsageAggregateQueryInput) ([]ActivityAggregateRecord, error) {
	if strings.TrimSpace(input.TenantID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id is required"}
	}
	if !input.PeriodFrom.IsZero() && !input.PeriodTo.IsZero() && !input.PeriodFrom.Before(input.PeriodTo) {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "activity period is invalid"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "LLM_ACTIVITY_BACKEND_UNCONFIGURED", Message: "LLM activity backend is not configured"}
	}
	where, args := activityAggregationWhere(input)
	query := fmt.Sprintf(`SELECT
  COALESCE(project_id::text, ''),
  module_key,
  COALESCE(run_id::text, ''),
  COUNT(*)::int,
  COUNT(*) FILTER (WHERE prompt_tokens IS NOT NULL OR completion_tokens IS NOT NULL)::int,
  COUNT(*) FILTER (WHERE prompt_tokens IS NULL AND completion_tokens IS NULL)::int,
  COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0)::float8
FROM llm_activity
WHERE %s
GROUP BY project_id, module_key, run_id
ORDER BY project_id, module_key, run_id`, where)
	rows, err := r.queryRows(ctx, input.TenantID, query, args...)
	if err != nil {
		return nil, telemetryQueryError()
	}

	records := []ActivityAggregateRecord{}
	for rows.Next() {
		record := ActivityAggregateRecord{TenantID: strings.TrimSpace(input.TenantID)}
		if err := rows.Scan(
			&record.ProjectID,
			&record.ModuleKey,
			&record.RunID,
			&record.CompletedCalls,
			&record.TokenReportedCalls,
			&record.TokenUnavailableCalls,
			&record.Tokens,
		); err != nil {
			_ = rows.Close()
			return nil, telemetryQueryError()
		}
		if record.CompletedCalls < 0 || record.TokenReportedCalls < 0 || record.TokenUnavailableCalls < 0 ||
			!finiteNonNegative(record.Tokens) {
			_ = rows.Close()
			return nil, &AppError{Code: "LLM_USAGE_DATA_INVALID", Message: "LLM usage data is invalid"}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, telemetryQueryError()
	}
	if err := rows.Close(); err != nil {
		return nil, telemetryQueryError()
	}
	return records, nil
}

func activityAggregationWhere(input UsageAggregateQueryInput) (string, []any) {
	clauses := []string{"tenant_id::text = $1", "status = 'completed'"}
	args := []any{strings.TrimSpace(input.TenantID)}
	add := func(clause string, value any) {
		args = append(args, value)
		clauses = append(clauses, fmt.Sprintf(clause, len(args)))
	}
	if value := strings.TrimSpace(input.ProjectID); value != "" {
		add("project_id::text = $%d", value)
	}
	if value := strings.TrimSpace(input.RunID); value != "" {
		add("run_id::text = $%d", value)
	}
	if value := strings.TrimSpace(input.ModuleKey); value != "" {
		add("module_key = $%d", value)
	}
	if !input.PeriodFrom.IsZero() {
		add("created_at >= $%d", input.PeriodFrom.UTC())
	}
	if !input.PeriodTo.IsZero() {
		add("created_at < $%d", input.PeriodTo.UTC())
	}
	return strings.Join(clauses, " AND "), args
}

func ReconcileTelemetry(activity []ActivityAggregateRecord, usage []UsageAggregateRecord) []TelemetryReconciliation {
	type key struct{ projectID, moduleKey, runID string }
	reconciled := map[key]*TelemetryReconciliation{}
	for _, record := range usage {
		currentKey := key{record.ProjectID, record.ModuleKey, record.RunID}
		recordOut := reconciled[currentKey]
		if recordOut == nil {
			recordOut = &TelemetryReconciliation{ProjectID: record.ProjectID, ModuleKey: record.ModuleKey, RunID: record.RunID}
			reconciled[currentKey] = recordOut
		}
		recordOut.UsageTokens += record.Quantity
		recordOut.CallIdentityStatus = mergeIdentityStatus(recordOut.CallIdentityStatus, record.CallIdentityStatus)
	}
	for _, record := range activity {
		currentKey := key{record.ProjectID, record.ModuleKey, record.RunID}
		recordOut := reconciled[currentKey]
		if recordOut == nil {
			recordOut = &TelemetryReconciliation{ProjectID: record.ProjectID, ModuleKey: record.ModuleKey, RunID: record.RunID, CallIdentityStatus: "unavailable"}
			reconciled[currentKey] = recordOut
		}
		recordOut.ActivityCalls += record.CompletedCalls
		recordOut.ActivityTokens += record.Tokens
		if record.TokenReportedCalls == 0 && record.TokenUnavailableCalls > 0 && recordOut.UsageTokens > 0 {
			recordOut.Status = "activity_tokens_unavailable"
		}
	}

	keys := make([]key, 0, len(reconciled))
	for currentKey := range reconciled {
		keys = append(keys, currentKey)
	}
	sort.Slice(keys, func(i, j int) bool {
		left := keys[i].projectID + "\x00" + keys[i].moduleKey + "\x00" + keys[i].runID
		right := keys[j].projectID + "\x00" + keys[j].moduleKey + "\x00" + keys[j].runID
		return left < right
	})
	result := make([]TelemetryReconciliation, 0, len(keys))
	for _, currentKey := range keys {
		record := reconciled[currentKey]
		if record.Status == "" {
			record.Status = reconciliationStatus(*record)
		}
		result = append(result, *record)
	}
	return result
}

func mergeIdentityStatus(current string, next string) string {
	if current == "" {
		return next
	}
	if current == next {
		return current
	}
	if current == "unavailable" && next == "unavailable" {
		return "unavailable"
	}
	return "partial"
}

func reconciliationStatus(record TelemetryReconciliation) string {
	switch {
	case record.ActivityCalls == 0 && record.UsageTokens == 0:
		return "unavailable"
	case record.ActivityCalls == 0:
		return "missing_activity"
	case record.UsageTokens == 0 && record.ActivityTokens > 0:
		return "missing_usage"
	case record.ActivityTokens == 0 && record.UsageTokens > 0:
		return "activity_tokens_unavailable"
	case record.ActivityTokens != record.UsageTokens:
		return "mismatch"
	case record.CallIdentityStatus != "complete":
		return "matched_identity_unavailable"
	default:
		return "matched"
	}
}

func finiteNonNegative(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0) && value >= 0
}
