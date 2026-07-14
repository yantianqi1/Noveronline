package projectadmin

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"unicode"
	"unicode/utf8"
)

// ServiceConfig configures the project administration service.
type ServiceConfig struct {
	DB *sql.DB
}

// Service creates and renames novels (projects) inside a tenant. Every write is
// tenant-scoped: the transaction establishes the RLS context before touching any
// tenant-owned table, matching the self-serve registration path.
type Service struct {
	beginTx func(context.Context) (transaction, error)
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

// NewService builds a Service backed by the given database handle.
func NewService(config ServiceConfig) *Service {
	service := &Service{}
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

// CreateProject creates a new novel owned by the actor within the tenant. The
// actor must be a tenant owner or admin. The insert mirrors registration so a
// second novel is indistinguishable from the first (project, project owner
// membership, and default asset-distillation settings).
func (s *Service) CreateProject(ctx context.Context, input CreateInput) (Project, error) {
	title, err := normalizeTitle(input.Title)
	if err != nil {
		return Project{}, err
	}
	tenantID := strings.TrimSpace(input.TenantID)
	actorID := strings.TrimSpace(input.ActorID)
	if tenantID == "" || actorID == "" {
		return Project{}, validationError("", "tenant and authenticated actor are required")
	}
	if s == nil || s.beginTx == nil {
		return Project{}, backendError()
	}

	tx, err := s.beginTx(ctx)
	if err != nil {
		return Project{}, backendError()
	}
	defer tx.Rollback()
	if err := setTenantContext(ctx, tx, tenantID, actorID); err != nil {
		return Project{}, backendError()
	}
	if err := requireTenantManager(ctx, tx, tenantID, actorID); err != nil {
		return Project{}, err
	}

	var project Project
	if err := tx.QueryRowContext(ctx, `INSERT INTO projects (
  tenant_id, title, status, created_by
) VALUES ($1::uuid, $2, 'active', $3::uuid)
RETURNING tenant_id::text, project_id::text, title, status`, tenantID, title, actorID).Scan(
		&project.TenantID, &project.ProjectID, &project.Title, &project.Status); err != nil {
		return Project{}, backendError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO project_members (
  tenant_id, project_id, user_id, role, status
) VALUES ($1::uuid, $2::uuid, $3::uuid, 'project_owner', 'active')`, tenantID, project.ProjectID, actorID); err != nil {
		return Project{}, backendError()
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO project_asset_distillation_settings (
  tenant_id, project_id, trigger_mode, enabled_asset_types, created_by, updated_by
) VALUES ($1::uuid, $2::uuid, 'after_adoption', ARRAY[]::TEXT[], $3::uuid, $3::uuid)`, tenantID, project.ProjectID, actorID); err != nil {
		return Project{}, backendError()
	}
	if err := insertAudit(ctx, tx, tenantID, project.ProjectID, actorID, "project.created", input.RequestID, map[string]any{"title": project.Title}); err != nil {
		return Project{}, backendError()
	}
	if err := tx.Commit(); err != nil {
		return Project{}, backendError()
	}
	project.Role = "project_owner"
	return project, nil
}

// RenameProject updates a novel's title. The actor must be a tenant owner/admin
// or the project owner of the target novel.
func (s *Service) RenameProject(ctx context.Context, input RenameInput) (Project, error) {
	title, err := normalizeTitle(input.Title)
	if err != nil {
		return Project{}, err
	}
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	actorID := strings.TrimSpace(input.ActorID)
	if tenantID == "" || projectID == "" || actorID == "" {
		return Project{}, validationError("", "tenant, project, and authenticated actor are required")
	}
	if s == nil || s.beginTx == nil {
		return Project{}, backendError()
	}

	tx, err := s.beginTx(ctx)
	if err != nil {
		return Project{}, backendError()
	}
	defer tx.Rollback()
	if err := setTenantContext(ctx, tx, tenantID, actorID); err != nil {
		return Project{}, backendError()
	}
	if err := requireProjectManager(ctx, tx, tenantID, projectID, actorID); err != nil {
		return Project{}, err
	}

	var project Project
	err = tx.QueryRowContext(ctx, `UPDATE projects
SET title = $3, updated_at = now()
WHERE tenant_id = $1::uuid AND project_id = $2::uuid
RETURNING tenant_id::text, project_id::text, title, status`, tenantID, projectID, title).Scan(
		&project.TenantID, &project.ProjectID, &project.Title, &project.Status)
	if errors.Is(err, sql.ErrNoRows) {
		return Project{}, &AppError{Code: CodeProjectNotFound, Message: "novel was not found"}
	}
	if err != nil {
		return Project{}, backendError()
	}
	if err := insertAudit(ctx, tx, tenantID, project.ProjectID, actorID, "project.renamed", input.RequestID, map[string]any{"title": project.Title}); err != nil {
		return Project{}, backendError()
	}
	if err := tx.Commit(); err != nil {
		return Project{}, backendError()
	}
	return project, nil
}

func setTenantContext(ctx context.Context, tx transaction, tenantID, actorID string) error {
	_, err := tx.ExecContext(ctx, `SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)`, tenantID, actorID)
	return err
}

func requireTenantManager(ctx context.Context, tx transaction, tenantID, actorID string) error {
	var allowed bool
	if err := tx.QueryRowContext(ctx, `SELECT EXISTS(
  SELECT 1 FROM tenant_memberships
  WHERE tenant_id = $1::uuid AND user_id = $2::uuid
    AND access_scope = 'tenant' AND status = 'active' AND role IN ('owner', 'admin')
)`, tenantID, actorID).Scan(&allowed); err != nil {
		return backendError()
	}
	if !allowed {
		return &AppError{Code: CodeAccessDenied, Message: "tenant owner or admin access is required to create a novel"}
	}
	return nil
}

func requireProjectManager(ctx context.Context, tx transaction, tenantID, projectID, actorID string) error {
	var allowed bool
	if err := tx.QueryRowContext(ctx, `SELECT EXISTS(
  SELECT 1 FROM tenant_memberships
  WHERE tenant_id = $1::uuid AND user_id = $3::uuid
    AND access_scope = 'tenant' AND status = 'active' AND role IN ('owner', 'admin')
) OR EXISTS(
  SELECT 1 FROM project_members
  WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND user_id = $3::uuid
    AND status = 'active' AND role = 'project_owner'
)`, tenantID, projectID, actorID).Scan(&allowed); err != nil {
		return backendError()
	}
	if !allowed {
		return &AppError{Code: CodeAccessDenied, Message: "novel management access is required"}
	}
	return nil
}

func insertAudit(ctx context.Context, tx transaction, tenantID, projectID, actorID, action, requestID string, metadata any) error {
	encoded, err := json.Marshal(metadata)
	if err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO audit_logs (
  tenant_id, actor_user_id, action, resource_type, resource_id, project_id, request_id, metadata_jsonb
) VALUES ($1::uuid, NULLIF($2, '')::uuid, $3, 'project', NULLIF($4, '')::uuid, NULLIF($4, '')::uuid, NULLIF($5, ''), $6::jsonb)`,
		tenantID, actorID, action, projectID, requestID, string(encoded))
	return err
}

func normalizeTitle(raw string) (string, error) {
	title := strings.TrimSpace(raw)
	if title == "" || !utf8.ValidString(title) || utf8.RuneCountInString(title) > maxProjectTitleRunes || containsControl(title) {
		return "", validationError("title", "title must be between 1 and 200 characters")
	}
	return title, nil
}

func containsControl(value string) bool {
	for _, character := range value {
		if unicode.IsControl(character) {
			return true
		}
	}
	return false
}

func validationError(field, message string) error {
	return &AppError{Code: CodeValidationFailed, Message: message, Field: field}
}

func backendError() error {
	return &AppError{Code: CodeBackendUnavailable, Message: "project administration backend is unavailable"}
}
