package llmadmin

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"
)

type Store interface {
	ListPolicies(context.Context, string, string) ([]Policy, error)
	CreatePolicy(context.Context, string, string, PolicyWrite) (Policy, error)
	UpdatePolicy(context.Context, string, string, string, PolicyWrite) (Policy, error)
	DeletePolicy(context.Context, string, string, string, string) error
	PreviewResolution(context.Context, string, string, string) (ResolutionPreview, error)
	ListReservations(context.Context, string, string, string, int) ([]Reservation, error)
	Reconcile(context.Context, string, string, string, int) ([]Reconciliation, error)
}

type SQLStore struct {
	db  *sql.DB
	now func() time.Time
}

func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db, now: time.Now} }

func (s *SQLStore) ListPolicies(ctx context.Context, tenantID, projectID string) ([]Policy, error) {
	tx, err := s.begin(ctx, tenantID, "", true)
	if err != nil {
		return nil, backendError()
	}
	defer tx.Rollback()
	rows, err := tx.QueryContext(ctx, policySelect+`
WHERE tenant_id::text = $1 AND ($2 = '' OR project_id IS NULL OR project_id::text = $2)
ORDER BY CASE scope_type WHEN 'module' THEN 1 WHEN 'project' THEN 2 ELSE 3 END, module_key NULLS LAST`, tenantID, projectID)
	if err != nil {
		return nil, backendError()
	}
	items, err := scanPolicies(rows)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, backendError()
	}
	return items, nil
}

func (s *SQLStore) CreatePolicy(ctx context.Context, tenantID, actorID string, input PolicyWrite) (Policy, error) {
	if err := validatePolicyWrite(input, false); err != nil {
		return Policy{}, err
	}
	tx, err := s.begin(ctx, tenantID, actorID, false)
	if err != nil {
		return Policy{}, backendError()
	}
	defer tx.Rollback()
	enabled := true
	if input.Enabled != nil {
		enabled = *input.Enabled
	}
	var id string
	err = tx.QueryRowContext(ctx, `INSERT INTO llm_quota_policies (
 tenant_id, scope_type, project_id, module_key, token_limit, cost_limit_micros,
 concurrency_limit, period_seconds, enabled, updated_by
) VALUES ($1, $2, NULLIF($3, '')::uuid, NULLIF($4, ''), $5, $6, $7, $8, $9, NULLIF($10, '')::uuid)
RETURNING policy_id::text`, tenantID, input.ScopeType, input.ProjectID, input.ModuleKey, input.TokenLimit,
		input.CostLimitMicros, input.ConcurrencyLimit, input.PeriodSeconds, enabled, actorID).Scan(&id)
	if err != nil {
		return Policy{}, conflictOrBackend(err)
	}
	policy, err := readPolicy(ctx, tx, tenantID, id)
	if err != nil {
		return Policy{}, err
	}
	if err := tx.Commit(); err != nil {
		return Policy{}, backendError()
	}
	return policy, nil
}

func (s *SQLStore) UpdatePolicy(ctx context.Context, tenantID, actorID, policyID string, input PolicyWrite) (Policy, error) {
	if strings.TrimSpace(policyID) == "" {
		return Policy{}, validationError()
	}
	if err := validatePolicyWrite(input, true); err != nil {
		return Policy{}, err
	}
	tx, err := s.begin(ctx, tenantID, actorID, false)
	if err != nil {
		return Policy{}, backendError()
	}
	defer tx.Rollback()
	result, err := tx.ExecContext(ctx, `UPDATE llm_quota_policies SET
 scope_type = $3, project_id = NULLIF($4, '')::uuid, module_key = NULLIF($5, ''), token_limit = $6,
 cost_limit_micros = $7, concurrency_limit = $8, period_seconds = $9, enabled = $10,
 updated_by = NULLIF($11, '')::uuid, updated_at = clock_timestamp()
WHERE tenant_id::text = $1 AND policy_id::text = $2 AND updated_at::text = $12`, tenantID, policyID,
		input.ScopeType, input.ProjectID, input.ModuleKey, input.TokenLimit, input.CostLimitMicros,
		input.ConcurrencyLimit, input.PeriodSeconds, *input.Enabled, actorID, input.ExpectedVersion)
	if err != nil {
		return Policy{}, conflictOrBackend(err)
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return Policy{}, backendError()
	}
	if affected == 0 {
		return Policy{}, versionConflict()
	}
	policy, err := readPolicy(ctx, tx, tenantID, policyID)
	if err != nil {
		return Policy{}, err
	}
	if err := tx.Commit(); err != nil {
		return Policy{}, backendError()
	}
	return policy, nil
}

