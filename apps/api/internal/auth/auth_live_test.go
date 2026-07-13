package auth

import (
	"context"
	"database/sql"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"golang.org/x/crypto/bcrypt"
)

const (
	liveAuthUserID          = "a9111111-1111-4111-8111-111111111111"
	liveAuthOtherUserID     = "a9222222-2222-4222-8222-222222222222"
	liveAuthAppRole         = "mirofish_auth_live_app"
	liveAuthAppRolePassword = "mirofish_auth_live_password"
)

func TestLiveSQLPasswordChangerReplacesCredentialAndRevokesOnlyTargetUserSessions(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_AUTH_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_AUTH_LIVE_DATABASE_URL to run live password-change E2E")
	}
	adminDB, appDB := prepareLivePasswordChangeFixture(t, adminURL)
	queryer := NewSQLDBQueryer(appDB)
	changer := NewSQLPasswordChanger(SQLPasswordChangerConfig{
		Queryer: queryer,
		Execer:  queryer,
	})
	changedAt := time.Date(2026, 7, 10, 12, 0, 0, 0, time.UTC)

	err := changer.ChangePassword(context.Background(), ChangePasswordInput{
		UserID:          liveAuthUserID,
		CurrentPassword: "current live password",
		NewPassword:     "replacement live password",
		Now:             changedAt,
		RequestID:       "req-live-password-change",
	})
	if err != nil {
		t.Fatalf("change live password: code=%s err=%v", ErrorCode(err), err)
	}

	var newHash string
	var passwordUpdatedAt time.Time
	if err := adminDB.QueryRow(`SELECT password_hash, password_updated_at
FROM user_password_credentials WHERE user_id = $1`, liveAuthUserID).Scan(&newHash, &passwordUpdatedAt); err != nil {
		t.Fatalf("read changed password credential: %v", err)
	}
	if bcrypt.CompareHashAndPassword([]byte(newHash), []byte("replacement live password")) != nil {
		t.Fatal("replacement password does not match persisted bcrypt hash")
	}
	if bcrypt.CompareHashAndPassword([]byte(newHash), []byte("current live password")) == nil {
		t.Fatal("previous password still matches persisted bcrypt hash")
	}
	if !passwordUpdatedAt.Equal(changedAt) {
		t.Fatalf("password_updated_at=%s, want %s", passwordUpdatedAt, changedAt)
	}

	assertLiveSessionStatus(t, adminDB, "auth-live-token-one", "revoked", changedAt)
	assertLiveSessionStatus(t, adminDB, "auth-live-token-two", "revoked", changedAt)
	assertLiveSessionStatus(t, adminDB, "auth-live-other-token", "active", time.Time{})
}

