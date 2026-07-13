package llmadmin

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	"mirofish-novel/apps/api/internal/platformratelimit"
)

type allowingLimiter struct{}

func (allowingLimiter) Allow(context.Context, platformratelimit.Input) (platformratelimit.Decision, error) {
	return platformratelimit.Decision{Allowed: true}, nil
}

type recordingLimiter struct {
	input    platformratelimit.Input
	decision platformratelimit.Decision
	err      error
	calls    int
}

func (l *recordingLimiter) Allow(_ context.Context, input platformratelimit.Input) (platformratelimit.Decision, error) {
	l.calls++
	l.input = input
	return l.decision, l.err
}

func TestPolicyWriteRateLimitRunsAfterStrictDecodeAndBeforeStore(t *testing.T) {
	store := &fakeStore{}
	limiter := &recordingLimiter{decision: platformratelimit.Decision{Allowed: false, RetryAfter: 1500 * time.Millisecond}}
	handler := NewHandler(Config{
		Store: store, Access: &roleAccess{role: "admin"}, ActorResolver: staticActor{id: "actor-1"}, RateLimiter: limiter,
	})
	body := []byte(`{"scope_type":"tenant","token_limit":10,"period_seconds":60} {"extra":true}`)
	response := perform(handler, http.MethodPost, "/v1/llm-admin/policies", "tenant-1", body)
	if response.Code != http.StatusBadRequest || limiter.calls != 0 || store.calls != 0 {
		t.Fatalf("invalid body reached limiter/store: status=%d limiter=%d store=%d", response.Code, limiter.calls, store.calls)
	}

	response = perform(handler, http.MethodPost, "/v1/llm-admin/policies", "tenant-1", []byte(`{"scope_type":"tenant","token_limit":10,"period_seconds":60}`))
	if response.Code != http.StatusTooManyRequests || response.Header().Get("Retry-After") != "2" || store.calls != 0 {
		t.Fatalf("denial reached store: status=%d headers=%#v store=%d", response.Code, response.Header(), store.calls)
	}
	if limiter.calls != 1 || limiter.input.Class != platformratelimit.ClassLLMAdminMutation || strings.Join(limiter.input.KeyParts, ",") != "tenant-1,actor-1,llm_admin.policy.write" {
		t.Fatalf("unexpected rate key: %#v", limiter)
	}
}

func TestProviderHealthRateLimitUsesOwnedIdentifiersBeforeProviderSideEffect(t *testing.T) {
	executor := &healthExecutor{result: HealthExecution{StatusCode: http.StatusOK}}
	health := NewHealthService(healthResolver{target: HealthTarget{
		ChannelID: "channel-1", ModelID: "model-1", BaseURL: "http://127.0.0.1:8080/v1", APIKey: "secret",
	}}, executor, nil)
	limiter := &recordingLimiter{err: errors.New("redis credential_ref=private")}
	handler := NewHandler(Config{
		Store: &fakeStore{}, Access: &roleAccess{role: "owner"}, ActorResolver: staticActor{id: "actor-1"},
		Health: health, RateLimiter: limiter,
	})
	response := perform(handler, http.MethodPost, "/v1/llm-admin/provider-health", "tenant-1", []byte(`{"project_id":"project-1","channel_id":"channel-1","model_id":"model-1"}`))
	if response.Code != http.StatusServiceUnavailable || executor.request.BaseURL != "" {
		t.Fatalf("backend failure reached provider: status=%d request=%#v", response.Code, executor.request)
	}
	if limiter.calls != 1 || limiter.input.Class != platformratelimit.ClassLLMProviderHealth || strings.Join(limiter.input.KeyParts, ",") != "tenant-1,actor-1,channel-1,model-1" {
		t.Fatalf("unexpected health key: %#v", limiter)
	}
	assertPrivate(response.Body.String(), t)
}

func TestMutationWithoutLimiterFailsClosedBeforeStore(t *testing.T) {
	store := &fakeStore{}
	handler := NewHandler(Config{Store: store, Access: &roleAccess{role: "admin"}, ActorResolver: staticActor{id: "actor-1"}})
	response := perform(handler, http.MethodDelete, "/v1/llm-admin/policies/policy-1?expected_version=v1", "tenant-1", nil)
	if response.Code != http.StatusServiceUnavailable || store.calls != 0 || !strings.Contains(response.Body.String(), "RATE_LIMIT_BACKEND_UNAVAILABLE") {
		t.Fatalf("nil limiter did not fail closed: %d %s store=%d", response.Code, response.Body.String(), store.calls)
	}
}
