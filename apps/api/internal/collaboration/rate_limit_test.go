package collaboration

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"mirofish-novel/apps/api/internal/platformratelimit"
)

type collaborationLimiter struct {
	input    platformratelimit.Input
	decision platformratelimit.Decision
	err      error
	calls    int
}

func (l *collaborationLimiter) Allow(_ context.Context, input platformratelimit.Input) (platformratelimit.Decision, error) {
	l.calls++
	l.input = input
	return l.decision, l.err
}

type staticTrustedClient struct {
	key   string
	err   error
	calls int
}

func (r *staticTrustedClient) ResolveTrustedClientKey(context.Context, *http.Request) (string, error) {
	r.calls++
	return r.key, r.err
}

func TestInvitationCreateStrictDecodePrecedesRateLimitAndDenialPrecedesService(t *testing.T) {
	limiter := &collaborationLimiter{decision: platformratelimit.Decision{Allowed: false, RetryAfter: 1100 * time.Millisecond}}
	handler := NewHandler(HandlerConfig{
		Service: NewService(ServiceConfig{}), ActorResolver: &countingActorResolver{},
		CSRFVerifier: &countingCSRFVerifier{}, RateLimiter: limiter,
	})
	invalid := httptest.NewRequest(http.MethodPost, "/v1/tenants/tenant-1/invitations", strings.NewReader(`{"email":"User@Example.test","tenant_role":"viewer"} {}`))
	invalidResponse := httptest.NewRecorder()
	handler.ServeHTTP(invalidResponse, invalid)
	if invalidResponse.Code != http.StatusBadRequest || limiter.calls != 0 {
		t.Fatalf("invalid body reached limiter: status=%d calls=%d", invalidResponse.Code, limiter.calls)
	}

	request := httptest.NewRequest(http.MethodPost, "/v1/tenants/tenant-1/invitations", strings.NewReader(`{"email":"User@Example.test","tenant_role":"viewer"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusTooManyRequests || response.Header().Get("Retry-After") != "2" {
		t.Fatalf("denial response mismatch: %d %#v %s", response.Code, response.Header(), response.Body.String())
	}
	if limiter.calls != 1 || limiter.input.Class != platformratelimit.ClassCollaborationInviteCreate || strings.Join(limiter.input.KeyParts, ",") != "tenant-1,actor,user@example.test" {
		t.Fatalf("unexpected create key: %#v", limiter)
	}
}

func TestInvitationAcceptUsesTrustedClientAndTokenHashBeforeService(t *testing.T) {
	limiter := &collaborationLimiter{err: errors.New("redis token=private")}
	client := &staticTrustedClient{key: "trusted-client-hash"}
	handler := NewHandler(HandlerConfig{
		Service: NewService(ServiceConfig{}), ActorResolver: &countingActorResolver{},
		CSRFVerifier: &countingCSRFVerifier{}, RateLimiter: limiter, TrustedClientKeyResolver: client,
	})
	rawToken := "raw-invitation-token-private"
	request := httptest.NewRequest(http.MethodPost, "/v1/collaboration/invitations/accept", strings.NewReader(`{"token":"`+rawToken+`"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable || client.calls != 1 || limiter.calls != 1 {
		t.Fatalf("backend failure mismatch: status=%d client=%d limiter=%d", response.Code, client.calls, limiter.calls)
	}
	expected := sha256.Sum256([]byte(rawToken))
	if limiter.input.Class != platformratelimit.ClassCollaborationInviteAccept || strings.Join(limiter.input.KeyParts, ",") != "trusted-client-hash,"+fmt.Sprintf("%x", expected[:]) {
		t.Fatalf("unexpected accept key: %#v", limiter.input)
	}
	if strings.Contains(strings.Join(limiter.input.KeyParts, ","), rawToken) || strings.Contains(response.Body.String(), rawToken) || strings.Contains(response.Body.String(), "redis") {
		t.Fatalf("private rate material leaked: %#v %s", limiter.input, response.Body.String())
	}
}

func TestInvitationAcceptMissingTrustedClientResolverFailsClosedBeforeLimiter(t *testing.T) {
	limiter := &collaborationLimiter{decision: platformratelimit.Decision{Allowed: true}}
	handler := NewHandler(HandlerConfig{
		Service: NewService(ServiceConfig{}), ActorResolver: &countingActorResolver{},
		CSRFVerifier: &countingCSRFVerifier{}, RateLimiter: limiter,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/collaboration/invitations/accept", strings.NewReader(`{"token":"private-token"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable || limiter.calls != 0 || !strings.Contains(response.Body.String(), "RATE_LIMIT_BACKEND_UNAVAILABLE") {
		t.Fatalf("missing client resolver did not fail closed: %d %s", response.Code, response.Body.String())
	}
}
