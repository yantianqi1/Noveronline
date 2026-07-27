package collaboration

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

type ServiceConfig struct {
	DB       *sql.DB
	Notifier InvitationNotifier
	Now      func() time.Time
}

type Service struct {
	db       *sql.DB
	notifier InvitationNotifier
	now      func() time.Time
}

func NewService(config ServiceConfig) *Service {
	now := config.Now
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{db: config.DB, notifier: config.Notifier, now: now}
}

func (s *Service) CreateInvitation(ctx context.Context, input CreateInvitationInput) (Invitation, error) {
	if err := validateCreate(input); err != nil {
		return Invitation{}, err
	}
	if s.db == nil {
		return Invitation{}, backendError()
	}
	token, tokenHash, err := newToken()
	if err != nil {
		return Invitation{}, backendError()
	}
	now := s.now()
	ttl := input.ExpiresIn
	if ttl <= 0 {
		ttl = 72 * time.Hour
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, input.ActorID)
	if err != nil {
		return Invitation{}, backendError()
	}
	defer tx.Rollback()
	if err := requireManager(ctx, tx, input.TenantID, input.ProjectID, input.ActorID); err != nil {
		return Invitation{}, err
	}
	if input.ProjectID == "" && input.TenantRole == "owner" {
		if err := requireTenantOwner(ctx, tx, input.TenantID, input.ActorID); err != nil {
			return Invitation{}, err
		}
	}
	var invitation Invitation
	err = tx.QueryRowContext(ctx, `INSERT INTO collaboration_invitations (
  tenant_id, project_id, email_normalized, tenant_role, project_role, token_hash,
  invited_by, request_id, expires_at
) VALUES ($1, NULLIF($2, '')::uuid, $3, NULLIF($4, ''), NULLIF($5, ''), $6, $7, NULLIF($8, ''), $9)
RETURNING invitation_id::text, tenant_id::text, COALESCE(project_id::text, ''), email_normalized,
  COALESCE(tenant_role, ''), COALESCE(project_role, ''), status, delivery_status,
  expires_at, created_at, updated_at`, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), normalizeEmail(input.Email),
		strings.TrimSpace(input.TenantRole), strings.TrimSpace(input.ProjectRole), tokenHash, strings.TrimSpace(input.ActorID),
		strings.TrimSpace(input.RequestID), now.Add(ttl)).Scan(&invitation.InvitationID, &invitation.TenantID, &invitation.ProjectID,
		&invitation.Email, &invitation.TenantRole, &invitation.ProjectRole, &invitation.Status, &invitation.Delivery,
		&invitation.ExpiresAt, &invitation.CreatedAt, &invitation.UpdatedAt)
	if err != nil {
		if strings.Contains(err.Error(), "idx_collaboration_invites_active") {
			return Invitation{}, &AppError{Code: CodeInvitationConflict, Message: "an active invitation already exists; use resend"}
		}
		return Invitation{}, backendError()
	}
	if err := insertAudit(ctx, tx, input.TenantID, input.ProjectID, input.ActorID, "collaboration.invitation.created", "collaboration_invitation", invitation.InvitationID, input.RequestID, map[string]any{"role": invitationRole(invitation), "scope": invitationScope(invitation)}); err != nil {
		return Invitation{}, backendError()
	}
	if err := tx.Commit(); err != nil {
		return Invitation{}, backendError()
	}
	return s.deliver(ctx, invitation, token)
}

