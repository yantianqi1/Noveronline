package authrecovery

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"strings"
	"time"
)

type SQLAbuseLimiter struct {
	db  *sql.DB
	now func() time.Time
}

func NewSQLAbuseLimiter(db *sql.DB, now func() time.Time) *SQLAbuseLimiter {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &SQLAbuseLimiter{db: db, now: now}
}

func (l *SQLAbuseLimiter) Allow(ctx context.Context, input AbuseLimitInput) (AbuseLimitDecision, error) {
	if l == nil || l.db == nil || strings.TrimSpace(input.Action) == "" || strings.TrimSpace(input.ScopeKey) == "" || input.Limit <= 0 || input.Window <= 0 {
		return AbuseLimitDecision{}, errors.New("auth abuse limiter is not configured")
	}
	now := l.now()
	windowSeconds := int64(input.Window / time.Second)
	if windowSeconds < 1 {
		return AbuseLimitDecision{}, errors.New("auth abuse limiter window is invalid")
	}
	var count int64
	var blockedUntil sql.NullTime
	err := l.db.QueryRowContext(ctx, `INSERT INTO auth_abuse_rate_limits(
  scope_key_hash,action,window_started_at,request_count,blocked_until,updated_at
) VALUES($1,$2,$3,1,NULL,$3)
ON CONFLICT(scope_key_hash) DO UPDATE SET
  action=EXCLUDED.action,
  window_started_at=CASE WHEN auth_abuse_rate_limits.window_started_at + make_interval(secs => $4) <= $3 THEN $3 ELSE auth_abuse_rate_limits.window_started_at END,
  request_count=CASE WHEN auth_abuse_rate_limits.window_started_at + make_interval(secs => $4) <= $3 THEN 1 ELSE auth_abuse_rate_limits.request_count + 1 END,
  blocked_until=CASE
    WHEN auth_abuse_rate_limits.blocked_until > $3 THEN auth_abuse_rate_limits.blocked_until
    WHEN auth_abuse_rate_limits.window_started_at + make_interval(secs => $4) <= $3 THEN NULL
    WHEN auth_abuse_rate_limits.request_count + 1 > $5 THEN auth_abuse_rate_limits.window_started_at + make_interval(secs => $4)
    ELSE NULL
  END,
  updated_at=$3
RETURNING request_count,blocked_until`, abuseScopeHash(input.Action, input.ScopeKey), input.Action, now, windowSeconds, input.Limit).Scan(&count, &blockedUntil)
	if err != nil {
		return AbuseLimitDecision{}, err
	}
	if blockedUntil.Valid && blockedUntil.Time.After(now) {
		return AbuseLimitDecision{Allowed: false, RetryAfter: blockedUntil.Time.Sub(now)}, nil
	}
	return AbuseLimitDecision{Allowed: count <= input.Limit}, nil
}

func abuseScopeHash(action, scopeKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(action) + "\x00" + strings.TrimSpace(scopeKey)))
	return hex.EncodeToString(sum[:])
}
