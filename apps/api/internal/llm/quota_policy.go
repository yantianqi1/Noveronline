package llm

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"
)

const (
	QuotaScopeTenant  = "tenant"
	QuotaScopeProject = "project"
	QuotaScopeModule  = "module"
)

type PersistentQuotaPolicy struct {
	PolicyID         string `json:"policy_id"`
	TenantID         string `json:"tenant_id"`
	ScopeType        string `json:"scope_type"`
	ProjectID        string `json:"project_id,omitempty"`
	ModuleKey        string `json:"module_key,omitempty"`
	TokenLimit       *int64 `json:"token_limit,omitempty"`
	CostLimitMicros  *int64 `json:"cost_limit_micros,omitempty"`
	ConcurrencyLimit *int   `json:"concurrency_limit,omitempty"`
	PeriodSeconds    int    `json:"period_seconds"`
	Enabled          bool   `json:"enabled"`
	UpdatedAt        string `json:"updated_at"`
}

type QuotaPolicyQuery struct {
	TenantID  string
	ProjectID string
	ModuleKey string
}

type UpsertQuotaPolicyInput struct {
	TenantID         string
	ActorUserID      string
	ScopeType        string
	ProjectID        string
	ModuleKey        string
	TokenLimit       *int64
	CostLimitMicros  *int64
	ConcurrencyLimit *int
	PeriodSeconds    int
	Enabled          bool
}

type QuotaPolicyStore interface {
	ListPolicies(context.Context, QuotaPolicyQuery) ([]PersistentQuotaPolicy, error)
	UpsertPolicy(context.Context, UpsertQuotaPolicyInput) (PersistentQuotaPolicy, error)
}

type SQLQuotaStore struct {
	db  *sql.DB
	now func() time.Time
}

func NewSQLQuotaStore(db *sql.DB) *SQLQuotaStore {
	return &SQLQuotaStore{db: db, now: time.Now}
}

func (s *SQLQuotaStore) ListPolicies(ctx context.Context, input QuotaPolicyQuery) ([]PersistentQuotaPolicy, error) {
	if strings.TrimSpace(input.TenantID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id is required"}
	}
	if s == nil || s.db == nil {
		return nil, quotaBackendError()
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, true)
	if err != nil {
		return nil, quotaBackendError()
	}
	defer tx.Rollback()
	rows, err := tx.QueryContext(ctx, `SELECT policy_id::text, tenant_id::text, scope_type,
  COALESCE(project_id::text, ''), COALESCE(module_key, ''), token_limit,
  cost_limit_micros, concurrency_limit, period_seconds, enabled, updated_at::text
FROM llm_quota_policies
WHERE tenant_id::text = $1
  AND ($2 = '' OR project_id::text = $2 OR project_id IS NULL)
  AND ($3 = '' OR module_key = $3 OR module_key IS NULL)
ORDER BY CASE scope_type WHEN 'tenant' THEN 1 WHEN 'project' THEN 2 ELSE 3 END,
  COALESCE(project_id::text, ''), COALESCE(module_key, '')`,
		strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), strings.TrimSpace(input.ModuleKey))
	if err != nil {
		return nil, quotaBackendError()
	}
	policies, err := scanQuotaPolicies(rows)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, quotaBackendError()
	}
	return policies, nil
}

