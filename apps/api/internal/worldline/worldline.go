package worldline

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type ListSavedPathsInput struct {
	TenantID  string
	ProjectID string
}

type SavedPathRecord struct {
	PathID            string   `json:"path_id"`
	SessionID         string   `json:"session_id"`
	ProjectID         string   `json:"project_id"`
	Title             string   `json:"title"`
	Summary           string   `json:"summary"`
	Lifecycle         string   `json:"lifecycle"`
	SelectedEventIDs  []string `json:"selected_event_ids"`
	WriterInstruction string   `json:"writer_instruction"`
	CreatedAt         string   `json:"created_at"`
	UpdatedAt         string   `json:"updated_at"`
}

type SavedPathReader interface {
	ListSavedPaths(context.Context, ListSavedPathsInput) ([]SavedPathRecord, error)
}

type CreateSavedPathInput struct {
	TenantID          string
	SessionID         string
	ActorUserID       string
	RequestID         string
	Title             string
	Summary           string
	SelectedEventIDs  []string
	WriterInstruction string
}

type SavedPathStore interface {
	CreateSavedPath(context.Context, CreateSavedPathInput) (SavedPathRecord, error)
}

type StartSessionInput struct {
	TenantID     string
	ProjectID    string
	ActorUserID  string
	RequestID    string
	Goal         string
	AnchorPathID string
	Options      map[string]any
}

type SessionRun struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type SessionStarter interface {
	StartSession(context.Context, StartSessionInput) (SessionRun, error)
}

type StartStepInput struct {
	TenantID    string
	SessionID   string
	ActorUserID string
	RequestID   string
	Mode        string
	Options     map[string]any
}

type StepRun struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	SessionID    string `json:"session_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type StepStarter interface {
	StartStep(context.Context, StartStepInput) (StepRun, error)
}

type ListSessionsInput struct {
	TenantID  string
	ProjectID string
}

type GetSessionInput struct {
	TenantID  string
	SessionID string
}

type SessionRecord struct {
	SessionID    string `json:"session_id"`
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	Status       string `json:"status"`
	Lifecycle    string `json:"lifecycle"`
	GoalSummary  string `json:"goal_summary"`
	AnchorPathID string `json:"anchor_path_id"`
	CreatedBy    string `json:"created_by"`
	CreatedAt    string `json:"created_at"`
	UpdatedAt    string `json:"updated_at"`
}

type SessionReader interface {
	ListSessions(context.Context, ListSessionsInput) ([]SessionRecord, error)
	GetSession(context.Context, GetSessionInput) (SessionRecord, error)
}

type ListTimelineInput struct {
	TenantID  string
	SessionID string
}

type TimelineEventRecord struct {
	EventID   string `json:"event_id"`
	SessionID string `json:"session_id"`
	RunID     string `json:"run_id"`
	ProjectID string `json:"project_id"`
	EventType string `json:"event_type"`
	Sequence  int    `json:"sequence"`
	Status    string `json:"status"`
	Lifecycle string `json:"lifecycle"`
	Title     string `json:"title"`
	Summary   string `json:"summary"`
	Kind      string `json:"kind"`
	CreatedAt string `json:"created_at"`
}

type TimelineReader interface {
	ListTimeline(context.Context, ListTimelineInput) ([]TimelineEventRecord, error)
}

type ListEventsInput struct {
	TenantID  string
	SessionID string
	Status    string
}

type EventRecord struct {
	EventID          string         `json:"event_id"`
	SessionID        string         `json:"session_id"`
	ProjectID        string         `json:"project_id"`
	Step             int            `json:"step"`
	Title            string         `json:"title"`
	Summary          string         `json:"summary"`
	Kind             string         `json:"kind"`
	Status           string         `json:"status"`
	Lifecycle        string         `json:"lifecycle"`
	Confidence       string         `json:"confidence"`
	InvolvedAgentIDs []string       `json:"involved_agent_ids"`
	StateChanges     map[string]any `json:"state_changes"`
	SourceRunID      string         `json:"source_run_id"`
	CreatedBy        string         `json:"created_by"`
	CreatedAt        string         `json:"created_at"`
	UpdatedAt        string         `json:"updated_at"`
}

type EventReader interface {
	ListEvents(context.Context, ListEventsInput) ([]EventRecord, error)
}

type AdoptEventInput struct {
	TenantID    string
	EventID     string
	ActorUserID string
	RequestID   string
	Note        string
}

type EventAdoptionStore interface {
	AdoptEvent(context.Context, AdoptEventInput) (EventRecord, error)
}

type UpdateEventInput struct {
	TenantID    string
	EventID     string
	ActorUserID string
	RequestID   string
	Title       string
	Summary     string
	Kind        string
}

type EventMutationStore interface {
	UpdateEvent(context.Context, UpdateEventInput) (EventRecord, error)
}

type InjectVariableInput struct {
	TenantID    string
	SessionID   string
	ActorUserID string
	RequestID   string
	Name        string
	Description string
	ImpactAxis  string
	Locked      bool
	Source      string
}

type VariableRecord struct {
	VariableID  string `json:"variable_id"`
	SessionID   string `json:"session_id"`
	ProjectID   string `json:"project_id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	ImpactAxis  string `json:"impact_axis"`
	Locked      bool   `json:"locked"`
	Source      string `json:"source"`
	CreatedBy   string `json:"created_by"`
	CreatedAt   string `json:"created_at"`
	UpdatedAt   string `json:"updated_at"`
}

type VariableStore interface {
	InjectVariable(context.Context, InjectVariableInput) (VariableRecord, error)
}

type CreatePreparationInput struct {
	TenantID     string
	ProjectID    string
	ActorUserID  string
	RequestID    string
	Goal         string
	AnchorPathID string
	Options      map[string]any
}

type GetPreparationInput struct {
	TenantID  string
	PrepareID string
}

type ListPreparedAgentsInput struct {
	TenantID  string
	PrepareID string
}

type PreparationRecord struct {
	PrepareID    string `json:"prepare_id"`
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
	Lifecycle    string `json:"lifecycle"`
	GoalSummary  string `json:"goal_summary"`
	AnchorPathID string `json:"anchor_path_id"`
	CreatedBy    string `json:"created_by"`
	CreatedAt    string `json:"created_at"`
	UpdatedAt    string `json:"updated_at"`
}

type PreparedAgentRecord struct {
	AgentID       string `json:"agent_id"`
	PrepareID     string `json:"prepare_id"`
	ProjectID     string `json:"project_id"`
	DisplayName   string `json:"display_name"`
	Role          string `json:"role"`
	Status        string `json:"status"`
	SourceAssetID string `json:"source_asset_id"`
	Summary       string `json:"summary"`
	CreatedAt     string `json:"created_at"`
	UpdatedAt     string `json:"updated_at"`
}

type PreparationStore interface {
	CreatePreparation(context.Context, CreatePreparationInput) (PreparationRecord, error)
	GetPreparation(context.Context, GetPreparationInput) (PreparationRecord, error)
	ListPreparedAgents(context.Context, ListPreparedAgentsInput) ([]PreparedAgentRecord, error)
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
	return "WORLDLINE_QUERY_FAILED"
}

type DisabledSavedPathReader struct{}

func NewDisabledSavedPathReader() *DisabledSavedPathReader {
	return &DisabledSavedPathReader{}
}

func (r *DisabledSavedPathReader) ListSavedPaths(context.Context, ListSavedPathsInput) ([]SavedPathRecord, error) {
	return nil, &AppError{
		Code:    "WORLDLINE_BACKEND_UNCONFIGURED",
		Message: "worldline backend is not configured",
	}
}

type DisabledSavedPathStore struct{}

func NewDisabledSavedPathStore() *DisabledSavedPathStore {
	return &DisabledSavedPathStore{}
}

