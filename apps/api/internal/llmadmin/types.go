package llmadmin

import (
	"context"
	"errors"
	"net/http"
	"time"
)

const (
	OperationPolicyRead         = "llm_admin.policy.read"
	OperationPolicyWrite        = "llm_admin.policy.write"
	OperationResolutionRead     = "llm_admin.resolution.read"
	OperationReservationRead    = "llm_admin.reservation.read"
	OperationReconciliationRead = "llm_admin.reconciliation.read"
	OperationProviderHealth     = "llm_admin.provider_health.execute"
)

type OperationMetadata struct {
	Operation    string   `json:"operation"`
	Methods      []string `json:"methods"`
	Path         string   `json:"path"`
	AllowedRoles []string `json:"allowed_roles"`
}

func Operations() []OperationMetadata {
	readRoles := []string{"owner", "admin", "billing"}
	writeRoles := []string{"owner", "admin"}
	return []OperationMetadata{
		{Operation: OperationPolicyRead, Methods: []string{http.MethodGet}, Path: "/v1/llm-admin/policies", AllowedRoles: readRoles},
		{Operation: OperationPolicyWrite, Methods: []string{http.MethodPost, http.MethodPut, http.MethodDelete}, Path: "/v1/llm-admin/policies/{policyId}", AllowedRoles: writeRoles},
		{Operation: OperationResolutionRead, Methods: []string{http.MethodGet}, Path: "/v1/llm-admin/resolution", AllowedRoles: readRoles},
		{Operation: OperationReservationRead, Methods: []string{http.MethodGet}, Path: "/v1/llm-admin/reservations", AllowedRoles: readRoles},
		{Operation: OperationReconciliationRead, Methods: []string{http.MethodGet}, Path: "/v1/llm-admin/reconciliation", AllowedRoles: readRoles},
		{Operation: OperationProviderHealth, Methods: []string{http.MethodPost}, Path: "/v1/llm-admin/provider-health", AllowedRoles: writeRoles},
	}
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string { return e.Message }

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "LLM_ADMIN_FAILED"
}

type ActorResolver interface {
	ResolveActor(context.Context, *http.Request) (string, error)
}

type AccessInput struct {
	TenantID  string
	UserID    string
	Operation string
	RequestID string
}

type AccessController interface {
	Authorize(context.Context, AccessInput) error
}