func (s *Service) ResendInvitation(ctx context.Context, input InvitationActionInput) (Invitation, error) {
	if err := validateAction(input); err != nil {
		return Invitation{}, err
	}
	token, tokenHash, err := newToken()
	if err != nil {
		return Invitation{}, backendError()
	}
	ttl := input.ExpiresIn
	if ttl <= 0 {
		ttl = 72 * time.Hour
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, input.ActorID)
	if err != nil {
		return Invitation{}, backendError()
	}
	defer tx.Rollback()
	var projectID string
	if err := tx.QueryRowContext(ctx, `SELECT COALESCE(project_id::text,'') FROM collaboration_invitations WHERE tenant_id=$1 AND invitation_id=$2 AND status='pending'`, input.TenantID, input.InvitationID).Scan(&projectID); errors.Is(err, sql.ErrNoRows) {
		return Invitation{}, &AppError{Code: CodeInvitationInvalid, Message: "invitation is not available"}
	} else if err != nil {
		return Invitation{}, backendError()
	}
	if err := requireManager(ctx, tx, input.TenantID, projectID, input.ActorID); err != nil {
		return Invitation{}, err
	}
	var invitation Invitation
	err = tx.QueryRowContext(ctx, `UPDATE collaboration_invitations i
SET token_hash = $3, expires_at = $4, delivery_status = 'pending', last_delivery_error_code = NULL,
    request_id = NULLIF($5, ''), updated_at = now()
WHERE i.tenant_id = $1 AND i.invitation_id = $2 AND i.status = 'pending'
RETURNING invitation_id::text, tenant_id::text, COALESCE(project_id::text, ''), email_normalized,
  COALESCE(tenant_role, ''), COALESCE(project_role, ''), status, delivery_status, expires_at, created_at, updated_at`,
		input.TenantID, input.InvitationID, tokenHash, s.now().Add(ttl), input.RequestID).Scan(&invitation.InvitationID,
		&invitation.TenantID, &invitation.ProjectID, &invitation.Email, &invitation.TenantRole, &invitation.ProjectRole,
		&invitation.Status, &invitation.Delivery, &invitation.ExpiresAt, &invitation.CreatedAt, &invitation.UpdatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return Invitation{}, &AppError{Code: CodeInvitationInvalid, Message: "invitation is not available"}
	}
	if err != nil {
		return Invitation{}, backendError()
	}
	if err := insertAudit(ctx, tx, input.TenantID, invitation.ProjectID, input.ActorID, "collaboration.invitation.resent", "collaboration_invitation", input.InvitationID, input.RequestID, map[string]any{"delivery_status_before": "pending"}); err != nil {
		return Invitation{}, backendError()
	}
	if err := tx.Commit(); err != nil {
		return Invitation{}, backendError()
	}
	return s.deliver(ctx, invitation, token)
}

func (s *Service) RevokeInvitation(ctx context.Context, input InvitationActionInput) (Invitation, error) {
	if err := validateAction(input); err != nil {
		return Invitation{}, err
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, input.ActorID)
	if err != nil {
		return Invitation{}, backendError()
	}
	defer tx.Rollback()
	var projectID string
	if err := tx.QueryRowContext(ctx, `SELECT COALESCE(project_id::text,'') FROM collaboration_invitations WHERE tenant_id=$1 AND invitation_id=$2 AND status='pending'`, input.TenantID, input.InvitationID).Scan(&projectID); errors.Is(err, sql.ErrNoRows) {
		return Invitation{}, &AppError{Code: CodeInvitationInvalid, Message: "invitation is not available"}
	} else if err != nil {
		return Invitation{}, backendError()
	}
	if err := requireManager(ctx, tx, input.TenantID, projectID, input.ActorID); err != nil {
		return Invitation{}, err
	}
	var invitation Invitation
	err = tx.QueryRowContext(ctx, `UPDATE collaboration_invitations i
SET status = 'revoked', revoked_at = $3, updated_at = now()
WHERE i.tenant_id = $1 AND i.invitation_id = $2 AND i.status = 'pending'
RETURNING invitation_id::text, tenant_id::text, COALESCE(project_id::text, ''), email_normalized,
  COALESCE(tenant_role, ''), COALESCE(project_role, ''), status, delivery_status, expires_at, created_at, updated_at`,
		input.TenantID, input.InvitationID, s.now()).Scan(&invitation.InvitationID, &invitation.TenantID,
		&invitation.ProjectID, &invitation.Email, &invitation.TenantRole, &invitation.ProjectRole, &invitation.Status,
		&invitation.Delivery, &invitation.ExpiresAt, &invitation.CreatedAt, &invitation.UpdatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return Invitation{}, &AppError{Code: CodeInvitationInvalid, Message: "invitation is not available"}
	}
	if err != nil {
		return Invitation{}, backendError()
	}
	if err := insertAudit(ctx, tx, input.TenantID, invitation.ProjectID, input.ActorID, "collaboration.invitation.revoked", "collaboration_invitation", input.InvitationID, input.RequestID, map[string]any{"status_before": "pending", "status_after": "revoked"}); err != nil {
		return Invitation{}, backendError()
	}
	if err := tx.Commit(); err != nil {
		return Invitation{}, backendError()
	}
	return invitation, nil
}

