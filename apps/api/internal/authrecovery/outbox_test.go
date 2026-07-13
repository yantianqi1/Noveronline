package authrecovery

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeRecoveryStore struct {
	enqueued       []EnqueueResetInput
	pending        *PendingDelivery
	finishInputs   []FinishDeliveryInput
	finishErr      error
	completeResult string
}

func (s *fakeRecoveryStore) EnqueueReset(_ context.Context, input EnqueueResetInput) error {
	s.enqueued = append(s.enqueued, input)
	return nil
}
func (s *fakeRecoveryStore) CompleteReset(context.Context, string, string, time.Time, string) (string, error) {
	return s.completeResult, nil
}
func (s *fakeRecoveryStore) ClaimDelivery(context.Context, string, time.Duration) (*PendingDelivery, error) {
	pending := s.pending
	s.pending = nil
	return pending, nil
}
func (s *fakeRecoveryStore) FinishDelivery(_ context.Context, input FinishDeliveryInput) error {
	s.finishInputs = append(s.finishInputs, input)
	return s.finishErr
}
func (s *fakeRecoveryStore) ExpireResets(context.Context, time.Time) (int64, error) { return 0, nil }

type allowingLimiter struct{}

func (allowingLimiter) Allow(context.Context, AbuseLimitInput) (AbuseLimitDecision, error) {
	return AbuseLimitDecision{Allowed: true}, nil
}

type recordingNotifier struct {
	calls int
	err   error
}

type deliveryMetricsProbe struct{ statuses []string }

func (m *deliveryMetricsProbe) RecordAuthRecoveryDelivery(status string) {
	m.statuses = append(m.statuses, status)
}

func (n *recordingNotifier) SendPasswordReset(context.Context, ResetDelivery) (DeliveryReceipt, error) {
	n.calls++
	return DeliveryReceipt{ProviderMessageID: "provider-message"}, n.err
}

func testTokenCipher(t *testing.T) *TokenCipher {
	t.Helper()
	cipher, err := NewTokenCipher([]byte("0123456789abcdef0123456789abcdef"))
	if err != nil {
		t.Fatal(err)
	}
	return cipher
}

func TestRequestResetOnlyPersistsOutboxAndNeverCallsSMTP(t *testing.T) {
	store := &fakeRecoveryStore{}
	service := NewService(ServiceConfig{Store: store, AbuseLimiter: allowingLimiter{}, TokenCipher: testTokenCipher(t)})
	result, err := service.RequestReset(context.Background(), RequestResetInput{Email: "user@example.test"})
	if err != nil || !result.OK {
		t.Fatalf("result=%+v err=%v", result, err)
	}
	if len(store.enqueued) != 1 || len(store.enqueued[0].TokenCiphertext) == 0 {
		t.Fatalf("outbox records=%d", len(store.enqueued))
	}
	if string(store.enqueued[0].TokenCiphertext) == store.enqueued[0].TokenHash {
		t.Fatal("outbox persisted plaintext-equivalent token material")
	}
}

func TestOutboxCiphertextIsBoundToNormalizedRecipient(t *testing.T) {
	cipher := testTokenCipher(t)
	ciphertext, err := cipher.EncryptForScope([]byte("raw-reset-token"), "user@example.test")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := cipher.DecryptForScope(ciphertext, "other@example.test"); err == nil {
		t.Fatal("ciphertext decrypted for a different recipient")
	}
}

func TestDispatcherReturnsFinishFailureAfterSuccessfulSMTP(t *testing.T) {
	cipher := testTokenCipher(t)
	ciphertext, _ := cipher.EncryptForScope([]byte("raw-reset-token"), "user@example.test")
	store := &fakeRecoveryStore{pending: &PendingDelivery{OutboxID: "outbox", ResetTokenID: "reset", TokenCiphertext: ciphertext, Email: "user@example.test", AttemptCount: 1}, finishErr: errors.New("finish unavailable")}
	notifier := &recordingNotifier{}
	metrics := &deliveryMetricsProbe{}
	dispatcher, err := NewDeliveryDispatcher(DeliveryDispatcherConfig{Store: store, Notifier: notifier, TokenCipher: cipher, WorkerID: "worker", Metrics: metrics})
	if err != nil {
		t.Fatal(err)
	}
	processed, err := dispatcher.DispatchOne(context.Background())
	if !processed || err == nil || notifier.calls != 1 {
		t.Fatalf("processed=%v err=%v notifier_calls=%d", processed, err, notifier.calls)
	}
	if len(store.finishInputs) != 1 || store.finishInputs[0].Status != "delivered" {
		t.Fatalf("finish=%+v", store.finishInputs)
	}
	if len(metrics.statuses) != 1 || metrics.statuses[0] != "backend_error" {
		t.Fatalf("metrics=%v", metrics.statuses)
	}
}

func TestDispatcherPersistsRetryAndSurfacesSMTPFailure(t *testing.T) {
	cipher := testTokenCipher(t)
	ciphertext, _ := cipher.EncryptForScope([]byte("raw-reset-token"), "user@example.test")
	store := &fakeRecoveryStore{pending: &PendingDelivery{OutboxID: "outbox", ResetTokenID: "reset", TokenCiphertext: ciphertext, Email: "user@example.test", AttemptCount: 1}}
	notifier := &recordingNotifier{err: errors.New("smtp unavailable")}
	metrics := &deliveryMetricsProbe{}
	dispatcher, _ := NewDeliveryDispatcher(DeliveryDispatcherConfig{Store: store, Notifier: notifier, TokenCipher: cipher, WorkerID: "worker", MaxAttempts: 3, Metrics: metrics})
	processed, err := dispatcher.DispatchOne(context.Background())
	if !processed || err == nil || len(store.finishInputs) != 1 || store.finishInputs[0].Status != "queued" || store.finishInputs[0].ErrorCode != "SMTP_DELIVERY_FAILED" {
		t.Fatalf("processed=%v err=%v finish=%+v", processed, err, store.finishInputs)
	}
	if len(metrics.statuses) != 1 || metrics.statuses[0] != "retry" {
		t.Fatalf("metrics=%v", metrics.statuses)
	}
}
