package llm

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestProviderCallGateChecksQuotaBeforeLeaseAndProvider(t *testing.T) {
	order := []string{}
	meter := &orderedTokenUsageMeter{order: &order, used: 100}
	leases := &recordingProviderLeaseManager{order: &order}
	gate := NewProviderCallGate(NewQuotaEnforcer(meter), leases)

	err := gate.Execute(context.Background(), providerCallInput(), enforcedCallQuota(100), func(context.Context) error {
		order = append(order, "provider")
		return nil
	})

	if code := ErrorCode(err); code != "LLM_QUOTA_EXCEEDED" {
		t.Fatalf("expected pre-call quota rejection, got %s (%v)", code, err)
	}
	if strings.Join(order, ",") != "quota" || leases.acquireCalls != 0 {
		t.Fatalf("quota must reject before lease/provider side effects: %#v", order)
	}
}

func TestProviderCallGateAcquiresCallsAndReleasesInOrder(t *testing.T) {
	order := []string{}
	leases := &recordingProviderLeaseManager{
		order: &order,
		lease: ProviderCallLease{LeaseID: "lease-123", ExpiresAt: time.Now().Add(time.Minute)},
	}
	gate := NewProviderCallGate(NewQuotaEnforcer(&orderedTokenUsageMeter{order: &order, used: 1}), leases)

	err := gate.Execute(context.Background(), providerCallInput(), enforcedCallQuota(100), func(context.Context) error {
		order = append(order, "provider")
		return nil
	})

	if err != nil {
		t.Fatalf("execute provider call: %v", err)
	}
	if strings.Join(order, ",") != "quota,acquire,provider,release" {
		t.Fatalf("unexpected provider gate order: %#v", order)
	}
}

func TestProviderCallGateRejectsExpiredLeaseAndStillReleases(t *testing.T) {
	now := time.Date(2026, 7, 10, 0, 0, 0, 0, time.UTC)
	providerCalled := false
	leases := &recordingProviderLeaseManager{lease: ProviderCallLease{LeaseID: "lease-123", ExpiresAt: now}}
	gate := NewProviderCallGate(NewQuotaEnforcer(&recordingTokenUsageMeter{}), leases)
	gate.now = func() time.Time { return now }

	err := gate.Execute(context.Background(), providerCallInput(), enforcedCallQuota(100), func(context.Context) error {
		providerCalled = true
		return nil
	})

	if code := ErrorCode(err); code != "LLM_CONCURRENCY_LEASE_EXPIRED" {
		t.Fatalf("expected expired lease error, got %s (%v)", code, err)
	}
	if providerCalled || leases.releaseCalls != 1 {
		t.Fatalf("expired lease must not call provider and must release: provider=%t releases=%d", providerCalled, leases.releaseCalls)
	}
}

func TestProviderCallGateSurfacesStableAcquireAndReleaseErrors(t *testing.T) {
	gate := NewProviderCallGate(NewQuotaEnforcer(&recordingTokenUsageMeter{}), &recordingProviderLeaseManager{
		acquireErr: errors.New("api_key=secret prompt=private"),
	})
	err := gate.Execute(context.Background(), providerCallInput(), enforcedCallQuota(100), func(context.Context) error { return nil })
	if code := ErrorCode(err); code != "LLM_CONCURRENCY_ACQUIRE_FAILED" || err.Error() != "LLM concurrency lease acquisition failed" {
		t.Fatalf("expected stable acquire error, got %s (%v)", code, err)
	}

	gate = NewProviderCallGate(NewQuotaEnforcer(&recordingTokenUsageMeter{}), &recordingProviderLeaseManager{
		lease:      ProviderCallLease{LeaseID: "lease-123", ExpiresAt: time.Now().Add(time.Minute)},
		releaseErr: errors.New("credential_ref=secret source_text=private"),
	})
	err = gate.Execute(context.Background(), providerCallInput(), enforcedCallQuota(100), func(context.Context) error { return nil })
	if code := ErrorCode(err); code != "LLM_CONCURRENCY_RELEASE_FAILED" || err.Error() != "LLM concurrency lease release failed" {
		t.Fatalf("expected stable release error, got %s (%v)", code, err)
	}
}