func (s *Service) AcceptInvitation(ctx context.Context, input AcceptInvitationInput) (Invitation, error) {
	if strings.TrimSpace(input.Token) == "" || strings.TrimSpace(input.ActorID) == "" {
		return Invitation{}, &AppError{Code: CodeValidationFailed, Message: "token and authenticated user are required"}
	}
	if s.db == nil {
		return Invitation{}, backendError()
	}
	hash := hashToken(input.Token)
	var tenantID string
	if err := s.db.QueryRowContext(ctx, `SELECT COALESCE(collaboration_invitation_tenant_for_token($1)::text, '')`, hash).Scan(&tenantID); err != nil || tenantID == "" {
		return Invitation{}, &AppError{Code: CodeInvitationInvalid, Message: "invitation is invalid"}
	}
	tx, err := s.beginTenantTx(ctx, tenantID, input.ActorID)
	if err != nil {
		return Invitation{}, backendError()
	}
	defer tx.Rollback()
	var invitation Invitation
	var actorEmail string
	err = tx.QueryRowContext(ctx, `SELECT i.invitation_id::text, i.tenant_id::text, COALESCE(i.project_id::text, ''), i.email_normalized,
  COALESCE(i.tenant_role, ''), COALESCE(i.project_role, ''), i.status, i.delivery_status, i.expires_at, i.created_at, i.updated_at,
  lower(btrim(u.email))
FROM collaboration_invitations i JOIN users u ON u.user_id = $2 AND u.status = 'active'
WHERE i.tenant_id = $1 AND i.token_hash = $3 FOR UPDATE`, tenantID, input.ActorID, hash).Scan(&invitation.InvitationID,
		&invitation.TenantID, &invitation.ProjectID, &invitation.Email, &invitation.TenantRole, &invitation.ProjectRole,
		&invitation.Status, &invitation.Delivery, &invitation.ExpiresAt, &invitation.CreatedAt, &invitation.UpdatedAt, &actorEmail)
	if errors.Is(err, sql.ErrNoRows) {
		return Invitation{}, &AppError{Code: CodeInvitationInvalid, Message: "invitation is invalid"}
	}
	if err != nil {
		return Invitation{}, backendError()
	}
	if invitation.Status != "pending" {
		return Invitation{}, &AppError{Code: CodeInvitationConsumed, Message: "invitation is no longer pending"}
	}
	if !invitation.ExpiresAt.After(s.now()) {
		_, _ = tx.ExecContext(ctx, `UPDATE collaboration_invitations SET status='expired', updated_at=now() WHERE tenant_id=$1 AND invitation_id=$2`, tenantID, invitation.InvitationID)
		if err := insertAudit(ctx, tx, tenantID, invitation.ProjectID, input.ActorID, "collaboration.invitation.expired", "collaboration_invitation", invitation.InvitationID, input.RequestID, map[string]any{"status_before": "pending", "status_after": "expired"}); err != nil {
			return Invitation{}, backendError()
		}
		_ = tx.Commit()
		return Invitation{}, &AppError{Code: CodeInvitationExpired, Message: "invitation has expired"}
	}
	if actorEmail != invitation.Email {
		return Invitation{}, &AppError{Code: CodeInvitationInvalid, Message: "invitation is invalid"}
	}
	if invitation.ProjectID == "" {
		_, err = tx.ExecContext(ctx, `INSERT INTO tenant_memberships (tenant_id,user_id,role,status,joined_at,access_scope) VALUES ($1,$2,$3,'active',$4,'tenant')
ON CONFLICT (tenant_id,user_id) DO UPDATE SET
  role=CASE WHEN tenant_memberships.role='owner' AND tenant_memberships.status='active' THEN 'owner' ELSE EXCLUDED.role END,
  status='active',joined_at=COALESCE(tenant_memberships.joined_at,EXCLUDED.joined_at),access_scope='tenant',updated_at=now()`, tenantID, input.ActorID, invitation.TenantRole, s.now())
	} else {
		_, err = tx.ExecContext(ctx, `INSERT INTO tenant_memberships (tenant_id,user_id,role,status,joined_at,access_scope) VALUES ($1,$2,'viewer','active',$3,'project_bridge')
	ON CONFLICT (tenant_id,user_id) DO UPDATE SET
	  role=CASE WHEN tenant_memberships.access_scope='tenant' AND tenant_memberships.status='active' THEN tenant_memberships.role ELSE 'viewer' END,
	  status='active',
	  joined_at=COALESCE(tenant_memberships.joined_at,EXCLUDED.joined_at),
	  access_scope=CASE WHEN tenant_memberships.access_scope='tenant' AND tenant_memberships.status='active' THEN 'tenant' ELSE 'project_bridge' END,
	  updated_at=now()`, tenantID, input.ActorID, s.now())
		if err == nil {
			_, err = tx.ExecContext(ctx, `INSERT INTO project_members (tenant_id,project_id,user_id,role,status) VALUES ($1,$2,$3,$4,'active')
ON CONFLICT (tenant_id,project_id,user_id) DO UPDATE SET role=EXCLUDED.role,status='active',updated_at=now()`, tenantID, invitation.ProjectID, input.ActorID, invitation.ProjectRole)
		}
	}
	if err != nil {
		return Invitation{}, backendError()
	}
	result, err := tx.ExecContext(ctx, `UPDATE collaboration_invitations SET status='accepted', accepted_by=$3, accepted_at=$4, updated_at=now()
WHERE tenant_id=$1 AND invitation_id=$2 AND status='pending'`, tenantID, invitation.InvitationID, input.ActorID, s.now())
	if err != nil {
		return Invitation{}, backendError()
	}
	if count, _ := result.RowsAffected(); count != 1 {
		return Invitation{}, &AppError{Code: CodeInvitationConsumed, Message: "invitation is no longer pending"}
	}
	if err := insertAudit(ctx, tx, tenantID, invitation.ProjectID, input.ActorID, "collaboration.invitation.accepted", "collaboration_invitation", invitation.InvitationID, input.RequestID, map[string]any{"scope": invitationScope(invitation), "role": invitationRole(invitation)}); err != nil {
		return Invitation{}, backendError()
	}
	if err := tx.Commit(); err != nil {
		return Invitation{}, backendError()
	}
	invitation.Status = "accepted"
	invitation.UpdatedAt = s.now()
	return invitation, nil
}

