package llmadmin

import (
	"context"
	"database/sql"
	"strings"
)

type SQLAccessController struct{ db *sql.DB }

func NewSQLAccessController(db *sql.DB) *SQLAccessController { return &SQLAccessController{db: db} }

func (a *SQLAccessController) Authorize(ctx context.Context, input AccessInput) error {
	if a == nil || a.db == nil {
		return &AppError{Code: "LLM_ADMIN_ACCESS_UNCONFIGURED", Message: "LLM admin access backend is not configured"}
	}
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.UserID) == "" {
		return &AppError{Code: "UNAUTHENTICATED", Message: "authentication is required"}
	}
	tx, err := a.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return accessFailed()
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, "SELECT set_config('app.current_user_id', $1, true)", strings.TrimSpace(input.UserID)); err != nil {
		return accessFailed()
	}
	var role string
	err = tx.QueryRowContext(ctx, `SELECT role FROM tenant_memberships
WHERE tenant_id::text = $1 AND user_id::text = $2 AND status = 'active'`, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.UserID)).Scan(&role)
	if err != nil {
		return &AppError{Code: "AUTH_ACCESS_DENIED", Message: "LLM admin access is denied"}
	}
	if !roleAllows(role, input.Operation) {
		return &AppError{Code: "AUTH_ACCESS_DENIED", Message: "LLM admin access is denied"}
	}
	if err := tx.Commit(); err != nil {
		return accessFailed()
	}
	return nil
}

func roleAllows(role, operation string) bool {
	role = strings.TrimSpace(role)
	if operation == OperationPolicyWrite || operation == OperationProviderHealth {
		return role == "owner" || role == "admin"
	}
	return role == "owner" || role == "admin" || role == "billing"
}

func accessFailed() error {
	return &AppError{Code: "LLM_ADMIN_ACCESS_FAILED", Message: "LLM admin access check failed"}
}