func TestProviderCallGateDoesNotSilentlyDropReleaseFailureAfterProviderFailure(t *testing.T) {
	leases := &recordingProviderLeaseManager{
		lease:      ProviderCallLease{LeaseID: "lease-123", ExpiresAt: time.Now().Add(time.Minute)},
		releaseErr: errors.New("release failed"),
	}
	gate := NewProviderCallGate(NewQuotaEnforcer(&recordingTokenUsageMeter{}), leases)

	err := gate.Execute(context.Background(), providerCallInput(), enforcedCallQuota(100), func(context.Context) error {
		return errors.New("provider failed with api_key=secret prompt=private")
	})

	if code := ErrorCode(err); code != "LLM_CONCURRENCY_RELEASE_FAILED" {
		t.Fatalf("release failure must remain visible, got %s (%v)", code, err)
	}
}

func TestProviderCallGateSanitizesProviderErrorsAndClassifiesRetry(t *testing.T) {
	leasing := &recordingProviderLeaseManager{lease: ProviderCallLease{LeaseID: "lease-123", ExpiresAt: time.Now().Add(time.Minute)}}
	gate := NewProviderCallGate(NewQuotaEnforcer(&recordingTokenUsageMeter{}), leasing)

	err := gate.Execute(context.Background(), providerCallInput(), enforcedCallQuota(100), func(context.Context) error {
		return errors.New("provider response leaked api_key=secret prompt=private")
	})

	if code := ErrorCode(err); code != "LLM_PROVIDER_ERROR" || err.Error() != "LLM provider call failed" {
		t.Fatalf("expected stable provider error, got %s (%v)", code, err)
	}
	if decision := ProviderCallRetryDecision(err); decision.Retryable || decision.Code != "LLM_PROVIDER_ERROR" {
		t.Fatalf("ambiguous post-call error must not auto-retry: %#v", decision)
	}
	quotaErr := &AppError{Code: "LLM_QUOTA_EXCEEDED", Message: "LLM token quota exceeded"}
	if decision := ProviderCallRetryDecision(quotaErr); decision.Retryable {
		t.Fatalf("quota rejection must not retry automatically: %#v", decision)
	}
	releaseErr := &AppError{Code: "LLM_CONCURRENCY_RELEASE_FAILED", Message: "LLM concurrency lease release failed"}
	if decision := ProviderCallRetryDecision(releaseErr); decision.Retryable {
		t.Fatalf("post-call release failure must not auto-retry: %#v", decision)
	}
}

func TestProviderCallGateRejectsMismatchedQuotaScope(t *testing.T) {
	leases := &recordingProviderLeaseManager{}
	gate := NewProviderCallGate(NewQuotaEnforcer(&recordingTokenUsageMeter{}), leases)
	policy := enforcedCallQuota(100)
	policy.Scope.ProjectID = "other-project"

	err := gate.Execute(context.Background(), providerCallInput(), policy, func(context.Context) error { return nil })

	if code := ErrorCode(err); code != "VALIDATION_FAILED" || leases.acquireCalls != 0 {
		t.Fatalf("mismatched quota scope reached lease backend: code=%s leases=%d", code, leases.acquireCalls)
	}
}

type orderedTokenUsageMeter struct {
	order *[]string
	used  float64
}

func (m *orderedTokenUsageMeter) MeasureTokens(context.Context, UsageAggregateQueryInput) (TokenUsageMeasurement, error) {
	*m.order = append(*m.order, "quota")
	return TokenUsageMeasurement{Used: m.used, Status: "available"}, nil
}

type recordingProviderLeaseManager struct {
	order        *[]string
	lease        ProviderCallLease
	acquireErr   error
	releaseErr   error
	acquireCalls int
	releaseCalls int
}

func (m *recordingProviderLeaseManager) Acquire(context.Context, ProviderCallLeaseInput) (ProviderCallLease, error) {
	m.acquireCalls++
	if m.order != nil {
		*m.order = append(*m.order, "acquire")
	}
	if m.acquireErr != nil {
		return ProviderCallLease{}, m.acquireErr
	}
	return m.lease, nil
}

func (m *recordingProviderLeaseManager) Release(context.Context, ProviderCallLeaseInput, ProviderCallLease) error {
	m.releaseCalls++
	if m.order != nil {
		*m.order = append(*m.order, "release")
	}
	return m.releaseErr
}

func providerCallInput() ProviderCallLeaseInput {
	return ProviderCallLeaseInput{
		TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer",
		ChannelID: "channel-123", RunID: "run-123",
	}
}

func enforcedCallQuota(limit float64) QuotaPolicy {
	return QuotaPolicy{
		Mode: QuotaModeEnforced, Limit: limit,
		Scope: UsageAggregateQueryInput{TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer", RunID: "run-123"},
	}
}
