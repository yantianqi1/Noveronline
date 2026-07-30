package worldline

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
)

// Live coverage for the candidate-decision contract: adopting one candidate
// rejects the remaining candidates of the same session+step in the same
// transaction, leaves other steps untouched, and explicit rejection only
// accepts candidate -> rejected.
func TestWorldlineEventDecisionLiveAdoptRejectsSiblingsAndRejectStaysCandidateOnly(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WORLDLINE_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WORLDLINE_LIVE_DATABASE_URL to run the live Worldline event decision E2E")
	}
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin database: %v", err)
	}
	defer adminDB.Close()
	applyWorldlineLiveSchema(t, adminDB)
	ensureWorldlineLiveAppRole(t, adminDB)

	tenantID := newUUID()
	userID := newUUID()
	projectID := newUUID()
	sessionRunID := newUUID()
	sessionID := newUUID()
	prepareWorldlineLiveSession(t, adminDB, tenantID, userID, projectID, sessionRunID, sessionID)
	defer cleanupWorldlineLiveSession(t, adminDB, tenantID, userID)

	adoptedID := newUUID()
	siblingID := newUUID()
	otherStepID := newUUID()
	preCanonID := newUUID()
	prepareWorldlineLiveEvent(t, adminDB, tenantID, projectID, sessionID, adoptedID, 3, "candidate", "simulation", userID)
	prepareWorldlineLiveEvent(t, adminDB, tenantID, projectID, sessionID, siblingID, 3, "candidate", "simulation", userID)
	prepareWorldlineLiveEvent(t, adminDB, tenantID, projectID, sessionID, otherStepID, 4, "candidate", "simulation", userID)
	prepareWorldlineLiveEvent(t, adminDB, tenantID, projectID, sessionID, preCanonID, 3, "canon", "canon_reference", userID)

	appConfig, err := pgx.ParseConfig(adminURL)
	if err != nil {
		t.Fatalf("parse admin database URL: %v", err)
	}
	appConfig.User = worldlineLiveAppRole
	appConfig.Password = worldlineLiveAppPassword
	appDB := stdlib.OpenDB(*appConfig)
	defer appDB.Close()
	queryer := NewSQLDBQueryer(appDB)
	adoptionStore := NewSQLEventAdoptionStore(SQLEventAdoptionStoreConfig{Queryer: queryer})
	rejectionStore := NewSQLEventRejectionStore(SQLEventRejectionStoreConfig{Queryer: queryer})

	adopted, err := adoptionStore.AdoptEvent(context.Background(), AdoptEventInput{
		TenantID: tenantID, EventID: adoptedID,
		ActorUserID: userID, RequestID: "req-live-adopt", Note: "canon pick",
	})
	if err != nil {
		t.Fatalf("adopt live event: %v", err)
	}
	if adopted.Status != "canon" || adopted.Lifecycle != "canon_reference" {
		t.Fatalf("unexpected adopted event: %#v", adopted)
	}

	for eventID, want := range map[string]string{
		adoptedID:   "canon",
		siblingID:   "rejected",
		otherStepID: "candidate",
		preCanonID:  "canon",
	} {
		if got := worldlineLiveEventStatus(t, adminDB, tenantID, eventID); got != want {
			t.Fatalf("event %s status = %s, want %s", eventID, got, want)
		}
	}

	rejected, err := rejectionStore.RejectEvent(context.Background(), RejectEventInput{
		TenantID: tenantID, EventID: otherStepID,
		ActorUserID: userID, RequestID: "req-live-reject", Note: "drop this branch",
	})
	if err != nil {
		t.Fatalf("reject live event: %v", err)
	}
	if rejected.Status != "rejected" {
		t.Fatalf("unexpected rejected event: %#v", rejected)
	}
	if got := worldlineLiveEventStatus(t, adminDB, tenantID, otherStepID); got != "rejected" {
		t.Fatalf("explicitly rejected event status = %s", got)
	}

	if _, err := rejectionStore.RejectEvent(context.Background(), RejectEventInput{
		TenantID: tenantID, EventID: otherStepID, ActorUserID: userID, RequestID: "req-live-reject-again",
	}); ErrorCode(err) != "NOT_FOUND" {
		t.Fatalf("expected NOT_FOUND rejecting an already rejected event, got %s (%v)", ErrorCode(err), err)
	}
	if _, err := rejectionStore.RejectEvent(context.Background(), RejectEventInput{
		TenantID: tenantID, EventID: adoptedID, ActorUserID: userID, RequestID: "req-live-reject-canon",
	}); ErrorCode(err) != "NOT_FOUND" {
		t.Fatalf("expected NOT_FOUND rejecting a canon event, got %s (%v)", ErrorCode(err), err)
	}

	var rejectedWorkflowEvents int
	if err := adminDB.QueryRow(`SELECT COUNT(*) FROM workflow_events
WHERE tenant_id = $1 AND project_id = $2 AND event_type = 'worldline.event.rejected'`, tenantID, projectID).Scan(&rejectedWorkflowEvents); err != nil {
		t.Fatalf("count rejection workflow events: %v", err)
	}
	if rejectedWorkflowEvents != 1 {
		t.Fatalf("expected one worldline.event.rejected workflow event, got %d", rejectedWorkflowEvents)
	}
}

func prepareWorldlineLiveEvent(t *testing.T, db *sql.DB, tenantID, projectID, sessionID, eventID string, step int, status string, lifecycle string, createdBy string) {
	t.Helper()
	if _, err := db.Exec(`INSERT INTO worldline_events (
  tenant_id, event_id, session_id, project_id, step, title, summary, kind, status, lifecycle, created_by
) VALUES ($1, $2, $3, $4, $5, $6, '', 'director', $7, $8, $9)`,
		tenantID, eventID, sessionID, projectID, step, "Live decision event "+eventID, status, lifecycle, createdBy); err != nil {
		t.Fatalf("prepare live event: %v", err)
	}
}

func worldlineLiveEventStatus(t *testing.T, db *sql.DB, tenantID string, eventID string) string {
	t.Helper()
	var status string
	if err := db.QueryRow(`SELECT status FROM worldline_events WHERE tenant_id = $1 AND event_id = $2`, tenantID, eventID).Scan(&status); err != nil {
		t.Fatalf("read live event status: %v", err)
	}
	return status
}
