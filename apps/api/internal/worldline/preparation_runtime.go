package worldline

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.temporal.io/sdk/client"
)

const (
	WorldlinePreparationWorkflowType = "worldline_preparation"
	WorldlinePreparationModuleKey    = "worldline_agent_prepare"
	worldlinePreparationWorkflow     = "WorldlinePrepareWorkflow"
)

type PreparationSourceRef struct {
	SourceKind string `json:"source_kind"`
	SourceID   string `json:"source_id"`
}

type PreparationAgentRef struct {
	SourceKind string `json:"source_kind"`
	SourceID   string `json:"source_id"`
}

type PreparationStarter interface {
	StartPreparation(context.Context, CreatePreparationInput) (PreparationRecord, error)
}

type PreparationAdmission struct {
	Record             PreparationRecord
	EventID            string
	TemporalWorkflowID string
	TraceID            string
}

type PreparationAdmissionStore interface {
	AdmitPreparation(context.Context, CreatePreparationInput, PreparationAdmission) (PreparationRecord, bool, error)
	CompensatePreparationStart(context.Context, CreatePreparationInput, PreparationRecord, string) error
}

type DisabledPreparationStarter struct{}

func NewDisabledPreparationStarter() *DisabledPreparationStarter {
	return &DisabledPreparationStarter{}
}

func (s *DisabledPreparationStarter) StartPreparation(context.Context, CreatePreparationInput) (PreparationRecord, error) {
	return PreparationRecord{}, &AppError{
		Code:    "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED",
		Message: "worldline preparation backend is not configured",
	}
}

type SQLPreparationAdmissionStore struct {
	db *sql.DB
}

func NewSQLPreparationAdmissionStore(db *sql.DB) *SQLPreparationAdmissionStore {
	return &SQLPreparationAdmissionStore{db: db}
}

func (s *SQLPreparationAdmissionStore) AdmitPreparation(
	ctx context.Context,
	input CreatePreparationInput,
	admission PreparationAdmission,
) (PreparationRecord, bool, error) {
	if s == nil || s.db == nil {
		return PreparationRecord{}, false, preparationAdmissionFailed()
	}
	payload, err := preparationQueuedEventPayload(input, admission)
	if err != nil {
		return PreparationRecord{}, false, err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PreparationRecord{}, false, preparationAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setPreparationTenantContext(ctx, tx, input); err != nil {
		return PreparationRecord{}, false, err
	}
	if err := lockPreparationProject(ctx, tx, input); err != nil {
		return PreparationRecord{}, false, err
	}
	if err := requirePreparationAnchor(ctx, tx, input); err != nil {
		return PreparationRecord{}, false, err
	}
	if existing, existingOptions, found, err := findPreparationReplay(ctx, tx, input); err != nil {
		return PreparationRecord{}, false, err
	} else if found {
		if !preparationReplayMatches(existing, existingOptions, input) {
			return PreparationRecord{}, false, &AppError{
				Code:    "IDEMPOTENCY_CONFLICT",
				Message: "request_id was already used for a different worldline preparation",
			}
		}
		if err := tx.Commit(); err != nil {
			return PreparationRecord{}, false, preparationAdmissionFailed()
		}
		return existing, true, nil
	}
	if err := persistPreparationAdmission(ctx, tx, input, admission, payload); err != nil {
		return PreparationRecord{}, false, err
	}
	if err := tx.Commit(); err != nil {
		return PreparationRecord{}, false, preparationAdmissionFailed()
	}
	return admission.Record, false, nil
}

func setPreparationTenantContext(ctx context.Context, tx *sql.Tx, input CreatePreparationInput) error {
	_, err := tx.ExecContext(
		ctx,
		"SELECT app_set_tenant_context($1::uuid, $2::uuid, false)",
		input.TenantID,
		input.ActorUserID,
	)
	if err != nil {
		return preparationAdmissionFailed()
	}
	return nil
}

func lockPreparationProject(ctx context.Context, tx *sql.Tx, input CreatePreparationInput) error {
	var projectID string
	err := tx.QueryRowContext(ctx, `SELECT project_id::text
FROM projects
WHERE tenant_id::text = $1 AND project_id::text = $2 AND status = 'active'
FOR UPDATE`, input.TenantID, input.ProjectID).Scan(&projectID)
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "NOT_FOUND", Message: "project not found"}
	}
	if err != nil {
		return preparationAdmissionFailed()
	}
	return nil
}

