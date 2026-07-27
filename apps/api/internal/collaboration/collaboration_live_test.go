package collaboration

import (
	"context"
	"database/sql"
	"net"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"time"

	"mirofish-novel/apps/api/internal/testschema"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveTenantID        = "27000000-0000-4000-8000-000000000001"
	liveProjectID       = "27000000-0000-4000-8000-000000000002"
	liveOtherProjectID  = "27000000-0000-4000-8000-000000000004"
	liveForeignTenantID = "27000000-0000-4000-8000-000000000003"
	liveOwnerID         = "27000000-0000-4000-8000-000000000011"
	liveInviteeID       = "27000000-0000-4000-8000-000000000012"
	liveForeignOwnerID  = "27000000-0000-4000-8000-000000000013"
	liveSuspendedID     = "27000000-0000-4000-8000-000000000014"
	liveAdminID         = "27000000-0000-4000-8000-000000000015"
)

func TestLiveInvitationAcceptanceMembershipLifecycleAndRLS(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_COLLABORATION_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_COLLABORATION_LIVE_DATABASE_URL to run collaboration live E2E")
	}
	probeDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	if err := testschema.RequireDisposableLiveDatabase(context.Background(), probeDB); err != nil {
		_ = probeDB.Close()
		t.Fatal(err)
	}
	_ = probeDB.Close()
	adminDB, appDB := prepareCollaborationFixture(t, adminURL)
	address, messages, closeSink := startSMTPSink(t)
	defer closeSink()
	host, portText, _ := net.SplitHostPort(address)
	port, _ := strconv.Atoi(portText)
	notifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: host, Port: port, Username: "test-user", Password: "test-pass", From: "collaboration@example.test", AcceptBaseURL: "http://localhost/invitations/accept", TLSMode: SMTPModeLoopbackPlaintext})
	if err != nil {
		t.Fatal(err)
	}
	service := NewService(ServiceConfig{DB: appDB, Notifier: notifier, Now: func() time.Time { return time.Date(2026, 7, 10, 15, 0, 0, 0, time.UTC) }})
	invitation, err := service.CreateInvitation(context.Background(), CreateInvitationInput{TenantID: liveTenantID, ProjectID: liveProjectID, Email: "INVITEE@EXAMPLE.TEST ", ProjectRole: "writer", ActorID: liveOwnerID, RequestID: "live-create"})
	if err != nil {
		t.Fatalf("create invitation: %v", err)
	}
	message := <-messages
	token := tokenFromSMTPMessage(t, message)
	var storedHash string
	if err := adminDB.QueryRow(`SELECT token_hash FROM collaboration_invitations WHERE invitation_id=$1`, invitation.InvitationID).Scan(&storedHash); err != nil {
		t.Fatal(err)
	}
	if storedHash == token || storedHash != hashToken(token) {
		t.Fatal("invitation token was not stored hash-only")
	}
	accepted, err := service.AcceptInvitation(context.Background(), AcceptInvitationInput{Token: token, ActorID: liveInviteeID, RequestID: "live-accept"})
	if err != nil {
		t.Fatalf("accept invitation: %v", err)
	}
	if accepted.Status != "accepted" {
		t.Fatalf("status=%s", accepted.Status)
	}
	var role, status string
	if err := adminDB.QueryRow(`SELECT role,status FROM project_members WHERE tenant_id=$1 AND project_id=$2 AND user_id=$3`, liveTenantID, liveProjectID, liveInviteeID).Scan(&role, &status); err != nil {
		t.Fatal(err)
	}
	if role != "writer" || status != "active" {
		t.Fatalf("unexpected accepted membership %s/%s", role, status)
	}
	var accessScope string
	if err := adminDB.QueryRow(`SELECT access_scope FROM tenant_memberships WHERE tenant_id=$1 AND user_id=$2`, liveTenantID, liveInviteeID).Scan(&accessScope); err != nil {
		t.Fatal(err)
	}
	if accessScope != "project_bridge" {
		t.Fatalf("project invitation created access_scope=%q, want project_bridge", accessScope)
	}
	assertProjectBridgeSeesOnlyInvitedProject(t, appDB, liveInviteeID)

	suspendedAddress, suspendedMessages, closeSuspendedSink := startSMTPSink(t)
	defer closeSuspendedSink()
	suspendedHost, suspendedPortText, _ := net.SplitHostPort(suspendedAddress)
	suspendedPort, _ := strconv.Atoi(suspendedPortText)
	suspendedNotifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: suspendedHost, Port: suspendedPort, Username: "test-user", Password: "test-pass", From: "collaboration@example.test", AcceptBaseURL: "http://localhost/invitations/accept", TLSMode: SMTPModeLoopbackPlaintext})
	if err != nil {
		t.Fatal(err)
	}
	suspendedService := NewService(ServiceConfig{DB: appDB, Notifier: suspendedNotifier, Now: func() time.Time { return time.Date(2026, 7, 10, 15, 0, 0, 0, time.UTC) }})
	suspendedInvitation, err := suspendedService.CreateInvitation(context.Background(), CreateInvitationInput{TenantID: liveTenantID, ProjectID: liveProjectID, Email: "suspended@example.test", ProjectRole: "writer", ActorID: liveOwnerID, RequestID: "live-suspended-create"})
	if err != nil {
		t.Fatalf("create suspended-member project invitation: %v", err)
	}
	suspendedToken := tokenFromSMTPMessage(t, <-suspendedMessages)
	if _, err := suspendedService.AcceptInvitation(context.Background(), AcceptInvitationInput{Token: suspendedToken, ActorID: liveSuspendedID, RequestID: "live-suspended-accept"}); err != nil {
		t.Fatalf("accept suspended-member project invitation: %v", err)
	}
	var suspendedRole, suspendedStatus, suspendedScope string
	if err := adminDB.QueryRow(`SELECT role,status,access_scope FROM tenant_memberships WHERE tenant_id=$1 AND user_id=$2`, liveTenantID, liveSuspendedID).Scan(&suspendedRole, &suspendedStatus, &suspendedScope); err != nil {
		t.Fatal(err)
	}
	if suspendedRole != "viewer" || suspendedStatus != "active" || suspendedScope != "project_bridge" {
		t.Fatalf("suspended workspace member regained broad access: role=%s status=%s scope=%s", suspendedRole, suspendedStatus, suspendedScope)
	}
	assertProjectBridgeSeesOnlyInvitedProject(t, appDB, liveSuspendedID)
	if suspendedInvitation.ProjectID != liveProjectID {
		t.Fatalf("suspended-member invitation project=%s", suspendedInvitation.ProjectID)
	}
	if _, err := service.AcceptInvitation(context.Background(), AcceptInvitationInput{Token: token, ActorID: liveInviteeID}); ErrorCode(err) != CodeInvitationConsumed {
		t.Fatalf("replay code=%s err=%v", ErrorCode(err), err)
	}
	member, err := service.ChangeMembership(context.Background(), MembershipChangeInput{TenantID: liveTenantID, ProjectID: liveProjectID, UserID: liveInviteeID, ActorID: liveOwnerID, Role: "editor", RequestID: "live-role"})
	if err != nil || member.Role != "editor" {
		t.Fatalf("role change: member=%+v err=%v", member, err)
	}
	if _, err := service.ChangeMembership(context.Background(), MembershipChangeInput{TenantID: liveTenantID, ProjectID: liveProjectID, UserID: liveInviteeID, ActorID: liveOwnerID, Status: "suspended"}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.ChangeMembership(context.Background(), MembershipChangeInput{TenantID: liveTenantID, ProjectID: liveProjectID, UserID: liveInviteeID, ActorID: liveOwnerID, Status: "active"}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.ListMembers(context.Background(), ListInput{TenantID: liveForeignTenantID, ActorID: liveOwnerID}); ErrorCode(err) != CodeAccessDenied {
		t.Fatalf("cross-tenant list code=%s err=%v", ErrorCode(err), err)
	}
	if _, err := service.CreateInvitation(context.Background(), CreateInvitationInput{TenantID: liveTenantID, Email: "owner-candidate@example.test", TenantRole: "owner", ActorID: liveAdminID}); ErrorCode(err) != CodeAccessDenied {
		t.Fatalf("admin owner invitation code=%s err=%v", ErrorCode(err), err)
	}
	if _, err := service.ChangeMembership(context.Background(), MembershipChangeInput{TenantID: liveTenantID, UserID: liveAdminID, ActorID: liveAdminID, Role: "owner"}); ErrorCode(err) != CodeAccessDenied {
		t.Fatalf("admin self-promotion code=%s err=%v", ErrorCode(err), err)
	}
	promoted, err := service.ChangeMembership(context.Background(), MembershipChangeInput{TenantID: liveTenantID, UserID: liveAdminID, ActorID: liveOwnerID, Role: "owner", RequestID: "live-owner-grant"})
	if err != nil || promoted.Role != "owner" {
		t.Fatalf("owner grant: member=%+v err=%v", promoted, err)
	}
	if _, err := service.ChangeMembership(context.Background(), MembershipChangeInput{TenantID: liveTenantID, UserID: liveAdminID, ActorID: liveOwnerID, Role: "admin", RequestID: "live-owner-grant-reset"}); err != nil {
		t.Fatalf("reset granted owner: %v", err)
	}
	ownerAddress, ownerMessages, closeOwnerSink := startSMTPSink(t)
	defer closeOwnerSink()
	ownerHost, ownerPortText, _ := net.SplitHostPort(ownerAddress)
	ownerPort, _ := strconv.Atoi(ownerPortText)
	ownerNotifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: ownerHost, Port: ownerPort, Username: "test-user", Password: "test-pass", From: "collaboration@example.test", AcceptBaseURL: "http://localhost/invitations/accept", TLSMode: SMTPModeLoopbackPlaintext})
	if err != nil {
		t.Fatal(err)
	}
	ownerService := NewService(ServiceConfig{DB: appDB, Notifier: ownerNotifier, Now: func() time.Time { return time.Date(2026, 7, 10, 15, 0, 0, 0, time.UTC) }})
	ownerViewerInvitation, err := ownerService.CreateInvitation(context.Background(), CreateInvitationInput{TenantID: liveTenantID, Email: "owner@example.test", TenantRole: "viewer", ActorID: liveOwnerID, RequestID: "live-owner-lower-invite"})
	if err != nil {
		t.Fatalf("create lower-role owner invitation: %v", err)
	}
	ownerViewerToken := tokenFromSMTPMessage(t, <-ownerMessages)
	if _, err := ownerService.AcceptInvitation(context.Background(), AcceptInvitationInput{Token: ownerViewerToken, ActorID: liveOwnerID, RequestID: "live-owner-lower-accept"}); err != nil {
		t.Fatalf("accept lower-role owner invitation: %v", err)
	}
	if err := adminDB.QueryRow(`SELECT role,status FROM tenant_memberships WHERE tenant_id=$1 AND user_id=$2`, liveTenantID, liveOwnerID).Scan(&role, &status); err != nil || role != "owner" || status != "active" {
		t.Fatalf("lower-role invitation changed active owner: invitation=%s role=%s status=%s err=%v", ownerViewerInvitation.InvitationID, role, status, err)
	}
	if err := service.RemoveMembership(context.Background(), MembershipChangeInput{TenantID: liveTenantID, UserID: liveOwnerID, ActorID: liveOwnerID}); ErrorCode(err) != CodeLastOwner {
		t.Fatalf("last owner code=%s err=%v", ErrorCode(err), err)
	}
	failedInvitation, deliveryErr := NewService(ServiceConfig{DB: appDB}).CreateInvitation(context.Background(), CreateInvitationInput{TenantID: liveTenantID, ProjectID: liveProjectID, Email: "second@example.test", ProjectRole: "viewer", ActorID: liveOwnerID})
	if ErrorCode(deliveryErr) != CodeDeliveryUnavailable || failedInvitation.Delivery != "not_configured" {
		t.Fatalf("missing notifier claimed delivery: invitation=%+v err=%v", failedInvitation, deliveryErr)
	}
	if _, err := service.RevokeInvitation(context.Background(), InvitationActionInput{TenantID: liveTenantID, InvitationID: failedInvitation.InvitationID, ActorID: liveOwnerID}); err != nil {
		t.Fatalf("revoke invitation: %v", err)
	}
	resendInvitation, deliveryErr := NewService(ServiceConfig{DB: appDB}).CreateInvitation(context.Background(), CreateInvitationInput{TenantID: liveTenantID, ProjectID: liveProjectID, Email: "resend@example.test", ProjectRole: "analyst", ActorID: liveOwnerID})
	if ErrorCode(deliveryErr) != CodeDeliveryUnavailable {
		t.Fatalf("prepare resend invitation: %v", deliveryErr)
	}
	resendAddress, resendMessages, closeResendSink := startSMTPSink(t)
	resendHost, resendPortText, _ := net.SplitHostPort(resendAddress)
	resendPort, _ := strconv.Atoi(resendPortText)
	resendNotifier, _ := NewSMTPNotifier(SMTPNotifierConfig{Host: resendHost, Port: resendPort, Username: "test-user", Password: "test-pass", From: "collaboration@example.test", AcceptBaseURL: "http://localhost/invitations/accept", TLSMode: SMTPModeLoopbackPlaintext})
	resent, err := NewService(ServiceConfig{DB: appDB, Notifier: resendNotifier}).ResendInvitation(context.Background(), InvitationActionInput{TenantID: liveTenantID, InvitationID: resendInvitation.InvitationID, ActorID: liveOwnerID, RequestID: "live-resend"})
	if err != nil || resent.Delivery != "delivered" {
		t.Fatalf("resend invitation: %+v %v", resent, err)
	}
	_ = <-resendMessages
	closeResendSink()
	expiredToken := "expired-live-invitation-token"
	var expiredID string
	if err := adminDB.QueryRow(`INSERT INTO collaboration_invitations(tenant_id,project_id,email_normalized,project_role,token_hash,invited_by,expires_at)VALUES($1,$2,'invitee@example.test','viewer',$3,$4,$5)RETURNING invitation_id::text`, liveTenantID, liveProjectID, hashToken(expiredToken), liveOwnerID, time.Date(2026, 7, 9, 0, 0, 0, 0, time.UTC)).Scan(&expiredID); err != nil {
		t.Fatal(err)
	}
	if _, err := service.AcceptInvitation(context.Background(), AcceptInvitationInput{Token: expiredToken, ActorID: liveInviteeID}); ErrorCode(err) != CodeInvitationExpired {
		t.Fatalf("expired invitation code=%s err=%v", ErrorCode(err), err)
	}
	var audits int
	if err := adminDB.QueryRow(`SELECT count(*) FROM audit_logs WHERE tenant_id=$1 AND action LIKE 'collaboration.%'`, liveTenantID).Scan(&audits); err != nil || audits < 6 {
		t.Fatalf("audit count=%d err=%v", audits, err)
	}
	var leaked int
	if err := adminDB.QueryRow(`SELECT count(*) FROM audit_logs WHERE tenant_id=$1 AND metadata_jsonb::text LIKE $2`, liveTenantID, "%"+token+"%").Scan(&leaked); err != nil || leaked != 0 {
		t.Fatalf("raw token leaked to audit: count=%d err=%v", leaked, err)
	}
}