func (s *Service) deliver(ctx context.Context, invitation Invitation, token string) (Invitation, error) {
	status, errorCode, providerID := "not_configured", CodeDeliveryUnavailable, ""
	if s.notifier != nil {
		receipt, err := s.notifier.SendInvitation(ctx, InvitationDelivery{InvitationID: invitation.InvitationID, Email: invitation.Email, Token: token, TenantID: invitation.TenantID, ProjectID: invitation.ProjectID, TenantRole: invitation.TenantRole, ProjectRole: invitation.ProjectRole, ExpiresAt: invitation.ExpiresAt})
		if err == nil {
			status, errorCode, providerID = "delivered", "", receipt.ProviderMessageID
		} else {
			status, errorCode = "failed", "SMTP_DELIVERY_FAILED"
		}
	}
	tx, err := s.beginTenantTx(ctx, invitation.TenantID, "")
	if err != nil {
		return Invitation{}, backendError()
	}
	defer tx.Rollback()
	_, err = tx.ExecContext(ctx, `WITH updated AS (UPDATE collaboration_invitations SET delivery_status=$3,delivery_attempts=delivery_attempts+1,last_delivery_error_code=NULLIF($4,''),last_sent_at=$5,updated_at=now() WHERE tenant_id=$1 AND invitation_id=$2 RETURNING invitation_id)
INSERT INTO collaboration_delivery_attempts(tenant_id,invitation_id,status,provider_message_id,error_code) SELECT $1,invitation_id,$3,NULLIF($6,''),NULLIF($4,'') FROM updated`, invitation.TenantID, invitation.InvitationID, status, errorCode, s.now(), providerID)
	if err != nil || tx.Commit() != nil {
		return Invitation{}, backendError()
	}
	invitation.Delivery = status
	invitation.UpdatedAt = s.now()
	if status != "delivered" {
		return invitation, &AppError{Code: CodeDeliveryUnavailable, Message: "invitation was created but email delivery was not completed"}
	}
	return invitation, nil
}