func (s *DisabledSavedPathStore) CreateSavedPath(context.Context, CreateSavedPathInput) (SavedPathRecord, error) {
	return SavedPathRecord{}, &AppError{
		Code:    "WORLDLINE_SAVED_PATH_BACKEND_UNCONFIGURED",
		Message: "worldline saved path backend is not configured",
	}
}

type DisabledSessionStarter struct{}

func NewDisabledSessionStarter() *DisabledSessionStarter {
	return &DisabledSessionStarter{}
}

func (s *DisabledSessionStarter) StartSession(context.Context, StartSessionInput) (SessionRun, error) {
	return SessionRun{}, &AppError{
		Code:    "WORLDLINE_SESSION_BACKEND_UNCONFIGURED",
		Message: "worldline session backend is not configured",
	}
}

type DisabledStepStarter struct{}

func NewDisabledStepStarter() *DisabledStepStarter {
	return &DisabledStepStarter{}
}

func (s *DisabledStepStarter) StartStep(context.Context, StartStepInput) (StepRun, error) {
	return StepRun{}, &AppError{
		Code:    "WORLDLINE_STEP_BACKEND_UNCONFIGURED",
		Message: "worldline step backend is not configured",
	}
}

type DisabledSessionReader struct{}

func NewDisabledSessionReader() *DisabledSessionReader {
	return &DisabledSessionReader{}
}

func (r *DisabledSessionReader) ListSessions(context.Context, ListSessionsInput) ([]SessionRecord, error) {
	return nil, &AppError{
		Code:    "WORLDLINE_SESSION_BACKEND_UNCONFIGURED",
		Message: "worldline session backend is not configured",
	}
}

func (r *DisabledSessionReader) GetSession(context.Context, GetSessionInput) (SessionRecord, error) {
	return SessionRecord{}, &AppError{
		Code:    "WORLDLINE_SESSION_BACKEND_UNCONFIGURED",
		Message: "worldline session backend is not configured",
	}
}

type DisabledPreparationStore struct{}

func NewDisabledPreparationStore() *DisabledPreparationStore {
	return &DisabledPreparationStore{}
}

func (s *DisabledPreparationStore) CreatePreparation(context.Context, CreatePreparationInput) (PreparationRecord, error) {
	return PreparationRecord{}, &AppError{
		Code:    "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED",
		Message: "worldline preparation backend is not configured",
	}
}

func (s *DisabledPreparationStore) GetPreparation(context.Context, GetPreparationInput) (PreparationRecord, error) {
	return PreparationRecord{}, &AppError{
		Code:    "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED",
		Message: "worldline preparation backend is not configured",
	}
}

func (s *DisabledPreparationStore) ListPreparedAgents(context.Context, ListPreparedAgentsInput) ([]PreparedAgentRecord, error) {
	return nil, &AppError{
		Code:    "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED",
		Message: "worldline preparation backend is not configured",
	}
}

type DisabledTimelineReader struct{}

func NewDisabledTimelineReader() *DisabledTimelineReader {
	return &DisabledTimelineReader{}
}

func (r *DisabledTimelineReader) ListTimeline(context.Context, ListTimelineInput) ([]TimelineEventRecord, error) {
	return nil, &AppError{
		Code:    "WORLDLINE_TIMELINE_BACKEND_UNCONFIGURED",
		Message: "worldline timeline backend is not configured",
	}
}

type DisabledEventReader struct{}

func NewDisabledEventReader() *DisabledEventReader {
	return &DisabledEventReader{}
}

func (r *DisabledEventReader) ListEvents(context.Context, ListEventsInput) ([]EventRecord, error) {
	return nil, &AppError{
		Code:    "WORLDLINE_EVENT_BACKEND_UNCONFIGURED",
		Message: "worldline event backend is not configured",
	}
}

type DisabledEventAdoptionStore struct{}

func NewDisabledEventAdoptionStore() *DisabledEventAdoptionStore {
	return &DisabledEventAdoptionStore{}
}

func (s *DisabledEventAdoptionStore) AdoptEvent(context.Context, AdoptEventInput) (EventRecord, error) {
	return EventRecord{}, &AppError{
		Code:    "WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED",
		Message: "worldline event adoption backend is not configured",
	}
}

type DisabledEventMutationStore struct{}

func NewDisabledEventMutationStore() *DisabledEventMutationStore {
	return &DisabledEventMutationStore{}
}

func (s *DisabledEventMutationStore) UpdateEvent(context.Context, UpdateEventInput) (EventRecord, error) {
	return EventRecord{}, &AppError{
		Code:    "WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED",
		Message: "worldline event mutation backend is not configured",
	}
}

type DisabledVariableStore struct{}

func NewDisabledVariableStore() *DisabledVariableStore {
	return &DisabledVariableStore{}
}

func (s *DisabledVariableStore) InjectVariable(context.Context, InjectVariableInput) (VariableRecord, error) {
	return VariableRecord{}, &AppError{
		Code:    "WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED",
		Message: "worldline variable backend is not configured",
	}
}

type SQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type SQLExecer interface {
	ExecContext(context.Context, string, ...any) (sql.Result, error)
}

type SQLQueryer interface {
	QueryContext(context.Context, string, ...any) (SQLRows, error)
}

type SQLDBQueryer struct {
	db *sql.DB
}

func NewSQLDBQueryer(db *sql.DB) *SQLDBQueryer {
	return &SQLDBQueryer{db: db}
}

func (q *SQLDBQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (q *SQLDBQueryer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	return q.db.ExecContext(ctx, query, args...)
}

type SQLSavedPathReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLSavedPathReader struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLSavedPathReader(config SQLSavedPathReaderConfig) *SQLSavedPathReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 50
	}
	return &SQLSavedPathReader{
		queryer: config.Queryer,
		limit:   limit,
	}
}