func (s *SQLQuotaStore) UpsertPolicy(ctx context.Context, input UpsertQuotaPolicyInput) (PersistentQuotaPolicy, error) {
	if err := validateQuotaPolicyInput(input); err != nil {
		return PersistentQuotaPolicy{}, err
	}
	if s == nil || s.db == nil {
		return PersistentQuotaPolicy{}, quotaBackendError()
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, false)
	if err != nil {
		return PersistentQuotaPolicy{}, quotaBackendError()
	}
	defer tx.Rollback()
	projectID, moduleKey := nullableString(input.ProjectID), nullableString(input.ModuleKey)
	var policyID string
	err = tx.QueryRowContext(ctx, `SELECT policy_id::text FROM llm_quota_policies
WHERE tenant_id::text = $1 AND scope_type = $2
  AND project_id IS NOT DISTINCT FROM $3::uuid
  AND module_key IS NOT DISTINCT FROM $4::text
FOR UPDATE`, strings.TrimSpace(input.TenantID), input.ScopeType, projectID, moduleKey).Scan(&policyID)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return PersistentQuotaPolicy{}, quotaBackendError()
	}
	if policyID == "" {
		err = tx.QueryRowContext(ctx, `INSERT INTO llm_quota_policies (
  tenant_id, scope_type, project_id, module_key, token_limit, cost_limit_micros,
  concurrency_limit, period_seconds, enabled, updated_by
) VALUES ($1, $2, $3::uuid, $4, $5, $6, $7, $8, $9, NULLIF($10, '')::uuid)
RETURNING policy_id::text`, strings.TrimSpace(input.TenantID), input.ScopeType, projectID, moduleKey,
			input.TokenLimit, input.CostLimitMicros, input.ConcurrencyLimit, input.PeriodSeconds, input.Enabled,
			strings.TrimSpace(input.ActorUserID)).Scan(&policyID)
	} else {
		_, err = tx.ExecContext(ctx, `UPDATE llm_quota_policies SET token_limit = $3,
  cost_limit_micros = $4, concurrency_limit = $5, period_seconds = $6,
  enabled = $7, updated_by = NULLIF($8, '')::uuid, updated_at = now()
WHERE tenant_id::text = $1 AND policy_id::text = $2`, strings.TrimSpace(input.TenantID), policyID,
			input.TokenLimit, input.CostLimitMicros, input.ConcurrencyLimit, input.PeriodSeconds, input.Enabled,
			strings.TrimSpace(input.ActorUserID))
	}
	if err != nil {
		return PersistentQuotaPolicy{}, quotaBackendError()
	}
	policy, err := readPolicy(ctx, tx, input.TenantID, policyID)
	if err != nil {
		return PersistentQuotaPolicy{}, err
	}
	if err := tx.Commit(); err != nil {
		return PersistentQuotaPolicy{}, quotaBackendError()
	}
	return policy, nil
}

type QuotaReservationInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	ModuleKey          string
	ChannelID          string
	ModelID            string
	ProviderCallID     string
	ReservedTokens     int64
	ReservedCostMicros int64
	TTL                time.Duration
}

type QuotaReservation struct {
	ReservationID  string    `json:"reservation_id"`
	ProviderCallID string    `json:"provider_call_id"`
	ExpiresAt      time.Time `json:"expires_at"`
}

type QuotaFinalizeInput struct {
	TenantID         string
	ReservationID    string
	PromptTokens     int64
	CompletionTokens int64
	CostMicros       *int64
}

func (s *SQLQuotaStore) Reserve(ctx context.Context, input QuotaReservationInput) (QuotaReservation, error) {
	if err := validateReservationInput(input); err != nil {
		return QuotaReservation{}, err
	}
	if s == nil || s.db == nil {
		return QuotaReservation{}, quotaBackendError()
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, false)
	if err != nil {
		return QuotaReservation{}, quotaBackendError()
	}
	defer tx.Rollback()
	policies, err := applicablePolicies(ctx, tx, input)
	if err != nil {
		return QuotaReservation{}, err
	}
	if len(policies) == 0 {
		return QuotaReservation{}, &AppError{Code: "LLM_QUOTA_POLICY_UNAVAILABLE", Message: "LLM quota policy is unavailable"}
	}
	if err := lockQuotaScopes(ctx, tx, input, policies); err != nil {
		return QuotaReservation{}, quotaBackendError()
	}
	now := s.currentTime()
	if existing, found, err := findExistingReservation(ctx, tx, input, now); err != nil {
		return QuotaReservation{}, err
	} else if found {
		if err := tx.Commit(); err != nil {
			return QuotaReservation{}, quotaBackendError()
		}
		return existing, nil
	}
	for _, policy := range policies {
		if err := checkPolicyCapacity(ctx, tx, input, policy, now); err != nil {
			return QuotaReservation{}, err
		}
	}
	expiresAt := now.Add(input.TTL)
	var reservation QuotaReservation
	err = tx.QueryRowContext(ctx, `INSERT INTO llm_quota_reservations (
  tenant_id, provider_call_id, project_id, run_id, module_key, channel_id, model_id,
  reserved_tokens, reserved_cost_micros, expires_at
) VALUES ($1, $2, $3, NULLIF($4, '')::uuid, $5, $6, $7, $8, $9, $10)
ON CONFLICT (tenant_id, provider_call_id) DO UPDATE
SET updated_at = llm_quota_reservations.updated_at
WHERE llm_quota_reservations.status = 'reserved'
  AND llm_quota_reservations.project_id::text = EXCLUDED.project_id::text
  AND llm_quota_reservations.module_key = EXCLUDED.module_key
  AND llm_quota_reservations.channel_id = EXCLUDED.channel_id
  AND llm_quota_reservations.model_id = EXCLUDED.model_id
  AND llm_quota_reservations.reserved_tokens = EXCLUDED.reserved_tokens
  AND llm_quota_reservations.reserved_cost_micros = EXCLUDED.reserved_cost_micros
RETURNING reservation_id::text, provider_call_id, expires_at`, input.TenantID, input.ProviderCallID,
		input.ProjectID, input.RunID, input.ModuleKey, input.ChannelID, input.ModelID,
		input.ReservedTokens, input.ReservedCostMicros, expiresAt).Scan(
		&reservation.ReservationID, &reservation.ProviderCallID, &reservation.ExpiresAt)
	if err != nil {
		return QuotaReservation{}, &AppError{Code: "LLM_QUOTA_RESERVE_FAILED", Message: "LLM quota reservation failed"}
	}
	if err := tx.Commit(); err != nil {
		return QuotaReservation{}, quotaBackendError()
	}
	return reservation, nil
}

