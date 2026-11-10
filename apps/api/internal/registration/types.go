package registration

import (
	"errors"
	"strings"
	"time"
)

const (
	CodeValidationFailed    = "VALIDATION_FAILED"
	CodeEmailConflict       = "REGISTRATION_EMAIL_CONFLICT"
	CodeVerificationInvalid = "REGISTRATION_VERIFICATION_INVALID"
	CodeVerificationExpired = "REGISTRATION_VERIFICATION_EXPIRED"
	CodeBackendUnconfigured = "REGISTRATION_BACKEND_UNCONFIGURED"
	CodeRegistrationFailed  = "REGISTRATION_FAILED"
)

type RegisterInput struct {
	DisplayName           string
	Email                 string
	Password              string
	ProjectTitle          string
	InitialSessionFactory InitialSessionFactory
}

type InitialSession struct {
	TokenHash string
	ExpiresAt time.Time
}

type InitialSessionFactory func(userID string) (InitialSession, error)

type EmailVerificationStartInput struct {
	DisplayName  string
	Email        string
	Password     string
	ProjectTitle string
}

type EmailVerificationChallenge struct {
	Email     string
	Token     string
	ExpiresAt time.Time
}

type EmailVerificationInput struct {
	Token                 string
	InitialSessionFactory InitialSessionFactory
}

type UserSummary struct {
	UserID      string `json:"user_id"`
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

type WorkspaceSummary struct {
	TenantID string `json:"tenant_id"`
	Slug     string `json:"slug"`
	Name     string `json:"name"`
	Type     string `json:"type"`
	Role     string `json:"role"`
	Status   string `json:"status"`
}

type ProjectSummary struct {
	TenantID  string `json:"tenant_id"`
	ProjectID string `json:"project_id"`
	Title     string `json:"title"`
	Role      string `json:"role"`
	Status    string `json:"status"`
}

type Result struct {
	User      UserSummary      `json:"user"`
	Workspace WorkspaceSummary `json:"workspace"`
	Project   ProjectSummary   `json:"project"`
}

type AppError struct {
	Code    string
	Message string
	Field   string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	if err == nil {
		return ""
	}
	return CodeRegistrationFailed
}

func ErrorField(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return strings.TrimSpace(appErr.Field)
	}
	return ""
}