func (r *SQLSavedPathReader) ListSavedPaths(ctx context.Context, input ListSavedPathsInput) ([]SavedPathRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "WORLDLINE_BACKEND_UNCONFIGURED", Message: "worldline backend is not configured"}
	}

	query := `
SELECT
  path_id::text,
  session_id::text,
  project_id::text,
  title,
  COALESCE(summary, ''),
  lifecycle,
  COALESCE(selected_event_ids_jsonb, '[]'::jsonb)::text,
  COALESCE(writer_instruction, ''),
  created_at::text,
  updated_at::text
FROM worldline_saved_paths
WHERE tenant_id::text = $1
  AND project_id::text = $2
ORDER BY updated_at DESC, created_at DESC
LIMIT $3`
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, r.limit)
	if err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	records := []SavedPathRecord{}
	for rows.Next() {
		record, err := scanSavedPathRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func scanSavedPathRecord(rows SQLRows) (SavedPathRecord, error) {
	var record SavedPathRecord
	var eventIDsJSON string
	if err := rows.Scan(
		&record.PathID,
		&record.SessionID,
		&record.ProjectID,
		&record.Title,
		&record.Summary,
		&record.Lifecycle,
		&eventIDsJSON,
		&record.WriterInstruction,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return SavedPathRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	var eventIDs []string
	if err := json.Unmarshal([]byte(eventIDsJSON), &eventIDs); err != nil {
		return SavedPathRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: "saved path selected_event_ids is malformed"}
	}
	record.SelectedEventIDs = eventIDs
	return record, nil
}

type SQLSavedPathStoreConfig struct {
	Queryer SQLQueryer
	Execer  SQLExecer
	NewID   func() string
}

type SQLSavedPathStore struct {
	queryer SQLQueryer
	execer  SQLExecer
	newID   func() string
}

func NewSQLSavedPathStore(config SQLSavedPathStoreConfig) *SQLSavedPathStore {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLSavedPathStore{
		queryer: config.Queryer,
		execer:  config.Execer,
		newID:   newID,
	}
}

func (s *SQLSavedPathStore) CreateSavedPath(ctx context.Context, input CreateSavedPathInput) (SavedPathRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	sessionID := strings.TrimSpace(input.SessionID)
	title := strings.TrimSpace(input.Title)
	if tenantID == "" || sessionID == "" || title == "" || len(input.SelectedEventIDs) == 0 {
		return SavedPathRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, session_id, title, and selected_event_ids are required"}
	}
	if s.queryer == nil && s.execer == nil {
		return SavedPathRecord{}, &AppError{Code: "WORLDLINE_SAVED_PATH_BACKEND_UNCONFIGURED", Message: "worldline saved path backend is not configured"}
	}

	selectedEventIDs := make([]string, 0, len(input.SelectedEventIDs))
	for _, eventID := range input.SelectedEventIDs {
		eventID = strings.TrimSpace(eventID)
		if eventID == "" {
			continue
		}
		selectedEventIDs = append(selectedEventIDs, eventID)
	}
	if len(selectedEventIDs) == 0 {
		return SavedPathRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "selected_event_ids are required"}
	}
	selectedEventIDsJSON, err := json.Marshal(selectedEventIDs)
	if err != nil {
		return SavedPathRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "selected_event_ids must be JSON serializable"}
	}

	pathID := s.newID()
	eventID := s.newID()
	summary := strings.TrimSpace(input.Summary)
	writerInstruction := strings.TrimSpace(input.WriterInstruction)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	eventPayload, err := json.Marshal(map[string]any{
		"status":             "saved",
		"lifecycle":          "saved",
		"kind":               "saved_path",
		"title":              title,
		"summary":            summary,
		"path_id":            pathID,
		"selected_event_ids": selectedEventIDs,
		"writer_instruction": writerInstruction,
		"request_id":         strings.TrimSpace(input.RequestID),
	})
	if err != nil {
		return SavedPathRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "worldline saved path payload must be JSON serializable"}
	}

	args := []any{
		tenantID,
		sessionID,
		pathID,
		title,
		summary,
		string(selectedEventIDsJSON),
		writerInstruction,
		actorUserID,
		eventID,
		string(eventPayload),
	}
	if s.queryer != nil {
		return s.createSavedPathReturning(ctx, args)
	}
	result, err := s.execer.ExecContext(ctx, createSavedPathExecQuery(), args...)
	if err != nil {
		return SavedPathRecord{}, &AppError{Code: "WORLDLINE_SAVED_PATH_WRITE_FAILED", Message: err.Error()}
	}
	if affected, err := result.RowsAffected(); err == nil && affected == 0 {
		return SavedPathRecord{}, &AppError{Code: "NOT_FOUND", Message: "worldline session or selected events not found"}
	}
	return SavedPathRecord{
		PathID:            pathID,
		SessionID:         sessionID,
		Title:             title,
		Summary:           summary,
		Lifecycle:         "saved",
		SelectedEventIDs:  selectedEventIDs,
		WriterInstruction: writerInstruction,
	}, nil
}

func (s *SQLSavedPathStore) createSavedPathReturning(ctx context.Context, args []any) (SavedPathRecord, error) {
	rows, err := s.queryer.QueryContext(ctx, createSavedPathReturningQuery(), args...)
	if err != nil {
		return SavedPathRecord{}, &AppError{Code: "WORLDLINE_SAVED_PATH_WRITE_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return SavedPathRecord{}, &AppError{Code: "WORLDLINE_SAVED_PATH_WRITE_FAILED", Message: err.Error()}
		}
		return SavedPathRecord{}, &AppError{Code: "NOT_FOUND", Message: "worldline session or selected events not found"}
	}
	record, err := scanSavedPathRecord(rows)
	if err != nil {
		return SavedPathRecord{}, err
	}
	if err := rows.Err(); err != nil {
		return SavedPathRecord{}, &AppError{Code: "WORLDLINE_SAVED_PATH_WRITE_FAILED", Message: err.Error()}
	}
	return record, nil
}

func createSavedPathReturningQuery() string {
	return createSavedPathCTE() + `
SELECT
  path_id::text,
  session_id::text,
  project_id::text,
  title,
  COALESCE(summary, ''),
  lifecycle,
  COALESCE(selected_event_ids_jsonb, '[]'::jsonb)::text,
  COALESCE(writer_instruction, ''),
  created_at::text,
  updated_at::text
FROM saved_path_insert
JOIN event_insert
  ON true`
}

func createSavedPathExecQuery() string {
	return createSavedPathCTE() + `
SELECT 1 FROM event_insert`
}

func createSavedPathCTE() string {
	return `WITH session_scope AS (
  SELECT
    s.tenant_id,
    s.project_id,
    s.session_id,
    s.run_id
  FROM (SELECT 1) input
  JOIN worldline_sessions s
    ON s.tenant_id::text = $1
   AND s.session_id::text = $2
  LIMIT 1
),
input_event_ids AS (
  SELECT
    value::uuid AS event_id,
    ordinality AS event_order
  FROM jsonb_array_elements_text($6::jsonb) WITH ORDINALITY
),
matched_event_ids AS (
  SELECT
    input_event_ids.event_id,
    input_event_ids.event_order
  FROM input_event_ids
  JOIN session_scope
    ON true
  JOIN worldline_events e
    ON e.tenant_id = session_scope.tenant_id
   AND e.project_id = session_scope.project_id
   AND e.session_id = session_scope.session_id
   AND e.event_id = input_event_ids.event_id
),
event_selection AS (
  SELECT
    COALESCE(jsonb_agg(input_event_ids.event_id::text ORDER BY input_event_ids.event_order), '[]'::jsonb) AS selected_event_ids_jsonb,
    COUNT(input_event_ids.event_id) AS input_count,
    (SELECT COUNT(matched_event_ids.event_id) FROM matched_event_ids) AS matched_count
  FROM input_event_ids
),
saved_path_insert AS (
  INSERT INTO worldline_saved_paths (
    tenant_id,
    path_id,
    session_id,
    project_id,
    title,
    summary,
    lifecycle,
    selected_event_ids_jsonb,
    writer_instruction,
    created_by
  )
  SELECT
    session_scope.tenant_id,
    $3::uuid,
    session_scope.session_id,
    session_scope.project_id,
    $4,
    $5,
    'saved',
    event_selection.selected_event_ids_jsonb,
    $7,
    NULLIF($8, '')::uuid
  FROM session_scope
  JOIN event_selection
    ON event_selection.input_count > 0
   AND event_selection.input_count = event_selection.matched_count
  RETURNING
    path_id,
    session_id,
    project_id,
    title,
    summary,
    lifecycle,
    selected_event_ids_jsonb,
    writer_instruction,
    created_at,
    updated_at
),
event_insert AS (
  INSERT INTO workflow_events (
    tenant_id,
    event_id,
    run_id,
    workflow_type,
    project_id,
    event_type,
    sequence,
    payload_jsonb
  )
  SELECT
    session_scope.tenant_id,
    $9::uuid,
    session_scope.run_id,
    'worldline_session',
    session_scope.project_id,
    'worldline.saved_path.created',
    COALESCE((
      SELECT MAX(sequence) + 1
      FROM workflow_events existing
      WHERE existing.tenant_id = session_scope.tenant_id
        AND existing.run_id = session_scope.run_id
    ), 1),
    $10::jsonb
  FROM session_scope
  JOIN saved_path_insert
    ON saved_path_insert.session_id = session_scope.session_id
  RETURNING 1
)`
}

type SQLSessionStoreConfig struct {
	Queryer SQLQueryer
	Execer  SQLExecer
	Limit   int
	NewID   func() string
}

type SQLSessionStore struct {
	queryer SQLQueryer
	execer  SQLExecer
	limit   int
	newID   func() string
}