func findExistingReservation(ctx context.Context, tx *sql.Tx, input QuotaReservationInput, now time.Time) (QuotaReservation, bool, error) {
	var reservation QuotaReservation
	var projectID, moduleKey, channelID, modelID, status string
	var tokens, cost int64
	err := tx.QueryRowContext(ctx, `SELECT reservation_id::text, provider_call_id, expires_at,
  project_id::text, module_key, channel_id::text, model_id, reserved_tokens, reserved_cost_micros, status
FROM llm_quota_reservations
WHERE tenant_id::text = $1 AND provider_call_id = $2
FOR UPDATE`, input.TenantID, input.ProviderCallID).Scan(
		&reservation.ReservationID, &reservation.ProviderCallID, &reservation.ExpiresAt,
		&projectID, &moduleKey, &channelID, &modelID, &tokens, &cost, &status)
	if errors.Is(err, sql.ErrNoRows) {
		return QuotaReservation{}, false, nil
	}
	if err != nil {
		return QuotaReservation{}, false, quotaBackendError()
	}
	matches := projectID == input.ProjectID && moduleKey == input.ModuleKey && channelID == input.ChannelID &&
		modelID == input.ModelID && tokens == input.ReservedTokens && cost == input.ReservedCostMicros
	if status != "reserved" || !reservation.ExpiresAt.After(now) {
		return QuotaReservation{}, false, &AppError{Code: "LLM_QUOTA_RESERVATION_CLOSED", Message: "LLM quota reservation is closed"}
	}
	if !matches {
		return QuotaReservation{}, false, &AppError{Code: "LLM_PROVIDER_CALL_CONFLICT", Message: "LLM provider call identity conflicts with an existing reservation"}
	}
	return reservation, true, nil
}

