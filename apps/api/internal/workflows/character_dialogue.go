package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	CharacterDialogueWorkflowType = "character_dialogue"
	CharacterDialogueModuleKey    = "character_dialogue"
	CharacterDialogueWorkflowName = "CharacterDialogueWorkflow"
	CharacterDialogueTaskQueue    = "character-interactive"
)

type StartCharacterDialogueInput struct {
	TenantID      string
	ProjectID     string
	InteractionID string
	UserTurnID    string
	ActorUserID   string
	RequestID     string
}

type CharacterDialogueRun struct {
	RunID         string `json:"run_id"`
	TraceID       string `json:"trace_id"`
	ProjectID     string `json:"project_id"`
	InteractionID string `json:"interaction_id"`
	WorkflowType  string `json:"workflow_type"`
	Status        string `json:"status"`
}

type CharacterDialogueStarter interface {
	StartCharacterDialogue(context.Context, StartCharacterDialogueInput) (CharacterDialogueRun, error)
}

type CharacterDialogueAdmissionStore interface {
	AdmitCharacterDialogue(context.Context, StartCharacterDialogueInput, CharacterDialogueRun, string) (CharacterDialogueRun, bool, error)
	CompensateCharacterDialogueStart(context.Context, StartCharacterDialogueInput, CharacterDialogueRun) error
}

type DisabledCharacterDialogueStarter struct{}

func NewDisabledCharacterDialogueStarter() *DisabledCharacterDialogueStarter {
	return &DisabledCharacterDialogueStarter{}
}

func (s *DisabledCharacterDialogueStarter) StartCharacterDialogue(context.Context, StartCharacterDialogueInput) (CharacterDialogueRun, error) {
	return CharacterDialogueRun{}, &AppError{Code: "CHARACTER_DIALOGUE_BACKEND_UNCONFIGURED", Message: "character dialogue backend is not configured"}
}

type TemporalCharacterDialogueConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore CharacterDialogueAdmissionStore
}

type TemporalCharacterDialogueStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore CharacterDialogueAdmissionStore
}

func NewTemporalCharacterDialogueStarter(config TemporalCharacterDialogueConfig) *TemporalCharacterDialogueStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = CharacterDialogueTaskQueue
	}
	return &TemporalCharacterDialogueStarter{client: config.Client, taskQueue: taskQueue, admissionStore: config.AdmissionStore}
}

func (s *TemporalCharacterDialogueStarter) StartCharacterDialogue(ctx context.Context, input StartCharacterDialogueInput) (CharacterDialogueRun, error) {
	input = normalizeCharacterDialogueInput(input)
	if input.TenantID == "" || input.ProjectID == "" || input.InteractionID == "" || input.UserTurnID == "" || input.ActorUserID == "" {
		return CharacterDialogueRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, interaction_id, user_turn_id, and actor_user_id are required"}
	}
	if s.client == nil || s.admissionStore == nil {
		return CharacterDialogueRun{}, &AppError{Code: "CHARACTER_DIALOGUE_BACKEND_UNCONFIGURED", Message: "character dialogue backend is not configured"}
	}
	runID, err := newRunID()
	if err != nil {
		return CharacterDialogueRun{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to allocate character dialogue run id"}
	}
	run := CharacterDialogueRun{
		RunID: runID, TraceID: traceIDForRun(runID), ProjectID: input.ProjectID,
		InteractionID: input.InteractionID, WorkflowType: CharacterDialogueWorkflowType, Status: "queued",
	}
	temporalWorkflowID := "character_dialogue_" + runID
	admitted, replayed, err := s.admissionStore.AdmitCharacterDialogue(ctx, input, run, temporalWorkflowID)
	if err != nil {
		return CharacterDialogueRun{}, err
	}
	if replayed {
		return admitted, nil
	}
	payload := characterDialogueTemporalPayload(input, admitted)
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID: temporalWorkflowID, TaskQueue: s.taskQueue,
		WorkflowExecutionTimeout: time.Hour, WorkflowRunTimeout: time.Hour,
	}, CharacterDialogueWorkflowName, payload)
	if err != nil {
		compensationCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		if compensateErr := s.admissionStore.CompensateCharacterDialogueStart(compensationCtx, input, admitted); compensateErr != nil {
			return CharacterDialogueRun{}, compensateErr
		}
		return CharacterDialogueRun{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to start character dialogue workflow"}
	}
	return admitted, nil
}