func requirePreparationAnchor(ctx context.Context, tx *sql.Tx, input CreatePreparationInput) error {
	if input.AnchorPathID == "" {
		return nil
	}
	var found int
	err := tx.QueryRowContext(ctx, `SELECT 1
FROM worldline_saved_paths
WHERE tenant_id::text = $1 AND project_id::text = $2 AND path_id::text = $3
LIMIT 1`, input.TenantID, input.ProjectID, input.AnchorPathID).Scan(&found)
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "NOT_FOUND", Message: "worldline preparation anchor path not found"}
	}
	if err != nil {
		return preparationAdmissionFailed()
	}
	return nil
}

func findPreparationReplay(
	ctx context.Context,
	tx *sql.Tx,
	input CreatePreparationInput,
) (PreparationRecord, map[string]any, bool, error) {
	var record PreparationRecord
	var optionsJSON string
	err := tx.QueryRowContext(ctx, `SELECT
  preparation.prepare_id::text,
  preparation.run_id::text,
  preparation.project_id::text,
  workflow_run.workflow_type,
  preparation.status,
  preparation.lifecycle,
  preparation.goal_summary,
  COALESCE(preparation.anchor_path_id::text, ''),
  COALESCE(preparation.created_by::text, ''),
  preparation.created_at::text,
  preparation.updated_at::text,
  COALESCE(queued_event.payload_jsonb->'options', '{}'::jsonb)::text
FROM worldline_preparations preparation
JOIN workflow_runs workflow_run
  ON workflow_run.tenant_id = preparation.tenant_id
 AND workflow_run.project_id = preparation.project_id
 AND workflow_run.run_id = preparation.run_id
JOIN workflow_events queued_event
  ON queued_event.tenant_id = workflow_run.tenant_id
 AND queued_event.run_id = workflow_run.run_id
 AND queued_event.workflow_type = workflow_run.workflow_type
 AND queued_event.event_type = 'workflow.queued'
WHERE preparation.tenant_id::text = $1
  AND preparation.project_id::text = $2
  AND workflow_run.workflow_type = 'worldline_preparation'
  AND queued_event.payload_jsonb->>'request_id' = $3
ORDER BY queued_event.created_at ASC
LIMIT 1`, input.TenantID, input.ProjectID, input.RequestID).Scan(
		&record.PrepareID,
		&record.RunID,
		&record.ProjectID,
		&record.WorkflowType,
		&record.Status,
		&record.Lifecycle,
		&record.GoalSummary,
		&record.AnchorPathID,
		&record.CreatedBy,
		&record.CreatedAt,
		&record.UpdatedAt,
		&optionsJSON,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return PreparationRecord{}, nil, false, nil
	}
	if err != nil {
		return PreparationRecord{}, nil, false, preparationAdmissionFailed()
	}
	options := map[string]any{}
	if err := json.Unmarshal([]byte(optionsJSON), &options); err != nil {
		return PreparationRecord{}, nil, false, preparationAdmissionFailed()
	}
	return record, options, true, nil
}

func preparationReplayMatches(record PreparationRecord, existingOptions map[string]any, input CreatePreparationInput) bool {
	existingJSON, existingErr := json.Marshal(existingOptions)
	inputJSON, inputErr := json.Marshal(input.Options)
	return record.GoalSummary == input.Goal &&
		record.AnchorPathID == input.AnchorPathID &&
		existingErr == nil && inputErr == nil && string(existingJSON) == string(inputJSON)
}

