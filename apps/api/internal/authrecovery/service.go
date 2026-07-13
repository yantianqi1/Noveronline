package authrecovery

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
)

const genericRequestMessage = "If an eligible account exists, password reset delivery will be attempted."

type ServiceConfig struct {
	DB           *sql.DB
	Store        RecoveryStore
	AbuseLimiter AbuseLimiter
	TokenCipher  *TokenCipher
	BcryptCost   int
	Now          func() time.Time
}
type Service struct {
	store        RecoveryStore
	abuseLimiter AbuseLimiter
	tokenCipher  *TokenCipher
	bcryptCost   int
	now          func() time.Time
}

func NewService(config ServiceConfig) *Service {
	cost := config.BcryptCost
	if cost < bcrypt.MinCost || cost > bcrypt.MaxCost {
		cost = bcrypt.DefaultCost
	}
	now := config.Now
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	limiter := config.AbuseLimiter
	if limiter == nil && config.DB != nil {
		limiter = NewSQLAbuseLimiter(config.DB, now)
	}
	store := config.Store
	if store == nil && config.DB != nil {
		store = NewSQLStore(config.DB)
	}
	return &Service{store: store, abuseLimiter: limiter, tokenCipher: config.TokenCipher, bcryptCost: cost, now: now}
}

func (s *Service) RequestReset(ctx context.Context, input RequestResetInput) (PublicRequestResult, error) {
	email := normalizeEmail(input.Email)
	if email == "" || !strings.Contains(email, "@") {
		return PublicRequestResult{}, &AppError{Code: CodeValidationFailed, Message: "a valid email is required"}
	}
	if err := s.checkRequestLimit(ctx, "password_reset_request_email", email, 5, 15*time.Minute); err != nil {
		return PublicRequestResult{}, err
	}
	if clientKey := strings.TrimSpace(input.ClientKey); clientKey != "" {
		if err := s.checkRequestLimit(ctx, "password_reset_request_client", clientKey, 20, 15*time.Minute); err != nil {
			return PublicRequestResult{}, err
		}
	}
	if s.store == nil || s.tokenCipher == nil {
		return PublicRequestResult{}, backendError()
	}
	token, tokenHash, err := newToken()
	if err != nil {
		return PublicRequestResult{}, backendError()
	}
	ttl := input.ExpiresIn
	if ttl <= 0 {
		ttl = 30 * time.Minute
	}
	ciphertext, err := s.tokenCipher.EncryptForScope([]byte(token), email)
	if err != nil {
		return PublicRequestResult{}, backendError()
	}
	expiresAt := s.now().Add(ttl)
	if err := s.store.EnqueueReset(ctx, EnqueueResetInput{EmailNormalized: email, TokenHash: tokenHash, TokenCiphertext: ciphertext, RequestID: input.RequestID, ExpiresAt: expiresAt}); err != nil {
		return PublicRequestResult{}, backendError()
	}
	return PublicRequestResult{OK: true, Message: genericRequestMessage}, nil
}

func (s *Service) checkRequestLimit(ctx context.Context, action, scopeKey string, limit int64, window time.Duration) error {
	if s.abuseLimiter == nil {
		return backendError()
	}
	decision, err := s.abuseLimiter.Allow(ctx, AbuseLimitInput{Action: action, ScopeKey: scopeKey, Limit: limit, Window: window})
	if err != nil {
		return backendError()
	}
	if !decision.Allowed {
		return &AppError{Code: CodeRateLimited, Message: "password recovery requests are temporarily limited"}
	}
	return nil
}

func (s *Service) CompleteReset(ctx context.Context, input CompleteResetInput) error {
	if strings.TrimSpace(input.Token) == "" || len([]byte(input.NewPassword)) < 12 || len([]byte(input.NewPassword)) > 72 {
		return &AppError{Code: CodeValidationFailed, Message: "token and a password between 12 and 72 bytes are required"}
	}
	if s.store == nil {
		return backendError()
	}
	newHash, err := bcrypt.GenerateFromPassword([]byte(input.NewPassword), s.bcryptCost)
	if err != nil {
		return backendError()
	}
	outcome, err := s.store.CompleteReset(ctx, hashToken(input.Token), string(newHash), s.now(), input.RequestID)
	if err != nil {
		return backendError()
	}
	switch outcome {
	case "completed":
		return nil
	case "invalid":
		return &AppError{Code: CodeTokenInvalid, Message: "password reset token is invalid"}
	case "consumed":
		return &AppError{Code: CodeTokenConsumed, Message: "password reset token is no longer available"}
	case "expired":
		return &AppError{Code: CodeTokenExpired, Message: "password reset token has expired"}
	default:
		return backendError()
	}
}
func normalizeEmail(v string) string { return strings.ToLower(strings.TrimSpace(v)) }
func newToken() (string, string, error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", "", err
	}
	token := base64.RawURLEncoding.EncodeToString(raw)
	return token, hashToken(token), nil
}
func hashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}
func backendError() error {
	return &AppError{Code: CodeBackendUnavailable, Message: "password recovery service is unavailable"}
}
