package worldline

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
	"go.temporal.io/sdk/client"
)

type livePreparationTemporalClient struct {
	calls    int
	options  client.StartWorkflowOptions
	workflow any
	payload  map[string]any
}

func (c *livePreparationTemporalClient) ExecuteWorkflow(
	_ context.Context,
	options client.StartWorkflowOptions,
	workflow any,
	args ...any,
) (client.WorkflowRun, error) {
	c.calls++
	c.options = options
	c.workflow = workflow
	if len(args) == 1 {
		c.payload, _ = args[0].(map[string]any)
	}
	return nil, nil
}

func TestWorldlinePreparationAdmissionAndReadUseAppRoleTenantContext(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_WORLDLINE_PREPARATION_LIVE_DATABASE_URL"))
	if adminURL == "" {
		t.Skip("set MIROFISH_WORLDLINE_PREPARATION_LIVE_DATABASE_URL to run the live Worldline preparation test")
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

	appConfig, err := pgx.ParseConfig(adminURL)
	if err != nil {
		t.Fatalf("parse admin database URL: %v", err)
	}
	appConfig.User = worldlineLiveAppRole
	appConfig.Password = worldlineLiveAppPassword
	appDB := stdlib.OpenDB(*appConfig)
	defer appDB.Close()
	queryer := NewSQLDBQueryer(appDB)
	reader := NewSQLPreparationStore(SQLPreparationStoreConfig{Queryer: queryer, Execer: queryer})
	temporalClient := &livePreparationTemporalClient{}
	starter := NewSQLPreparationStarter(SQLPreparationStarterConfig{
		Store: NewSQLPreparationAdmissionStore(appDB), Client: temporalClient,
	})
	agentEntityID := newUUID()

	input := CreatePreparationInput{
		TenantID: tenantID, ProjectID: projectID, ActorUserID: userID,
		RequestID: "req-worldline-prepare-live", Goal: "Prepare the council for a current-world decision",
		AgentRefs: []PreparationAgentRef{{SourceKind: "entity", SourceID: agentEntityID}},
		Options: map[string]any{
			"pace": "steady", "prompt": "must not persist", "branch_id": "must not persist",
		},
	}
	record, err := starter.StartPreparation(context.Background(), input)
	if err != nil {
		t.Fatalf("create preparation through app role: %v", err)
	}
	if record.Status != "queued" || record.Lifecycle != "preparing" || record.PrepareID == "" || record.RunID == "" {
		t.Fatalf("unexpected preparation admission: %#v", record)
	}
	if temporalClient.calls != 1 || temporalClient.workflow != worldlinePreparationWorkflow ||
		temporalClient.options.ID != "worldline_preparation_"+record.RunID || temporalClient.payload["prepare_id"] != record.PrepareID {
		t.Fatalf("unexpected preparation Temporal handoff: %#v", temporalClient)
	}

	replayed, err := starter.StartPreparation(context.Background(), input)
	if err != nil {
		t.Fatalf("replay preparation admission: %v", err)
	}
	if replayed.RunID != record.RunID || replayed.PrepareID != record.PrepareID || temporalClient.calls != 1 {
		t.Fatalf("preparation replay duplicated admission or Temporal start: first=%#v replay=%#v calls=%d", record, replayed, temporalClient.calls)
	}

	var temporalWorkflowID string
	var persistedOptions string
	if err := adminDB.QueryRow(`SELECT workflow_run.temporal_workflow_id,
       queued_event.payload_jsonb->'options'::text
FROM workflow_runs workflow_run
JOIN workflow_events queued_event
  ON queued_event.tenant_id = workflow_run.tenant_id
 AND queued_event.run_id = workflow_run.run_id
 AND queued_event.workflow_type = workflow_run.workflow_type
WHERE workflow_run.tenant_id = $1 AND workflow_run.project_id = $2 AND workflow_run.run_id = $3
  AND workflow_run.workflow_type = 'worldline_preparation'
  AND queued_event.event_type = 'workflow.queued'`, tenantID, projectID, record.RunID).Scan(&temporalWorkflowID, &persistedOptions); err != nil {
		t.Fatalf("read persisted preparation handoff: %v", err)
	}
	if temporalWorkflowID != "worldline_preparation_"+record.RunID ||
		!strings.Contains(persistedOptions, agentEntityID) || !strings.Contains(persistedOptions, `"pace": "steady"`) ||
		strings.Contains(persistedOptions, "prompt") || strings.Contains(persistedOptions, "branch_id") {
		t.Fatalf("unexpected persisted preparation options: temporal=%q options=%s", temporalWorkflowID, persistedOptions)
	}

	persisted, err := reader.GetPreparation(context.Background(), GetPreparationInput{
		TenantID: tenantID, PrepareID: record.PrepareID,
	})
	if err != nil {
		t.Fatalf("read preparation through app role: %v", err)
	}
	if persisted.PrepareID != record.PrepareID || persisted.RunID != record.RunID || persisted.ProjectID != projectID {
		t.Fatalf("unexpected persisted preparation: %#v", persisted)
	}
	agents, err := reader.ListPreparedAgents(context.Background(), ListPreparedAgentsInput{
		TenantID: tenantID, PrepareID: record.PrepareID,
	})
	if err != nil || len(agents) != 0 {
		t.Fatalf("expected an admitted preparation without fabricated agents, agents=%#v err=%v", agents, err)
	}

	_, err = reader.GetPreparation(context.Background(), GetPreparationInput{
		TenantID: newUUID(), PrepareID: record.PrepareID,
	})
	if ErrorCode(err) != "NOT_FOUND" {
		t.Fatalf("cross-tenant preparation read must be hidden, code=%s err=%v", ErrorCode(err), err)
	}
}