func (s *SQLQuotaStore) Finalize(ctx context.Context, input QuotaFinalizeInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ReservationID) == "" ||
		input.PromptTokens < 0 || input.CompletionTokens < 0 || (input.CostMicros != nil && *input.CostMicros < 0) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota finalization is invalid"}
	}
	if s == nil || s.db == nil {
		return quotaBackendError()
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, false)
	if err != nil {
		return quotaBackendError()
	}
	defer tx.Rollback()
	var status, projectID, runID, moduleKey, modelID, providerCallID string
	var reservedTokens, reservedCost int64
	err = tx.QueryRowContext(ctx, `SELECT status, project_id::text, COALESCE(run_id::text, ''), module_key,
  model_id, provider_call_id, reserved_tokens, reserved_cost_micros
FROM llm_quota_reservations
WHERE tenant_id::text = $1 AND reservation_id::text = $2 FOR UPDATE`, input.TenantID, input.ReservationID).Scan(
		&status, &projectID, &runID, &moduleKey, &modelID, &providerCallID, &reservedTokens, &reservedCost)
	if err != nil {
		return &AppError{Code: "LLM_QUOTA_RESERVATION_NOT_FOUND", Message: "LLM quota reservation was not found"}
	}
	if status == "finalized" {
		return tx.Commit()
	}
	if status != "reserved" {
		return &AppError{Code: "LLM_QUOTA_RESERVATION_CLOSED", Message: "LLM quota reservation is closed"}
	}
	actualTokens, ok := checkedNonNegativeSum(input.PromptTokens, input.CompletionTokens)
	if !ok {
		return &AppError{Code: "LLM_USAGE_DATA_INVALID", Message: "LLM usage data is invalid"}
	}
	if actualTokens > reservedTokens || (input.CostMicros != nil && *input.CostMicros > reservedCost) {
		return &AppError{Code: "LLM_USAGE_EXCEEDS_RESERVATION", Message: "LLM provider usage exceeded its reservation"}
	}
	_, err = tx.ExecContext(ctx, `UPDATE llm_quota_reservations SET status = 'finalized',
  actual_prompt_tokens = $3, actual_completion_tokens = $4, actual_cost_micros = $5,
  finalized_at = now(), updated_at = now()
WHERE tenant_id::text = $1 AND reservation_id::text = $2`, input.TenantID, input.ReservationID,
		input.PromptTokens, input.CompletionTokens, input.CostMicros)
	if err == nil {
		_, err = tx.ExecContext(ctx, `INSERT INTO usage_events (
  tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
) VALUES ($1, $2, NULLIF($3, '')::uuid, $4, 'llm_tokens', $5, 'tokens',
  jsonb_build_object('provider_call_id', $6::text, 'model_id', $7::text))`, input.TenantID, projectID,
			runID, moduleKey, actualTokens, providerCallID, modelID)
	}
	if err == nil && input.CostMicros != nil {
		_, err = tx.ExecContext(ctx, `INSERT INTO usage_events (
  tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
) VALUES ($1, $2, NULLIF($3, '')::uuid, $4, 'llm_cost_micros', $5, 'micros',
  jsonb_build_object('provider_call_id', $6::text, 'model_id', $7::text))`, input.TenantID, projectID,
			runID, moduleKey, *input.CostMicros, providerCallID, modelID)
	}
	if err != nil {
		return &AppError{Code: "LLM_TELEMETRY_WRITE_FAILED", Message: "LLM telemetry write failed"}
	}
	if err := tx.Commit(); err != nil {
		return &AppError{Code: "LLM_TELEMETRY_WRITE_FAILED", Message: "LLM telemetry write failed"}
	}
	return nil
}

func (s *SQLQuotaStore) Release(ctx context.Context, tenantID, reservationID string) error {
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(reservationID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota release is invalid"}
	}
	if s == nil || s.db == nil {
		return quotaBackendError()
	}
	tx, err := s.beginTenantTx(ctx, tenantID, false)
	if err != nil {
		return quotaBackendError()
	}
	defer tx.Rollback()
	result, err := tx.ExecContext(ctx, `UPDATE llm_quota_reservations
SET status = 'released', updated_at = now()
WHERE tenant_id::text = $1 AND reservation_id::text = $2 AND status = 'reserved'`, tenantID, reservationID)
	if err != nil {
		return &AppError{Code: "LLM_QUOTA_RELEASE_FAILED", Message: "LLM quota reservation release failed"}
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return &AppError{Code: "LLM_QUOTA_RELEASE_FAILED", Message: "LLM quota reservation release failed"}
	}
	if affected == 0 {
		var status string
		if err := tx.QueryRowContext(ctx, `SELECT status FROM llm_quota_reservations
WHERE tenant_id::text = $1 AND reservation_id::text = $2`, tenantID, reservationID).Scan(&status); err != nil || status != "released" {
			return &AppError{Code: "LLM_QUOTA_RESERVATION_CLOSED", Message: "LLM quota reservation is closed"}
		}
	}
	return tx.Commit()
}

func (s *SQLQuotaStore) beginTenantTx(ctx context.Context, tenantID string, readOnly bool) (*sql.Tx, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: readOnly})
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULL::uuid, false)", strings.TrimSpace(tenantID)); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return tx, nil
}

func (s *SQLQuotaStore) currentTime() time.Time {
	if s.now != nil {
		return s.now().UTC()
	}
	return time.Now().UTC()
}