func (s *SQLStore) DeletePolicy(ctx context.Context, tenantID, actorID, policyID, expectedVersion string) error {
	if strings.TrimSpace(policyID) == "" || strings.TrimSpace(expectedVersion) == "" {
		return validationError()
	}
	tx, err := s.begin(ctx, tenantID, actorID, false)
	if err != nil {
		return backendError()
	}
	defer tx.Rollback()
	result, err := tx.ExecContext(ctx, `DELETE FROM llm_quota_policies
WHERE tenant_id::text = $1 AND policy_id::text = $2 AND updated_at::text = $3`, tenantID, policyID, expectedVersion)
	if err != nil {
		return backendError()
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return backendError()
	}
	if affected == 0 {
		return versionConflict()
	}
	if err := tx.Commit(); err != nil {
		return backendError()
	}
	return nil
}

func (s *SQLStore) PreviewResolution(ctx context.Context, tenantID, projectID, moduleKey string) (ResolutionPreview, error) {
	if strings.TrimSpace(projectID) == "" || strings.TrimSpace(moduleKey) == "" {
		return ResolutionPreview{}, validationError()
	}
	tx, err := s.begin(ctx, tenantID, "", true)
	if err != nil {
		return ResolutionPreview{}, backendError()
	}
	defer tx.Rollback()
	rows, err := tx.QueryContext(ctx, policySelect+`
WHERE tenant_id::text = $1 AND enabled AND (
 scope_type = 'tenant' OR (scope_type = 'project' AND project_id::text = $2) OR
 (scope_type = 'module' AND project_id::text = $2 AND module_key = $3))
ORDER BY CASE scope_type WHEN 'module' THEN 1 WHEN 'project' THEN 2 ELSE 3 END`, tenantID, projectID, moduleKey)
	if err != nil {
		return ResolutionPreview{}, backendError()
	}
	policies, err := scanPolicies(rows)
	if err != nil {
		return ResolutionPreview{}, err
	}
	preview := ResolutionPreview{ProjectID: projectID, ModuleKey: moduleKey, ResolutionOrder: []string{"module", "project", "tenant"}, Applicable: []PolicyUsage{}, Status: "unconfigured"}
	now := s.currentTime()
	for _, policy := range policies {
		usage, err := readPolicyUsage(ctx, tx, tenantID, projectID, moduleKey, policy, now)
		if err != nil {
			return ResolutionPreview{}, err
		}
		preview.Applicable = append(preview.Applicable, usage)
	}
	if len(preview.Applicable) > 0 {
		preview.Status = "effective"
		preview.LimitingScopes = limitingScopes(preview.Applicable)
	}
	if err := tx.Commit(); err != nil {
		return ResolutionPreview{}, backendError()
	}
	return preview, nil
}

func (s *SQLStore) ListReservations(ctx context.Context, tenantID, projectID, status string, limit int) ([]Reservation, error) {
	if !validReservationStatus(status) {
		return nil, validationError()
	}
	limit = normalizeLimit(limit)
	tx, err := s.begin(ctx, tenantID, "", true)
	if err != nil {
		return nil, backendError()
	}
	defer tx.Rollback()
	rows, err := tx.QueryContext(ctx, `SELECT reservation_id::text, provider_call_id, project_id::text,
 COALESCE(run_id::text, ''), module_key, channel_id::text, model_id, reserved_tokens,
 reserved_cost_micros, actual_prompt_tokens, actual_completion_tokens, actual_cost_micros,
 status, expires_at, finalized_at, created_at, updated_at
FROM llm_quota_reservations WHERE tenant_id::text = $1
 AND ($2 = '' OR project_id::text = $2) AND ($3 = '' OR status = $3)
ORDER BY created_at DESC LIMIT $4`, tenantID, projectID, status, limit)
	if err != nil {
		return nil, backendError()
	}
	defer rows.Close()
	items := []Reservation{}
	for rows.Next() {
		var item Reservation
		if err := rows.Scan(&item.ReservationID, &item.ProviderCallID, &item.ProjectID, &item.RunID,
			&item.ModuleKey, &item.ChannelID, &item.ModelID, &item.ReservedTokens, &item.ReservedCostMicros,
			&item.ActualPromptTokens, &item.ActualCompletionTokens, &item.ActualCostMicros, &item.Status,
			&item.ExpiresAt, &item.FinalizedAt, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, backendError()
		}
		items = append(items, item)
	}
	if rows.Err() != nil {
		return nil, backendError()
	}
	if err := tx.Commit(); err != nil {
		return nil, backendError()
	}
	return items, nil
}