type Policy struct {
	PolicyID         string    `json:"policy_id"`
	ScopeType        string    `json:"scope_type"`
	ProjectID        string    `json:"project_id,omitempty"`
	ModuleKey        string    `json:"module_key,omitempty"`
	TokenLimit       *int64    `json:"token_limit"`
	CostLimitMicros  *int64    `json:"cost_limit_micros"`
	ConcurrencyLimit *int      `json:"concurrency_limit"`
	PeriodSeconds    int       `json:"period_seconds"`
	Enabled          bool      `json:"enabled"`
	Version          string    `json:"version"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

type PolicyWrite struct {
	ScopeType        string `json:"scope_type"`
	ProjectID        string `json:"project_id"`
	ModuleKey        string `json:"module_key"`
	TokenLimit       *int64 `json:"token_limit"`
	CostLimitMicros  *int64 `json:"cost_limit_micros"`
	ConcurrencyLimit *int   `json:"concurrency_limit"`
	PeriodSeconds    int    `json:"period_seconds"`
	Enabled          *bool  `json:"enabled"`
	ExpectedVersion  string `json:"expected_version"`
}

type PolicyUsage struct {
	Policy               Policy    `json:"policy"`
	PeriodFrom           time.Time `json:"period_from"`
	PeriodTo             time.Time `json:"period_to"`
	UsedTokens           int64     `json:"used_tokens"`
	UsedCostMicros       int64     `json:"used_cost_micros"`
	ReservedTokens       int64     `json:"reserved_tokens"`
	ReservedCostMicros   int64     `json:"reserved_cost_micros"`
	ActiveReservations   int       `json:"active_reservations"`
	RemainingTokens      *int64    `json:"remaining_tokens"`
	RemainingCostMicros  *int64    `json:"remaining_cost_micros"`
	RemainingConcurrency *int      `json:"remaining_concurrency"`
}

type ResolutionPreview struct {
	ProjectID       string        `json:"project_id"`
	ModuleKey       string        `json:"module_key"`
	ResolutionOrder []string      `json:"resolution_order"`
	Applicable      []PolicyUsage `json:"applicable"`
	LimitingScopes  []string      `json:"limiting_scopes"`
	Status          string        `json:"status"`
}

type Reservation struct {
	ReservationID          string     `json:"reservation_id"`
	ProviderCallID         string     `json:"provider_call_id"`
	ProjectID              string     `json:"project_id"`
	RunID                  string     `json:"run_id,omitempty"`
	ModuleKey              string     `json:"module_key"`
	ChannelID              string     `json:"channel_id"`
	ModelID                string     `json:"model_id"`
	ReservedTokens         int64      `json:"reserved_tokens"`
	ReservedCostMicros     int64      `json:"reserved_cost_micros"`
	ActualPromptTokens     *int64     `json:"actual_prompt_tokens"`
	ActualCompletionTokens *int64     `json:"actual_completion_tokens"`
	ActualCostMicros       *int64     `json:"actual_cost_micros"`
	Status                 string     `json:"status"`
	ExpiresAt              time.Time  `json:"expires_at"`
	FinalizedAt            *time.Time `json:"finalized_at,omitempty"`
	CreatedAt              time.Time  `json:"created_at"`
	UpdatedAt              time.Time  `json:"updated_at"`
}

type Reconciliation struct {
	ProviderCallID    string   `json:"provider_call_id"`
	ReservationID     string   `json:"reservation_id,omitempty"`
	ProjectID         string   `json:"project_id,omitempty"`
	RunID             string   `json:"run_id,omitempty"`
	ModuleKey         string   `json:"module_key,omitempty"`
	ModelID           string   `json:"model_id,omitempty"`
	ReservationStatus string   `json:"reservation_status,omitempty"`
	ActivityStatus    string   `json:"activity_status,omitempty"`
	ReservedTokens    *int64   `json:"reserved_tokens"`
	ActualTokens      *int64   `json:"actual_tokens"`
	UsageTokens       *int64   `json:"usage_tokens"`
	ActualCostMicros  *int64   `json:"actual_cost_micros"`
	UsageCostMicros   *int64   `json:"usage_cost_micros"`
	PricingStatus     string   `json:"pricing_status"`
	BillingStatus     string   `json:"billing_status"`
	Issues            []string `json:"issues"`
}

type HealthTarget struct {
	ChannelID             string
	ModelID               string
	BaseURL               string
	APIKey                string
	ExternalProviderOptIn bool
	SupportsTools         bool
	SupportsJSON          bool
}

type HealthCredentialResolver interface {
	ResolveHealthTarget(context.Context, string, string, string, string) (HealthTarget, error)
}

type HealthRequest struct {
	BaseURL               string
	APIKey                string
	ModelID               string
	ExternalProviderOptIn bool
	ProviderCallID        string
	Body                  []byte
}

type HealthExecution struct{ StatusCode int }

type HealthExecutor interface {
	ExecuteHealth(context.Context, HealthRequest) (HealthExecution, error)
}

type HealthResult struct {
	ChannelID     string    `json:"channel_id"`
	ModelID       string    `json:"model_id"`
	Status        string    `json:"status"`
	StatusCode    int       `json:"status_code,omitempty"`
	LatencyMS     int64     `json:"latency_ms"`
	SupportsTools bool      `json:"supports_tools"`
	SupportsJSON  bool      `json:"supports_json"`
	CheckedAt     time.Time `json:"checked_at"`
}
