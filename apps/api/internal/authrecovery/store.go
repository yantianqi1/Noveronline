package authrecovery

import (
	"context"
	"database/sql"
	"errors"
	"time"
)

type SQLStore struct{ db *sql.DB }

func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db} }

func (s *SQLStore) EnqueueReset(ctx context.Context, input EnqueueResetInput) error {
	if s == nil || s.db == nil {
		return errors.New("auth recovery store is not configured")
	}
	var matched bool
	var resetTokenID sql.NullString
	return s.db.QueryRowContext(ctx, `SELECT account_matched,reset_token_id::text FROM auth_recovery_request($1,$2,$3,NULLIF($4,''),$5)`, input.EmailNormalized, input.TokenHash, input.TokenCiphertext, input.RequestID, input.ExpiresAt).Scan(&matched, &resetTokenID)
}

func (s *SQLStore) CompleteReset(ctx context.Context, tokenHash, passwordHash string, now time.Time, requestID string) (string, error) {
	if s == nil || s.db == nil {
		return "", errors.New("auth recovery store is not configured")
	}
	var outcome string
	err := s.db.QueryRowContext(ctx, `SELECT auth_recovery_complete($1,$2,$3,NULLIF($4,''))`, tokenHash, passwordHash, now, requestID).Scan(&outcome)
	return outcome, err
}

func (s *SQLStore) ClaimDelivery(ctx context.Context, workerID string, lease time.Duration) (*PendingDelivery, error) {
	if s == nil || s.db == nil || workerID == "" || lease <= 0 {
		return nil, errors.New("auth recovery delivery store is not configured")
	}
	var pending PendingDelivery
	err := s.db.QueryRowContext(ctx, `SELECT outbox_id::text,reset_token_id::text,token_ciphertext,email,expires_at,attempt_count FROM auth_recovery_claim_delivery($1,$2)`, workerID, int64(lease/time.Second)).Scan(&pending.OutboxID, &pending.ResetTokenID, &pending.TokenCiphertext, &pending.Email, &pending.ExpiresAt, &pending.AttemptCount)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &pending, nil
}

func (s *SQLStore) FinishDelivery(ctx context.Context, input FinishDeliveryInput) error {
	if s == nil || s.db == nil {
		return errors.New("auth recovery delivery store is not configured")
	}
	var finished bool
	err := s.db.QueryRowContext(ctx, `SELECT auth_recovery_finish_delivery($1,$2,$3,NULLIF($4,''),NULLIF($5,''),$6)`, input.OutboxID, input.WorkerID, input.Status, input.ErrorCode, input.ProviderMessageID, input.NextAttemptAt).Scan(&finished)
	if err != nil {
		return err
	}
	if !finished {
		return errors.New("auth recovery delivery lease was lost")
	}
	return nil
}

func (s *SQLStore) ExpireResets(ctx context.Context, now time.Time) (int64, error) {
	if s == nil || s.db == nil {
		return 0, errors.New("auth recovery store is not configured")
	}
	var count int64
	err := s.db.QueryRowContext(ctx, `SELECT auth_recovery_expire($1)`, now).Scan(&count)
	return count, err
}