func (s *SQLStore) Reconcile(ctx context.Context, tenantID, projectID, moduleKey string, limit int) ([]Reconciliation, error) {
	limit = normalizeLimit(limit)
	tx, err := s.begin(ctx, tenantID, "", true)
	if err != nil {
		return nil, backendError()
	}
	defer tx.Rollback()
	rows, err := tx.QueryContext(ctx, reconciliationQuery, tenantID, projectID, moduleKey, limit)
	if err != nil {
		return nil, backendError()
	}
	defer rows.Close()
	items := []Reconciliation{}
	for rows.Next() {
		var item Reconciliation
		var usageIdentity, activityIdentity bool
		if err := rows.Scan(&item.ProviderCallID, &item.ReservationID, &item.ProjectID, &item.RunID,
			&item.ModuleKey, &item.ModelID, &item.ReservationStatus, &item.ActivityStatus,
			&item.ReservedTokens, &item.ActualTokens, &item.UsageTokens, &item.ActualCostMicros,
			&item.UsageCostMicros, &usageIdentity, &activityIdentity); err != nil {
			return nil, backendError()
		}
		reconcileStatuses(&item, usageIdentity, activityIdentity)
		items = append(items, item)
	}
	if rows.Err() != nil {
		return nil, backendError()
	}
	if err := tx.Commit(); err != nil {
		return nil, backendError()
	}
	return items, nil
}

func (s *SQLStore) begin(ctx context.Context, tenantID, actorID string, readOnly bool) (*sql.Tx, error) {
	if s == nil || s.db == nil || strings.TrimSpace(tenantID) == "" {
		return nil, backendError()
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: readOnly})
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)", tenantID, actorID); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return tx, nil
}

func (s *SQLStore) currentTime() time.Time {
	if s.now != nil {
		return s.now().UTC()
	}
	return time.Now().UTC()
}

const policySelect = `SELECT policy_id::text, scope_type, COALESCE(project_id::text, ''),
 COALESCE(module_key, ''), token_limit, cost_limit_micros, concurrency_limit,
 period_seconds, enabled, updated_at::text, created_at, updated_at FROM llm_quota_policies `

func scanPolicies(rows *sql.Rows) ([]Policy, error) {
	defer rows.Close()
	items := []Policy{}
	for rows.Next() {
		var item Policy
		if err := rows.Scan(&item.PolicyID, &item.ScopeType, &item.ProjectID, &item.ModuleKey,
			&item.TokenLimit, &item.CostLimitMicros, &item.ConcurrencyLimit, &item.PeriodSeconds,
			&item.Enabled, &item.Version, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, backendError()
		}
		items = append(items, item)
	}
	if rows.Err() != nil {
		return nil, backendError()
	}
	return items, nil
}

func readPolicy(ctx context.Context, tx *sql.Tx, tenantID, policyID string) (Policy, error) {
	rows, err := tx.QueryContext(ctx, policySelect+`WHERE tenant_id::text = $1 AND policy_id::text = $2`, tenantID, policyID)
	if err != nil {
		return Policy{}, backendError()
	}
	items, err := scanPolicies(rows)
	if err != nil {
		return Policy{}, err
	}
	if len(items) != 1 {
		return Policy{}, &AppError{Code: "LLM_QUOTA_POLICY_NOT_FOUND", Message: "LLM quota policy was not found"}
	}
	return items[0], nil
}

