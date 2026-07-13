package authrecovery

import (
	"context"
	"errors"
	"strings"
	"time"
)

type DeliveryDispatcherConfig struct {
	Store       RecoveryStore
	Notifier    ResetNotifier
	TokenCipher *TokenCipher
	WorkerID    string
	Lease       time.Duration
	RetryDelay  time.Duration
	MaxAttempts int
	Now         func() time.Time
	Metrics     DeliveryMetrics
}

type DeliveryMetrics interface {
	RecordAuthRecoveryDelivery(status string)
}

type DeliveryDispatcher struct {
	store       RecoveryStore
	notifier    ResetNotifier
	tokenCipher *TokenCipher
	workerID    string
	lease       time.Duration
	retryDelay  time.Duration
	maxAttempts int
	now         func() time.Time
	metrics     DeliveryMetrics
}

func NewDeliveryDispatcher(config DeliveryDispatcherConfig) (*DeliveryDispatcher, error) {
	if config.Store == nil || config.Notifier == nil || config.TokenCipher == nil || strings.TrimSpace(config.WorkerID) == "" {
		return nil, errors.New("auth recovery delivery dispatcher is not configured")
	}
	if config.Lease <= 0 {
		config.Lease = time.Minute
	}
	if config.RetryDelay <= 0 {
		config.RetryDelay = time.Minute
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = 5
	}
	if config.Now == nil {
		config.Now = func() time.Time { return time.Now().UTC() }
	}
	return &DeliveryDispatcher{store: config.Store, notifier: config.Notifier, tokenCipher: config.TokenCipher, workerID: strings.TrimSpace(config.WorkerID), lease: config.Lease, retryDelay: config.RetryDelay, maxAttempts: config.MaxAttempts, now: config.Now, metrics: config.Metrics}, nil
}

// DispatchOne processes at most one leased delivery. A true result means an
// outbox item was claimed, even when the delivery attempt failed.
func (d *DeliveryDispatcher) DispatchOne(ctx context.Context) (bool, error) {
	if _, err := d.store.ExpireResets(ctx, d.now()); err != nil {
		d.record("backend_error")
		return false, err
	}
	pending, err := d.store.ClaimDelivery(ctx, d.workerID, d.lease)
	if err != nil {
		d.record("backend_error")
		return false, err
	}
	if pending == nil {
		return false, err
	}
	token, err := d.tokenCipher.DecryptForScope(pending.TokenCiphertext, normalizeEmail(pending.Email))
	if err != nil {
		finishErr := d.finish(ctx, pending, "dead", "TOKEN_DECRYPTION_FAILED", "")
		if finishErr != nil {
			d.record("backend_error")
			return true, errors.Join(err, finishErr)
		}
		d.record("dead")
		return true, err
	}
	receipt, sendErr := d.notifier.SendPasswordReset(ctx, ResetDelivery{ResetTokenID: pending.ResetTokenID, Email: pending.Email, Token: string(token), ExpiresAt: pending.ExpiresAt})
	if sendErr == nil {
		if err := d.finish(ctx, pending, "delivered", "", receipt.ProviderMessageID); err != nil {
			d.record("backend_error")
			return true, err
		}
		d.record("delivered")
		return true, nil
	}
	status := "queued"
	if pending.AttemptCount >= d.maxAttempts {
		status = "dead"
	}
	if err := d.finish(ctx, pending, status, "SMTP_DELIVERY_FAILED", ""); err != nil {
		d.record("backend_error")
		return true, errors.Join(sendErr, err)
	}
	d.record(map[string]string{"queued": "retry", "dead": "dead"}[status])
	return true, sendErr
}

func (d *DeliveryDispatcher) record(status string) {
	if d.metrics != nil {
		d.metrics.RecordAuthRecoveryDelivery(status)
	}
}

func (d *DeliveryDispatcher) finish(ctx context.Context, pending *PendingDelivery, status, errorCode, providerID string) error {
	nextAttempt := d.now()
	if status == "queued" {
		nextAttempt = nextAttempt.Add(d.retryDelay)
	}
	return d.store.FinishDelivery(ctx, FinishDeliveryInput{OutboxID: pending.OutboxID, WorkerID: d.workerID, Status: status, ErrorCode: errorCode, ProviderMessageID: providerID, NextAttemptAt: nextAttempt})
}