func (s *Service) ListMembers(ctx context.Context, input ListInput) ([]Member, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ActorID) == "" {
		return nil, &AppError{Code: CodeValidationFailed, Message: "tenant and actor are required"}
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, input.ActorID)
	if err != nil {
		return nil, backendError()
	}
	defer tx.Rollback()
	if err := requireManager(ctx, tx, input.TenantID, input.ProjectID, input.ActorID); err != nil {
		return nil, err
	}
	query := `SELECT tm.tenant_id::text,'',tm.user_id::text,u.email,u.display_name,tm.role,tm.status,tm.created_at,tm.updated_at FROM tenant_memberships tm JOIN users u ON u.user_id=tm.user_id WHERE tm.tenant_id=$1 AND tm.access_scope='tenant' ORDER BY u.email`
	args := []any{input.TenantID}
	if input.ProjectID != "" {
		query = `SELECT pm.tenant_id::text,pm.project_id::text,pm.user_id::text,u.email,u.display_name,pm.role,pm.status,pm.created_at,pm.updated_at FROM project_members pm JOIN users u ON u.user_id=pm.user_id WHERE pm.tenant_id=$1 AND pm.project_id=$2 ORDER BY u.email`
		args = append(args, input.ProjectID)
	}
	rows, err := tx.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, backendError()
	}
	defer rows.Close()
	members := []Member{}
	for rows.Next() {
		var m Member
		if err := rows.Scan(&m.TenantID, &m.ProjectID, &m.UserID, &m.Email, &m.Name, &m.Role, &m.Status, &m.CreatedAt, &m.UpdatedAt); err != nil {
			return nil, backendError()
		}
		members = append(members, m)
	}
	if rows.Err() != nil {
		return nil, backendError()
	}
	if tx.Commit() != nil {
		return nil, backendError()
	}
	return members, nil
}

func (s *Service) ListInvitations(ctx context.Context, input ListInput) ([]Invitation, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ActorID) == "" {
		return nil, &AppError{Code: CodeValidationFailed, Message: "tenant and actor are required"}
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, input.ActorID)
	if err != nil {
		return nil, backendError()
	}
	defer tx.Rollback()
	if err := requireManager(ctx, tx, input.TenantID, input.ProjectID, input.ActorID); err != nil {
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, `SELECT invitation_id::text, tenant_id::text, COALESCE(project_id::text,''), email_normalized,
  COALESCE(tenant_role,''), COALESCE(project_role,''),
  CASE WHEN status='pending' AND expires_at <= $3 THEN 'expired' ELSE status END,
  delivery_status, expires_at, created_at, updated_at
FROM collaboration_invitations
WHERE tenant_id=$1 AND (($2='' AND project_id IS NULL) OR project_id=NULLIF($2,'')::uuid)
ORDER BY created_at DESC`, input.TenantID, input.ProjectID, s.now())
	if err != nil {
		return nil, backendError()
	}
	defer rows.Close()
	items := []Invitation{}
	for rows.Next() {
		var item Invitation
		if err := rows.Scan(&item.InvitationID, &item.TenantID, &item.ProjectID, &item.Email, &item.TenantRole, &item.ProjectRole, &item.Status, &item.Delivery, &item.ExpiresAt, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, backendError()
		}
		items = append(items, item)
	}
	if rows.Err() != nil {
		return nil, backendError()
	}
	if tx.Commit() != nil {
		return nil, backendError()
	}
	return items, nil
}