func NewSQLSessionStore(config SQLSessionStoreConfig) *SQLSessionStore {
	limit := config.Limit
	if limit <= 0 {
		limit = 50
	}
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLSessionStore{
		queryer: config.Queryer,
		execer:  config.Execer,
		limit:   limit,
		newID:   newID,
	}
}

func (s *SQLSessionStore) StartSession(ctx context.Context, input StartSessionInput) (SessionRun, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	goal := strings.TrimSpace(input.Goal)
	if tenantID == "" || projectID == "" || goal == "" {
		return SessionRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and goal are required"}
	}
	if s.execer == nil {
		return SessionRun{}, &AppError{Code: "WORLDLINE_SESSION_BACKEND_UNCONFIGURED", Message: "worldline session backend is not configured"}
	}
	runID := s.newID()
	sessionID := s.newID()
	eventID := s.newID()
	traceID := "trace_" + runID
	status := "queued"
	anchorPathID := strings.TrimSpace(input.AnchorPathID)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	eventPayload, err := json.Marshal(map[string]any{
		"status":         status,
		"workflow_type":  "worldline_session",
		"request_id":     strings.TrimSpace(input.RequestID),
		"trace_id":       traceID,
		"session_id":     sessionID,
		"anchor_path_id": anchorPathID,
	})
	if err != nil {
		return SessionRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "worldline session admission payload must be JSON serializable"}
	}
	query := `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id,
    run_id,
    workflow_type,
    project_id,
    status,
    progress,
    message,
    started_by,
    temporal_workflow_id
  )
  VALUES (
    $1::uuid,
    $3::uuid,
    'worldline_session',
    $2::uuid,
    $5,
    0,
    'queued',
    NULLIF($7, '')::uuid,
    ''
  )
  RETURNING run_id
),
session_insert AS (
  INSERT INTO worldline_sessions (
    tenant_id,
    session_id,
    project_id,
    run_id,
    status,
    lifecycle,
    goal_summary,
    anchor_path_id,
    created_by
  )
  SELECT
    $1::uuid,
    $4::uuid,
    $2::uuid,
    workflow_insert.run_id,
    $5,
    'active',
    $6,
    NULLIF($8, '')::uuid,
    NULLIF($7, '')::uuid
  FROM workflow_insert
  RETURNING session_id, run_id, project_id
)
INSERT INTO workflow_events (
  tenant_id,
  event_id,
  run_id,
  workflow_type,
  project_id,
  event_type,
  sequence,
  payload_jsonb
)
SELECT
  $1::uuid,
  $9::uuid,
  session_insert.run_id,
  'worldline_session',
  session_insert.project_id,
  'workflow.queued',
  1,
  $10::jsonb
FROM session_insert`
	_, err = s.execer.ExecContext(
		ctx,
		query,
		tenantID,
		projectID,
		runID,
		sessionID,
		status,
		goal,
		actorUserID,
		anchorPathID,
		eventID,
		string(eventPayload),
	)
	if err != nil {
		return SessionRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	return SessionRun{
		RunID:        runID,
		ProjectID:    projectID,
		WorkflowType: "worldline_session",
		Status:       status,
	}, nil
}

