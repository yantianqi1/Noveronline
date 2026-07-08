package auth

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"time"
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
	RevokeSession(context.Context, RevokeSessionInput) error
	RevokeUserSessions(context.Context, RevokeUserSessionsInput) error
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

func (q *SQLDBQueryer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	return q.db.ExecContext(ctx, query, args...)
}

type SQLReaderConfig struct {
	Queryer SQLQueryer
}

type SQLReader struct {
	queryer SQLQueryer
}

type SQLSessionStoreConfig struct {
	Queryer SQLQueryer
	Execer  SQLExecer
}

type SQLSessionStore struct {
	queryer SQLQueryer
	execer  SQLExecer
}

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	return &SQLReader{queryer: config.Queryer}
}

func NewSQLSessionStore(config SQLSessionStoreConfig) *SQLSessionStore {
	return &SQLSessionStore{queryer: config.Queryer, execer: config.Execer}
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
	if err := ValidateGetCurrentUserInput(GetCurrentUserInput{UserID: input.UserID, RequestID: input.RequestID}); err != nil {
		return err
	}
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || input.Permission == "" {
		return &AppError{Code: CodeValidationFailed, Message: "tenant_id and permission are required"}
	}
	if !tenantScopedPermission(input.Permission) && projectID == "" {
		return &AppError{Code: CodeValidationFailed, Message: "project_id is required"}
	}
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

func tenantScopedPermission(permission Permission) bool {
	return permission == PermissionLLMModuleBindingManage
}

func (a *ReaderBackedAuthorizer) allowed(currentUser CurrentUser, tenantID string, projectID string, permission Permission) bool {
	switch permission {
	case PermissionProjectRead:
		return hasProjectRole(currentUser.ActiveProjects, tenantID, projectID, projectReadProjectRoles())
	case PermissionTraceFullAccess:
		return hasProjectRole(currentUser.ActiveProjects, tenantID, projectID, traceFullAccessProjectRoles())
	case PermissionWriterRun:
		return hasProjectRole(currentUser.ActiveProjects, tenantID, projectID, writerRunProjectRoles())
	case PermissionCreativeWrite:
		return hasProjectRole(currentUser.ActiveProjects, tenantID, projectID, creativeWriteProjectRoles())
	case PermissionAssetManage:
		return hasProjectRole(currentUser.ActiveProjects, tenantID, projectID, assetManageProjectRoles())
	case PermissionLLMModuleBindingManage:
		return hasTenantRole(currentUser.ActiveTenants, tenantID, llmModuleBindingManageTenantRoles())
	default:
		return false
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
	if s.queryer == nil || s.execer == nil {
		return authLookupFailed()
	}
	now := input.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	rows, err := s.queryer.QueryContext(ctx, `
SELECT user_session_id::text
FROM user_sessions
WHERE user_id = $1
  AND token_hash = $2
  AND expires_at > $3
  AND revoked_at IS NULL
  AND status = 'active'
LIMIT 1
`, userID, tokenHash, now)
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
	_, err = s.execer.ExecContext(ctx, `
UPDATE user_sessions
SET last_seen_at = $3,
    updated_at = now()
WHERE user_id = $1
  AND token_hash = $2
`, userID, tokenHash, now)
	if err != nil {
		return authLookupFailed()
	}
	return nil
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
	rows, err := r.queryer.QueryContext(ctx, `
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
	rows, err := r.queryer.QueryContext(ctx, `
SELECT p.tenant_id::text, p.project_id::text, p.title, pm.role, tm.role, p.status
FROM tenant_memberships tm
JOIN tenants t ON t.tenant_id = tm.tenant_id AND t.status = 'active'
JOIN projects p ON p.tenant_id = tm.tenant_id AND p.status = 'active'
LEFT JOIN project_members pm
  ON pm.tenant_id = p.tenant_id
 AND pm.project_id = p.project_id
 AND pm.user_id = tm.user_id
 AND pm.status = 'active'
WHERE tm.user_id = $1 AND tm.status = 'active'
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

func authLookupFailed() *AppError {
	return &AppError{Code: CodeLookupFailed, Message: "auth lookup failed"}
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