func applicablePolicies(ctx context.Context, tx *sql.Tx, input QuotaReservationInput) ([]PersistentQuotaPolicy, error) {
	rows, err := tx.QueryContext(ctx, `SELECT policy_id::text, tenant_id::text, scope_type,
  COALESCE(project_id::text, ''), COALESCE(module_key, ''), token_limit,
  cost_limit_micros, concurrency_limit, period_seconds, enabled, updated_at::text
FROM llm_quota_policies
WHERE tenant_id::text = $1 AND enabled
  AND (scope_type = 'tenant' OR (project_id::text = $2 AND scope_type = 'project') OR
       (project_id::text = $2 AND module_key = $3 AND scope_type = 'module'))
ORDER BY CASE scope_type WHEN 'tenant' THEN 1 WHEN 'project' THEN 2 ELSE 3 END`,
		input.TenantID, input.ProjectID, input.ModuleKey)
	if err != nil {
		return nil, quotaBackendError()
	}
	return scanQuotaPolicies(rows)
}

func lockQuotaScopes(ctx context.Context, tx *sql.Tx, input QuotaReservationInput, policies []PersistentQuotaPolicy) error {
	keys := make([]string, 0, len(policies))
	for _, policy := range policies {
		keys = append(keys, strings.Join([]string{input.TenantID, policy.ScopeType, policy.ProjectID, policy.ModuleKey}, ":"))
	}
	sort.Strings(keys)
	for _, key := range keys {
		if _, err := tx.ExecContext(ctx, "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", key); err != nil {
			return err
		}
	}
	return nil
}

func checkPolicyCapacity(ctx context.Context, tx *sql.Tx, input QuotaReservationInput, policy PersistentQuotaPolicy, now time.Time) error {
	filter, args := policyScopeSQL(policy, input, now.Add(-time.Duration(policy.PeriodSeconds)*time.Second), now)
	query := fmt.Sprintf(`SELECT
  COALESCE((SELECT SUM(quantity)::bigint FROM usage_events WHERE tenant_id::text = $1
    AND usage_type = 'llm_tokens' AND created_at >= $4 %s), 0),
  COALESCE((SELECT SUM(quantity)::bigint FROM usage_events WHERE tenant_id::text = $1
    AND usage_type = 'llm_cost_micros' AND created_at >= $4 %s), 0),
  COALESCE((SELECT SUM(reserved_tokens)::bigint FROM llm_quota_reservations WHERE tenant_id::text = $1
    AND status = 'reserved' AND expires_at > $5 %s), 0),
  COALESCE((SELECT SUM(reserved_cost_micros)::bigint FROM llm_quota_reservations WHERE tenant_id::text = $1
    AND status = 'reserved' AND expires_at > $5 %s), 0),
  COALESCE((SELECT COUNT(*)::int FROM llm_quota_reservations WHERE tenant_id::text = $1
    AND status = 'reserved' AND expires_at > $5 %s), 0)`, filter, filter, filter, filter, filter)
	var usedTokens, usedCost, reservedTokens, reservedCost int64
	var active int
	if err := tx.QueryRowContext(ctx, query, args...).Scan(&usedTokens, &usedCost, &reservedTokens, &reservedCost, &active); err != nil {
		return quotaBackendError()
	}
	if policy.TokenLimit != nil && exceedsQuotaLimit(*policy.TokenLimit, usedTokens, reservedTokens, input.ReservedTokens) {
		return &AppError{Code: "LLM_QUOTA_TOKENS_EXCEEDED", Message: "LLM token quota exceeded"}
	}
	if policy.CostLimitMicros != nil && exceedsQuotaLimit(*policy.CostLimitMicros, usedCost, reservedCost, input.ReservedCostMicros) {
		return &AppError{Code: "LLM_QUOTA_COST_EXCEEDED", Message: "LLM cost quota exceeded"}
	}
	if policy.ConcurrencyLimit != nil && active >= *policy.ConcurrencyLimit {
		return &AppError{Code: "LLM_QUOTA_CONCURRENCY_EXCEEDED", Message: "LLM quota concurrency limit reached"}
	}
	return nil
}

func exceedsQuotaLimit(limit int64, values ...int64) bool {
	remaining := limit
	for _, value := range values {
		if value < 0 || value > remaining {
			return true
		}
		remaining -= value
	}
	return false
}