func (s *SQLSessionStore) ListSessions(ctx context.Context, input ListSessionsInput) ([]SessionRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if s.queryer == nil {
		return nil, &AppError{Code: "WORLDLINE_SESSION_BACKEND_UNCONFIGURED", Message: "worldline session backend is not configured"}
	}
	query := sessionRecordSelectQuery() + `
WHERE tenant_id::text = $1
  AND project_id::text = $2
ORDER BY updated_at DESC, created_at DESC
LIMIT $3`
	rows, err := s.queryer.QueryContext(ctx, query, tenantID, projectID, s.limit)
	if err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	records := []SessionRecord{}
	for rows.Next() {
		record, err := scanSessionRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func (s *SQLSessionStore) GetSession(ctx context.Context, input GetSessionInput) (SessionRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	sessionID := strings.TrimSpace(input.SessionID)
	if tenantID == "" || sessionID == "" {
		return SessionRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and session_id are required"}
	}
	if s.queryer == nil {
		return SessionRecord{}, &AppError{Code: "WORLDLINE_SESSION_BACKEND_UNCONFIGURED", Message: "worldline session backend is not configured"}
	}
	query := sessionRecordSelectQuery() + `
WHERE tenant_id::text = $1
  AND session_id::text = $2
LIMIT 1`
	rows, err := s.queryer.QueryContext(ctx, query, tenantID, sessionID)
	if err != nil {
		return SessionRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return SessionRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
		}
		return SessionRecord{}, &AppError{Code: "NOT_FOUND", Message: "worldline session not found"}
	}
	record, err := scanSessionRecord(rows)
	if err != nil {
		return SessionRecord{}, err
	}
	return record, nil
}

func sessionRecordSelectQuery() string {
	return `
SELECT
  session_id::text,
  run_id::text,
  project_id::text,
  status,
  lifecycle,
  goal_summary,
  COALESCE(anchor_path_id::text, ''),
  COALESCE(created_by::text, ''),
  created_at::text,
  updated_at::text
FROM worldline_sessions
`
}

func scanSessionRecord(rows SQLRows) (SessionRecord, error) {
	var record SessionRecord
	if err := rows.Scan(
		&record.SessionID,
		&record.RunID,
		&record.ProjectID,
		&record.Status,
		&record.Lifecycle,
		&record.GoalSummary,
		&record.AnchorPathID,
		&record.CreatedBy,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return SessionRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return record, nil
}

type SQLStepStarterConfig struct {
	Queryer SQLQueryer
	Execer  SQLExecer
	NewID   func() string
}

type SQLStepStarter struct {
	queryer SQLQueryer
	execer  SQLExecer
	newID   func() string
}

func NewSQLStepStarter(config SQLStepStarterConfig) *SQLStepStarter {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLStepStarter{
		queryer: config.Queryer,
		execer:  config.Execer,
		newID:   newID,
	}
}

func (s *SQLStepStarter) StartStep(ctx context.Context, input StartStepInput) (StepRun, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	sessionID := strings.TrimSpace(input.SessionID)
	if tenantID == "" || sessionID == "" {
		return StepRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and session_id are required"}
	}
	if s.execer == nil && s.queryer == nil {
		return StepRun{}, &AppError{Code: "WORLDLINE_STEP_BACKEND_UNCONFIGURED", Message: "worldline step backend is not configured"}
	}
	runID := s.newID()
	eventID := s.newID()
	status := "queued"
	mode := strings.TrimSpace(input.Mode)
	if mode == "" {
		mode = "director"
	}
	actorUserID := strings.TrimSpace(input.ActorUserID)
	traceID := "trace_" + runID
	eventPayload, err := json.Marshal(map[string]any{
		"status":        status,
		"workflow_type": "worldline_step",
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      traceID,
		"session_id":    sessionID,
		"mode":          mode,
	})
	if err != nil {
		return StepRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "worldline step admission payload must be JSON serializable"}
	}

	args := []any{
		tenantID,
		sessionID,
		runID,
		status,
		actorUserID,
		eventID,
		string(eventPayload),
	}
	if s.queryer != nil {
		return s.startStepReturning(ctx, args)
	}
	result, err := s.execer.ExecContext(ctx, startStepExecQuery(), args...)
	if err != nil {
		return StepRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	if affected, err := result.RowsAffected(); err == nil && affected == 0 {
		return StepRun{}, &AppError{Code: "NOT_FOUND", Message: "worldline session not found"}
	}
	return StepRun{
		RunID:        runID,
		SessionID:    sessionID,
		WorkflowType: "worldline_step",
		Status:       status,
	}, nil
}

func (s *SQLStepStarter) startStepReturning(ctx context.Context, args []any) (StepRun, error) {
	rows, err := s.queryer.QueryContext(ctx, startStepReturningQuery(), args...)
	if err != nil {
		return StepRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return StepRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
		}
		return StepRun{}, &AppError{Code: "NOT_FOUND", Message: "worldline session not found"}
	}
	var run StepRun
	if err := rows.Scan(&run.RunID, &run.ProjectID, &run.SessionID, &run.WorkflowType, &run.Status); err != nil {
		return StepRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return StepRun{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	return run, nil
}

func startStepReturningQuery() string {
	return startStepCTE() + `
SELECT
  run_id::text,
  project_id::text,
  session_id::text,
  workflow_type,
  status
FROM workflow_insert
JOIN event_insert
  ON true
JOIN session_scope
  ON true`
}

func startStepExecQuery() string {
	return startStepCTE() + `
SELECT 1 FROM event_insert`
}

func startStepCTE() string {
	return `WITH session_scope AS (
  SELECT
    tenant_id,
    project_id,
    session_id
  FROM worldline_sessions
  WHERE tenant_id::text = $1
    AND session_id::text = $2
  LIMIT 1
),
workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id,
    run_id,
    workflow_type,
    project_id,
    status,
    progress,
    message,
    started_by,
    temporal_workflow_id
  )
  SELECT
    session_scope.tenant_id,
    $3::uuid,
    'worldline_step',
    session_scope.project_id,
    $4,
    0,
    'queued',
    NULLIF($5, '')::uuid,
    ''
  FROM session_scope
  RETURNING run_id, workflow_type, project_id, status
),
event_insert AS (
  INSERT INTO workflow_events (
    tenant_id,
    event_id,
    run_id,
    workflow_type,
    project_id,
    event_type,
    sequence,
    payload_jsonb
  )
  SELECT
    session_scope.tenant_id,
    $6::uuid,
    workflow_insert.run_id,
    'worldline_step',
    session_scope.project_id,
    'workflow.queued',
    1,
    $7::jsonb
  FROM session_scope
  JOIN workflow_insert
    ON true
  RETURNING 1
)`
}

type SQLPreparationStoreConfig struct {
	Queryer SQLQueryer
	Execer  SQLExecer
	Limit   int
	NewID   func() string
}

type SQLPreparationStore struct {
	queryer SQLQueryer
	execer  SQLExecer
	limit   int
	newID   func() string
}

type SQLTimelineReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLTimelineReader struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLTimelineReader(config SQLTimelineReaderConfig) *SQLTimelineReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLTimelineReader{
		queryer: config.Queryer,
		limit:   limit,
	}
}

func (r *SQLTimelineReader) ListTimeline(ctx context.Context, input ListTimelineInput) ([]TimelineEventRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	sessionID := strings.TrimSpace(input.SessionID)
	if tenantID == "" || sessionID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and session_id are required"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "WORLDLINE_TIMELINE_BACKEND_UNCONFIGURED", Message: "worldline timeline backend is not configured"}
	}
	query := `
SELECT
  e.event_id::text,
  s.session_id::text,
  e.run_id::text,
  e.project_id::text,
  e.event_type,
  e.sequence,
  COALESCE(e.payload_jsonb->>'status', ''),
  COALESCE(e.payload_jsonb->>'lifecycle', ''),
  COALESCE(e.payload_jsonb->>'title', ''),
  COALESCE(e.payload_jsonb->>'summary', ''),
  COALESCE(e.payload_jsonb->>'kind', ''),
  e.created_at::text
FROM workflow_events e
JOIN worldline_sessions s
  ON s.tenant_id = e.tenant_id
 AND s.project_id = e.project_id
 AND s.run_id = e.run_id
WHERE s.tenant_id::text = $1
  AND s.session_id::text = $2
  AND e.workflow_type = 'worldline_session'
ORDER BY e.sequence ASC, e.created_at ASC
LIMIT $3`
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, sessionID, r.limit)
	if err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	records := []TimelineEventRecord{}
	for rows.Next() {
		record, err := scanTimelineEventRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func scanTimelineEventRecord(rows SQLRows) (TimelineEventRecord, error) {
	var record TimelineEventRecord
	if err := rows.Scan(
		&record.EventID,
		&record.SessionID,
		&record.RunID,
		&record.ProjectID,
		&record.EventType,
		&record.Sequence,
		&record.Status,
		&record.Lifecycle,
		&record.Title,
		&record.Summary,
		&record.Kind,
		&record.CreatedAt,
	); err != nil {
		return TimelineEventRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return record, nil
}

type SQLEventReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLEventReader struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLEventReader(config SQLEventReaderConfig) *SQLEventReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLEventReader{
		queryer: config.Queryer,
		limit:   limit,
	}
}

func (r *SQLEventReader) ListEvents(ctx context.Context, input ListEventsInput) ([]EventRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	sessionID := strings.TrimSpace(input.SessionID)
	status := strings.TrimSpace(input.Status)
	if tenantID == "" || sessionID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and session_id are required"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "WORLDLINE_EVENT_BACKEND_UNCONFIGURED", Message: "worldline event backend is not configured"}
	}

	query := `
SELECT
  e.event_id::text,
  e.session_id::text,
  e.project_id::text,
  e.step,
  e.title,
  e.summary,
  e.kind,
  e.status,
  e.lifecycle,
  COALESCE(e.confidence::text, ''),
  COALESCE(e.involved_agent_ids_jsonb, '[]'::jsonb)::text,
  COALESCE(e.state_changes_jsonb, '{}'::jsonb)::text,
  COALESCE(e.source_run_id::text, ''),
  COALESCE(e.created_by::text, ''),
  e.created_at::text,
  e.updated_at::text
FROM worldline_events e
JOIN worldline_sessions s
  ON s.tenant_id = e.tenant_id
 AND s.project_id = e.project_id
 AND s.session_id = e.session_id
WHERE s.tenant_id::text = $1
  AND s.session_id::text = $2`
	args := []any{tenantID, sessionID}
	if status != "" {
		query += `
  AND e.status = $3`
		args = append(args, status)
	}
	query += fmt.Sprintf(`
ORDER BY e.step ASC, e.created_at ASC
LIMIT $%d`, len(args)+1)
	args = append(args, r.limit)

	rows, err := r.queryer.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	records := []EventRecord{}
	for rows.Next() {
		record, err := scanEventRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func scanEventRecord(rows SQLRows) (EventRecord, error) {
	var record EventRecord
	var involvedAgentIDsJSON string
	var stateChangesJSON string
	if err := rows.Scan(
		&record.EventID,
		&record.SessionID,
		&record.ProjectID,
		&record.Step,
		&record.Title,
		&record.Summary,
		&record.Kind,
		&record.Status,
		&record.Lifecycle,
		&record.Confidence,
		&involvedAgentIDsJSON,
		&stateChangesJSON,
		&record.SourceRunID,
		&record.CreatedBy,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	var involvedAgentIDs []string
	if err := json.Unmarshal([]byte(involvedAgentIDsJSON), &involvedAgentIDs); err != nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: "worldline event involved_agent_ids is malformed"}
	}
	var stateChanges map[string]any
	if err := json.Unmarshal([]byte(stateChangesJSON), &stateChanges); err != nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: "worldline event state_changes is malformed"}
	}
	record.InvolvedAgentIDs = involvedAgentIDs
	record.StateChanges = stateChanges
	return record, nil
}

type SQLEventMutationStoreConfig struct {
	Queryer SQLQueryer
	NewID   func() string
}

type SQLEventMutationStore struct {
	queryer SQLQueryer
	newID   func() string
}

func NewSQLEventMutationStore(config SQLEventMutationStoreConfig) *SQLEventMutationStore {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLEventMutationStore{
		queryer: config.Queryer,
		newID:   newID,
	}
}

