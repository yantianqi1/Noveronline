package projectadmin

import (
	"errors"
	"strings"
)

const (
	// CodeValidationFailed marks an invalid request payload.
	CodeValidationFailed = "VALIDATION_FAILED"
	// CodeUnauthenticated marks a request without an authenticated actor.
	CodeUnauthenticated = "UNAUTHENTICATED"
	// CodeAccessDenied marks an actor without sufficient membership rights.
	CodeAccessDenied = "ACCESS_DENIED"
	// CodeProjectNotFound marks a rename target that does not exist in the tenant.
	CodeProjectNotFound = "PROJECT_NOT_FOUND"
	// CodeBackendUnavailable marks a backend/database failure.
	CodeBackendUnavailable = "PROJECT_ADMIN_BACKEND_UNAVAILABLE"
)

// maxProjectTitleRunes mirrors the registration project-title bound so the two
// creation paths accept exactly the same novel titles.
const maxProjectTitleRunes = 200

// CreateInput describes a request to create a new novel (project) in a tenant.
type CreateInput struct {
	TenantID  string
	Title     string
	ActorID   string
	RequestID string
}

// RenameInput describes a request to rename an existing novel (project).
type RenameInput struct {
	TenantID  string
	ProjectID string
	Title     string
	ActorID   string
	RequestID string
}

// Project is the read model returned to callers after a mutation.
type Project struct {
	TenantID  string `json:"tenant_id"`
	ProjectID string `json:"project_id"`
	Title     string `json:"title"`
	Status    string `json:"status"`
	Role      string `json:"role"`
}

// AppError is a domain error carrying a stable code for HTTP mapping.
type AppError struct {
	Code    string
	Message string
	Field   string
}

func (e *AppError) Error() string { return e.Message }

// ErrorCode extracts the stable code from an error, defaulting to backend-unavailable.
func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	if err == nil {
		return ""
	}
	return CodeBackendUnavailable
}

// ErrorField extracts the offending field for validation errors, if any.
func ErrorField(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return strings.TrimSpace(appErr.Field)
	}
	return ""
}
