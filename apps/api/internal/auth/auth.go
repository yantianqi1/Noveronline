package auth

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"
)

const (
	CodeUnauthenticated     = "UNAUTHENTICATED"
	CodeBackendUnconfigured = "AUTH_BACKEND_UNCONFIGURED"
	CodeUserNotFound        = "AUTH_USER_NOT_FOUND"
	CodeAccessDenied        = "AUTH_ACCESS_DENIED"
	CodeLookupFailed        = "AUTH_LOOKUP_FAILED"
	CodeValidationFailed    = "VALIDATION_FAILED"
)

type GetCurrentUserInput struct {
	UserID    string
	RequestID string
}

type UserSummary struct {
	UserID      string `json:"user_id"`
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
	AvatarURL   string `json:"avatar_url"`
}

type TenantMembershipSummary struct {
	TenantID string `json:"tenant_id"`
	Name     string `json:"name"`
	Role     string `json:"role"`
	Status   string `json:"status"`
}

type ProjectMembershipSummary struct {
	TenantID  string `json:"tenant_id"`
	ProjectID string `json:"project_id"`
	Name      string `json:"name"`
	Role      string `json:"role"`
	Status    string `json:"status"`
}

type CurrentUser struct {
	User           UserSummary                `json:"user"`
	ActiveTenants  []TenantMembershipSummary  `json:"active_tenants"`
	ActiveProjects []ProjectMembershipSummary `json:"active_projects"`
}

type Reader interface {
	GetCurrentUser(context.Context, GetCurrentUserInput) (CurrentUser, error)
}

type PasswordLoginInput struct {
	Email     string
	Password  string
	RequestID string
}

type PasswordAuthenticator interface {
	AuthenticatePassword(context.Context, PasswordLoginInput) (CurrentUser, error)
}

type ChangePasswordInput struct {
	UserID          string
	CurrentPassword string
	NewPassword     string
	Now             time.Time
	RequestID       string
}

type PasswordChanger interface {
	ChangePassword(context.Context, ChangePasswordInput) error
}

type CreateSessionInput struct {
	UserID    string
	TokenHash string
	ExpiresAt time.Time
	RequestID string
}

type ValidateSessionInput struct {
	UserID    string
	TokenHash string
	Now       time.Time
	RequestID string
}

type ListUserSessionsInput struct {
	UserID    string
	TokenHash string
	Now       time.Time
	RequestID string
}

type SessionSummary struct {
	SessionID  string    `json:"session_id"`
	Status     string    `json:"status"`
	ExpiresAt  time.Time `json:"expires_at"`
	LastSeenAt time.Time `json:"last_seen_at"`
	Current    bool      `json:"current"`
}

type RevokeSessionInput struct {
	UserID    string
	TokenHash string
	Now       time.Time
	RequestID string
}

type RevokeUserSessionsInput struct {
	UserID    string
	TokenHash string
	Now       time.Time
	RequestID string
}

type RevokeTenantSessionsInput struct {
	TenantID  string
	ActorID   string
	Now       time.Time
	RequestID string
}

type RotateSessionInput struct {
	UserID       string
	OldTokenHash string
	NewTokenHash string
	ExpiresAt    time.Time
	Now          time.Time
	RequestID    string
}

type SessionStore interface {
	CreateSession(context.Context, CreateSessionInput) error
	ValidateSession(context.Context, ValidateSessionInput) error
	ListUserSessions(context.Context, ListUserSessionsInput) ([]SessionSummary, error)
	RevokeSession(context.Context, RevokeSessionInput) error
	RevokeUserSessions(context.Context, RevokeUserSessionsInput) error
	RevokeTenantSessions(context.Context, RevokeTenantSessionsInput) error
	RotateSession(context.Context, RotateSessionInput) error
}

type Permission string

const (
	PermissionProjectRead            Permission = "project_read"
	PermissionTraceFullAccess        Permission = "trace_full_access"
	PermissionWriterRun              Permission = "writer_run"
	PermissionCreativeWrite          Permission = "creative_write"
	PermissionAssetManage            Permission = "asset_manage"
	PermissionLLMModuleBindingManage Permission = "llm_module_binding_manage"
	PermissionTenantSessionManage    Permission = "tenant_session_manage"
)

type AuthorizeInput struct {
	UserID     string
	TenantID   string
	ProjectID  string
	Permission Permission
	RequestID  string
}

type Authorizer interface {
	Authorize(context.Context, AuthorizeInput) error
}

type SQLQueryer interface {
	QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error)
}

type SQLAuthQueryer interface {
	QueryAuthContext(ctx context.Context, userID string, query string, args ...any) (SQLRows, error)
}