func readPolicyUsage(ctx context.Context, tx *sql.Tx, tenantID, projectID, moduleKey string, policy Policy, now time.Time) (PolicyUsage, error) {
	from := now.Add(-time.Duration(policy.PeriodSeconds) * time.Second)
	scopeFilter := " AND $2::text IS NOT NULL AND $3::text IS NOT NULL"
	if policy.ScopeType == "project" || policy.ScopeType == "module" {
		scopeFilter += " AND project_id::text = $2"
	}
	if policy.ScopeType == "module" {
		scopeFilter += " AND module_key = $3"
	}
	query := fmt.Sprintf(`SELECT
 COALESCE((SELECT SUM(quantity)::bigint FROM usage_events WHERE tenant_id::text = $1 AND usage_type = 'llm_tokens' AND created_at >= $4%s), 0),
 COALESCE((SELECT SUM(quantity)::bigint FROM usage_events WHERE tenant_id::text = $1 AND usage_type = 'llm_cost_micros' AND created_at >= $4%s), 0),
 COALESCE((SELECT SUM(reserved_tokens)::bigint FROM llm_quota_reservations WHERE tenant_id::text = $1 AND status = 'reserved' AND expires_at > $5%s), 0),
 COALESCE((SELECT SUM(reserved_cost_micros)::bigint FROM llm_quota_reservations WHERE tenant_id::text = $1 AND status = 'reserved' AND expires_at > $5%s), 0),
 COALESCE((SELECT COUNT(*)::int FROM llm_quota_reservations WHERE tenant_id::text = $1 AND status = 'reserved' AND expires_at > $5%s), 0)`, scopeFilter, scopeFilter, scopeFilter, scopeFilter, scopeFilter)
	result := PolicyUsage{Policy: policy, PeriodFrom: from, PeriodTo: now}
	err := tx.QueryRowContext(ctx, query, tenantID, projectID, moduleKey, from, now).Scan(&result.UsedTokens,
		&result.UsedCostMicros, &result.ReservedTokens, &result.ReservedCostMicros, &result.ActiveReservations)
	if err != nil {
		return PolicyUsage{}, backendError()
	}
	result.RemainingTokens = remainingInt64(policy.TokenLimit, result.UsedTokens, result.ReservedTokens)
	result.RemainingCostMicros = remainingInt64(policy.CostLimitMicros, result.UsedCostMicros, result.ReservedCostMicros)
	result.RemainingConcurrency = remainingInt(policy.ConcurrencyLimit, result.ActiveReservations)
	return result, nil
}

func remainingInt64(limit *int64, values ...int64) *int64 {
	if limit == nil {
		return nil
	}
	value := *limit
	for _, used := range values {
		value -= used
	}
	if value < 0 {
		value = 0
	}
	return &value
}

func remainingInt(limit *int, used int) *int {
	if limit == nil {
		return nil
	}
	value := *limit - used
	if value < 0 {
		value = 0
	}
	return &value
}

func limitingScopes(items []PolicyUsage) []string {
	selected := map[string]bool{}
	selectMinimum64 := func(value func(PolicyUsage) *int64) {
		var minimum *int64
		for _, item := range items {
			remaining := value(item)
			if remaining != nil && (minimum == nil || *remaining < *minimum) {
				copy := *remaining
				minimum = &copy
			}
		}
		if minimum != nil {
			for _, item := range items {
				if remaining := value(item); remaining != nil && *remaining == *minimum {
					selected[item.Policy.ScopeType] = true
				}
			}
		}
	}
	selectMinimum64(func(item PolicyUsage) *int64 { return item.RemainingTokens })
	selectMinimum64(func(item PolicyUsage) *int64 { return item.RemainingCostMicros })
	minimumConcurrency := (*int)(nil)
	for _, item := range items {
		if value := item.RemainingConcurrency; value != nil && (minimumConcurrency == nil || *value < *minimumConcurrency) {
			copy := *value
			minimumConcurrency = &copy
		}
	}
	if minimumConcurrency != nil {
		for _, item := range items {
			if value := item.RemainingConcurrency; value != nil && *value == *minimumConcurrency {
				selected[item.Policy.ScopeType] = true
			}
		}
	}
	result := []string{}
	for _, item := range items {
		if selected[item.Policy.ScopeType] {
			result = append(result, item.Policy.ScopeType)
			delete(selected, item.Policy.ScopeType)
		}
	}
	return result
}

