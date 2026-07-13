package collaboration

import (
	"context"
	"errors"
	"time"
)

const (
	CodeValidationFailed    = "VALIDATION_FAILED"
	CodeUnauthenticated     = "UNAUTHENTICATED"
	CodeAccessDenied        = "COLLABORATION_ACCESS_DENIED"
	CodeBackendUnavailable  = "COLLABORATION_BACKEND_UNAVAILABLE"
	CodeInvitationConflict  = "INVITATION_ACTIVE_CONFLICT"
	CodeInvitationInvalid   = "INVITATION_INVALID"
	CodeInvitationExpired   = "INVITATION_EXPIRED"
	CodeInvitationConsumed  = "INVITATION_ALREADY_USED"
	CodeLastOwner           = "LAST_ACTIVE_OWNER_REQUIRED"
	CodeMembershipNotFound  = "MEMBERSHIP_NOT_FOUND"
	CodeDeliveryUnavailable = "DELIVERY_BACKEND_UNAVAILABLE"
)

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string { return e.Message }

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return CodeBackendUnavailable
}

type Invitation struct {
	InvitationID string    `json:"invitation_id"`
	TenantID     string    `json:"tenant_id"`
	ProjectID    string    `json:"project_id,omitempty"`
	Email        string    `json:"email"`
	TenantRole   string    `json:"tenant_role,omitempty"`
	ProjectRole  string    `json:"project_role,omitempty"`
	Status       string    `json:"status"`
	Delivery     string    `json:"delivery_status"`
	ExpiresAt    time.Time `json:"expires_at"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

type Member struct {
	TenantID  string    `json:"tenant_id"`
	ProjectID string    `json:"project_id,omitempty"`
	UserID    string    `json:"user_id"`
	Email     string    `json:"email"`
	Name      string    `json:"display_name"`
	Role      string    `json:"role"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type CreateInvitationInput struct {
	TenantID    string
	ProjectID   string
	Email       string
	TenantRole  string
	ProjectRole string
	ActorID     string
	RequestID   string
	ExpiresIn   time.Duration
}

type InvitationActionInput struct {
	TenantID     string
	InvitationID string
	ActorID      string
	RequestID    string
	ExpiresIn    time.Duration
}

type AcceptInvitationInput struct {
	Token     string
	ActorID   string
	RequestID string
}

type ListInput struct {
	TenantID  string
	ProjectID string
	ActorID   string
	RequestID string
}

type MembershipChangeInput struct {
	TenantID  string
	ProjectID string
	UserID    string
	ActorID   string
	Role      string
	Status    string
	RequestID string
}

type InvitationDelivery struct {
	InvitationID string
	Email        string
	Token        string
	TenantID     string
	ProjectID    string
	TenantRole   string
	ProjectRole  string
	ExpiresAt    time.Time
}

type DeliveryReceipt struct {
	ProviderMessageID string
}

type InvitationNotifier interface {
	SendInvitation(context.Context, InvitationDelivery) (DeliveryReceipt, error)
}