func characterDialogueTemporalPayload(input StartCharacterDialogueInput, run CharacterDialogueRun) map[string]any {
	return map[string]any{
		"context": map[string]any{
			"tenant_id": input.TenantID, "project_id": input.ProjectID,
			"run_id": run.RunID, "workflow_type": CharacterDialogueWorkflowType,
			"actor_user_id": input.ActorUserID, "module_key": CharacterDialogueModuleKey,
			"trace_id":    run.TraceID,
			"permissions": map[string][]string{CharacterDialogueModuleKey: {"run"}},
		},
		"interaction_id": input.InteractionID,
		"session_id":     input.InteractionID,
		"user_turn_id":   input.UserTurnID,
		"request_id":     input.RequestID,
	}
}

func normalizeCharacterDialogueInput(input StartCharacterDialogueInput) StartCharacterDialogueInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.InteractionID = strings.TrimSpace(input.InteractionID)
	input.UserTurnID = strings.TrimSpace(input.UserTurnID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	return input
}

type SQLCharacterDialogueAdmissionStore struct {
	db *sql.DB
}

func NewSQLCharacterDialogueAdmissionStore(db *sql.DB) *SQLCharacterDialogueAdmissionStore {
	return &SQLCharacterDialogueAdmissionStore{db: db}
}