const reconciliationQuery = `WITH reservations AS (
 SELECT reservation_id::text, provider_call_id, project_id::text, COALESCE(run_id::text, '') run_id,
  module_key, model_id, status, reserved_tokens,
  CASE WHEN actual_prompt_tokens IS NULL OR actual_completion_tokens IS NULL THEN NULL
       ELSE actual_prompt_tokens + actual_completion_tokens END actual_tokens,
  actual_cost_micros, created_at
 FROM llm_quota_reservations
 WHERE tenant_id::text = $1 AND ($2 = '' OR project_id::text = $2) AND ($3 = '' OR module_key = $3)
), usage AS (
 SELECT metadata_jsonb->>'provider_call_id' provider_call_id,
	COALESCE(MAX(project_id::text), '') project_id, COALESCE(MAX(run_id::text), '') run_id,
	COALESCE(MAX(module_key), '') module_key, COALESCE(MAX(metadata_jsonb->>'model_id'), '') model_id,
	(MAX(quantity) FILTER (WHERE usage_type = 'llm_tokens'))::bigint usage_tokens,
	(MAX(quantity) FILTER (WHERE usage_type = 'llm_cost_micros'))::bigint usage_cost,
	BOOL_AND(NULLIF(BTRIM(metadata_jsonb->>'provider_call_id'), '') IS NOT NULL) identity_ok
 FROM usage_events WHERE tenant_id::text = $1 AND usage_type IN ('llm_tokens','llm_cost_micros')
	AND NULLIF(BTRIM(metadata_jsonb->>'provider_call_id'), '') IS NOT NULL
	AND ($2 = '' OR project_id::text = $2) AND ($3 = '' OR module_key = $3)
 GROUP BY metadata_jsonb->>'provider_call_id'
), activity AS (
 SELECT DISTINCT ON (COALESCE(error_jsonb->>'provider_call_id', ''), project_id, run_id, module_key, model_id)
  COALESCE(error_jsonb->>'provider_call_id', '') provider_call_id, project_id::text, COALESCE(run_id::text, '') run_id,
  module_key, COALESCE(model_id, '') model_id, status, created_at
 FROM llm_activity WHERE tenant_id::text = $1 AND ($2 = '' OR project_id::text = $2) AND ($3 = '' OR module_key = $3)
	ORDER BY COALESCE(error_jsonb->>'provider_call_id', ''), project_id, run_id, module_key, model_id, created_at DESC
), provider_calls AS (
	SELECT provider_call_id FROM reservations
	UNION SELECT provider_call_id FROM usage
	UNION SELECT provider_call_id FROM activity WHERE provider_call_id <> ''
)
SELECT calls.provider_call_id, COALESCE(r.reservation_id, ''),
	COALESCE(r.project_id, u.project_id, exact.project_id, ''), COALESCE(r.run_id, u.run_id, exact.run_id, ''),
	COALESCE(r.module_key, u.module_key, exact.module_key, ''), COALESCE(r.model_id, u.model_id, exact.model_id, ''), COALESCE(r.status, ''),
 COALESCE(a.status, ''), r.reserved_tokens, r.actual_tokens, u.usage_tokens, r.actual_cost_micros,
	 u.usage_cost, COALESCE(u.identity_ok, false), COALESCE(a.provider_call_id = calls.provider_call_id AND a.provider_call_id <> '', false)
FROM provider_calls calls LEFT JOIN reservations r ON r.provider_call_id = calls.provider_call_id
LEFT JOIN usage u ON u.provider_call_id = calls.provider_call_id
LEFT JOIN activity exact ON exact.provider_call_id = calls.provider_call_id
LEFT JOIN LATERAL (
	SELECT * FROM activity a WHERE a.provider_call_id = calls.provider_call_id OR
	 (a.provider_call_id = '' AND a.project_id = COALESCE(r.project_id, u.project_id, '')
	  AND a.run_id = COALESCE(r.run_id, u.run_id, '') AND a.module_key = COALESCE(r.module_key, u.module_key, '')
	  AND a.model_id = COALESCE(r.model_id, u.model_id, ''))
	 ORDER BY (a.provider_call_id = calls.provider_call_id) DESC, a.created_at DESC LIMIT 1
) a ON true ORDER BY COALESCE(r.created_at, a.created_at) DESC NULLS LAST LIMIT $4`

