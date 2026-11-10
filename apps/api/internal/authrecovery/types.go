package authrecovery

import (
	"context"
	"errors"
	"time"
)

const (
	CodeValidationFailed   = "VALIDATION_FAILED"
	CodeBackendUnavailable = "AUTH_RECOVERY_BACKEND_UNAVAILABLE"
	CodeTokenInvalid       = "PASSWORD_RESET_TOKEN_INVALID"
	CodeTokenExpired       = "PASSWORD_RESET_TOKEN_EXPIRED"
	CodeTokenConsumed      = "PASSWORD_RESET_TOKEN_ALREADY_USED"
	CodeRateLimited        = "AUTH_RECOVERY_RATE_LIMITED"
)

type AppError struct{ Code, Message string }

func (e *AppError) Error() string { return e.Message }
func ErrorCode(err error) string {
	var target *AppError
	if errors.As(err, &target) {
		return target.Code
	}
	return CodeBackendUnavailable
}

type RequestResetInput struct {
	Email, RequestID, ClientKey string
	ExpiresIn                   time.Duration
}
type CompleteResetInput struct{ Token, NewPassword, RequestID string }
type PublicRequestResult struct {
	OK      bool   `json:"ok"`
	Message string `json:"message"`
}
type ResetDelivery struct {
	ResetTokenID, Email, Token string
	ExpiresAt                  time.Time
}
type DeliveryReceipt struct{ ProviderMessageID string }
type EmailVerificationDelivery struct {
	Email     string
	Token     string
	ExpiresAt time.Time
}
type ResetNotifier interface {
	SendPasswordReset(context.Context, ResetDelivery) (DeliveryReceipt, error)
}

type AbuseLimitInput struct {
	Action   string
	ScopeKey string
	Limit    int64
	Window   time.Duration
}

type AbuseLimitDecision struct {
	Allowed    bool
	RetryAfter time.Duration
}

type AbuseLimiter interface {
	Allow(context.Context, AbuseLimitInput) (AbuseLimitDecision, error)
}

type EnqueueResetInput struct {
	EmailNormalized string
	TokenHash       string
	TokenCiphertext []byte
	RequestID       string
	ExpiresAt       time.Time
}

type PendingDelivery struct {
	OutboxID        string
	ResetTokenID    string
	TokenCiphertext []byte
	Email           string
	ExpiresAt       time.Time
	AttemptCount    int
}

type FinishDeliveryInput struct {
	OutboxID          string
	WorkerID          string
	Status            string
	ErrorCode         string
	ProviderMessageID string
	NextAttemptAt     time.Time
}

type RecoveryStore interface {
	EnqueueReset(context.Context, EnqueueResetInput) error
	CompleteReset(context.Context, string, string, time.Time, string) (string, error)
	ClaimDelivery(context.Context, string, time.Duration) (*PendingDelivery, error)
	FinishDelivery(context.Context, FinishDeliveryInput) error
	ExpireResets(context.Context, time.Time) (int64, error)
}
