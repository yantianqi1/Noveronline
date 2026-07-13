package registration

import (
	"context"
	"database/sql"
	"errors"
	"net/mail"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
)

const (
	maxDisplayNameRunes  = 120
	maxEmailBytes        = 254
	minPasswordBytes     = 12
	maxPasswordBytes     = 72
	maxProjectTitleRunes = 200
)

type ServiceConfig struct {
	DB         *sql.DB
	BcryptCost int
}

type Service struct {
	beginTx      func(context.Context) (transaction, error)
	hashPassword func([]byte, int) ([]byte, error)
	newUUID      func() (uuid.UUID, error)
	bcryptCost   int
}

type transaction interface {
	ExecContext(context.Context, string, ...any) (sql.Result, error)
	QueryRowContext(context.Context, string, ...any) rowScanner
	Commit() error
	Rollback() error
}

type rowScanner interface {
	Scan(...any) error
}

type sqlTransaction struct {
	*sql.Tx
}

func (t sqlTransaction) QueryRowContext(ctx context.Context, query string, args ...any) rowScanner {
	return t.Tx.QueryRowContext(ctx, query, args...)
}

func NewService(config ServiceConfig) *Service {
	cost := config.BcryptCost
	if cost < bcrypt.MinCost || cost > bcrypt.MaxCost {
		cost = bcrypt.DefaultCost
	}
	service := &Service{
		hashPassword: bcrypt.GenerateFromPassword,
		newUUID:      uuid.NewRandom,
		bcryptCost:   cost,
	}
	if config.DB != nil {
		service.beginTx = func(ctx context.Context) (transaction, error) {
			tx, err := config.DB.BeginTx(ctx, nil)
			if err != nil {
				return nil, err
			}
			return sqlTransaction{Tx: tx}, nil
		}
	}
	return service
}