func reconcileStatuses(item *Reconciliation, usageIdentity, activityIdentity bool) {
	item.Issues = []string{}
	if item.ReservationID == "" {
		item.Issues = append(item.Issues, "reservation_missing")
	}
	if item.UsageCostMicros == nil && item.ActualCostMicros == nil {
		item.PricingStatus = "unavailable"
	} else {
		item.PricingStatus = "available"
	}
	if !usageIdentity {
		item.Issues = append(item.Issues, "usage_identity_unavailable")
	}
	if item.ActivityStatus == "" {
		item.Issues = append(item.Issues, "activity_missing")
	} else if !activityIdentity {
		item.Issues = append(item.Issues, "activity_identity_unavailable")
	}
	if item.ReservationStatus == "finalized" {
		if item.ActualTokens == nil {
			item.Issues = append(item.Issues, "actual_tokens_missing")
		}
		if item.UsageTokens == nil {
			item.Issues = append(item.Issues, "usage_tokens_missing")
		}
		if item.ActualTokens != nil && item.UsageTokens != nil && *item.ActualTokens != *item.UsageTokens {
			item.Issues = append(item.Issues, "token_mismatch")
		}
		if item.ActualCostMicros != nil && item.UsageCostMicros != nil && *item.ActualCostMicros != *item.UsageCostMicros {
			item.Issues = append(item.Issues, "cost_mismatch")
		}
	}
	if len(item.Issues) == 0 && item.PricingStatus == "available" {
		item.BillingStatus = "reconciled"
	} else if len(item.Issues) == 0 {
		item.BillingStatus = "pricing_unavailable"
	} else {
		item.BillingStatus = "attention_required"
	}
}

func validatePolicyWrite(input PolicyWrite, update bool) error {
	validScope := input.ScopeType == "tenant" && strings.TrimSpace(input.ProjectID) == "" && strings.TrimSpace(input.ModuleKey) == "" ||
		input.ScopeType == "project" && strings.TrimSpace(input.ProjectID) != "" && strings.TrimSpace(input.ModuleKey) == "" ||
		input.ScopeType == "module" && strings.TrimSpace(input.ProjectID) != "" && strings.TrimSpace(input.ModuleKey) != ""
	if !validScope || input.PeriodSeconds <= 0 || input.TokenLimit == nil && input.CostLimitMicros == nil && input.ConcurrencyLimit == nil {
		return validationError()
	}
	if input.TokenLimit != nil && *input.TokenLimit < 0 || input.CostLimitMicros != nil && *input.CostLimitMicros < 0 || input.ConcurrencyLimit != nil && *input.ConcurrencyLimit <= 0 {
		return validationError()
	}
	if update && (input.Enabled == nil || strings.TrimSpace(input.ExpectedVersion) == "") {
		return validationError()
	}
	return nil
}

func validReservationStatus(status string) bool {
	return status == "" || status == "reserved" || status == "finalized" || status == "released" || status == "expired"
}

func normalizeLimit(limit int) int {
	if limit <= 0 {
		return 100
	}
	if limit > 500 {
		return 500
	}
	return limit
}
func validationError() error {
	return &AppError{Code: "VALIDATION_FAILED", Message: "LLM admin request is invalid"}
}
func backendError() error {
	return &AppError{Code: "LLM_ADMIN_BACKEND_FAILED", Message: "LLM admin backend failed"}
}
func versionConflict() error {
	return &AppError{Code: "LLM_QUOTA_POLICY_VERSION_CONFLICT", Message: "LLM quota policy changed; reload before saving"}
}
func conflictOrBackend(err error) error {
	if err != nil && strings.Contains(strings.ToLower(err.Error()), "duplicate key") {
		return &AppError{Code: "LLM_QUOTA_POLICY_SCOPE_CONFLICT", Message: "A quota policy already exists for this scope"}
	}
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "LLM_QUOTA_POLICY_NOT_FOUND", Message: "LLM quota policy was not found"}
	}
	return backendError()
}
