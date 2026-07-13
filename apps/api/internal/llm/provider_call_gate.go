package llm

import (
	"context"
	"errors"
	"strings"
	"time"
)

type ProviderCallLease struct {
	LeaseID   string
	ExpiresAt time.Time
}

type ProviderCallLeaseInput struct {
	TenantID  string
	ProjectID string
	ModuleKey string
	ChannelID string
	RunID     string
}

type ProviderCallLeaseManager interface {
	Acquire(context.Context, ProviderCallLeaseInput) (ProviderCallLease, error)
	Release(context.Context, ProviderCallLeaseInput, ProviderCallLease) error
}

type ProviderCallGate struct {
	quota  *QuotaEnforcer
	leases ProviderCallLeaseManager
	now    func() time.Time
}

func NewProviderCallGate(quota *QuotaEnforcer, leases ProviderCallLeaseManager) *ProviderCallGate {
	return &ProviderCallGate{quota: quota, leases: leases, now: time.Now}
}

func (g *ProviderCallGate) Execute(
	ctx context.Context,
	input ProviderCallLeaseInput,
	policy QuotaPolicy,
	call func(context.Context) error,
) error {
	if err := validateProviderCallGateInput(input, call); err != nil {
		return err
	}
	if g == nil || g.quota == nil {
		return &AppError{Code: "LLM_QUOTA_POLICY_UNAVAILABLE", Message: "LLM quota policy is unavailable"}
	}
	if !quotaScopeMatchesCall(policy, input) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "LLM quota scope does not match provider call context"}
	}
	if _, err := g.quota.CheckBeforeProviderCall(ctx, policy); err != nil {
		return err
	}
	if g.leases == nil {
		return &AppError{Code: "LLM_CONCURRENCY_BACKEND_UNCONFIGURED", Message: "LLM concurrency backend is not configured"}
	}

	lease, err := g.leases.Acquire(ctx, input)
	if err != nil {
		return stableLeaseAcquireError(err)
	}
	now := time.Now()
	if g.now != nil {
		now = g.now()
	}
	if strings.TrimSpace(lease.LeaseID) == "" {
		return &AppError{Code: "LLM_CONCURRENCY_ACQUIRE_FAILED", Message: "LLM concurrency lease acquisition failed"}
	}
	if lease.ExpiresAt.IsZero() || !lease.ExpiresAt.After(now) {
		releaseCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
		defer cancel()
		if releaseErr := g.leases.Release(releaseCtx, input, lease); releaseErr != nil {
			return &AppError{Code: "LLM_CONCURRENCY_RELEASE_FAILED", Message: "LLM concurrency lease release failed"}
		}
		return &AppError{Code: "LLM_CONCURRENCY_LEASE_EXPIRED", Message: "LLM concurrency lease expired before provider call"}
	}

	callErr := call(ctx)
	releaseCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	releaseErr := g.leases.Release(releaseCtx, input, lease)
	if releaseErr != nil {
		return &AppError{Code: "LLM_CONCURRENCY_RELEASE_FAILED", Message: "LLM concurrency lease release failed"}
	}
	if callErr != nil {
		return stableProviderCallError(callErr)
	}
	return nil
}

func quotaScopeMatchesCall(policy QuotaPolicy, input ProviderCallLeaseInput) bool {
	if policy.Mode == QuotaModeUnlimited && strings.TrimSpace(policy.Scope.TenantID) == "" {
		return true
	}
	if strings.TrimSpace(policy.Scope.TenantID) != strings.TrimSpace(input.TenantID) {
		return false
	}
	checks := [][2]string{
		{policy.Scope.ProjectID, input.ProjectID},
		{policy.Scope.ModuleKey, input.ModuleKey},
		{policy.Scope.RunID, input.RunID},
	}
	for _, check := range checks {
		if scope := strings.TrimSpace(check[0]); scope != "" && scope != strings.TrimSpace(check[1]) {
			return false
		}
	}
	return true
}

func validateProviderCallGateInput(input ProviderCallLeaseInput, call func(context.Context) error) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.ModuleKey) == "" || strings.TrimSpace(input.ChannelID) == "" ||
		strings.TrimSpace(input.RunID) == "" || call == nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "provider call context is incomplete"}
	}
	return nil
}

func stableLeaseAcquireError(err error) error {
	var appErr *AppError
	if errors.As(err, &appErr) && appErr.Code == "LLM_CONCURRENCY_LIMITED" {
		return &AppError{Code: "LLM_CONCURRENCY_LIMITED", Message: "LLM concurrency limit reached"}
	}
	return &AppError{Code: "LLM_CONCURRENCY_ACQUIRE_FAILED", Message: "LLM concurrency lease acquisition failed"}
}

func stableProviderCallError(err error) error {
	var appErr *AppError
	if errors.As(err, &appErr) {
		switch appErr.Code {
		case "LLM_PROVIDER_RATE_LIMITED":
			return &AppError{Code: appErr.Code, Message: "LLM provider rate limit reached"}
		case "LLM_PROVIDER_UNAVAILABLE":
			return &AppError{Code: appErr.Code, Message: "LLM provider is unavailable"}
		}
	}
	return &AppError{Code: "LLM_PROVIDER_ERROR", Message: "LLM provider call failed"}
}

type RetryDecision struct {
	Code      string `json:"code"`
	Retryable bool   `json:"retryable"`
}

func ProviderCallRetryDecision(err error) RetryDecision {
	code := ErrorCode(err)
	switch code {
	case "LLM_CONCURRENCY_LIMITED", "LLM_CONCURRENCY_ACQUIRE_FAILED", "LLM_CONCURRENCY_LEASE_EXPIRED",
		"LLM_PROVIDER_RATE_LIMITED", "LLM_PROVIDER_UNAVAILABLE":
		return RetryDecision{Code: code, Retryable: true}
	default:
		return RetryDecision{Code: code, Retryable: false}
	}
}