func persistPreparationAdmission(
	ctx context.Context,
	tx *sql.Tx,
	input CreatePreparationInput,
	admission PreparationAdmission,
	payload string,
) error {
	result, err := tx.ExecContext(ctx, `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  )
  VALUES (
    $1::uuid, $3::uuid, 'worldline_preparation', $2::uuid, 'queued', 0,
    'queued', $7::uuid, $8
  )
  RETURNING tenant_id, run_id, project_id
), preparation_insert AS (
  INSERT INTO worldline_preparations (
    tenant_id, prepare_id, project_id, run_id, status, lifecycle,
    goal_summary, anchor_path_id, created_by
  )
  SELECT
    workflow_insert.tenant_id, $4::uuid, workflow_insert.project_id,
    workflow_insert.run_id, 'queued', 'preparing', $5,
    NULLIF($6, '')::uuid, $7::uuid
  FROM workflow_insert
  RETURNING tenant_id, prepare_id, project_id, run_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type,
  sequence, payload_jsonb
)
SELECT
  preparation_insert.tenant_id, $9::uuid, preparation_insert.run_id,
  'worldline_preparation', preparation_insert.project_id, 'workflow.queued',
  1, $10::jsonb
FROM preparation_insert`,
		input.TenantID,
		input.ProjectID,
		admission.Record.RunID,
		admission.Record.PrepareID,
		input.Goal,
		input.AnchorPathID,
		input.ActorUserID,
		admission.TemporalWorkflowID,
		admission.EventID,
		payload,
	)
	if err != nil {
		return preparationAdmissionFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil || affected != 1 {
		return preparationAdmissionFailed()
	}
	return nil
}

func (s *SQLPreparationAdmissionStore) CompensatePreparationStart(
	ctx context.Context,
	input CreatePreparationInput,
	record PreparationRecord,
	eventID string,
) error {
	if s == nil || s.db == nil {
		return preparationCompensationFailed()
	}
	payload, err := preparationStartFailurePayload(input, record)
	if err != nil {
		return err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return preparationCompensationFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setPreparationTenantContext(ctx, tx, input); err != nil {
		return preparationCompensationFailed()
	}
	result, err := tx.ExecContext(ctx, `WITH failed_run AS (
  UPDATE workflow_runs
  SET status = 'failed', progress = 100, message = 'failed to start',
      error_code = 'WORKFLOW_FAILED',
      error_message = 'failed to start worldline preparation workflow',
      updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND run_id::text = $3
    AND workflow_type = 'worldline_preparation' AND status = 'queued'
  RETURNING tenant_id, run_id, project_id
), failed_preparation AS (
  UPDATE worldline_preparations
  SET status = 'failed', lifecycle = 'cancelled', updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND prepare_id::text = $4
    AND run_id::text = $3 AND status = 'queued'
    AND EXISTS (SELECT 1 FROM failed_run)
  RETURNING tenant_id, run_id, project_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type,
  sequence, payload_jsonb
)
SELECT tenant_id, $5::uuid, run_id, 'worldline_preparation', project_id,
       'workflow.start_failed', 2, $6::jsonb
FROM failed_preparation`,
		input.TenantID,
		input.ProjectID,
		record.RunID,
		record.PrepareID,
		eventID,
		payload,
	)
	if err != nil {
		return preparationCompensationFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil || affected != 1 {
		return preparationCompensationFailed()
	}
	if err := tx.Commit(); err != nil {
		return preparationCompensationFailed()
	}
	return nil
}

type SQLPreparationStarterConfig struct {
	Store     PreparationAdmissionStore
	NewID     func() string
	Client    TemporalWorkflowClient
	TaskQueue string
}

type SQLPreparationStarter struct {
	store     PreparationAdmissionStore
	newID     func() string
	client    TemporalWorkflowClient
	taskQueue string
}

func NewSQLPreparationStarter(config SQLPreparationStarterConfig) *SQLPreparationStarter {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLPreparationStarter{
		store:     config.Store,
		newID:     newID,
		client:    config.Client,
		taskQueue: normalizeWorldlineTaskQueue(config.TaskQueue),
	}
}

func (s *SQLPreparationStarter) StartPreparation(
	ctx context.Context,
	input CreatePreparationInput,
) (PreparationRecord, error) {
	input = normalizePreparationInput(input)
	if err := validatePreparationInput(input); err != nil {
		return PreparationRecord{}, err
	}
	if s == nil || s.store == nil || s.client == nil {
		return PreparationRecord{}, &AppError{
			Code:    "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED",
			Message: "worldline preparation backend is not configured",
		}
	}
	if _, err := json.Marshal(input.Options); err != nil {
		return PreparationRecord{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "worldline preparation options must be JSON serializable",
		}
	}
	admission := s.newPreparationAdmission(input)
	record, replayed, err := s.store.AdmitPreparation(ctx, input, admission)
	if err != nil {
		return PreparationRecord{}, sanitizePreparationAdmissionError(err)
	}
	if replayed {
		return record, nil
	}
	if err := s.startTemporalWorkflow(ctx, input, record, admission); err != nil {
		return PreparationRecord{}, err
	}
	return record, nil
}

func (s *SQLPreparationStarter) newPreparationAdmission(input CreatePreparationInput) PreparationAdmission {
	runID := s.newID()
	prepareID := s.newID()
	return PreparationAdmission{
		Record: PreparationRecord{
			PrepareID:    prepareID,
			RunID:        runID,
			ProjectID:    input.ProjectID,
			WorkflowType: WorldlinePreparationWorkflowType,
			Status:       "queued",
			Lifecycle:    "preparing",
			GoalSummary:  input.Goal,
			AnchorPathID: input.AnchorPathID,
			CreatedBy:    input.ActorUserID,
		},
		EventID:            s.newID(),
		TemporalWorkflowID: "worldline_preparation_" + runID,
		TraceID:            "trace_" + runID,
	}
}

func (s *SQLPreparationStarter) startTemporalWorkflow(
	ctx context.Context,
	input CreatePreparationInput,
	record PreparationRecord,
	admission PreparationAdmission,
) error {
	_, err := s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:        admission.TemporalWorkflowID,
		TaskQueue: s.taskQueue,
	}, worldlinePreparationWorkflow, preparationTemporalPayload(input, record, admission.TraceID))
	if err == nil {
		return nil
	}
	compensationContext, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
	defer cancel()
	if compensationErr := s.store.CompensatePreparationStart(
		compensationContext,
		input,
		record,
		s.newID(),
	); compensationErr != nil {
		return preparationCompensationFailed()
	}
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to start worldline preparation workflow"}
}

func normalizePreparationInput(input CreatePreparationInput) CreatePreparationInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Goal = strings.TrimSpace(input.Goal)
	input.AnchorPathID = strings.TrimSpace(input.AnchorPathID)
	input.AgentRefs = normalizePreparationAgentRefs(input.AgentRefs)
	input.SourceRefs = normalizePreparationSourceRefs(input.SourceRefs)
	input.Options = preparationOptions(input.Options, input.AgentRefs, input.SourceRefs)
	return input
}

