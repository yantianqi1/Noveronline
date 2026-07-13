package authrecovery

import (
	"context"
	"testing"
	"time"
)

type denyingLimiter struct {
	calls int
	key   string
}

func (l *denyingLimiter) Allow(_ context.Context, input AbuseLimitInput) (AbuseLimitDecision, error) {
	l.calls++
	l.key = input.ScopeKey
	return AbuseLimitDecision{Allowed: false, RetryAfter: time.Minute}, nil
}

func TestRequestResetFailsBeforeDatabaseWorkWhenDistributedLimitExceeded(t *testing.T) {
	limiter := &denyingLimiter{}
	service := NewService(ServiceConfig{AbuseLimiter: limiter})
	_, err := service.RequestReset(context.Background(), RequestResetInput{Email: "USER@example.test"})
	if ErrorCode(err) != CodeRateLimited {
		t.Fatalf("code=%s err=%v", ErrorCode(err), err)
	}
	if limiter.calls != 1 || limiter.key != "user@example.test" {
		t.Fatalf("limiter calls=%d key=%q", limiter.calls, limiter.key)
	}
}

func TestSQLAbuseLimiterHashesScopeKey(t *testing.T) {
	first := abuseScopeHash("password_reset_request", "user@example.test")
	second := abuseScopeHash("password_reset_request", "user@example.test")
	if first != second || len(first) != 64 || first == "user@example.test" {
		t.Fatalf("unexpected scope hash %q", first)
	}
}