type SQLExecer interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
}

type SQLRows interface {
	Next() bool
	Scan(dest ...any) error
	Err() error
	Close() error
}

type SQLDBQueryer struct {
	db *sql.DB
}

func NewSQLDBQueryer(db *sql.DB) *SQLDBQueryer {
	return &SQLDBQueryer{db: db}
}

func (q *SQLDBQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (q *SQLDBQueryer) QueryAuthContext(ctx context.Context, userID string, query string, args ...any) (SQLRows, error) {
	tx, err := q.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT set_config('app.current_user_id', $1, true)", strings.TrimSpace(userID)); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, query, args...)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return &authScopedRows{rows: rows, tx: tx}, nil
}

func (q *SQLDBQueryer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	return q.db.ExecContext(ctx, query, args...)
}

type authScopedRows struct {
	rows SQLRows
	tx   *sql.Tx
}

func (r *authScopedRows) Next() bool {
	return r.rows.Next()
}

func (r *authScopedRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *authScopedRows) Err() error {
	return r.rows.Err()
}

func (r *authScopedRows) Close() error {
	rowsErr := r.rows.Close()
	if rowsErr != nil {
		_ = r.tx.Rollback()
		return rowsErr
	}
	return r.tx.Commit()
}

type SQLReaderConfig struct {
	Queryer SQLQueryer
}

type SQLPasswordAuthenticatorConfig struct {
	Queryer SQLQueryer
	Reader  Reader
}

type SQLPasswordChangerConfig struct {
	Queryer    SQLQueryer
	Execer     SQLExecer
	BcryptCost int
}

type SQLAuthorizerConfig struct {
	Queryer SQLQueryer
}

type SQLReader struct {
	queryer SQLQueryer
}

type SQLPasswordAuthenticator struct {
	queryer SQLQueryer
	reader  Reader
}

type SQLPasswordChanger struct {
	queryer    SQLQueryer
	execer     SQLExecer
	bcryptCost int
}

type SQLAuthorizer struct {
	queryer SQLQueryer
}

type SQLSessionStoreConfig struct {
	Queryer       SQLQueryer
	Execer        SQLExecer
	TouchInterval time.Duration
}

type SQLSessionStore struct {
	queryer       SQLQueryer
	execer        SQLExecer
	touchInterval time.Duration
}

const defaultSessionTouchInterval = 5 * time.Minute

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	return &SQLReader{queryer: config.Queryer}
}

func NewSQLPasswordAuthenticator(config SQLPasswordAuthenticatorConfig) *SQLPasswordAuthenticator {
	reader := config.Reader
	if reader == nil {
		reader = NewSQLReader(SQLReaderConfig{Queryer: config.Queryer})
	}
	return &SQLPasswordAuthenticator{queryer: config.Queryer, reader: reader}
}

func NewSQLPasswordChanger(config SQLPasswordChangerConfig) *SQLPasswordChanger {
	cost := config.BcryptCost
	if cost < bcrypt.MinCost || cost > bcrypt.MaxCost {
		cost = bcrypt.DefaultCost
	}
	return &SQLPasswordChanger{queryer: config.Queryer, execer: config.Execer, bcryptCost: cost}
}

func NewSQLAuthorizer(config SQLAuthorizerConfig) *SQLAuthorizer {
	return &SQLAuthorizer{queryer: config.Queryer}
}

func NewSQLSessionStore(config SQLSessionStoreConfig) *SQLSessionStore {
	touchInterval := config.TouchInterval
	if touchInterval <= 0 {
		touchInterval = defaultSessionTouchInterval
	}
	return &SQLSessionStore{
		queryer:       config.Queryer,
		execer:        config.Execer,
		touchInterval: touchInterval,
	}
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return CodeLookupFailed
}

type DisabledReader struct{}

func NewDisabledReader() DisabledReader {
	return DisabledReader{}
}

type DisabledPasswordChanger struct{}

func NewDisabledPasswordChanger() DisabledPasswordChanger {
	return DisabledPasswordChanger{}
}

func (DisabledPasswordChanger) ChangePassword(context.Context, ChangePasswordInput) error {
	return &AppError{Code: CodeBackendUnconfigured, Message: "password change backend is not configured"}
}

func (DisabledReader) GetCurrentUser(context.Context, GetCurrentUserInput) (CurrentUser, error) {
	return CurrentUser{}, &AppError{
		Code:    CodeBackendUnconfigured,
		Message: "auth reader is not configured",
	}
}