func validatePreparationInput(input CreatePreparationInput) error {
	if input.TenantID == "" || input.ProjectID == "" || input.ActorUserID == "" ||
		input.RequestID == "" || input.Goal == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, actor_user_id, request_id, and goal are required",
		}
	}
	if len(input.AgentRefs) == 0 {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "worldline preparation requires at least one agent_ref",
		}
	}
	for _, ref := range input.AgentRefs {
		if ref.SourceKind != "asset" && ref.SourceKind != "entity" {
			return &AppError{Code: "VALIDATION_FAILED", Message: "worldline preparation agent_ref kind is invalid"}
		}
		if _, err := uuid.Parse(ref.SourceID); err != nil {
			return &AppError{Code: "VALIDATION_FAILED", Message: "worldline preparation agent_ref id is invalid"}
		}
	}
	for _, ref := range input.SourceRefs {
		switch ref.SourceKind {
		case "asset", "entity", "saved_path", "worldline_event":
		default:
			return &AppError{Code: "VALIDATION_FAILED", Message: "worldline preparation source_ref kind is invalid"}
		}
		if _, err := uuid.Parse(ref.SourceID); err != nil {
			return &AppError{Code: "VALIDATION_FAILED", Message: "worldline preparation source_ref id is invalid"}
		}
	}
	if input.AnchorPathID != "" {
		if _, err := uuid.Parse(input.AnchorPathID); err != nil {
			return &AppError{Code: "VALIDATION_FAILED", Message: "worldline preparation anchor_path_id is invalid"}
		}
	}
	return nil
}

func normalizePreparationAgentRefs(refs []PreparationAgentRef) []PreparationAgentRef {
	result := make([]PreparationAgentRef, 0, len(refs))
	seen := map[string]struct{}{}
	for _, ref := range refs {
		normalized := PreparationAgentRef{
			SourceKind: normalizePreparationSourceKind(ref.SourceKind),
			SourceID:   strings.TrimSpace(ref.SourceID),
		}
		key := normalized.SourceKind + ":" + normalized.SourceID
		if normalized.SourceKind == "" || normalized.SourceID == "" {
			continue
		}
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		result = append(result, normalized)
	}
	return result
}

func normalizePreparationSourceRefs(refs []PreparationSourceRef) []PreparationSourceRef {
	result := make([]PreparationSourceRef, 0, len(refs))
	seen := map[string]struct{}{}
	for _, ref := range refs {
		normalized := PreparationSourceRef{
			SourceKind: normalizePreparationSourceKind(ref.SourceKind),
			SourceID:   strings.TrimSpace(ref.SourceID),
		}
		key := normalized.SourceKind + ":" + normalized.SourceID
		if normalized.SourceKind == "" || normalized.SourceID == "" {
			continue
		}
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		result = append(result, normalized)
	}
	return result
}

