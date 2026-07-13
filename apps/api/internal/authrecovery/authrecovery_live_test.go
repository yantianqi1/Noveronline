package authrecovery

import (
	"context"
	"database/sql"
	"net"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"golang.org/x/crypto/bcrypt"
)

const liveRecoveryUserID = "28000000-0000-4000-8000-000000000001"
const liveRecoveryOtherID = "28000000-0000-4000-8000-000000000002"

func TestLivePasswordResetIsGenericAtomicAndRevokesSessions(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_AUTH_RECOVERY_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_AUTH_RECOVERY_LIVE_DATABASE_URL to run auth recovery live E2E")
	}
	adminDB, appDB := prepareRecoveryFixture(t, adminURL)
	address, messages, closeSink := startSMTPSink(t)
	defer closeSink()
	host, portText, _ := net.SplitHostPort(address)
	port, _ := strconv.Atoi(portText)
	notifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: host, Port: port, Username: "test-user", Password: "test-pass", From: "security@example.test", ResetBaseURL: "http://localhost/recovery/reset", TLSMode: SMTPModeLoopbackPlaintext})
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	tokenCipher := testTokenCipher(t)
	store := NewSQLStore(appDB)
	service := NewService(ServiceConfig{DB: appDB, Store: store, TokenCipher: tokenCipher, BcryptCost: bcrypt.MinCost, Now: func() time.Time { return now }})
	dispatcher, err := NewDeliveryDispatcher(DeliveryDispatcherConfig{Store: store, Notifier: notifier, TokenCipher: tokenCipher, WorkerID: "live-recovery-worker", Now: func() time.Time { return now }})
	if err != nil {
		t.Fatal(err)
	}
	existing, err := service.RequestReset(context.Background(), RequestResetInput{Email: " RECOVERY@EXAMPLE.TEST ", RequestID: "live-existing"})
	if err != nil {
		t.Fatal(err)
	}
	select {
	case <-messages:
		t.Fatal("request path performed synchronous SMTP delivery")
	default:
	}
	var queuedStatus, tokenDeliveryStatus string
	var queuedAttempts int
	var storedCiphertext []byte
	if err := adminDB.QueryRow(`SELECT queued.status,queued.attempt_count,queued.token_ciphertext,token.delivery_status FROM password_reset_delivery_outbox queued JOIN password_reset_tokens token USING(reset_token_id) WHERE token.user_id=$1 AND token.status='pending'`, liveRecoveryUserID).Scan(&queuedStatus, &queuedAttempts, &storedCiphertext, &tokenDeliveryStatus); err != nil {
		t.Fatal(err)
	}
	if queuedStatus != "queued" || queuedAttempts != 0 || tokenDeliveryStatus != "pending" || len(storedCiphertext) == 0 {
		t.Fatalf("queued status=%s attempts=%d token_delivery=%s ciphertext=%d", queuedStatus, queuedAttempts, tokenDeliveryStatus, len(storedCiphertext))
	}
	processed, err := dispatcher.DispatchOne(context.Background())
	if err != nil || !processed {
		t.Fatalf("dispatch reset: processed=%v err=%v", processed, err)
	}
	message := <-messages
	token := resetTokenFromMessage(t, message)
	if strings.Contains(string(storedCiphertext), token) {
		t.Fatal("outbox ciphertext exposed raw reset token")
	}
	if err := adminDB.QueryRow(`SELECT queued.status,queued.attempt_count,token.delivery_status FROM password_reset_delivery_outbox queued JOIN password_reset_tokens token USING(reset_token_id) WHERE token.user_id=$1 AND token.status='pending'`, liveRecoveryUserID).Scan(&queuedStatus, &queuedAttempts, &tokenDeliveryStatus); err != nil {
		t.Fatal(err)
	}
	if queuedStatus != "delivered" || queuedAttempts != 1 || tokenDeliveryStatus != "delivered" {
		t.Fatalf("delivered status=%s attempts=%d token_delivery=%s", queuedStatus, queuedAttempts, tokenDeliveryStatus)
	}
	var forbiddenCount int
	if err := appDB.QueryRow(`SELECT count(*) FROM password_reset_tokens`).Scan(&forbiddenCount); err == nil {
		t.Fatal("app role retained direct password_reset_tokens read access")
	}
	missing, err := service.RequestReset(context.Background(), RequestResetInput{Email: "missing@example.test", RequestID: "live-missing"})
	if err != nil {
		t.Fatal(err)
	}
	if processed, err := dispatcher.DispatchOne(context.Background()); err != nil || processed {
		t.Fatalf("missing account created delivery: processed=%v err=%v", processed, err)
	}
	if existing != missing || existing.Message != genericRequestMessage {
		t.Fatalf("enumeration responses differ: %+v %+v", existing, missing)
	}
	var storedHash string
	if err := adminDB.QueryRow(`SELECT token_hash FROM password_reset_tokens WHERE user_id=$1 AND status='pending'`, liveRecoveryUserID).Scan(&storedHash); err != nil {
		t.Fatal(err)
	}
	if storedHash == token || storedHash != hashToken(token) {
		t.Fatal("reset token was not stored hash-only")
	}
	results := make(chan error, 2)
	var wg sync.WaitGroup
	for range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			results <- service.CompleteReset(context.Background(), CompleteResetInput{Token: token, NewPassword: "replacement live password", RequestID: "live-complete"})
		}()
	}
	wg.Wait()
	close(results)
	success, consumed := 0, 0
	for err := range results {
		if err == nil {
			success++
		} else if ErrorCode(err) == CodeTokenConsumed {
			consumed++
		} else {
			t.Fatalf("unexpected concurrent reset error: %v", err)
		}
	}
	if success != 1 || consumed != 1 {
		t.Fatalf("concurrent outcomes success=%d consumed=%d", success, consumed)
	}
	var passwordHash string
	if err := adminDB.QueryRow(`SELECT password_hash FROM user_password_credentials WHERE user_id=$1`, liveRecoveryUserID).Scan(&passwordHash); err != nil {
		t.Fatal(err)
	}
	if bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte("replacement live password")) != nil || bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte("old live password")) == nil {
		t.Fatal("credential replacement did not invalidate old password")
	}
	var activeSessions int
	if err := adminDB.QueryRow(`SELECT count(*) FROM user_sessions WHERE user_id=$1 AND status='active'`, liveRecoveryUserID).Scan(&activeSessions); err != nil || activeSessions != 0 {
		t.Fatalf("active sessions=%d err=%v", activeSessions, err)
	}
	var otherStatus string
	if err := adminDB.QueryRow(`SELECT status FROM user_sessions WHERE user_id=$1`, liveRecoveryOtherID).Scan(&otherStatus); err != nil || otherStatus != "active" {
		t.Fatalf("other session status=%s err=%v", otherStatus, err)
	}
	var audits int
	if err := adminDB.QueryRow(`SELECT count(*) FROM auth_security_audit_logs WHERE user_id=$1`, liveRecoveryUserID).Scan(&audits); err != nil || audits < 2 {
		t.Fatalf("audit count=%d err=%v", audits, err)
	}
	expiredToken := "expired-live-reset-token"
	if _, err := adminDB.Exec(`INSERT INTO password_reset_tokens(user_id,token_hash,expires_at)VALUES($1,$2,$3)`, liveRecoveryUserID, hashToken(expiredToken), now.Add(-time.Minute)); err != nil {
		t.Fatal(err)
	}
	if err := service.CompleteReset(context.Background(), CompleteResetInput{Token: expiredToken, NewPassword: "another replacement password"}); ErrorCode(err) != CodeTokenExpired {
		t.Fatalf("expired reset code=%s err=%v", ErrorCode(err), err)
	}
	var leaked int
	if err := adminDB.QueryRow(`SELECT count(*) FROM auth_security_audit_logs WHERE metadata_jsonb::text LIKE $1`, "%"+token+"%").Scan(&leaked); err != nil || leaked != 0 {
		t.Fatalf("raw reset token leaked to audit: count=%d err=%v", leaked, err)
	}
}