func prepareCollaborationFixture(t *testing.T, adminURL string) (*sql.DB, *sql.DB) {
	t.Helper()
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	if err = adminDB.Ping(); err != nil {
		t.Fatal(err)
	}
	_, _ = adminDB.Exec(`DELETE FROM tenants WHERE tenant_id IN($1,$2)`, liveTenantID, liveForeignTenantID)
	_, _ = adminDB.Exec(`DELETE FROM users WHERE user_id IN($1,$2,$3,$4,$5)`, liveOwnerID, liveInviteeID, liveForeignOwnerID, liveSuspendedID, liveAdminID)
	_, err = adminDB.Exec(`INSERT INTO users(user_id,email,display_name)VALUES($1,'owner@example.test','Owner'),($2,'invitee@example.test','Invitee'),($3,'foreign@example.test','Foreign'),($4,'suspended@example.test','Suspended'),($5,'admin@example.test','Admin')`, liveOwnerID, liveInviteeID, liveForeignOwnerID, liveSuspendedID, liveAdminID)
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO tenants(tenant_id,slug,name,tenant_type)VALUES($1,'collab-live','Collab Live','organization'),($2,'collab-foreign','Collab Foreign','organization')`, liveTenantID, liveForeignTenantID)
	}
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO tenant_memberships(tenant_id,user_id,role,status)VALUES($1,$2,'owner','active'),($3,$4,'owner','active')`, liveTenantID, liveOwnerID, liveForeignTenantID, liveForeignOwnerID)
	}
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO tenant_memberships(tenant_id,user_id,role,status,access_scope)VALUES($1,$2,'admin','suspended','tenant')`, liveTenantID, liveSuspendedID)
	}
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO tenant_memberships(tenant_id,user_id,role,status,access_scope)VALUES($1,$2,'admin','active','tenant')`, liveTenantID, liveAdminID)
	}
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO projects(tenant_id,project_id,title,created_by)VALUES
($1,$2,'Live Project',$4),($1,$3,'Private Sibling Project',$4)`, liveTenantID, liveProjectID, liveOtherProjectID, liveOwnerID)
	}
	if err == nil {
		_, err = adminDB.Exec(`INSERT INTO project_members(tenant_id,project_id,user_id,role,status)VALUES