func (s *Service) ChangeMembership(ctx context.Context, input MembershipChangeInput) (Member, error) {
	if err := validateMembershipChange(input); err != nil {
		return Member{}, err
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, input.ActorID)
	if err != nil {
		return Member{}, backendError()
	}
	defer tx.Rollback()
	if err := requireManager(ctx, tx, input.TenantID, input.ProjectID, input.ActorID); err != nil {
		return Member{}, err
	}
	if input.ProjectID == "" && input.Role == "owner" {
		if err := requireTenantOwner(ctx, tx, input.TenantID, input.ActorID); err != nil {
			return Member{}, err
		}
	}
	if _, err := tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, input.TenantID); err != nil {
		return Member{}, backendError()
	}
	table, scopeWhere := "tenant_memberships", "tenant_id=$1 AND user_id=$2 AND access_scope='tenant'"
	args := []any{input.TenantID, input.UserID}
	if input.ProjectID != "" {
		table = "project_members"
		scopeWhere = "tenant_id=$1 AND project_id=$3 AND user_id=$2"
		args = append(args, input.ProjectID)
	}
	var beforeRole, beforeStatus string
	if err := tx.QueryRowContext(ctx, "SELECT role,status FROM "+table+" WHERE "+scopeWhere+" FOR UPDATE", args...).Scan(&beforeRole, &beforeStatus); errors.Is(err, sql.ErrNoRows) {
		return Member{}, &AppError{Code: CodeMembershipNotFound, Message: "membership was not found"}
	} else if err != nil {
		return Member{}, backendError()
	}
	afterRole, afterStatus := beforeRole, beforeStatus
	if input.Role != "" {
		afterRole = input.Role
	}
	if input.Status != "" {
		afterStatus = input.Status
	}
	if input.ProjectID == "" && beforeRole == "owner" && beforeStatus == "active" && (afterRole != "owner" || afterStatus != "active") {
		var owners int
		if err := tx.QueryRowContext(ctx, `SELECT count(*) FROM tenant_memberships WHERE tenant_id=$1 AND access_scope='tenant' AND role='owner' AND status='active'`, input.TenantID).Scan(&owners); err != nil {
			return Member{}, backendError()
		}
		if owners <= 1 {
			return Member{}, &AppError{Code: CodeLastOwner, Message: "the last active owner cannot be changed"}
		}
	}
	if input.ProjectID == "" && beforeStatus == "active" && afterStatus == "suspended" {
		if _, err := tx.ExecContext(ctx, `UPDATE project_members SET status='suspended',updated_at=now() WHERE tenant_id=$1 AND user_id=$2 AND status='active'`, input.TenantID, input.UserID); err != nil {
			return Member{}, backendError()
		}
	}
	var member Member
	rolePlaceholder, statusPlaceholder := "$3", "$4"
	queryArgs := []any{input.TenantID, input.UserID, afterRole, afterStatus}
	if input.ProjectID != "" {
		rolePlaceholder, statusPlaceholder = "$4", "$5"
		queryArgs = []any{input.TenantID, input.UserID, input.ProjectID, afterRole, afterStatus}
	}
	query := "UPDATE " + table + " SET role=" + rolePlaceholder + ",status=" + statusPlaceholder + ",updated_at=now() WHERE " + scopeWhere + " RETURNING tenant_id::text," + func() string {
		if input.ProjectID != "" {
			return "project_id::text"
		}
		return "''"
	}() + ",user_id::text,role,status,created_at,updated_at"
	if err := tx.QueryRowContext(ctx, query, queryArgs...).Scan(&member.TenantID, &member.ProjectID, &member.UserID, &member.Role, &member.Status, &member.CreatedAt, &member.UpdatedAt); err != nil {
		return Member{}, backendError()
	}
	if err := tx.QueryRowContext(ctx, `SELECT email,display_name FROM users WHERE user_id=$1`, input.UserID).Scan(&member.Email, &member.Name); err != nil {
		return Member{}, backendError()
	}
	action := "collaboration.membership.updated"
	if afterStatus == "suspended" {
		action = "collaboration.membership.suspended"
	}
	if beforeStatus == "suspended" && afterStatus == "active" {
		action = "collaboration.membership.reactivated"
	}
	if err := insertAudit(ctx, tx, input.TenantID, input.ProjectID, input.ActorID, action, "membership", input.UserID, input.RequestID, map[string]any{"before": map[string]string{"role": beforeRole, "status": beforeStatus}, "after": map[string]string{"role": afterRole, "status": afterStatus}}); err != nil {
		return Member{}, backendError()
	}
	if tx.Commit() != nil {
		return Member{}, backendError()
	}
	return member, nil
}