func prepareLivePasswordChangeFixture(t *testing.T, adminURL string) (*sql.DB, *sql.DB) {
	t.Helper()
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open live auth admin db: %v", err)
	}
	if err := adminDB.Ping(); err != nil {
		_ = adminDB.Close()
		t.Fatalf("ping live auth admin db: %v", err)
	}
	if _, err := adminDB.Exec(`SELECT pg_advisory_lock(hashtext('mirofish_auth_live_fixture'))`); err != nil {
		_ = adminDB.Close()
		t.Fatalf("lock live auth fixture: %v", err)
	}
	roleSQL := `DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '` + liveAuthAppRole + `') THEN
    CREATE ROLE ` + liveAuthAppRole + ` LOGIN PASSWORD '` + liveAuthAppRolePassword + `' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE ` + liveAuthAppRole + ` WITH LOGIN PASSWORD '` + liveAuthAppRolePassword + `';
  END IF;
END $$;
GRANT mirofish_app TO ` + liveAuthAppRole
	if _, err := adminDB.Exec(roleSQL); err != nil {
		_ = adminDB.Close()
		t.Fatalf("ensure live auth app role: %v", err)
	}
	if _, err := adminDB.Exec("DELETE FROM users WHERE user_id IN ($1, $2)", liveAuthUserID, liveAuthOtherUserID); err != nil {
		_, _ = adminDB.Exec(`SELECT pg_advisory_unlock(hashtext('mirofish_auth_live_fixture'))`)
		_ = adminDB.Close()
		t.Fatalf("clean previous live auth fixture: %v", err)
	}
	oldHash, err := bcrypt.GenerateFromPassword([]byte("current live password"), bcrypt.MinCost)
	if err != nil {
		_ = adminDB.Close()
		t.Fatalf("hash live current password: %v", err)
	}
	otherHash, err := bcrypt.GenerateFromPassword([]byte("other live password"), bcrypt.MinCost)
	if err != nil {
		_ = adminDB.Close()
		t.Fatalf("hash live other password: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO users (user_id, email, display_name) VALUES
  ($1, 'auth-live@example.test', 'Auth Live'),
  ($2, 'auth-live-other@example.test', 'Auth Live Other')`, liveAuthUserID, liveAuthOtherUserID); err != nil {
		_ = adminDB.Close()
		t.Fatalf("seed live auth users: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO user_password_credentials (user_id, password_hash)
VALUES ($1, $3), ($2, $4)`, liveAuthUserID, liveAuthOtherUserID, string(oldHash), string(otherHash)); err != nil {
		_ = adminDB.Close()
		t.Fatalf("seed live auth credentials: %v", err)
	}
	if _, err := adminDB.Exec(`INSERT INTO user_sessions (user_session_id, user_id, token_hash, expires_at) VALUES
	  ('a9333333-3333-4333-8333-333333333333', $1, 'auth-live-token-one', now() + interval '1 day'),
	  ('a9444444-4444-4444-8444-444444444444', $1, 'auth-live-token-two', now() + interval '1 day'),
	('a9555555-5555-4555-8555-555555555555', $2, 'auth-live-other-token', now() + interval '1 day')`,
		liveAuthUserID, liveAuthOtherUserID); err != nil {
		_ = adminDB.Close()
		t.Fatalf("seed live auth sessions: %v", err)
	}
	appDB, err := sql.Open("pgx", liveAuthAppDatabaseURL(t, adminURL))
	if err != nil {
		_ = adminDB.Close()
		t.Fatalf("open live auth app db: %v", err)
	}
	if err := appDB.Ping(); err != nil {
		_ = appDB.Close()
		_ = adminDB.Close()
		t.Fatalf("ping live auth app db: %v", err)
	}
	t.Cleanup(func() {
		_ = appDB.Close()
		_, _ = adminDB.Exec("DELETE FROM users WHERE user_id IN ($1, $2)", liveAuthUserID, liveAuthOtherUserID)
		_, _ = adminDB.Exec(`SELECT pg_advisory_unlock(hashtext('mirofish_auth_live_fixture'))`)
		_ = adminDB.Close()
	})
	return adminDB, appDB
}

func liveAuthAppDatabaseURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatalf("parse live auth database URL: %v", err)
	}
	parsed.User = url.UserPassword(liveAuthAppRole, liveAuthAppRolePassword)
	return parsed.String()
}

func assertLiveSessionStatus(t *testing.T, db *sql.DB, tokenHash string, expectedStatus string, expectedRevokedAt time.Time) {
	t.Helper()
	var status string
	var revokedAt sql.NullTime
	if err := db.QueryRow(`SELECT status, revoked_at FROM user_sessions WHERE token_hash = $1`, tokenHash).Scan(&status, &revokedAt); err != nil {
		t.Fatalf("read live session %q: %v", tokenHash, err)
	}
	if status != expectedStatus {
		t.Fatalf("session %q status=%q, want %q", tokenHash, status, expectedStatus)
	}
	if expectedRevokedAt.IsZero() {
		if revokedAt.Valid {
			t.Fatalf("session %q unexpectedly has revoked_at=%s", tokenHash, revokedAt.Time)
		}
		return
	}
	if !revokedAt.Valid || !revokedAt.Time.Equal(expectedRevokedAt) {
		t.Fatalf("session %q revoked_at=%v, want %s", tokenHash, revokedAt, expectedRevokedAt)
	}
}