($1,$2,$4,'project_owner','active'),($1,$3,$4,'project_owner','active')`, liveTenantID, liveProjectID, liveOtherProjectID, liveOwnerID)
	}
	if err != nil {
		t.Fatal(err)
	}
	parsed, _ := url.Parse(adminURL)
	parsed.User = url.UserPassword("mirofish_runtime", "mirofish_runtime_dev_password")
	appDB, err := sql.Open("pgx", parsed.String())
	if err != nil {
		t.Fatal(err)
	}
	if err = appDB.Ping(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		appDB.Close()
		_, _ = adminDB.Exec(`DELETE FROM tenants WHERE tenant_id IN($1,$2)`, liveTenantID, liveForeignTenantID)
		_, _ = adminDB.Exec(`DELETE FROM users WHERE user_id IN($1,$2,$3,$4,$5)`, liveOwnerID, liveInviteeID, liveForeignOwnerID, liveSuspendedID, liveAdminID)
		adminDB.Close()
	})
	return adminDB, appDB
}

func assertProjectBridgeSeesOnlyInvitedProject(t *testing.T, appDB *sql.DB, userID string) {
	t.Helper()
	tx, err := appDB.BeginTx(context.Background(), &sql.TxOptions{ReadOnly: true})
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec(`SELECT set_config('app.current_user_id',$1,true)`, userID); err != nil {
		t.Fatal(err)
	}
	var projectCount int
	var projectID string
	if err := tx.QueryRow(`SELECT count(*), min(project_id::text) FROM projects WHERE tenant_id=$1`, liveTenantID).Scan(&projectCount, &projectID); err != nil {
		t.Fatal(err)
	}
	if projectCount != 1 || projectID != liveProjectID {
		t.Fatalf("project bridge visibility count=%d project=%q, want only %s", projectCount, projectID, liveProjectID)
	}
}

func tokenFromSMTPMessage(t *testing.T, message string) string {
	t.Helper()
	match := regexp.MustCompile(`token=([A-Za-z0-9_-]+)`).FindStringSubmatch(message)
	if len(match) != 2 {
		t.Fatal("SMTP message omitted token")
	}
	return match[1]
}