func (s *Service) RemoveMembership(ctx context.Context, input MembershipChangeInput) error {
	input.Status = ""
	input.Role = ""
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.UserID) == "" || strings.TrimSpace(input.ActorID) == "" {
		return &AppError{Code: CodeValidationFailed, Message: "membership identifiers are required"}
	}
	tx, err := s.beginTenantTx(ctx, input.TenantID, input.ActorID)
	if err != nil {
		return backendError()
	}
	defer tx.Rollback()
	if err := requireManager(ctx, tx, input.TenantID, input.ProjectID, input.ActorID); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, input.TenantID); err != nil {
		return backendError()
	}
	table, where := "tenant_memberships", "tenant_id=$1 AND user_id=$2 AND access_scope='tenant'"
	args := []any{input.TenantID, input.UserID}
	if input.ProjectID != "" {
		table = "project_members"
		where = "tenant_id=$1 AND project_id=$3 AND user_id=$2"
		args = append(args, input.ProjectID)
	}
	var role, status string
	if err := tx.QueryRowContext(ctx, "SELECT role,status FROM "+table+" WHERE "+where+" FOR UPDATE", args...).Scan(&role, &status); errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: CodeMembershipNotFound, Message: "membership was not found"}
	} else if err != nil {
		return backendError()
	}
	if input.ProjectID == "" && role == "owner" && status == "active" {
		var owners int
		if err := tx.QueryRowContext(ctx, `SELECT count(*) FROM tenant_memberships WHERE tenant_id=$1 AND access_scope='tenant' AND role='owner' AND status='active'`, input.TenantID).Scan(&owners); err != nil {
			return backendError()
		}
		if owners <= 1 {
			return &AppError{Code: CodeLastOwner, Message: "the last active owner cannot be removed"}
		}
	}
	if input.ProjectID == "" {
		if _, err := tx.ExecContext(ctx, `DELETE FROM project_members WHERE tenant_id=$1 AND user_id=$2`, input.TenantID, input.UserID); err != nil {
			return backendError()
		}
	}
	if _, err := tx.ExecContext(ctx, "DELETE FROM "+table+" WHERE "+where, args...); err != nil {
		return backendError()
	}
	if input.ProjectID != "" {
		if _, err := tx.ExecContext(ctx, `DELETE FROM tenant_memberships tm
WHERE tm.tenant_id=$1 AND tm.user_id=$2 AND tm.access_scope='project_bridge'
  AND NOT EXISTS (
    SELECT 1 FROM project_members pm
    WHERE pm.tenant_id=tm.tenant_id AND pm.user_id=tm.user_id
  )`, input.TenantID, input.UserID); err != nil {
			return backendError()
		}
	}
	if err := insertAudit(ctx, tx, input.TenantID, input.ProjectID, input.ActorID, "collaboration.membership.removed", "membership", input.UserID, input.RequestID, map[string]any{"before": map[string]string{"role": role, "status": status}, "after": nil}); err != nil {
		return backendError()
	}
	return tx.Commit()
}