func normalizePreparationSourceKind(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "event" {
		return "worldline_event"
	}
	return value
}

func preparationOptions(
	options map[string]any,
	agentRefs []PreparationAgentRef,
	sourceRefs []PreparationSourceRef,
) map[string]any {
	clean := sanitizePreparationOptions(options)
	clean["agent_refs"] = preparationAgentRefPayload(agentRefs)
	if len(sourceRefs) > 0 {
		clean["source_refs"] = preparationSourceRefPayload(sourceRefs)
	} else {
		delete(clean, "source_refs")
	}
	return clean
}

func preparationAgentRefPayload(refs []PreparationAgentRef) []map[string]string {
	result := make([]map[string]string, 0, len(refs))
	for _, ref := range refs {
		result = append(result, map[string]string{"source_kind": ref.SourceKind, "source_id": ref.SourceID})
	}
	return result
}

func preparationSourceRefPayload(refs []PreparationSourceRef) []map[string]string {
	result := make([]map[string]string, 0, len(refs))
	for _, ref := range refs {
		result = append(result, map[string]string{"source_kind": ref.SourceKind, "source_id": ref.SourceID})
	}
	return result
}

func sanitizePreparationOptions(options map[string]any) map[string]any {
	clean := map[string]any{}
	for key, value := range sanitizeWorldlineOptions(options) {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		switch normalizedKey {
		case "agent_refs", "selected_agent_refs", "source_refs", "selected_source_refs",
			"branch", "branch_id", "branch_ids", "branches", "comparison", "comparisons", "worlds":
			continue
		default:
			clean[key] = sanitizePreparationOptionValue(value)
		}
	}
	return clean
}

func sanitizePreparationOptionValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizePreparationOptions(typed)
	case []any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, sanitizePreparationOptionValue(item))
		}
		return items
	default:
		return value
	}
}

func preparationQueuedEventPayload(input CreatePreparationInput, admission PreparationAdmission) (string, error) {
	payload, err := json.Marshal(map[string]any{
		"status":           "queued",
		"workflow_type":    WorldlinePreparationWorkflowType,
		"request_id":       input.RequestID,
		"trace_id":         admission.TraceID,
		"prepare_id":       admission.Record.PrepareID,
		"anchor_path_id":   input.AnchorPathID,
		"agent_ref_count":  len(input.AgentRefs),
		"source_ref_count": len(input.SourceRefs),
		"options":          input.Options,
	})
	if err != nil {
		return "", &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "worldline preparation admission payload must be JSON serializable",
		}
	}
	return string(payload), nil
}

func preparationStartFailurePayload(input CreatePreparationInput, record PreparationRecord) (string, error) {
	payload, err := json.Marshal(map[string]any{
		"status":        "failed",
		"workflow_type": WorldlinePreparationWorkflowType,
		"request_id":    input.RequestID,
		"prepare_id":    record.PrepareID,
		"error_code":    "WORKFLOW_FAILED",
	})
	if err != nil {
		return "", preparationCompensationFailed()
	}
	return string(payload), nil
}

func preparationTemporalPayload(
	input CreatePreparationInput,
	record PreparationRecord,
	traceID string,
) map[string]any {
	return map[string]any{
		"context": map[string]any{
			"tenant_id":     input.TenantID,
			"project_id":    record.ProjectID,
			"run_id":        record.RunID,
			"workflow_type": WorldlinePreparationWorkflowType,
			"actor_user_id": input.ActorUserID,
			"module_key":    WorldlinePreparationModuleKey,
			"trace_id":      traceID,
			"permissions":   map[string][]string{WorldlinePreparationModuleKey: {"run"}},
		},
		"prepare_id": record.PrepareID,
		"request_id": input.RequestID,
	}
}

func sanitizePreparationAdmissionError(err error) error {
	var appErr *AppError
	if !errors.As(err, &appErr) {
		return preparationAdmissionFailed()
	}
	switch appErr.Code {
	case "VALIDATION_FAILED", "IDEMPOTENCY_CONFLICT", "NOT_FOUND":
		return &AppError{Code: appErr.Code, Message: appErr.Message}
	default:
		return preparationAdmissionFailed()
	}
}

func preparationAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "worldline preparation admission failed"}
}

func preparationCompensationFailed() *AppError {
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to record worldline preparation start failure"}
}