func TestLiveSQLAbuseLimiterIsSharedAcrossConcurrentInstances(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_AUTH_RECOVERY_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_AUTH_RECOVERY_LIVE_DATABASE_URL to run auth recovery live E2E")
	}
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	defer adminDB.Close()
	parsed, _ := url.Parse(adminURL)
	parsed.User = url.UserPassword("mirofish_runtime", "mirofish_runtime_dev_password")
	appDB, err := sql.Open("pgx", parsed.String())
	if err != nil {
		t.Fatal(err)
	}
	defer appDB.Close()
	now := time.Date(2026, 7, 10, 18, 0, 0, 0, time.UTC)
	key := "rate-limit-live@example.test"
	hash := abuseScopeHash("password_reset_request_email_live", key)
	_, _ = adminDB.Exec(`DELETE FROM auth_abuse_rate_limits WHERE scope_key_hash=$1`, hash)
	defer adminDB.Exec(`DELETE FROM auth_abuse_rate_limits WHERE scope_key_hash=$1`, hash)
	limiters := []*SQLAbuseLimiter{
		NewSQLAbuseLimiter(appDB, func() time.Time { return now }),
		NewSQLAbuseLimiter(appDB, func() time.Time { return now }),
	}
	results := make(chan AbuseLimitDecision, 10)
	errors := make(chan error, 10)
	var wg sync.WaitGroup
	for index := range 10 {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			decision, err := limiters[index%len(limiters)].Allow(context.Background(), AbuseLimitInput{Action: "password_reset_request_email_live", ScopeKey: key, Limit: 5, Window: time.Minute})
			if err != nil {
				errors <- err
				return
			}
			results <- decision
		}(index)
	}
	wg.Wait()
	close(results)
	close(errors)
	for err := range errors {
		t.Fatal(err)
	}
	allowed, blocked := 0, 0
	for decision := range results {
		if decision.Allowed {
			allowed++
		} else {
			blocked++
		}
	}
	if allowed != 5 || blocked != 5 {
		t.Fatalf("allowed=%d blocked=%d", allowed, blocked)
	}
	var storedHash, storedAction, serialized string
	var count int
	if err := adminDB.QueryRow(`SELECT scope_key_hash,action,request_count,row_to_json(auth_abuse_rate_limits)::text FROM auth_abuse_rate_limits WHERE scope_key_hash=$1`, hash).Scan(&storedHash, &storedAction, &count, &serialized); err != nil {
		t.Fatal(err)
	}
	if storedHash != hash || storedAction != "password_reset_request_email_live" || count != 10 || strings.Contains(serialized, key) {
		t.Fatalf("unexpected persisted limiter row hash=%q action=%q count=%d", storedHash, storedAction, count)
	}
}