func checkedNonNegativeSum(left, right int64) (int64, bool) {
	if left < 0 || right < 0 || left > (1<<63-1)-right {
		return 0, false
	}
	return left + right, true
}

func policyScopeSQL(policy PersistentQuotaPolicy, input QuotaReservationInput, from, now time.Time) (string, []any) {
	filter := ""
	if policy.ScopeType == QuotaScopeProject || policy.ScopeType == QuotaScopeModule {
		filter += " AND project_id::text = $2"
	}
	if policy.ScopeType == QuotaScopeModule {
		filter += " AND module_key = $3"
	}
	return filter, []any{input.TenantID, input.ProjectID, input.ModuleKey, from, now}
}

func scanQuotaPolicies(rows *sql.Rows) ([]PersistentQuotaPolicy, error) {
	defer rows.Close()
	policies := []PersistentQuotaPolicy{}
	for rows.Next() {
		var policy PersistentQuotaPolicy
		if err := rows.Scan(&policy.PolicyID, &policy.TenantID, &policy.ScopeType, &policy.ProjectID,
			&policy.ModuleKey, &policy.TokenLimit, &policy.CostLimitMicros, &policy.ConcurrencyLimit,
			&policy.PeriodSeconds, &policy.Enabled, &policy.UpdatedAt); err != nil {
			return nil, quotaBackendError()
		}
		policies = append(policies, policy)
	}
	if err := rows.Err(); err != nil {
		return nil, quotaBackendError()
	}
	return policies, nil
}

func readPolicy(ctx context.Context, tx *sql.Tx, tenantID, policyID string) (PersistentQuotaPolicy, error) {
	var policy PersistentQuotaPolicy
	err := tx.QueryRowContext(ctx, `SELECT policy_id::text, tenant_id::text, scope_type,
  COALESCE(project_id::text, ''), COALESCE(module_key, ''), token_limit,
  cost_limit_micros, concurrency_limit, period_seconds, enabled, updated_at::text
FROM llm_quota_policies WHERE tenant_id::text = $1 AND policy_id::text = $2`, tenantID, policyID).Scan(
		&policy.PolicyID, &policy.TenantID, &policy.ScopeType, &policy.ProjectID, &policy.ModuleKey,
		&policy.TokenLimit, &policy.CostLimitMicros, &policy.ConcurrencyLimit, &policy.PeriodSeconds,
		&policy.Enabled, &policy.UpdatedAt)
	if err != nil {
		return PersistentQuotaPolicy{}, quotaBackendError()
	}
	return policy, nil
}

func validateQuotaPolicyInput(input UpsertQuotaPolicyInput) error {
	if strings.TrimSpace(input.TenantID) == "" || input.PeriodSeconds <= 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota policy is invalid"}
	}
	projectID, moduleKey := strings.TrimSpace(input.ProjectID), strings.TrimSpace(input.ModuleKey)
	validScope := input.ScopeType == QuotaScopeTenant && projectID == "" && moduleKey == "" ||
		input.ScopeType == QuotaScopeProject && projectID != "" && moduleKey == "" ||
		input.ScopeType == QuotaScopeModule && projectID != "" && moduleKey != ""
	if !validScope || input.TokenLimit == nil && input.CostLimitMicros == nil && input.ConcurrencyLimit == nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota policy is invalid"}
	}
	if input.TokenLimit != nil && *input.TokenLimit < 0 || input.CostLimitMicros != nil && *input.CostLimitMicros < 0 ||
		input.ConcurrencyLimit != nil && *input.ConcurrencyLimit <= 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota limits are invalid"}
	}
	return nil
}

func validateReservationInput(input QuotaReservationInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.ModuleKey) == "" || strings.TrimSpace(input.ChannelID) == "" ||
		strings.TrimSpace(input.ModelID) == "" || strings.TrimSpace(input.ProviderCallID) == "" ||
		input.ReservedTokens < 0 || input.ReservedCostMicros < 0 || input.TTL <= 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota reservation is invalid"}
	}
	return nil
}

func nullableString(value string) any {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return value
}

func quotaBackendError() error {
	return &AppError{Code: "LLM_QUOTA_BACKEND_FAILED", Message: "LLM quota backend failed"}
}