func (s *SQLEventMutationStore) UpdateEvent(ctx context.Context, input UpdateEventInput) (EventRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	eventID := strings.TrimSpace(input.EventID)
	title := strings.TrimSpace(input.Title)
	summary := strings.TrimSpace(input.Summary)
	kind := strings.TrimSpace(input.Kind)
	if tenantID == "" || eventID == "" || (title == "" && summary == "" && kind == "") {
		return EventRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, event_id, and at least one event metadata field are required"}
	}
	if s.queryer == nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED", Message: "worldline event mutation backend is not configured"}
	}

	workflowEventID := s.newID()
	eventPayload, err := json.Marshal(map[string]any{
		"status":     "candidate",
		"lifecycle":  "simulation",
		"kind":       "event_update",
		"title":      title,
		"summary":    summary,
		"event_id":   eventID,
		"event_kind": kind,
		"request_id": strings.TrimSpace(input.RequestID),
	})
	if err != nil {
		return EventRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "worldline event mutation payload must be JSON serializable"}
	}

	rows, err := s.queryer.QueryContext(
		ctx,
		updateEventReturningQuery(),
		tenantID,
		eventID,
		title,
		summary,
		kind,
		workflowEventID,
		string(eventPayload),
	)
	if err != nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_MUTATION_WRITE_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_MUTATION_WRITE_FAILED", Message: err.Error()}
		}
		return EventRecord{}, &AppError{Code: "NOT_FOUND", Message: "candidate worldline event not found"}
	}
	record, err := scanEventRecord(rows)
	if err != nil {
		return EventRecord{}, err
	}
	if err := rows.Err(); err != nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_MUTATION_WRITE_FAILED", Message: err.Error()}
	}
	return record, nil
}

func updateEventReturningQuery() string {
	return `WITH candidate_scope AS (
  SELECT
    e.tenant_id,
    e.project_id,
    e.session_id,
    e.event_id,
    s.run_id
  FROM worldline_events e
  JOIN worldline_sessions s
    ON s.tenant_id = e.tenant_id
   AND s.project_id = e.project_id
   AND s.session_id = e.session_id
  WHERE e.tenant_id::text = $1
    AND e.event_id::text = $2
    AND e.status = 'candidate'
  LIMIT 1
),
updated_event AS (
  UPDATE worldline_events
  SET
    title = COALESCE(NULLIF($3, ''), worldline_events.title),
    summary = COALESCE(NULLIF($4, ''), worldline_events.summary),
    kind = COALESCE(NULLIF($5, ''), worldline_events.kind),
    updated_at = now()
  FROM candidate_scope
  WHERE worldline_events.tenant_id = candidate_scope.tenant_id
    AND worldline_events.project_id = candidate_scope.project_id
    AND worldline_events.session_id = candidate_scope.session_id
    AND worldline_events.event_id = candidate_scope.event_id
  RETURNING
    worldline_events.event_id,
    worldline_events.session_id,
    worldline_events.project_id,
    worldline_events.step,
    worldline_events.title,
    worldline_events.summary,
    worldline_events.kind,
    worldline_events.status,
    worldline_events.lifecycle,
    worldline_events.confidence,
    worldline_events.involved_agent_ids_jsonb,
    worldline_events.state_changes_jsonb,
    worldline_events.source_run_id,
    worldline_events.created_by,
    worldline_events.created_at,
    worldline_events.updated_at
),
workflow_event_insert AS (
  INSERT INTO workflow_events (
    tenant_id,
    event_id,
    run_id,
    workflow_type,
    project_id,
    event_type,
    sequence,
    payload_jsonb
  )
  SELECT
    candidate_scope.tenant_id,
    $6::uuid,
    candidate_scope.run_id,
    'worldline_session',
    candidate_scope.project_id,
    'worldline.event.updated',
    COALESCE((
      SELECT MAX(sequence) + 1
      FROM workflow_events existing
      WHERE existing.tenant_id = candidate_scope.tenant_id
        AND existing.run_id = candidate_scope.run_id
    ), 1),
    $7::jsonb
  FROM candidate_scope
  JOIN updated_event
    ON updated_event.event_id = candidate_scope.event_id
  RETURNING 1
)
SELECT
  updated_event.event_id::text,
  updated_event.session_id::text,
  updated_event.project_id::text,
  updated_event.step,
  updated_event.title,
  updated_event.summary,
  updated_event.kind,
  updated_event.status,
  updated_event.lifecycle,
  COALESCE(updated_event.confidence::text, ''),
  COALESCE(updated_event.involved_agent_ids_jsonb, '[]'::jsonb)::text,
  COALESCE(updated_event.state_changes_jsonb, '{}'::jsonb)::text,
  COALESCE(updated_event.source_run_id::text, ''),
  COALESCE(updated_event.created_by::text, ''),
  updated_event.created_at::text,
  updated_event.updated_at::text
FROM updated_event
JOIN workflow_event_insert
  ON true`
}

type SQLEventAdoptionStoreConfig struct {
	Queryer SQLQueryer
	NewID   func() string
}

type SQLEventAdoptionStore struct {
	queryer SQLQueryer
	newID   func() string
}

func NewSQLEventAdoptionStore(config SQLEventAdoptionStoreConfig) *SQLEventAdoptionStore {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLEventAdoptionStore{
		queryer: config.Queryer,
		newID:   newID,
	}
}

func (s *SQLEventAdoptionStore) AdoptEvent(ctx context.Context, input AdoptEventInput) (EventRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	eventID := strings.TrimSpace(input.EventID)
	if tenantID == "" || eventID == "" {
		return EventRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and event_id are required"}
	}
	if s.queryer == nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED", Message: "worldline event adoption backend is not configured"}
	}
	adoptionID := s.newID()
	workflowEventID := s.newID()
	actorUserID := strings.TrimSpace(input.ActorUserID)
	note := strings.TrimSpace(input.Note)
	eventPayload, err := json.Marshal(map[string]any{
		"status":      "canon",
		"lifecycle":   "canon_reference",
		"kind":        "event_adoption",
		"title":       "Worldline event adopted",
		"summary":     note,
		"event_id":    eventID,
		"adoption_id": adoptionID,
		"request_id":  strings.TrimSpace(input.RequestID),
	})
	if err != nil {
		return EventRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "worldline event adoption payload must be JSON serializable"}
	}

	rows, err := s.queryer.QueryContext(
		ctx,
		adoptEventReturningQuery(),
		tenantID,
		eventID,
		adoptionID,
		actorUserID,
		note,
		workflowEventID,
		string(eventPayload),
	)
	if err != nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_ADOPTION_WRITE_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_ADOPTION_WRITE_FAILED", Message: err.Error()}
		}
		return EventRecord{}, &AppError{Code: "NOT_FOUND", Message: "candidate worldline event not found"}
	}
	record, err := scanEventRecord(rows)
	if err != nil {
		return EventRecord{}, err
	}
	if err := rows.Err(); err != nil {
		return EventRecord{}, &AppError{Code: "WORLDLINE_EVENT_ADOPTION_WRITE_FAILED", Message: err.Error()}
	}
	return record, nil
}

