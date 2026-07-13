package registration

import (
	"context"
	"database/sql"
	"os"
	"testing"
	"time"

	"mirofish-novel/apps/api/internal/testschema"

	"github.com/google/uuid"
	_ "github.com/jackc/pgx/v5/stdlib"
	"golang.org/x/crypto/bcrypt"
)

func TestRegistrationLiveCreatesRLSScopedPersonalWorkspace(t *testing.T) {
	databaseURL := os.Getenv("MIROFISH_REGISTRATION_LIVE_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("set MIROFISH_REGISTRATION_LIVE_DATABASE_URL to run the registration live test")
	}

	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.SetMaxOpenConns(2)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Fatal(err)
	}
	if err := testschema.RequireDisposableLiveDatabase(ctx, db); err != nil {
		t.Fatal(err)
	}

	suffix := uuid.NewString()
	input := RegisterInput{
		DisplayName:  "Registration Live",
		Email:        "registration-live-" + suffix + "@example.invalid",
		Password:     "registration live password",
		ProjectTitle: "Registration Live Novel",
		InitialSessionFactory: func(string) (InitialSession, error) {
			return InitialSession{
				TokenHash: "registration-live-session-" + suffix,
				ExpiresAt: time.Now().UTC().Add(time.Hour),
			}, nil
		},
	}
	service := NewService(ServiceConfig{DB: db, BcryptCost: bcrypt.MinCost})
	result, err := service.Register(ctx, input)
	if err != nil {
		t.Fatalf("register through live database: code=%s err=%v", ErrorCode(err), err)
	}
	defer cleanupRegistrationLive(t, db, result)

	var passwordHash string
	if err := db.QueryRowContext(ctx, `SELECT c.password_hash
FROM user_password_credentials c
JOIN users u ON u.user_id = c.user_id
WHERE u.user_id = $1::uuid AND u.email = $2 AND u.status = 'active' AND c.status = 'active'`,
		result.User.UserID, input.Email).Scan(&passwordHash); err != nil {
		t.Fatalf("read live credential: %v", err)
	}
	if passwordHash == input.Password || bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte(input.Password)) != nil {
		t.Fatal("live registration did not persist only a matching bcrypt password hash")
	}
	var sessionCount int
	if err := db.QueryRowContext(ctx, `SELECT count(*) FROM user_sessions WHERE user_id = $1::uuid AND token_hash = $2 AND status = 'active'`,
		result.User.UserID, "registration-live-session-"+suffix).Scan(&sessionCount); err != nil || sessionCount != 1 {
		t.Fatalf("read live initial session: count=%d err=%v", sessionCount, err)
	}

	tx, err := db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	if _, err := tx.ExecContext(ctx, `SELECT app_set_tenant_context($1::uuid, $2::uuid, false)`, result.Workspace.TenantID, result.User.UserID); err != nil {
		t.Fatalf("set live registration tenant context: %v", err)
	}
	var workspaceRole, workspaceStatus, projectRole, projectStatus string
	if err := tx.QueryRowContext(ctx, `SELECT tm.role, tm.status, pm.role, pm.status
FROM tenant_memberships tm
JOIN projects p ON p.tenant_id = tm.tenant_id AND p.project_id = $3::uuid AND p.status = 'active'
JOIN project_members pm ON pm.tenant_id = p.tenant_id AND pm.project_id = p.project_id AND pm.user_id = tm.user_id
WHERE tm.tenant_id = $1::uuid AND tm.user_id = $2::uuid`,
		result.Workspace.TenantID, result.User.UserID, result.Project.ProjectID,
	).Scan(&workspaceRole, &workspaceStatus, &projectRole, &projectStatus); err != nil {
		t.Fatalf("read live RLS-scoped registration rows: %v", err)
	}
	if workspaceRole != "owner" || workspaceStatus != "active" || projectRole != "project_owner" || projectStatus != "active" {
		t.Fatalf("unexpected live memberships: workspace=%s/%s project=%s/%s", workspaceRole, workspaceStatus, projectRole, projectStatus)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}

	if _, err := service.Register(ctx, input); ErrorCode(err) != CodeEmailConflict {
		t.Fatalf("duplicate live registration code=%s err=%v", ErrorCode(err), err)
	}
}

func cleanupRegistrationLive(t *testing.T, db *sql.DB, result Result) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if _, err := db.ExecContext(ctx, `DELETE FROM tenants WHERE tenant_id = $1::uuid`, result.Workspace.TenantID); err != nil {
		t.Logf("cleanup live registration workspace: %v", err)
	}
	if _, err := db.ExecContext(ctx, `DELETE FROM users WHERE user_id = $1::uuid`, result.User.UserID); err != nil {
		t.Logf("cleanup live registration user: %v", err)
	}
}