func (s *Service) Register(ctx context.Context, input RegisterInput) (Result, error) {
	normalized, err := validateAndNormalize(input)
	if err != nil {
		return Result{}, err
	}
	if s == nil || s.beginTx == nil || s.hashPassword == nil || s.newUUID == nil || input.InitialSessionFactory == nil {
		return Result{}, backendUnconfiguredError()
	}

	passwordHash, err := s.hashPassword([]byte(normalized.Password), s.bcryptCost)
	if err != nil {
		return Result{}, registrationFailedError()
	}
	identities, err := s.newIdentities()
	if err != nil {
		return Result{}, registrationFailedError()
	}
	initialSession, err := input.InitialSessionFactory(identities.userID)
	if err != nil || strings.TrimSpace(initialSession.TokenHash) == "" || initialSession.ExpiresAt.IsZero() {
		return Result{}, registrationFailedError()
	}

	tx, err := s.beginTx(ctx)
	if err != nil {
		return Result{}, registrationFailedError()
	}
	defer tx.Rollback()

	var emailExists bool
	if err := tx.QueryRowContext(ctx,
		`SELECT EXISTS(SELECT 1 FROM users WHERE lower(btrim(email)) = $1)`,
		normalized.Email,
	).Scan(&emailExists); err != nil {
		return Result{}, registrationFailedError()
	}
	if emailExists {
		return Result{}, emailConflictError()
	}

	if _, err := tx.ExecContext(ctx, `INSERT INTO users (
  user_id, email, display_name, status
) VALUES ($1::uuid, $2, $3, 'active')`, identities.userID, normalized.Email, normalized.DisplayName); err != nil {
		if isUniqueViolation(err) {
			return Result{}, emailConflictError()
		}
		return Result{}, registrationFailedError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO user_password_credentials (
  user_id, password_hash, status
) VALUES ($1::uuid, $2, 'active')`, identities.userID, string(passwordHash)); err != nil {
		return Result{}, registrationFailedError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO user_sessions (
  user_id, token_hash, status, expires_at, revoked_at, last_seen_at
) VALUES ($1::uuid, $2, 'active', $3, NULL, now())`, identities.userID, strings.TrimSpace(initialSession.TokenHash), initialSession.ExpiresAt.UTC()); err != nil {
		return Result{}, registrationFailedError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO tenants (
  tenant_id, slug, name, tenant_type, plan, status
) VALUES ($1::uuid, $2, $3, 'personal', 'free', 'active')`, identities.tenantID, identities.workspaceSlug, personalWorkspaceName(normalized.DisplayName)); err != nil {
		return Result{}, registrationFailedError()
	}

	// The remaining tables enforce tenant RLS. Establish both identities before any scoped write.
	if _, err := tx.ExecContext(ctx,
		`SELECT app_set_tenant_context($1::uuid, $2::uuid, false)`,
		identities.tenantID,
		identities.userID,
	); err != nil {
		return Result{}, registrationFailedError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO tenant_memberships (
  tenant_id, user_id, role, status, joined_at
) VALUES ($1::uuid, $2::uuid, 'owner', 'active', now())`, identities.tenantID, identities.userID); err != nil {
		return Result{}, registrationFailedError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO projects (
  tenant_id, project_id, title, status, created_by
) VALUES ($1::uuid, $2::uuid, $3, 'active', $4::uuid)`, identities.tenantID, identities.projectID, normalized.ProjectTitle, identities.userID); err != nil {
		return Result{}, registrationFailedError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO project_members (
  tenant_id, project_id, user_id, role, status
) VALUES ($1::uuid, $2::uuid, $3::uuid, 'project_owner', 'active')`, identities.tenantID, identities.projectID, identities.userID); err != nil {
		return Result{}, registrationFailedError()
	}
	// New projects default to after_adoption; existing projects keep manual via 0018 backfill.
	if _, err := tx.ExecContext(ctx, `INSERT INTO project_asset_distillation_settings (
  tenant_id, project_id, trigger_mode, enabled_asset_types, created_by, updated_by
) VALUES ($1::uuid, $2::uuid, 'after_adoption', ARRAY[]::TEXT[], $3::uuid, $3::uuid)`, identities.tenantID, identities.projectID, identities.userID); err != nil {
		return Result{}, registrationFailedError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO llm_quota_policies (
  tenant_id, scope_type, project_id, module_key, token_limit, concurrency_limit, period_seconds, enabled, updated_by
) VALUES ($1::uuid, 'tenant', NULL, NULL, 5000000, 8, 2592000, true, $2::uuid)`, identities.tenantID, identities.userID); err != nil {
		return Result{}, registrationFailedError()
	}
	if err := tx.Commit(); err != nil {
		return Result{}, registrationFailedError()
	}

	return newResult(normalized, identities), nil
}

type normalizedInput struct {
	DisplayName  string
	Email        string
	Password     string
	ProjectTitle string
}

func validateAndNormalize(input RegisterInput) (normalizedInput, error) {
	displayName := strings.TrimSpace(input.DisplayName)
	if !validDisplayText(displayName, maxDisplayNameRunes) {
		return normalizedInput{}, validationError("display_name", "display_name must be between 1 and 120 characters")
	}

	email := strings.ToLower(strings.TrimSpace(input.Email))
	parsed, err := mail.ParseAddress(email)
	if err != nil || parsed.Address != email || len([]byte(email)) > maxEmailBytes || containsControl(email) {
		return normalizedInput{}, validationError("email", "email must be a valid email address")
	}

	passwordBytes := len([]byte(input.Password))
	if passwordBytes < minPasswordBytes || passwordBytes > maxPasswordBytes {
		return normalizedInput{}, validationError("password", "password must be between 12 and 72 bytes")
	}

	projectTitle := strings.TrimSpace(input.ProjectTitle)
	if !validDisplayText(projectTitle, maxProjectTitleRunes) {
		return normalizedInput{}, validationError("project_title", "project_title must be between 1 and 200 characters")
	}

	return normalizedInput{
		DisplayName:  displayName,
		Email:        email,
		Password:     input.Password,
		ProjectTitle: projectTitle,
	}, nil
}

func validDisplayText(value string, maxRunes int) bool {
	return value != "" && utf8.ValidString(value) && utf8.RuneCountInString(value) <= maxRunes && !containsControl(value)
}

func containsControl(value string) bool {
	for _, character := range value {
		if unicode.IsControl(character) {
			return true
		}
	}
	return false
}

type generatedIdentities struct {
	userID        string
	tenantID      string
	projectID     string
	workspaceSlug string
}

func (s *Service) newIdentities() (generatedIdentities, error) {
	userID, err := s.newUUID()
	if err != nil {
		return generatedIdentities{}, err
	}
	tenantID, err := s.newUUID()
	if err != nil {
		return generatedIdentities{}, err
	}
	projectID, err := s.newUUID()
	if err != nil {
		return generatedIdentities{}, err
	}
	if userID == uuid.Nil || tenantID == uuid.Nil || projectID == uuid.Nil || userID == tenantID || userID == projectID || tenantID == projectID {
		return generatedIdentities{}, errors.New("registration identity generation failed")
	}
	tenantText := tenantID.String()
	return generatedIdentities{
		userID:        userID.String(),
		tenantID:      tenantText,
		projectID:     projectID.String(),
		workspaceSlug: "workspace-" + strings.ReplaceAll(tenantText, "-", ""),
	}, nil
}

func newResult(input normalizedInput, identities generatedIdentities) Result {
	return Result{
		User: UserSummary{
			UserID:      identities.userID,
			Email:       input.Email,
			DisplayName: input.DisplayName,
		},
		Workspace: WorkspaceSummary{
			TenantID: identities.tenantID,
			Slug:     identities.workspaceSlug,
			Name:     personalWorkspaceName(input.DisplayName),
			Type:     "personal",
			Role:     "owner",
			Status:   "active",
		},
		Project: ProjectSummary{
			TenantID:  identities.tenantID,
			ProjectID: identities.projectID,
			Title:     input.ProjectTitle,
			Role:      "project_owner",
			Status:    "active",
		},
	}
}

func personalWorkspaceName(displayName string) string {
	return displayName + " 的工作区"
}

type sqlStateError interface {
	SQLState() string
}

func isUniqueViolation(err error) bool {
	var stateError sqlStateError
	return errors.As(err, &stateError) && stateError.SQLState() == "23505"
}

func validationError(field, message string) error {
	return &AppError{Code: CodeValidationFailed, Message: message, Field: field}
}

func emailConflictError() error {
	return &AppError{Code: CodeEmailConflict, Message: "an account with this email already exists", Field: "email"}
}

func backendUnconfiguredError() error {
	return &AppError{Code: CodeBackendUnconfigured, Message: "registration backend is not configured"}
}

func registrationFailedError() error {
	return &AppError{Code: CodeRegistrationFailed, Message: "registration failed"}
}
