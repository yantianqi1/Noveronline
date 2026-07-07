package auth

import (
	"context"
	"errors"
	"strings"
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