func (s *Service) beginTenantTx(ctx context.Context, tenantID, actorID string) (*sql.Tx, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err = tx.ExecContext(ctx, `SELECT app_set_tenant_context($1::uuid,NULLIF($2,'')::uuid,false)`, strings.TrimSpace(tenantID), strings.TrimSpace(actorID)); err != nil {
		tx.Rollback()
		return nil, err
	}
	return tx, nil
}
func requireManager(ctx context.Context, tx *sql.Tx, tenantID, projectID, actorID string) error {
	var allowed bool
	err := tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM tenant_memberships WHERE tenant_id=$1 AND user_id=$2 AND access_scope='tenant' AND status='active' AND role IN ('owner','admin')) OR ($3<>'' AND EXISTS(SELECT 1 FROM project_members WHERE tenant_id=$1 AND project_id=NULLIF($3,'')::uuid AND user_id=$2 AND status='active' AND role='project_owner'))`, tenantID, actorID, projectID).Scan(&allowed)
	if err != nil {
		return backendError()
	}
	if !allowed {
		return &AppError{Code: CodeAccessDenied, Message: "membership management access is required"}
	}
	return nil
}
func requireTenantOwner(ctx context.Context, tx *sql.Tx, tenantID, actorID string) error {
	var allowed bool
	err := tx.QueryRowContext(ctx, `SELECT EXISTS(
  SELECT 1 FROM tenant_memberships
  WHERE tenant_id=$1 AND user_id=$2 AND access_scope='tenant'
    AND status='active' AND role='owner'
)`, tenantID, actorID).Scan(&allowed)
	if err != nil {
		return backendError()
	}
	if !allowed {
		return &AppError{Code: CodeAccessDenied, Message: "tenant owner access is required to grant owner role"}
	}
	return nil
}
func insertAudit(ctx context.Context, tx *sql.Tx, tenantID, projectID, actorID, action, resourceType, resourceID, requestID string, metadata any) error {
	encoded, err := json.Marshal(metadata)
	if err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO audit_logs(tenant_id,actor_user_id,action,resource_type,resource_id,project_id,request_id,metadata_jsonb) VALUES($1,NULLIF($2,'')::uuid,$3,$4,NULLIF($5,'')::uuid,NULLIF($6,'')::uuid,NULLIF($7,''),$8::jsonb)`, tenantID, actorID, action, resourceType, resourceID, projectID, requestID, string(encoded))
	return err
}
func validateCreate(i CreateInvitationInput) error {
	if strings.TrimSpace(i.TenantID) == "" || strings.TrimSpace(i.ActorID) == "" || normalizeEmail(i.Email) == "" || !strings.Contains(normalizeEmail(i.Email), "@") {
		return &AppError{Code: CodeValidationFailed, Message: "tenant, actor, and valid email are required"}
	}
	if i.ProjectID == "" {
		if !validTenantRole(i.TenantRole) || i.ProjectRole != "" {
			return &AppError{Code: CodeValidationFailed, Message: "a valid tenant role is required"}
		}
	} else if !validProjectRole(i.ProjectRole) || i.TenantRole != "" {
		return &AppError{Code: CodeValidationFailed, Message: "a valid project role is required"}
	}
	return nil
}
func validateAction(i InvitationActionInput) error {
	if strings.TrimSpace(i.TenantID) == "" || strings.TrimSpace(i.InvitationID) == "" || strings.TrimSpace(i.ActorID) == "" {
		return &AppError{Code: CodeValidationFailed, Message: "invitation action identifiers are required"}
	}
	return nil
}
func validateMembershipChange(i MembershipChangeInput) error {
	if strings.TrimSpace(i.TenantID) == "" || strings.TrimSpace(i.UserID) == "" || strings.TrimSpace(i.ActorID) == "" || (i.Role == "" && i.Status == "") {
		return &AppError{Code: CodeValidationFailed, Message: "membership change is invalid"}
	}
	if i.Role != "" && ((i.ProjectID == "" && !validTenantRole(i.Role)) || (i.ProjectID != "" && !validProjectRole(i.Role))) {
		return &AppError{Code: CodeValidationFailed, Message: "membership role is invalid"}
	}
	if i.Status != "" && i.Status != "active" && i.Status != "suspended" {
		return &AppError{Code: CodeValidationFailed, Message: "membership status is invalid"}
	}
	return nil
}
func validTenantRole(v string) bool {
	switch v {
	case "owner", "admin", "editor", "writer", "viewer", "billing":
		return true
	}
	return false
}
func validProjectRole(v string) bool {
	switch v {
	case "project_owner", "editor", "writer", "analyst", "viewer":
		return true
	}
	return false
}
func normalizeEmail(v string) string { return strings.ToLower(strings.TrimSpace(v)) }
func invitationScope(i Invitation) string {
	if i.ProjectID != "" {
		return "project"
	}
	return "tenant"
}
func invitationRole(i Invitation) string {
	if i.ProjectRole != "" {
		return i.ProjectRole
	}
	return i.TenantRole
}
func newToken() (string, string, error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", "", err
	}
	token := base64.RawURLEncoding.EncodeToString(raw)
	return token, hashToken(token), nil
}
func hashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}
func backendError() error {
	return &AppError{Code: CodeBackendUnavailable, Message: "collaboration service is unavailable"}
}