func (s *SQLCharacterDialogueAdmissionStore) AdmitCharacterDialogue(
	ctx context.Context,
	input StartCharacterDialogueInput,
	proposed CharacterDialogueRun,
	temporalWorkflowID string,
) (CharacterDialogueRun, bool, error) {
	if s.db == nil {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	eventID, err := newRunID()
	if err != nil {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	if err := lockCharacterInteraction(ctx, tx, input); err != nil {
		return CharacterDialogueRun{}, false, err
	}
	if existing, found, err := findCharacterDialogueReplay(ctx, tx, input); err != nil {
		return CharacterDialogueRun{}, false, err
	} else if found {
		if err := tx.Commit(); err != nil {
			return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
		}
		return existing, true, nil
	}
	if active, err := hasActiveCharacterDialogue(ctx, tx, input); err != nil {
		return CharacterDialogueRun{}, false, err
	} else if active {
		return CharacterDialogueRun{}, false, &AppError{Code: "CHARACTER_TURN_ACTIVE", Message: "character interaction already has an active dialogue turn"}
	}
	eventPayload, err := json.Marshal(map[string]any{
		"status": "queued", "workflow_type": CharacterDialogueWorkflowType,
		"request_id": input.RequestID, "trace_id": proposed.TraceID,
		"interaction_id": input.InteractionID, "session_id": input.InteractionID,
		"user_turn_id": input.UserTurnID, "module_key": CharacterDialogueModuleKey,
		"world_scope": "current_world",
	})
	if err != nil {
		return CharacterDialogueRun{}, false, &AppError{Code: "VALIDATION_FAILED", Message: "character dialogue admission payload must be JSON serializable"}
	}
	result, err := tx.ExecContext(ctx, `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  ) VALUES ($1::uuid, $4::uuid, 'character_dialogue', $2::uuid, 'queued', 0,
            'queued', $3::uuid, $7)
  RETURNING run_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT $1::uuid, $5::uuid, workflow_insert.run_id, 'character_dialogue', $2::uuid,
       'workflow.queued', 1, $6::jsonb FROM workflow_insert`,
		input.TenantID, input.ProjectID, input.ActorUserID, proposed.RunID,
		eventID, string(eventPayload), temporalWorkflowID,
	)
	if err != nil {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	if err := tx.Commit(); err != nil {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	return proposed, false, nil
}

func lockCharacterInteraction(ctx context.Context, tx *sql.Tx, input StartCharacterDialogueInput) error {
	var status string
	err := tx.QueryRowContext(ctx, `SELECT status FROM character_interaction_sessions
WHERE tenant_id::text = $1 AND project_id::text = $2 AND interaction_id::text = $3
FOR UPDATE`, input.TenantID, input.ProjectID, input.InteractionID).Scan(&status)
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "NOT_FOUND", Message: "character interaction was not found"}
	}
	if err != nil {
		return characterDialogueAdmissionFailed()
	}
	if status != "active" && status != "saved" {
		return &AppError{Code: "CHARACTER_INTERACTION_NOT_ACTIVE", Message: "character interaction is not active"}
	}
	var actorType string
	err = tx.QueryRowContext(ctx, `SELECT actor_type FROM character_interaction_turns
WHERE tenant_id::text = $1 AND project_id::text = $2 AND interaction_id::text = $3
  AND turn_id::text = $4`, input.TenantID, input.ProjectID, input.InteractionID, input.UserTurnID).Scan(&actorType)
	if errors.Is(err, sql.ErrNoRows) || actorType != "user" {
		return &AppError{Code: "CHARACTER_USER_TURN_NOT_FOUND", Message: "character dialogue user turn was not found"}
	}
	if err != nil {
		return characterDialogueAdmissionFailed()
	}
	return nil
}

func findCharacterDialogueReplay(ctx context.Context, tx *sql.Tx, input StartCharacterDialogueInput) (CharacterDialogueRun, bool, error) {
	if input.RequestID == "" {
		return CharacterDialogueRun{}, false, nil
	}
	var run CharacterDialogueRun
	err := tx.QueryRowContext(ctx, `SELECT workflow.run_id::text,
  queued.payload_jsonb->>'trace_id', workflow.project_id::text,
  queued.payload_jsonb->>'interaction_id', workflow.workflow_type, workflow.status
FROM workflow_runs AS workflow
JOIN workflow_events AS queued ON queued.tenant_id = workflow.tenant_id
 AND queued.run_id = workflow.run_id AND queued.event_type = 'workflow.queued'
WHERE workflow.tenant_id::text = $1 AND workflow.project_id::text = $2
  AND workflow.workflow_type = 'character_dialogue'
  AND queued.payload_jsonb->>'interaction_id' = $3
  AND queued.payload_jsonb->>'request_id' = $4
ORDER BY queued.created_at LIMIT 1`, input.TenantID, input.ProjectID, input.InteractionID, input.RequestID).Scan(
		&run.RunID, &run.TraceID, &run.ProjectID, &run.InteractionID, &run.WorkflowType, &run.Status,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return CharacterDialogueRun{}, false, nil
	}
	if err != nil {
		return CharacterDialogueRun{}, false, characterDialogueAdmissionFailed()
	}
	return run, true, nil
}

func hasActiveCharacterDialogue(ctx context.Context, tx *sql.Tx, input StartCharacterDialogueInput) (bool, error) {
	var active bool
	err := tx.QueryRowContext(ctx, `SELECT EXISTS (
  SELECT 1 FROM workflow_runs AS workflow
  JOIN workflow_events AS queued ON queued.tenant_id = workflow.tenant_id
    AND queued.run_id = workflow.run_id AND queued.event_type = 'workflow.queued'
  WHERE workflow.tenant_id::text = $1 AND workflow.project_id::text = $2
    AND workflow.workflow_type = 'character_dialogue'
    AND workflow.status IN ('queued', 'running')
    AND queued.payload_jsonb->>'interaction_id' = $3
)`, input.TenantID, input.ProjectID, input.InteractionID).Scan(&active)
	if err != nil {
		return false, characterDialogueAdmissionFailed()
	}
	return active, nil
}

func (s *SQLCharacterDialogueAdmissionStore) CompensateCharacterDialogueStart(ctx context.Context, input StartCharacterDialogueInput, run CharacterDialogueRun) error {
	if s.db == nil {
		return characterDialogueAdmissionFailed()
	}
	eventID, err := newRunID()
	if err != nil {
		return characterDialogueAdmissionFailed()
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return characterDialogueAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return characterDialogueAdmissionFailed()
	}
	payload, _ := json.Marshal(map[string]any{
		"status": "failed", "workflow_type": CharacterDialogueWorkflowType,
		"interaction_id": input.InteractionID, "session_id": input.InteractionID,
		"trace_id": run.TraceID, "error_code": "WORKFLOW_START_FAILED",
		"message": "character dialogue workflow failed to start",
	})
	result, err := tx.ExecContext(ctx, `WITH failed AS (
  UPDATE workflow_runs SET status = 'failed', progress = 0,
    message = 'character dialogue workflow failed to start',
    error_code = 'WORKFLOW_START_FAILED', error_message = 'character dialogue workflow failed to start',
    updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND run_id::text = $3
    AND workflow_type = 'character_dialogue' AND status = 'queued'
  RETURNING tenant_id, run_id, project_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT tenant_id, $4::uuid, run_id, 'character_dialogue', project_id,
  'workflow.start_failed', 2, $5::jsonb FROM failed`,
		input.TenantID, input.ProjectID, run.RunID, eventID, string(payload),
	)
	if err != nil {
		return characterDialogueAdmissionFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return characterDialogueAdmissionFailed()
	}
	if err := tx.Commit(); err != nil {
		return characterDialogueAdmissionFailed()
	}
	return nil
}

func characterDialogueAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "character dialogue admission failed"}
}