func prepareRecoveryFixture(t *testing.T, adminURL string) (*sql.DB, *sql.DB) {
	t.Helper()
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	if err = adminDB.Ping(); err != nil {
		t.Fatal(err)
	}
	_, _ = adminDB.Exec(`DELETE FROM users WHERE user_id IN($1,$2)`, liveRecoveryUserID, liveRecoveryOtherID)
	_, _ = adminDB.Exec(`DELETE FROM auth_abuse_rate_limits WHERE scope_key_hash IN($1,$2)`, abuseScopeHash("password_reset_request_email", "recovery@example.test"), abuseScopeHash("password_reset_request_email", "missing@example.test"))
	oldHash, _ := bcrypt.GenerateFromPassword([]byte("old live password"), bcrypt.MinCost)
	otherHash, _ := bcrypt.GenerateFromPassword([]byte("other live password"), bcrypt.MinCost)
	_, err = adminDB.Exec(`INSERT INTO users(user_id,email,display_name)VALUES($1,'recovery@example.test','Recovery'),($2,'recovery-other@example.test','Other')`, liveRecoveryUserID, liveRecoveryOtherID)
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO user_password_credentials(user_id,password_hash)VALUES($1,$3),($2,$4)`, liveRecoveryUserID, liveRecoveryOtherID, string(oldHash), string(otherHash))
	}
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO user_sessions(user_id,token_hash,expires_at)VALUES($1,'recovery-session-one',now()+interval '1 day'),($1,'recovery-session-two',now()+interval '1 day'),($2,'recovery-session-other',now()+interval '1 day')`, liveRecoveryUserID, liveRecoveryOtherID)
	}
	if err != nil {
		t.Fatal(err)
	}
	parsed, _ := url.Parse(adminURL)
	parsed.User = url.UserPassword("mirofish_runtime", "mirofish_runtime_dev_password")
	appDB, err := sql.Open("pgx", parsed.String())
	if err != nil {
		t.Fatal(err)
	}
	if err = appDB.Ping(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		appDB.Close()
		_, _ = adminDB.Exec(`DELETE FROM users WHERE user_id IN($1,$2)`, liveRecoveryUserID, liveRecoveryOtherID)
		adminDB.Close()
	})
	return adminDB, appDB
}
func resetTokenFromMessage(t *testing.T, message string) string {
	t.Helper()
	match := regexp.MustCompile(`token=([A-Za-z0-9_-]+)`).FindStringSubmatch(message)
	if len(match) != 2 {
		t.Fatal("SMTP reset message omitted token")
	}
	return match[1]
}