func ValidateGetCurrentUserInput(input GetCurrentUserInput) error {
	if strings.TrimSpace(input.UserID) == "" {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	return nil
}

func ValidatePasswordLoginInput(input PasswordLoginInput) error {
	if strings.TrimSpace(input.Email) == "" || strings.TrimSpace(input.Password) == "" {
		return &AppError{Code: CodeValidationFailed, Message: "email and password are required"}
	}
	return nil
}

func ValidateChangePasswordInput(input ChangePasswordInput) error {
	if strings.TrimSpace(input.UserID) == "" {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	if input.CurrentPassword == "" || input.NewPassword == "" {
		return &AppError{Code: CodeValidationFailed, Message: "current_password and new_password are required"}
	}
	if input.CurrentPassword == input.NewPassword {
		return &AppError{Code: CodeValidationFailed, Message: "new password must differ from current password"}
	}
	if len([]byte(input.NewPassword)) < 12 || len([]byte(input.NewPassword)) > 72 {
		return &AppError{Code: CodeValidationFailed, Message: "new password must be between 12 and 72 bytes"}
	}
	return nil
}

type ReaderBackedAuthorizer struct {
	reader Reader
}

func NewReaderBackedAuthorizer(reader Reader) *ReaderBackedAuthorizer {
	if reader == nil {
		reader = NewDisabledReader()
	}
	return &ReaderBackedAuthorizer{reader: reader}
}

func (a *ReaderBackedAuthorizer) Authorize(ctx context.Context, input AuthorizeInput) error {
	if err := validateAuthorizeInput(input); err != nil {
		return err
	}
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if a.reader == nil {
		return &AppError{Code: CodeBackendUnconfigured, Message: "auth reader is not configured"}
	}
	currentUser, err := a.reader.GetCurrentUser(ctx, GetCurrentUserInput{
		UserID:    strings.TrimSpace(input.UserID),
		RequestID: input.RequestID,
	})
	if err != nil {
		return publicAuthErrorFromCode(ErrorCode(err))
	}
	if a.allowed(currentUser, tenantID, projectID, input.Permission) {
		return nil
	}
	return accessDenied()
}

func (a *SQLAuthorizer) Authorize(ctx context.Context, input AuthorizeInput) error {
	if err := validateAuthorizeInput(input); err != nil {
		return err
	}
	if a.queryer == nil {
		return authLookupFailed()
	}

	userID := strings.TrimSpace(input.UserID)
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	role, err := a.readResolvedRole(ctx, userID, tenantID, projectID, input.Permission)
	if err != nil {
		return err
	}
	if _, ok := allowedRolesForPermission(input.Permission)[normalizedRole(role)]; ok {
		return nil
	}
	return accessDenied()
}

func validateAuthorizeInput(input AuthorizeInput) error {
	if err := ValidateGetCurrentUserInput(GetCurrentUserInput{UserID: input.UserID, RequestID: input.RequestID}); err != nil {
		return err
	}
	if strings.TrimSpace(input.TenantID) == "" || input.Permission == "" {
		return &AppError{Code: CodeValidationFailed, Message: "tenant_id and permission are required"}
	}
	if !tenantScopedPermission(input.Permission) && strings.TrimSpace(input.ProjectID) == "" {
		return &AppError{Code: CodeValidationFailed, Message: "project_id is required"}
	}
	return nil
}

func (a *SQLAuthorizer) readResolvedRole(
	ctx context.Context,
	userID string,
	tenantID string,
	projectID string,
	permission Permission,
) (string, error) {
	query := `SELECT tm.role
FROM tenant_memberships tm
JOIN tenants t ON t.tenant_id = tm.tenant_id AND t.status = 'active'
WHERE tm.user_id = $1
  AND tm.tenant_id = $2
  AND tm.status = 'active'
  AND tm.access_scope = 'tenant'
LIMIT 1`
	args := []any{userID, tenantID}
	if !tenantScopedPermission(permission) {
		query = `SELECT COALESCE(NULLIF(BTRIM(pm.role), ''), tm.role) AS resolved_role
FROM tenant_memberships tm
JOIN tenants t ON t.tenant_id = tm.tenant_id AND t.status = 'active'
JOIN projects p ON p.tenant_id = tm.tenant_id AND p.status = 'active'
LEFT JOIN project_members pm
  ON pm.tenant_id = p.tenant_id
 AND pm.project_id = p.project_id
 AND pm.user_id = tm.user_id
 AND pm.status = 'active'
WHERE tm.user_id = $1
  AND tm.tenant_id = $2
  AND p.project_id = $3
  AND tm.status = 'active'
  AND (tm.access_scope = 'tenant' OR pm.user_id IS NOT NULL)
LIMIT 1`
		args = append(args, projectID)
	}

	rows, err := a.queryAuthContext(ctx, userID, query, args...)
	if err != nil {
		return "", authLookupFailed()
	}
	role := ""
	if rows.Next() {
		if err := rows.Scan(&role); err != nil {
			_ = rows.Close()
			return "", authLookupFailed()
		}
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return "", authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return "", authLookupFailed()
	}
	return strings.TrimSpace(role), nil
}

func (a *SQLAuthorizer) queryAuthContext(ctx context.Context, userID string, query string, args ...any) (SQLRows, error) {
	if authQueryer, ok := a.queryer.(SQLAuthQueryer); ok {
		return authQueryer.QueryAuthContext(ctx, userID, query, args...)
	}
	return a.queryer.QueryContext(ctx, query, args...)
}

func tenantScopedPermission(permission Permission) bool {
	return permission == PermissionLLMModuleBindingManage || permission == PermissionTenantSessionManage
}

func (a *ReaderBackedAuthorizer) allowed(currentUser CurrentUser, tenantID string, projectID string, permission Permission) bool {
	allowedRoles := allowedRolesForPermission(permission)
	if tenantScopedPermission(permission) {
		return hasTenantRole(currentUser.ActiveTenants, tenantID, allowedRoles)
	}
	return hasProjectRole(currentUser.ActiveProjects, tenantID, projectID, allowedRoles)
}

func allowedRolesForPermission(permission Permission) map[string]struct{} {
	switch permission {
	case PermissionProjectRead:
		return projectReadProjectRoles()
	case PermissionTraceFullAccess:
		return traceFullAccessProjectRoles()
	case PermissionWriterRun:
		return writerRunProjectRoles()
	case PermissionCreativeWrite:
		return creativeWriteProjectRoles()
	case PermissionAssetManage:
		return assetManageProjectRoles()
	case PermissionLLMModuleBindingManage, PermissionTenantSessionManage:
		return llmModuleBindingManageTenantRoles()
	default:
		return map[string]struct{}{}
	}
}

func (r *SQLReader) GetCurrentUser(ctx context.Context, input GetCurrentUserInput) (CurrentUser, error) {
	if err := ValidateGetCurrentUserInput(input); err != nil {
		return CurrentUser{}, err
	}
	if r.queryer == nil {
		return CurrentUser{}, authLookupFailed()
	}
	userID := strings.TrimSpace(input.UserID)

	user, err := r.readActiveUser(ctx, userID)
	if err != nil {
		return CurrentUser{}, err
	}
	tenants, err := r.readActiveTenants(ctx, userID)
	if err != nil {
		return CurrentUser{}, err
	}
	projects, err := r.readActiveProjects(ctx, userID)
	if err != nil {
		return CurrentUser{}, err
	}
	return CurrentUser{
		User:           user,
		ActiveTenants:  tenants,
		ActiveProjects: projects,
	}, nil
}

func (a *SQLPasswordAuthenticator) AuthenticatePassword(ctx context.Context, input PasswordLoginInput) (CurrentUser, error) {
	if err := ValidatePasswordLoginInput(input); err != nil {
		return CurrentUser{}, err
	}
	if a.queryer == nil || a.reader == nil {
		return CurrentUser{}, authLookupFailed()
	}
	email := strings.ToLower(strings.TrimSpace(input.Email))
	password := input.Password
	userID, passwordHash, err := a.readActivePasswordCredential(ctx, email)
	if err != nil {
		return CurrentUser{}, err
	}
	if bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte(password)) != nil {
		return CurrentUser{}, invalidEmailOrPassword()
	}
	return a.reader.GetCurrentUser(ctx, GetCurrentUserInput{
		UserID:    userID,
		RequestID: input.RequestID,
	})
}

func (c *SQLPasswordChanger) ChangePassword(ctx context.Context, input ChangePasswordInput) error {
	if err := ValidateChangePasswordInput(input); err != nil {
		return err
	}
	if c.queryer == nil || c.execer == nil {
		return authLookupFailed()
	}
	userID := strings.TrimSpace(input.UserID)
	oldHash, err := c.readPasswordCredential(ctx, userID)
	if err != nil {
		return err
	}
	if bcrypt.CompareHashAndPassword([]byte(oldHash), []byte(input.CurrentPassword)) != nil {
		return &AppError{Code: CodeUnauthenticated, Message: "current password is invalid"}
	}
	newHash, err := bcrypt.GenerateFromPassword([]byte(input.NewPassword), c.bcryptCost)
	if err != nil {
		return authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	result, err := c.execer.ExecContext(ctx, `WITH changed_credential AS (
  UPDATE user_password_credentials
  SET password_hash = $2,
      status = 'active',
      password_updated_at = $4,
      updated_at = now()
  WHERE user_id = $1
    AND password_hash = $3
    AND status IN ('active', 'reset_required')
  RETURNING user_id
), revoked_sessions AS (
  UPDATE user_sessions
  SET status = 'revoked',
      revoked_at = $4,
      updated_at = now()
  WHERE user_id IN (SELECT user_id FROM changed_credential)
    AND status = 'active'
    AND revoked_at IS NULL
  RETURNING user_session_id
)
SELECT user_id::text FROM changed_credential`, userID, string(newHash), oldHash, now)
	if err != nil || result == nil {
		return authLookupFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil || affected != 1 {
		return authLookupFailed()
	}
	return nil
}

func (c *SQLPasswordChanger) readPasswordCredential(ctx context.Context, userID string) (string, error) {
	rows, err := c.queryer.QueryContext(ctx, `SELECT credential.password_hash
FROM user_password_credentials AS credential
JOIN users AS app_user ON app_user.user_id = credential.user_id
WHERE credential.user_id = $1
  AND credential.status IN ('active', 'reset_required')
  AND app_user.status = 'active'
LIMIT 1`, userID)
	if err != nil {
		return "", authLookupFailed()
	}
	if !rows.Next() {
		if rows.Err() != nil {
			_ = rows.Close()
			return "", authLookupFailed()
		}
		if err := rows.Close(); err != nil {
			return "", authLookupFailed()
		}
		return "", &AppError{Code: CodeUnauthenticated, Message: "current password is invalid"}
	}
	var passwordHash string
	if err := rows.Scan(&passwordHash); err != nil {
		_ = rows.Close()
		return "", authLookupFailed()
	}
	if rows.Err() != nil {
		_ = rows.Close()
		return "", authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return "", authLookupFailed()
	}
	if strings.TrimSpace(passwordHash) == "" {
		return "", &AppError{Code: CodeUnauthenticated, Message: "current password is invalid"}
	}
	return strings.TrimSpace(passwordHash), nil
}

func (a *SQLPasswordAuthenticator) readActivePasswordCredential(ctx context.Context, email string) (string, string, error) {
	rows, err := a.queryer.QueryContext(ctx, `
SELECT u.user_id, c.password_hash
FROM users u
JOIN user_password_credentials c ON c.user_id = u.user_id
WHERE lower(u.email) = $1
  AND u.status = 'active'
  AND c.status = 'active'
LIMIT 1
`, email)
	if err != nil {
		return "", "", authLookupFailed()
	}
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return "", "", authLookupFailed()
		}
		if err := rows.Close(); err != nil {
			return "", "", authLookupFailed()
		}
		return "", "", invalidEmailOrPassword()
	}
	var userID string
	var passwordHash string
	if err := rows.Scan(&userID, &passwordHash); err != nil {
		_ = rows.Close()
		return "", "", authLookupFailed()
	}
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(passwordHash) == "" {
		_ = rows.Close()
		return "", "", invalidEmailOrPassword()
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return "", "", authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return "", "", authLookupFailed()
	}
	return strings.TrimSpace(userID), strings.TrimSpace(passwordHash), nil
}

func (s *SQLSessionStore) CreateSession(ctx context.Context, input CreateSessionInput) error {
	userID := strings.TrimSpace(input.UserID)
	tokenHash := strings.TrimSpace(input.TokenHash)
	if userID == "" || tokenHash == "" || input.ExpiresAt.IsZero() {
		return &AppError{Code: CodeValidationFailed, Message: "invalid auth request"}
	}
	if s.execer == nil {
		return authLookupFailed()
	}
	_, err := s.execer.ExecContext(ctx, `
INSERT INTO user_sessions (user_id, token_hash, status, expires_at, revoked_at, last_seen_at)
VALUES ($1, $2, 'active', $3, NULL, now())
ON CONFLICT (token_hash) DO UPDATE
SET user_id = EXCLUDED.user_id,
    status = 'active',
    expires_at = EXCLUDED.expires_at,
    revoked_at = NULL,
    last_seen_at = now(),
    updated_at = now()
`, userID, tokenHash, input.ExpiresAt)
	if err != nil {
		return authLookupFailed()
	}
	return nil
}

func (s *SQLSessionStore) ValidateSession(ctx context.Context, input ValidateSessionInput) error {
	userID := strings.TrimSpace(input.UserID)
	tokenHash := strings.TrimSpace(input.TokenHash)
	if userID == "" || tokenHash == "" {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	if s.queryer == nil {
		return authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	rows, err := s.queryer.QueryContext(ctx, `
WITH valid_session AS MATERIALIZED (
  SELECT user_session_id
  FROM user_sessions
  WHERE user_id = $1
    AND token_hash = $2
    AND expires_at > $3
    AND revoked_at IS NULL
    AND status = 'active'
  LIMIT 1
), touched_session AS (
  UPDATE user_sessions AS session
  SET last_seen_at = $3,
      updated_at = now()
  FROM valid_session
  WHERE session.user_session_id = valid_session.user_session_id
    AND COALESCE(last_seen_at, created_at) <= $4
  RETURNING session.user_session_id
)
SELECT valid_session.user_session_id::text
FROM valid_session
`, userID, tokenHash, now, now.Add(-s.touchInterval))
	if err != nil {
		return authLookupFailed()
	}

	sessionID := ""
	if rows.Next() {
		if err := rows.Scan(&sessionID); err != nil {
			_ = rows.Close()
			return authLookupFailed()
		}
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return authLookupFailed()
	}
	if strings.TrimSpace(sessionID) == "" {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	return nil
}

func (s *SQLSessionStore) ListUserSessions(ctx context.Context, input ListUserSessionsInput) ([]SessionSummary, error) {
	userID := strings.TrimSpace(input.UserID)
	tokenHash := strings.TrimSpace(input.TokenHash)
	if userID == "" || tokenHash == "" {
		return nil, &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	if s.queryer == nil {
		return nil, authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	rows, err := s.queryer.QueryContext(ctx, `
SELECT user_session_id::text,
       status,
       expires_at,
       COALESCE(last_seen_at, created_at) AS last_seen_at,
       token_hash = $2 AS current_session
FROM user_sessions
WHERE user_id = $1
  AND expires_at > $3
  AND revoked_at IS NULL
  AND status = 'active'
  AND EXISTS (
    SELECT 1
    FROM user_sessions presented
    WHERE presented.user_id = $1
      AND presented.token_hash = $2
      AND presented.expires_at > $3
      AND presented.revoked_at IS NULL
      AND presented.status = 'active'
  )
ORDER BY current_session DESC, COALESCE(last_seen_at, created_at) DESC
LIMIT 100
`, userID, tokenHash, now)
	if err != nil {
		return nil, authLookupFailed()
	}
	sessions := make([]SessionSummary, 0)
	for rows.Next() {
		var session SessionSummary
		if err := rows.Scan(&session.SessionID, &session.Status, &session.ExpiresAt, &session.LastSeenAt, &session.Current); err != nil {
			_ = rows.Close()
			return nil, authLookupFailed()
		}
		sessions = append(sessions, session)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return nil, authLookupFailed()
	}
	if len(sessions) == 0 {
		return nil, &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	return sessions, nil
}

func (s *SQLSessionStore) RevokeSession(ctx context.Context, input RevokeSessionInput) error {
	userID := strings.TrimSpace(input.UserID)
	tokenHash := strings.TrimSpace(input.TokenHash)
	if userID == "" || tokenHash == "" {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	if s.execer == nil {
		return authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	result, err := s.execer.ExecContext(ctx, `
UPDATE user_sessions
SET status = 'revoked',
    revoked_at = $3,
    updated_at = now()
WHERE user_id = $1
  AND token_hash = $2
  AND expires_at > $3
  AND revoked_at IS NULL
  AND status = 'active'
`, userID, tokenHash, now)
	if err != nil {
		return authLookupFailed()
	}
	if result == nil {
		return authLookupFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return authLookupFailed()
	}
	if affected == 0 {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	return nil
}

func (s *SQLSessionStore) RevokeUserSessions(ctx context.Context, input RevokeUserSessionsInput) error {
	userID := strings.TrimSpace(input.UserID)
	tokenHash := strings.TrimSpace(input.TokenHash)
	if userID == "" || tokenHash == "" {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	if s.execer == nil {
		return authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	result, err := s.execer.ExecContext(ctx, `
UPDATE user_sessions
SET status = 'revoked',
    revoked_at = $3,
    updated_at = now()
WHERE user_id = $1
  AND expires_at > $3
  AND revoked_at IS NULL
  AND status = 'active'
  AND EXISTS (
    SELECT 1
    FROM user_sessions presented
    WHERE presented.user_id = $1
      AND presented.token_hash = $2
      AND presented.expires_at > $3
      AND presented.revoked_at IS NULL
      AND presented.status = 'active'
  )
`, userID, tokenHash, now)
	if err != nil {
		return authLookupFailed()
	}
	if result == nil {
		return authLookupFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return authLookupFailed()
	}
	if affected == 0 {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	return nil
}

func (s *SQLSessionStore) RevokeTenantSessions(ctx context.Context, input RevokeTenantSessionsInput) error {
	tenantID := strings.TrimSpace(input.TenantID)
	if tenantID == "" || strings.TrimSpace(input.ActorID) == "" {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	if s.execer == nil {
		return authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	result, err := s.execer.ExecContext(ctx, `
UPDATE user_sessions
SET status = 'revoked',
    revoked_at = $2,
    updated_at = now()
WHERE user_sessions.expires_at > $2
  AND user_sessions.revoked_at IS NULL
  AND user_sessions.status = 'active'
  AND EXISTS (
    SELECT 1
    FROM tenant_memberships tm
    WHERE tm.tenant_id = $1
      AND tm.user_id = user_sessions.user_id
      AND tm.status = 'active'
  )
`, tenantID, now)
	if err != nil {
		return authLookupFailed()
	}
	if result == nil {
		return authLookupFailed()
	}
	if _, err := result.RowsAffected(); err != nil {
		return authLookupFailed()
	}
	return nil
}

func (s *SQLSessionStore) RotateSession(ctx context.Context, input RotateSessionInput) error {
	userID := strings.TrimSpace(input.UserID)
	oldTokenHash := strings.TrimSpace(input.OldTokenHash)
	newTokenHash := strings.TrimSpace(input.NewTokenHash)
	if userID == "" || oldTokenHash == "" || newTokenHash == "" || input.ExpiresAt.IsZero() {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	if oldTokenHash == newTokenHash {
		return &AppError{Code: CodeValidationFailed, Message: "invalid auth request"}
	}
	if s.execer == nil {
		return authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	result, err := s.execer.ExecContext(ctx, `
UPDATE user_sessions
SET token_hash = $3,
    expires_at = $4,
    last_seen_at = $5,
    status = 'active',
    revoked_at = NULL,
    updated_at = now()
WHERE user_id = $1
  AND token_hash = $2
  AND expires_at > $5
  AND revoked_at IS NULL
  AND status = 'active'
`, userID, oldTokenHash, newTokenHash, input.ExpiresAt, now)
	if err != nil {
		return authLookupFailed()
	}
	if result == nil {
		return authLookupFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return authLookupFailed()
	}
	if affected == 0 {
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	}
	return nil
}

func (r *SQLReader) readActiveUser(ctx context.Context, userID string) (UserSummary, error) {
	rows, err := r.queryer.QueryContext(ctx, `
SELECT user_id::text, email, display_name, COALESCE(avatar_url, '')
FROM users
WHERE user_id = $1 AND status = 'active'
LIMIT 1
`, userID)
	if err != nil {
		return UserSummary{}, authLookupFailed()
	}

	var user UserSummary
	found := false
	if rows.Next() {
		if err := rows.Scan(&user.UserID, &user.Email, &user.DisplayName, &user.AvatarURL); err != nil {
			_ = rows.Close()
			return UserSummary{}, authLookupFailed()
		}
		found = true
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return UserSummary{}, authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return UserSummary{}, authLookupFailed()
	}
	if !found {
		return UserSummary{}, &AppError{Code: CodeUserNotFound, Message: "current user was not found"}
	}
	return user, nil
}

func (r *SQLReader) readActiveTenants(ctx context.Context, userID string) ([]TenantMembershipSummary, error) {
	rows, err := r.queryAuthContext(ctx, userID, `
SELECT t.tenant_id::text, t.name, tm.role, tm.status
FROM tenant_memberships tm
JOIN tenants t ON t.tenant_id = tm.tenant_id AND t.status = 'active'
WHERE tm.user_id = $1 AND tm.status = 'active'
ORDER BY t.name, t.tenant_id
`, userID)
	if err != nil {
		return nil, authLookupFailed()
	}

	tenants := make([]TenantMembershipSummary, 0)
	for rows.Next() {
		var tenant TenantMembershipSummary
		if err := rows.Scan(&tenant.TenantID, &tenant.Name, &tenant.Role, &tenant.Status); err != nil {
			_ = rows.Close()
			return nil, authLookupFailed()
		}
		tenants = append(tenants, tenant)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return nil, authLookupFailed()
	}
	return tenants, nil
}

func (r *SQLReader) readActiveProjects(ctx context.Context, userID string) ([]ProjectMembershipSummary, error) {
	rows, err := r.queryAuthContext(ctx, userID, `
SELECT p.tenant_id::text, p.project_id::text, p.title, pm.role, tm.role, p.status
FROM tenant_memberships tm
JOIN tenants t ON t.tenant_id = tm.tenant_id AND t.status = 'active'
JOIN projects p ON p.tenant_id = tm.tenant_id AND p.status = 'active'
LEFT JOIN project_members pm
  ON pm.tenant_id = p.tenant_id
 AND pm.project_id = p.project_id
 AND pm.user_id = tm.user_id
 AND pm.status = 'active'
WHERE tm.user_id = $1
  AND tm.status = 'active'
  AND (tm.access_scope = 'tenant' OR pm.user_id IS NOT NULL)
ORDER BY p.title, p.project_id
`, userID)
	if err != nil {
		return nil, authLookupFailed()
	}

	projects := make([]ProjectMembershipSummary, 0)
	for rows.Next() {
		var project ProjectMembershipSummary
		var projectRole sql.NullString
		var tenantRole string
		if err := rows.Scan(&project.TenantID, &project.ProjectID, &project.Name, &projectRole, &tenantRole, &project.Status); err != nil {
			_ = rows.Close()
			return nil, authLookupFailed()
		}
		project.Role = tenantRole
		if projectRole.Valid && strings.TrimSpace(projectRole.String) != "" {
			project.Role = projectRole.String
		}
		projects = append(projects, project)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, authLookupFailed()
	}
	if err := rows.Close(); err != nil {
		return nil, authLookupFailed()
	}
	return projects, nil
}

func (r *SQLReader) queryAuthContext(ctx context.Context, userID string, query string, args ...any) (SQLRows, error) {
	if authQueryer, ok := r.queryer.(SQLAuthQueryer); ok {
		return authQueryer.QueryAuthContext(ctx, userID, query, args...)
	}
	return r.queryer.QueryContext(ctx, query, args...)
}

func authLookupFailed() *AppError {
	return &AppError{Code: CodeLookupFailed, Message: "auth lookup failed"}
}

func invalidEmailOrPassword() *AppError {
	return &AppError{Code: CodeUnauthenticated, Message: "invalid email or password"}
}

func accessDenied() *AppError {
	return &AppError{Code: CodeAccessDenied, Message: "current user access is denied"}
}

func publicAuthErrorFromCode(code string) *AppError {
	switch code {
	case CodeUnauthenticated:
		return &AppError{Code: CodeUnauthenticated, Message: "user context is required"}
	case CodeBackendUnconfigured:
		return &AppError{Code: CodeBackendUnconfigured, Message: "auth reader is not configured"}
	case CodeUserNotFound:
		return &AppError{Code: CodeUserNotFound, Message: "current user was not found"}
	case CodeAccessDenied:
		return accessDenied()
	case CodeValidationFailed:
		return &AppError{Code: CodeValidationFailed, Message: "invalid auth request"}
	case CodeLookupFailed:
		return authLookupFailed()
	default:
		return authLookupFailed()
	}
}

func hasProjectRole(projects []ProjectMembershipSummary, tenantID string, projectID string, allowed map[string]struct{}) bool {
	for _, project := range projects {
		if !activeStatus(project.Status) {
			continue
		}
		if strings.TrimSpace(project.TenantID) != tenantID || strings.TrimSpace(project.ProjectID) != projectID {
			continue
		}
		if _, ok := allowed[normalizedRole(project.Role)]; ok {
			return true
		}
	}
	return false
}

func hasTenantRole(tenants []TenantMembershipSummary, tenantID string, allowed map[string]struct{}) bool {
	for _, tenant := range tenants {
		if !activeStatus(tenant.Status) {
			continue
		}
		if strings.TrimSpace(tenant.TenantID) != tenantID {
			continue
		}
		if _, ok := allowed[normalizedRole(tenant.Role)]; ok {
			return true
		}
	}
	return false
}

func activeStatus(status string) bool {
	return normalizedRole(status) == "active"
}

func normalizedRole(role string) string {
	return strings.ToLower(strings.TrimSpace(role))
}

func projectReadProjectRoles() map[string]struct{} {
	return roleSet("project_owner", "owner", "admin", "editor", "writer", "analyst", "viewer")
}

func writerRunProjectRoles() map[string]struct{} {
	return roleSet("project_owner", "owner", "admin", "editor", "writer")
}

func creativeWriteProjectRoles() map[string]struct{} {
	return roleSet("project_owner", "owner", "admin", "editor", "writer")
}

func traceFullAccessProjectRoles() map[string]struct{} {
	return roleSet("project_owner", "owner", "admin", "editor")
}

func assetManageProjectRoles() map[string]struct{} {
	return roleSet("project_owner", "owner", "admin", "editor")
}

func llmModuleBindingManageTenantRoles() map[string]struct{} {
	return roleSet("owner", "admin")
}

func roleSet(roles ...string) map[string]struct{} {
	set := make(map[string]struct{}, len(roles))
	for _, role := range roles {
		set[role] = struct{}{}
	}
	return set
}