func adoptEventReturningQuery() string {
	return `WITH candidate_scope AS (
  SELECT
    e.tenant_id,
    e.project_id,
    e.session_id,
    e.event_id,
    e.status AS from_status,
    s.run_id
  FROM worldline_events e
  JOIN worldline_sessions s
    ON s.tenant_id = e.tenant_id
   AND s.project_id = e.project_id
   AND s.session_id = e.session_id
  WHERE e.tenant_id::text = $1
    AND e.event_id::text = $2
    AND e.status = 'candidate'
  LIMIT 1
),
updated_event AS (
  UPDATE worldline_events
  SET
    status = 'canon',
    lifecycle = 'canon_reference',
    updated_at = now()
  FROM candidate_scope
  WHERE worldline_events.tenant_id = candidate_scope.tenant_id
    AND worldline_events.project_id = candidate_scope.project_id
    AND worldline_events.session_id = candidate_scope.session_id
    AND worldline_events.event_id = candidate_scope.event_id
  RETURNING
    worldline_events.event_id,
    worldline_events.session_id,
    worldline_events.project_id,
    worldline_events.step,
    worldline_events.title,
    worldline_events.summary,
    worldline_events.kind,
    worldline_events.status,
    worldline_events.lifecycle,
    worldline_events.confidence,
    worldline_events.involved_agent_ids_jsonb,
    worldline_events.state_changes_jsonb,
    worldline_events.source_run_id,
    worldline_events.created_by,
    worldline_events.created_at,
    worldline_events.updated_at
),
adoption_insert AS (
  INSERT INTO worldline_event_adoptions (
    tenant_id,
    adoption_id,
    event_id,
    session_id,
    project_id,
    from_status,
    to_status,
    note,
    adopted_by
  )
  SELECT
    candidate_scope.tenant_id,
    $3::uuid,
    candidate_scope.event_id,
    candidate_scope.session_id,
    candidate_scope.project_id,
    candidate_scope.from_status,
    'canon',
    $5,
    NULLIF($4, '')::uuid
  FROM candidate_scope
  JOIN updated_event
    ON updated_event.event_id = candidate_scope.event_id
  RETURNING adoption_id
),
workflow_event_insert AS (
  INSERT INTO workflow_events (
    tenant_id,
    event_id,
    run_id,
    workflow_type,
    project_id,
    event_type,
    sequence,
    payload_jsonb
  )
  SELECT
    candidate_scope.tenant_id,
    $6::uuid,
    candidate_scope.run_id,
    'worldline_session',
    candidate_scope.project_id,
    'worldline.event.adopted',
    COALESCE((
      SELECT MAX(sequence) + 1
      FROM workflow_events existing
      WHERE existing.tenant_id = candidate_scope.tenant_id
        AND existing.run_id = candidate_scope.run_id
    ), 1),
    $7::jsonb
  FROM candidate_scope
  JOIN adoption_insert
    ON true
  RETURNING 1
)
SELECT
  updated_event.event_id::text,
  updated_event.session_id::text,
  updated_event.project_id::text,
  updated_event.step,
  updated_event.title,
  updated_event.summary,
  updated_event.kind,
  updated_event.status,
  updated_event.lifecycle,
  COALESCE(updated_event.confidence::text, ''),
  COALESCE(updated_event.involved_agent_ids_jsonb, '[]'::jsonb)::text,
  COALESCE(updated_event.state_changes_jsonb, '{}'::jsonb)::text,
  COALESCE(updated_event.source_run_id::text, ''),
  COALESCE(updated_event.created_by::text, ''),
  updated_event.created_at::text,
  updated_event.updated_at::text
FROM updated_event
JOIN workflow_event_insert
  ON true`
}

type SQLVariableStoreConfig struct {
	Queryer SQLQueryer
	Execer  SQLExecer
	NewID   func() string
}

type SQLVariableStore struct {
	queryer SQLQueryer
	execer  SQLExecer
	newID   func() string
}

func NewSQLVariableStore(config SQLVariableStoreConfig) *SQLVariableStore {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLVariableStore{
		queryer: config.Queryer,
		execer:  config.Execer,
		newID:   newID,
	}
}

func (s *SQLVariableStore) InjectVariable(ctx context.Context, input InjectVariableInput) (VariableRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	sessionID := strings.TrimSpace(input.SessionID)
	name := strings.TrimSpace(input.Name)
	if tenantID == "" || sessionID == "" || name == "" {
		return VariableRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, session_id, and name are required"}
	}
	if s.queryer == nil && s.execer == nil {
		return VariableRecord{}, &AppError{Code: "WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED", Message: "worldline variable backend is not configured"}
	}
	variableID := s.newID()
	eventID := s.newID()
	description := strings.TrimSpace(input.Description)
	impactAxis := strings.TrimSpace(input.ImpactAxis)
	source := strings.TrimSpace(input.Source)
	if source == "" {
		source = "author"
	}
	actorUserID := strings.TrimSpace(input.ActorUserID)
	eventPayload, err := json.Marshal(map[string]any{
		"status":      "recorded",
		"lifecycle":   "active",
		"kind":        "variable",
		"title":       name,
		"summary":     description,
		"variable_id": variableID,
		"impact_axis": impactAxis,
		"locked":      input.Locked,
		"source":      source,
		"request_id":  strings.TrimSpace(input.RequestID),
	})
	if err != nil {
		return VariableRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "worldline variable payload must be JSON serializable"}
	}
	args := []any{
		tenantID,
		sessionID,
		variableID,
		name,
		description,
		impactAxis,
		input.Locked,
		source,
		actorUserID,
		eventID,
		string(eventPayload),
	}
	if s.queryer != nil {
		return s.injectVariableReturning(ctx, args)
	}
	result, err := s.execer.ExecContext(ctx, injectVariableExecQuery(), args...)
	if err != nil {
		return VariableRecord{}, &AppError{Code: "WORLDLINE_VARIABLE_WRITE_FAILED", Message: err.Error()}
	}
	if affected, err := result.RowsAffected(); err == nil && affected == 0 {
		return VariableRecord{}, &AppError{Code: "NOT_FOUND", Message: "worldline session not found"}
	}
	return VariableRecord{
		VariableID:  variableID,
		SessionID:   sessionID,
		Name:        name,
		Description: description,
		ImpactAxis:  impactAxis,
		Locked:      input.Locked,
		Source:      source,
		CreatedBy:   actorUserID,
	}, nil
}

func (s *SQLVariableStore) injectVariableReturning(ctx context.Context, args []any) (VariableRecord, error) {
	rows, err := s.queryer.QueryContext(ctx, injectVariableReturningQuery(), args...)
	if err != nil {
		return VariableRecord{}, &AppError{Code: "WORLDLINE_VARIABLE_WRITE_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return VariableRecord{}, &AppError{Code: "WORLDLINE_VARIABLE_WRITE_FAILED", Message: err.Error()}
		}
		return VariableRecord{}, &AppError{Code: "NOT_FOUND", Message: "worldline session not found"}
	}
	record, err := scanVariableRecord(rows)
	if err != nil {
		return VariableRecord{}, err
	}
	if err := rows.Err(); err != nil {
		return VariableRecord{}, &AppError{Code: "WORLDLINE_VARIABLE_WRITE_FAILED", Message: err.Error()}
	}
	return record, nil
}

func injectVariableReturningQuery() string {
	return injectVariableCTE() + `
SELECT
  variable_id::text,
  session_id::text,
  project_id::text,
  name,
  description,
  impact_axis,
  locked,
  source,
  COALESCE(created_by::text, ''),
  created_at::text,
  updated_at::text
FROM variable_insert
JOIN event_insert
  ON true`
}

func injectVariableExecQuery() string {
	return injectVariableCTE() + `
SELECT 1 FROM event_insert`
}

func injectVariableCTE() string {
	return `WITH session_scope AS (
  SELECT
    s.tenant_id,
    s.project_id,
    s.session_id,
    s.run_id
  FROM (SELECT 1) input
  JOIN worldline_sessions s
    ON s.tenant_id::text = $1
   AND s.session_id::text = $2
  LIMIT 1
),
variable_insert AS (
  INSERT INTO worldline_variables (
    tenant_id,
    variable_id,
    session_id,
    project_id,
    name,
    description,
    impact_axis,
    locked,
    source,
    created_by
  )
  SELECT
    session_scope.tenant_id,
    $3::uuid,
    session_scope.session_id,
    session_scope.project_id,
    $4,
    $5,
    $6,
    $7,
    $8,
    NULLIF($9, '')::uuid
  FROM session_scope
  RETURNING
    variable_id,
    session_id,
    project_id,
    name,
    description,
    impact_axis,
    locked,
    source,
    created_by,
    created_at,
    updated_at
),
event_insert AS (
  INSERT INTO workflow_events (
    tenant_id,
    event_id,
    run_id,
    workflow_type,
    project_id,
    event_type,
    sequence,
    payload_jsonb
  )
  SELECT
    session_scope.tenant_id,
    $10::uuid,
    session_scope.run_id,
    'worldline_session',
    session_scope.project_id,
    'worldline.variable.injected',
    COALESCE((
      SELECT MAX(sequence) + 1
      FROM workflow_events existing
      WHERE existing.tenant_id = session_scope.tenant_id
        AND existing.run_id = session_scope.run_id
    ), 1),
    $11::jsonb
  FROM session_scope
  JOIN variable_insert
    ON variable_insert.session_id = session_scope.session_id
  RETURNING 1
)`
}

func scanVariableRecord(rows SQLRows) (VariableRecord, error) {
	var record VariableRecord
	if err := rows.Scan(
		&record.VariableID,
		&record.SessionID,
		&record.ProjectID,
		&record.Name,
		&record.Description,
		&record.ImpactAxis,
		&record.Locked,
		&record.Source,
		&record.CreatedBy,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return VariableRecord{}, &AppError{Code: "WORLDLINE_VARIABLE_WRITE_FAILED", Message: err.Error()}
	}
	return record, nil
}

func NewSQLPreparationStore(config SQLPreparationStoreConfig) *SQLPreparationStore {
	limit := config.Limit
	if limit <= 0 {
		limit = 50
	}
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLPreparationStore{
		queryer: config.Queryer,
		execer:  config.Execer,
		limit:   limit,
		newID:   newID,
	}
}

func (s *SQLPreparationStore) CreatePreparation(ctx context.Context, input CreatePreparationInput) (PreparationRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	goal := strings.TrimSpace(input.Goal)
	if tenantID == "" || projectID == "" || goal == "" {
		return PreparationRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and goal are required"}
	}
	if s.execer == nil {
		return PreparationRecord{}, &AppError{Code: "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED", Message: "worldline preparation backend is not configured"}
	}
	runID := s.newID()
	prepareID := s.newID()
	eventID := s.newID()
	traceID := "trace_" + runID
	status := "queued"
	lifecycle := "preparing"
	anchorPathID := strings.TrimSpace(input.AnchorPathID)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	eventPayload, err := json.Marshal(map[string]any{
		"status":         status,
		"workflow_type":  "worldline_preparation",
		"request_id":     strings.TrimSpace(input.RequestID),
		"trace_id":       traceID,
		"prepare_id":     prepareID,
		"anchor_path_id": anchorPathID,
	})
	if err != nil {
		return PreparationRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "worldline preparation admission payload must be JSON serializable"}
	}
	query := `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id,
    run_id,
    workflow_type,
    project_id,
    status,
    progress,
    message,
    started_by,
    temporal_workflow_id
  )
  VALUES (
    $1::uuid,
    $3::uuid,
    'worldline_preparation',
    $2::uuid,
    $5,
    0,
    'queued',
    NULLIF($8, '')::uuid,
    ''
  )
  RETURNING run_id
),
preparation_insert AS (
  INSERT INTO worldline_preparations (
    tenant_id,
    prepare_id,
    project_id,
    run_id,
    status,
    lifecycle,
    goal_summary,
    anchor_path_id,
    created_by
  )
  SELECT
    $1::uuid,
    $4::uuid,
    $2::uuid,
    workflow_insert.run_id,
    $5,
    $6,
    $7,
    NULLIF($9, '')::uuid,
    NULLIF($8, '')::uuid
  FROM workflow_insert
  RETURNING prepare_id, run_id, project_id
)
INSERT INTO workflow_events (
  tenant_id,
  event_id,
  run_id,
  workflow_type,
  project_id,
  event_type,
  sequence,
  payload_jsonb
)
SELECT
  $1::uuid,
  $10::uuid,
  preparation_insert.run_id,
  'worldline_preparation',
  preparation_insert.project_id,
  'workflow.queued',
  1,
  $11::jsonb
FROM preparation_insert`
	_, err = s.execer.ExecContext(
		ctx,
		query,
		tenantID,
		projectID,
		runID,
		prepareID,
		status,
		lifecycle,
		goal,
		actorUserID,
		anchorPathID,
		eventID,
		string(eventPayload),
	)
	if err != nil {
		return PreparationRecord{}, &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	return PreparationRecord{
		PrepareID:    prepareID,
		RunID:        runID,
		ProjectID:    projectID,
		WorkflowType: "worldline_preparation",
		Status:       status,
		Lifecycle:    lifecycle,
		GoalSummary:  goal,
		AnchorPathID: anchorPathID,
		CreatedBy:    actorUserID,
	}, nil
}

func (s *SQLPreparationStore) GetPreparation(ctx context.Context, input GetPreparationInput) (PreparationRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	prepareID := strings.TrimSpace(input.PrepareID)
	if tenantID == "" || prepareID == "" {
		return PreparationRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and prepare_id are required"}
	}
	if s.queryer == nil {
		return PreparationRecord{}, &AppError{Code: "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED", Message: "worldline preparation backend is not configured"}
	}
	query := preparationRecordSelectQuery() + `
WHERE tenant_id::text = $1
  AND prepare_id::text = $2
LIMIT 1`
	rows, err := s.queryer.QueryContext(ctx, query, tenantID, prepareID)
	if err != nil {
		return PreparationRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return PreparationRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
		}
		return PreparationRecord{}, &AppError{Code: "NOT_FOUND", Message: "worldline preparation not found"}
	}
	record, err := scanPreparationRecord(rows)
	if err != nil {
		return PreparationRecord{}, err
	}
	return record, nil
}

func (s *SQLPreparationStore) ListPreparedAgents(ctx context.Context, input ListPreparedAgentsInput) ([]PreparedAgentRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	prepareID := strings.TrimSpace(input.PrepareID)
	if tenantID == "" || prepareID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and prepare_id are required"}
	}
	if s.queryer == nil {
		return nil, &AppError{Code: "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED", Message: "worldline preparation backend is not configured"}
	}
	query := `
SELECT
  agent_id::text,
  prepare_id::text,
  project_id::text,
  display_name,
  role,
  status,
  COALESCE(source_asset_id::text, ''),
  summary,
  created_at::text,
  updated_at::text
FROM worldline_prepared_agents
WHERE tenant_id::text = $1
  AND prepare_id::text = $2
ORDER BY updated_at DESC, created_at DESC
LIMIT $3`
	rows, err := s.queryer.QueryContext(ctx, query, tenantID, prepareID, s.limit)
	if err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	records := []PreparedAgentRecord{}
	for rows.Next() {
		record, err := scanPreparedAgentRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func preparationRecordSelectQuery() string {
	return `
SELECT
  prepare_id::text,
  run_id::text,
  project_id::text,
  'worldline_preparation',
  status,
  lifecycle,
  goal_summary,
  COALESCE(anchor_path_id::text, ''),
  COALESCE(created_by::text, ''),
  created_at::text,
  updated_at::text
FROM worldline_preparations
`
}

func scanPreparationRecord(rows SQLRows) (PreparationRecord, error) {
	var record PreparationRecord
	if err := rows.Scan(
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
	); err != nil {
		return PreparationRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return record, nil
}

func scanPreparedAgentRecord(rows SQLRows) (PreparedAgentRecord, error) {
	var record PreparedAgentRecord
	if err := rows.Scan(
		&record.AgentID,
		&record.PrepareID,
		&record.ProjectID,
		&record.DisplayName,
		&record.Role,
		&record.Status,
		&record.SourceAssetID,
		&record.Summary,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return PreparedAgentRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	return record, nil
}

func newUUID() string {
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return ""
	}
	bytes[6] = (bytes[6] & 0x0f) | 0x40
	bytes[8] = (bytes[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", bytes[0:4], bytes[4:6], bytes[6:8], bytes[8:10], bytes[10:16])
}
