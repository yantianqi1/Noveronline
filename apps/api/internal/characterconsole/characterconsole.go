package characterconsole

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type CreateInteractionInput struct {
	TenantID           string
	ProjectID          string
	ActorUserID        string
	RequestID          string
	WorldlineSessionID string
	AnchorType         string
	AnchorID           string
	POVAgentID         string
	Mode               string
	Title              string
	Summary            string
	Metadata           map[string]any
}

type ListInteractionsInput struct {
	TenantID  string
	ProjectID string
	Status    string
}

type GetInteractionInput struct {
	TenantID      string
	InteractionID string
}

type UpdateInteractionStatusInput struct {
	TenantID      string
	InteractionID string
	ActorUserID   string
	RequestID     string
	Status        string
}

type AppendTurnInput struct {
	TenantID        string
	InteractionID   string
	ActorUserID     string
	RequestID       string
	ActorType       string
	ActorID         string
	TurnKind        string
	Summary         string
	Action          map[string]any
	WorldStateDelta map[string]any
	TraceID         string
}

type ListTurnsInput struct {
	TenantID      string
	InteractionID string
}

type ListEventsInput struct {
	TenantID      string
	InteractionID string
	AfterEventID  string
}

type InteractionRecord struct {
	InteractionID      string         `json:"interaction_id"`
	ProjectID          string         `json:"project_id"`
	WorldlineSessionID string         `json:"worldline_session_id"`
	AnchorType         string         `json:"anchor_type"`
	AnchorID           string         `json:"anchor_id"`
	POVAgentID         string         `json:"pov_agent_id"`
	Mode               string         `json:"mode"`
	Status             string         `json:"status"`
	Title              string         `json:"title"`
	Summary            string         `json:"summary"`
	Metadata           map[string]any `json:"metadata"`
	CreatedBy          string         `json:"created_by"`
	CreatedAt          string         `json:"created_at"`
	UpdatedAt          string         `json:"updated_at"`
}

type TurnRecord struct {
	TurnID          string         `json:"turn_id"`
	InteractionID   string         `json:"interaction_id"`
	ProjectID       string         `json:"project_id"`
	TurnOrder       int            `json:"turn_order"`
	ActorType       string         `json:"actor_type"`
	ActorID         string         `json:"actor_id"`
	TurnKind        string         `json:"turn_kind"`
	Summary         string         `json:"summary"`
	Action          map[string]any `json:"action"`
	WorldStateDelta map[string]any `json:"world_state_delta"`
	TraceID         string         `json:"trace_id"`
	CreatedBy       string         `json:"created_by"`
	CreatedAt       string         `json:"created_at"`
}

type EventRecord struct {
	EventID       string         `json:"event_id"`
	InteractionID string         `json:"interaction_id"`
	Sequence      int            `json:"sequence"`
	EventType     string         `json:"event_type"`
	Payload       map[string]any `json:"payload"`
	CreatedAt     string         `json:"created_at"`
}

type Store interface {
	CreateInteraction(context.Context, CreateInteractionInput) (InteractionRecord, error)
	ListInteractions(context.Context, ListInteractionsInput) ([]InteractionRecord, error)
	GetInteraction(context.Context, GetInteractionInput) (InteractionRecord, error)
	UpdateInteractionStatus(context.Context, UpdateInteractionStatusInput) (InteractionRecord, error)
	AppendTurn(context.Context, AppendTurnInput) (TurnRecord, error)
	ListTurns(context.Context, ListTurnsInput) ([]TurnRecord, error)
	ListEvents(context.Context, ListEventsInput) ([]EventRecord, error)
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
	return "CHARACTER_INTERACTION_QUERY_FAILED"
}

type DisabledStore struct{}

func NewDisabledStore() *DisabledStore {
	return &DisabledStore{}
}

func (s *DisabledStore) CreateInteraction(context.Context, CreateInteractionInput) (InteractionRecord, error) {
	return InteractionRecord{}, backendUnconfigured()
}

func (s *DisabledStore) ListInteractions(context.Context, ListInteractionsInput) ([]InteractionRecord, error) {
	return nil, backendUnconfigured()
}

func (s *DisabledStore) GetInteraction(context.Context, GetInteractionInput) (InteractionRecord, error) {
	return InteractionRecord{}, backendUnconfigured()
}

func (s *DisabledStore) UpdateInteractionStatus(context.Context, UpdateInteractionStatusInput) (InteractionRecord, error) {
	return InteractionRecord{}, backendUnconfigured()
}

func (s *DisabledStore) AppendTurn(context.Context, AppendTurnInput) (TurnRecord, error) {
	return TurnRecord{}, backendUnconfigured()
}

func (s *DisabledStore) ListTurns(context.Context, ListTurnsInput) ([]TurnRecord, error) {
	return nil, backendUnconfigured()
}

func (s *DisabledStore) ListEvents(context.Context, ListEventsInput) ([]EventRecord, error) {
	return nil, backendUnconfigured()
}

func backendUnconfigured() error {
	return &AppError{
		Code:    "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED",
		Message: "character interaction backend is not configured",
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

type SQLTenantQueryer interface {
	QueryTenantContext(context.Context, string, string, ...any) (SQLRows, error)
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

func (q *SQLDBQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	tx, err := q.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULL::uuid, false)", strings.TrimSpace(tenantID)); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, query, args...)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return &tenantScopedRows{rows: rows, tx: tx}, nil
}

func (q *SQLDBQueryer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	return q.db.ExecContext(ctx, query, args...)
}

type tenantScopedRows struct {
	rows SQLRows
	tx   *sql.Tx
}

func (r *tenantScopedRows) Next() bool {
	return r.rows.Next()
}

func (r *tenantScopedRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *tenantScopedRows) Close() error {
	closeErr := r.rows.Close()
	rowsErr := r.rows.Err()
	if closeErr != nil || rowsErr != nil {
		_ = r.tx.Rollback()
		if closeErr != nil {
			return closeErr
		}
		return rowsErr
	}
	return r.tx.Commit()
}

func (r *tenantScopedRows) Abort() error {
	closeErr := r.rows.Close()
	rollbackErr := r.tx.Rollback()
	if closeErr != nil {
		return closeErr
	}
	return rollbackErr
}

func (r *tenantScopedRows) Err() error {
	return r.rows.Err()
}

type SQLStoreConfig struct {
	Queryer SQLQueryer
	Execer  SQLExecer
	Limit   int
	NewID   func() string
}

type SQLStore struct {
	queryer SQLQueryer
	execer  SQLExecer
	limit   int
	newID   func() string
}

func NewSQLStore(config SQLStoreConfig) *SQLStore {
	limit := config.Limit
	if limit <= 0 {
		limit = 50
	}
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLStore{
		queryer: config.Queryer,
		execer:  config.Execer,
		limit:   limit,
		newID:   newID,
	}
}

func (s *SQLStore) queryRows(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := s.queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return s.queryer.QueryContext(ctx, query, args...)
}

func (s *SQLStore) CreateInteraction(ctx context.Context, input CreateInteractionInput) (InteractionRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return InteractionRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	mode, err := allowedCharacterInteractionMode(input.Mode)
	if err != nil {
		return InteractionRecord{}, err
	}
	anchorType, err := allowedCharacterInteractionAnchorType(input.AnchorType)
	if err != nil {
		return InteractionRecord{}, err
	}
	metadata, err := encodePublicJSON(input.Metadata)
	if err != nil {
		return InteractionRecord{}, err
	}
	rows, err := s.queryRows(ctx, tenantID, `
WITH scoped_project AS (
  SELECT $2::uuid AS project_id
  WHERE NULLIF($4::text, '') IS NULL
  UNION ALL
  SELECT project_id
  FROM worldline_sessions
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND session_id = NULLIF($4::text, '')::uuid
)
INSERT INTO character_interaction_sessions (
  tenant_id,
  interaction_id,
  project_id,
  worldline_session_id,
  anchor_type,
  anchor_id,
  pov_agent_id,
  mode,
  status,
  title,
  summary,
  metadata_jsonb,
  created_by,
  created_at,
  updated_at
)
SELECT
  $1::uuid,
  $3::uuid,
  scoped_project.project_id,
  NULLIF($4, '')::uuid,
  $5,
  $6,
  $7,
  $8,
  'active',
  $9,
  $10,
  $11::jsonb,
  NULLIF($12, '')::uuid,
  NOW(),
  NOW()
FROM scoped_project
LIMIT 1
RETURNING interaction_id::text, project_id::text, COALESCE(worldline_session_id::text, ''), anchor_type, anchor_id, pov_agent_id, mode, status, title, summary, metadata_jsonb::text, COALESCE(created_by::text, ''), created_at::text, updated_at::text
`, tenantID, projectID, s.newID(), strings.TrimSpace(input.WorldlineSessionID), anchorType, strings.TrimSpace(input.AnchorID), strings.TrimSpace(input.POVAgentID), mode, strings.TrimSpace(input.Title), strings.TrimSpace(input.Summary), metadata, strings.TrimSpace(input.ActorUserID))
	if err != nil {
		return InteractionRecord{}, &AppError{Code: "CHARACTER_INTERACTION_QUERY_FAILED", Message: "character interaction query failed"}
	}
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return InteractionRecord{}, characterInteractionQueryFailed("character interaction query failed")
		}
		if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
			return InteractionRecord{}, err
		}
		return InteractionRecord{}, &AppError{Code: "NOT_FOUND", Message: "character interaction anchor was not found"}
	}
	record, err := scanInteraction(rows)
	if err != nil {
		_ = abortCharacterConsoleRows(rows)
		return InteractionRecord{}, err
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return InteractionRecord{}, characterInteractionQueryFailed("character interaction query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
		return InteractionRecord{}, err
	}
	return record, nil
}

func (s *SQLStore) ListInteractions(ctx context.Context, input ListInteractionsInput) ([]InteractionRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	status, err := allowedCharacterInteractionStatusFilter(input.Status)
	if err != nil {
		return nil, err
	}
	rows, err := s.queryRows(ctx, tenantID, `
SELECT interaction_id::text, project_id::text, COALESCE(worldline_session_id::text, ''), anchor_type, anchor_id, pov_agent_id, mode, status, title, summary, metadata_jsonb::text, COALESCE(created_by::text, ''), created_at::text, updated_at::text
FROM character_interaction_sessions
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND ($3 = '' OR status = $3)
ORDER BY updated_at DESC
LIMIT $4
`, tenantID, projectID, status, s.limit)
	if err != nil {
		return nil, &AppError{Code: "CHARACTER_INTERACTION_QUERY_FAILED", Message: "character interaction query failed"}
	}
	records := []InteractionRecord{}
	for rows.Next() {
		record, err := scanInteraction(rows)
		if err != nil {
			_ = abortCharacterConsoleRows(rows)
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, characterInteractionQueryFailed("character interaction query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
		return nil, err
	}
	return records, nil
}

func (s *SQLStore) GetInteraction(ctx context.Context, input GetInteractionInput) (InteractionRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	interactionID := strings.TrimSpace(input.InteractionID)
	if tenantID == "" || interactionID == "" {
		return InteractionRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and interaction_id are required"}
	}
	rows, err := s.queryRows(ctx, tenantID, `
SELECT interaction_id::text, project_id::text, COALESCE(worldline_session_id::text, ''), anchor_type, anchor_id, pov_agent_id, mode, status, title, summary, metadata_jsonb::text, COALESCE(created_by::text, ''), created_at::text, updated_at::text
FROM character_interaction_sessions
WHERE tenant_id::text = $1
  AND interaction_id::text = $2
LIMIT 1
`, tenantID, interactionID)
	if err != nil {
		return InteractionRecord{}, &AppError{Code: "CHARACTER_INTERACTION_QUERY_FAILED", Message: "character interaction query failed"}
	}
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return InteractionRecord{}, characterInteractionQueryFailed("character interaction query failed")
		}
		if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
			return InteractionRecord{}, err
		}
		return InteractionRecord{}, &AppError{Code: "NOT_FOUND", Message: "character interaction was not found"}
	}
	record, err := scanInteraction(rows)
	if err != nil {
		_ = abortCharacterConsoleRows(rows)
		return InteractionRecord{}, err
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return InteractionRecord{}, characterInteractionQueryFailed("character interaction query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
		return InteractionRecord{}, err
	}
	return record, nil
}

func (s *SQLStore) UpdateInteractionStatus(ctx context.Context, input UpdateInteractionStatusInput) (InteractionRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	interactionID := strings.TrimSpace(input.InteractionID)
	if tenantID == "" || interactionID == "" {
		return InteractionRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and interaction_id are required"}
	}
	status, err := allowedCharacterInteractionStatus(input.Status)
	if err != nil {
		return InteractionRecord{}, err
	}
	rows, err := s.queryRows(ctx, tenantID, `
UPDATE character_interaction_sessions
SET status = $3,
    updated_at = NOW()
WHERE tenant_id::text = $1
  AND interaction_id::text = $2
RETURNING interaction_id::text, project_id::text, COALESCE(worldline_session_id::text, ''), anchor_type, anchor_id, pov_agent_id, mode, status, title, summary, metadata_jsonb::text, COALESCE(created_by::text, ''), created_at::text, updated_at::text
`, tenantID, interactionID, status)
	if err != nil {
		return InteractionRecord{}, &AppError{Code: "CHARACTER_INTERACTION_QUERY_FAILED", Message: "character interaction query failed"}
	}
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return InteractionRecord{}, characterInteractionQueryFailed("character interaction query failed")
		}
		if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
			return InteractionRecord{}, err
		}
		return InteractionRecord{}, &AppError{Code: "NOT_FOUND", Message: "character interaction was not found"}
	}
	record, err := scanInteraction(rows)
	if err != nil {
		_ = abortCharacterConsoleRows(rows)
		return InteractionRecord{}, err
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return InteractionRecord{}, characterInteractionQueryFailed("character interaction query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
		return InteractionRecord{}, err
	}
	return record, nil
}

func (s *SQLStore) AppendTurn(ctx context.Context, input AppendTurnInput) (TurnRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	interactionID := strings.TrimSpace(input.InteractionID)
	if tenantID == "" || interactionID == "" {
		return TurnRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and interaction_id are required"}
	}
	actorType, err := allowedCharacterInteractionActorType(input.ActorType)
	if err != nil {
		return TurnRecord{}, err
	}
	turnKind, err := allowedCharacterInteractionTurnKind(input.TurnKind)
	if err != nil {
		return TurnRecord{}, err
	}
	action, err := encodePublicJSON(input.Action)
	if err != nil {
		return TurnRecord{}, err
	}
	delta, err := encodePublicJSON(input.WorldStateDelta)
	if err != nil {
		return TurnRecord{}, err
	}
	rows, err := s.queryRows(ctx, tenantID, `
WITH scoped_interaction AS (
  SELECT project_id
  FROM character_interaction_sessions
  WHERE tenant_id = $1::uuid
    AND interaction_id = $2::uuid
),
turn_lock AS (
  SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':' || $2::text, 0))
),
next_turn AS (
  SELECT COALESCE(MAX(turn_order), 0) + 1 AS turn_order
  FROM character_interaction_turns
  CROSS JOIN turn_lock
  WHERE tenant_id = $1::uuid
    AND interaction_id = $2::uuid
)
INSERT INTO character_interaction_turns (
  tenant_id,
  turn_id,
  interaction_id,
  project_id,
  turn_order,
  actor_type,
  actor_id,
  turn_kind,
  summary,
  action_jsonb,
  world_state_delta_jsonb,
  trace_id,
  created_by,
  created_at
)
SELECT
  $1::uuid,
  $3::uuid,
  $2::uuid,
  scoped_interaction.project_id,
  next_turn.turn_order,
  $4,
  $5,
  $6,
  $7,
  $8::jsonb,
  $9::jsonb,
  $10,
  NULLIF($11, '')::uuid,
  NOW()
FROM scoped_interaction, next_turn
RETURNING turn_id::text, interaction_id::text, project_id::text, turn_order, actor_type, actor_id, turn_kind, summary, action_jsonb::text, world_state_delta_jsonb::text, trace_id, COALESCE(created_by::text, ''), created_at::text
`, tenantID, interactionID, s.newID(), actorType, strings.TrimSpace(input.ActorID), turnKind, strings.TrimSpace(input.Summary), action, delta, strings.TrimSpace(input.TraceID), strings.TrimSpace(input.ActorUserID))
	if err != nil {
		return TurnRecord{}, &AppError{Code: "CHARACTER_INTERACTION_QUERY_FAILED", Message: "character interaction turn query failed"}
	}
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return TurnRecord{}, characterInteractionQueryFailed("character interaction turn query failed")
		}
		if err := closeCharacterConsoleRows(rows, "character interaction turn query failed"); err != nil {
			return TurnRecord{}, err
		}
		return TurnRecord{}, &AppError{Code: "NOT_FOUND", Message: "character interaction was not found"}
	}
	record, err := scanTurn(rows)
	if err != nil {
		_ = abortCharacterConsoleRows(rows)
		return TurnRecord{}, err
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return TurnRecord{}, characterInteractionQueryFailed("character interaction turn query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction turn query failed"); err != nil {
		return TurnRecord{}, err
	}
	return record, nil
}

func (s *SQLStore) ListTurns(ctx context.Context, input ListTurnsInput) ([]TurnRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	interactionID := strings.TrimSpace(input.InteractionID)
	if tenantID == "" || interactionID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and interaction_id are required"}
	}
	if err := s.ensureInteractionExists(ctx, tenantID, interactionID); err != nil {
		return nil, err
	}
	rows, err := s.queryRows(ctx, tenantID, `
SELECT turn_id::text, interaction_id::text, project_id::text, turn_order, actor_type, actor_id, turn_kind, summary, action_jsonb::text, world_state_delta_jsonb::text, trace_id, COALESCE(created_by::text, ''), created_at::text
FROM character_interaction_turns
WHERE tenant_id::text = $1
  AND interaction_id::text = $2
ORDER BY turn_order ASC
`, tenantID, interactionID)
	if err != nil {
		return nil, &AppError{Code: "CHARACTER_INTERACTION_QUERY_FAILED", Message: "character interaction turn query failed"}
	}
	records := []TurnRecord{}
	for rows.Next() {
		record, err := scanTurn(rows)
		if err != nil {
			_ = abortCharacterConsoleRows(rows)
			return nil, err
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, characterInteractionQueryFailed("character interaction turn query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction turn query failed"); err != nil {
		return nil, err
	}
	return records, nil
}

func (s *SQLStore) ListEvents(ctx context.Context, input ListEventsInput) ([]EventRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	interactionID := strings.TrimSpace(input.InteractionID)
	afterEventID := strings.TrimSpace(input.AfterEventID)
	if tenantID == "" || interactionID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and interaction_id are required"}
	}
	rows, err := s.queryRows(ctx, tenantID, `
WITH after_cursor AS (
  SELECT created_at, event_id
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND workflow_type = 'character_dialogue'
    AND payload_jsonb->>'interaction_id' = $2
    AND event_id::text = $3
  LIMIT 1
),
cursor_state AS (
  SELECT ($3 = '' OR EXISTS (SELECT 1 FROM after_cursor)) AS cursor_found
),
event_rows AS (
  SELECT event_id::text, sequence, event_type, payload_jsonb::text, created_at::text
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND workflow_type = 'character_dialogue'
    AND payload_jsonb->>'interaction_id' = $2
    AND (
      $3 = '' OR (created_at, event_id) > (
        SELECT created_at, event_id FROM after_cursor
      )
    )
  ORDER BY created_at, event_id
  LIMIT $4
)
SELECT cursor_state.cursor_found, event_rows.event_id, event_rows.sequence,
       event_rows.event_type, event_rows.payload_jsonb, event_rows.created_at
FROM cursor_state
LEFT JOIN event_rows ON true
ORDER BY event_rows.created_at NULLS LAST, event_rows.event_id NULLS LAST`,
		tenantID, interactionID, afterEventID, s.limit,
	)
	if err != nil {
		return nil, characterInteractionQueryFailed("character interaction event query failed")
	}

	records := []EventRecord{}
	for rows.Next() {
		var cursorFound bool
		var eventID sql.NullString
		var sequence sql.NullInt64
		var eventType sql.NullString
		var payloadJSON sql.NullString
		var createdAt sql.NullString
		if err := rows.Scan(&cursorFound, &eventID, &sequence, &eventType, &payloadJSON, &createdAt); err != nil {
			_ = abortCharacterConsoleRows(rows)
			return nil, characterInteractionQueryFailed("character interaction event query failed")
		}
		if !cursorFound {
			_ = abortCharacterConsoleRows(rows)
			return nil, &AppError{Code: "EVENT_CURSOR_NOT_FOUND", Message: "character interaction event cursor was not found"}
		}
		if !eventID.Valid {
			continue
		}
		records = append(records, EventRecord{
			EventID:       eventID.String,
			InteractionID: interactionID,
			Sequence:      int(sequence.Int64),
			EventType:     eventType.String,
			Payload:       decodeMap(payloadJSON.String),
			CreatedAt:     createdAt.String,
		})
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, characterInteractionQueryFailed("character interaction event query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction event query failed"); err != nil {
		return nil, err
	}
	return records, nil
}

func (s *SQLStore) ensureInteractionExists(ctx context.Context, tenantID string, interactionID string) error {
	rows, err := s.queryRows(ctx, tenantID, `
SELECT interaction_id::text
FROM character_interaction_sessions
WHERE tenant_id::text = $1
  AND interaction_id::text = $2
`, tenantID, interactionID)
	if err != nil {
		return characterInteractionQueryFailed("character interaction query failed")
	}
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			_ = rows.Close()
			return characterInteractionQueryFailed("character interaction query failed")
		}
		if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
			return err
		}
		return &AppError{Code: "NOT_FOUND", Message: "character interaction was not found"}
	}
	var foundInteractionID string
	if err := rows.Scan(&foundInteractionID); err != nil {
		_ = abortCharacterConsoleRows(rows)
		return characterInteractionQueryFailed("character interaction query failed")
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return characterInteractionQueryFailed("character interaction query failed")
	}
	if err := closeCharacterConsoleRows(rows, "character interaction query failed"); err != nil {
		return err
	}
	return nil
}

func scanInteraction(rows SQLRows) (InteractionRecord, error) {
	var record InteractionRecord
	var metadata string
	if err := rows.Scan(
		&record.InteractionID,
		&record.ProjectID,
		&record.WorldlineSessionID,
		&record.AnchorType,
		&record.AnchorID,
		&record.POVAgentID,
		&record.Mode,
		&record.Status,
		&record.Title,
		&record.Summary,
		&metadata,
		&record.CreatedBy,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return InteractionRecord{}, characterInteractionQueryFailed("character interaction query failed")
	}
	record.Metadata = decodeMap(metadata)
	return record, nil
}

func scanTurn(rows SQLRows) (TurnRecord, error) {
	var record TurnRecord
	var action string
	var delta string
	if err := rows.Scan(
		&record.TurnID,
		&record.InteractionID,
		&record.ProjectID,
		&record.TurnOrder,
		&record.ActorType,
		&record.ActorID,
		&record.TurnKind,
		&record.Summary,
		&action,
		&delta,
		&record.TraceID,
		&record.CreatedBy,
		&record.CreatedAt,
	); err != nil {
		return TurnRecord{}, characterInteractionQueryFailed("character interaction turn query failed")
	}
	record.Action = decodeMap(action)
	record.WorldStateDelta = decodeMap(delta)
	return record, nil
}

func encodePublicJSON(value map[string]any) (string, error) {
	if value == nil {
		return "{}", nil
	}
	encoded, err := json.Marshal(sanitizeMap(value))
	if err != nil {
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "metadata must be valid JSON"}
	}
	return string(encoded), nil
}

func characterInteractionQueryFailed(message string) error {
	return &AppError{Code: "CHARACTER_INTERACTION_QUERY_FAILED", Message: message}
}

func closeCharacterConsoleRows(rows SQLRows, message string) error {
	if err := rows.Close(); err != nil {
		return characterInteractionQueryFailed(message)
	}
	return nil
}

func abortCharacterConsoleRows(rows SQLRows) error {
	if abortable, ok := rows.(interface{ Abort() error }); ok {
		return abortable.Abort()
	}
	return rows.Close()
}

func decodeMap(value string) map[string]any {
	decoded := map[string]any{}
	if strings.TrimSpace(value) == "" {
		return decoded
	}
	if err := json.Unmarshal([]byte(value), &decoded); err != nil {
		return map[string]any{}
	}
	return sanitizeMap(decoded)
}

func sanitizeMap(value map[string]any) map[string]any {
	clean := map[string]any{}
	for key, item := range value {
		if isHighRiskField(strings.ToLower(strings.TrimSpace(key))) {
			continue
		}
		clean[key] = sanitizeValue(item)
	}
	return clean
}

func sanitizeValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeMap(typed)
	case []any:
		values := make([]any, 0, len(typed))
		for _, item := range typed {
			values = append(values, sanitizeValue(item))
		}
		return values
	default:
		return value
	}
}

func isHighRiskField(field string) bool {
	switch field {
	case "input_text", "output_text", "body_text", "content_text", "material_text", "source_material", "source_text", "prompt", "response", "body", "content", "raw_body", "raw_content", "raw_text", "api_key", "apikey", "encrypted_api_key", "credential_ref", "candidate_body", "candidate_event_body", "event_body", "draft", "manuscript":
		return true
	default:
		return false
	}
}

func defaultString(value string, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	return value
}

func allowedCharacterInteractionMode(value string) (string, error) {
	mode := defaultString(value, "first_person")
	switch mode {
	case "first_person", "director_assisted", "dialogue", "replay":
		return mode, nil
	default:
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "character interaction mode is not supported"}
	}
}

func allowedCharacterInteractionAnchorType(value string) (string, error) {
	anchorType := strings.TrimSpace(value)
	switch anchorType {
	case "", "worldline_session", "worldline_event", "saved_path", "chapter", "scene", "graph_node", "plot_thread":
		return anchorType, nil
	default:
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "character interaction anchor_type is not supported"}
	}
}

func allowedCharacterInteractionStatusFilter(value string) (string, error) {
	status := strings.TrimSpace(value)
	switch status {
	case "", "active", "saved", "archived":
		return status, nil
	default:
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "character interaction status filter is not supported"}
	}
}

func allowedCharacterInteractionStatus(value string) (string, error) {
	status := strings.TrimSpace(value)
	switch status {
	case "active", "saved", "archived":
		return status, nil
	default:
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "character interaction status is not supported"}
	}
}

func allowedCharacterInteractionActorType(value string) (string, error) {
	actorType := defaultString(value, "user")
	switch actorType {
	case "user", "agent", "director", "system":
		return actorType, nil
	default:
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "character interaction actor_type is not supported"}
	}
}

func allowedCharacterInteractionTurnKind(value string) (string, error) {
	turnKind := defaultString(value, "action")
	switch turnKind {
	case "action", "dialogue", "thought", "director_note", "system_note":
		return turnKind, nil
	default:
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "character interaction turn_kind is not supported"}
	}
}

func newUUID() string {
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		panic(fmt.Errorf("generate uuid: %w", err))
	}
	bytes[6] = (bytes[6] & 0x0f) | 0x40
	bytes[8] = (bytes[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", bytes[0:4], bytes[4:6], bytes[6:8], bytes[8:10], bytes[10:16])
}
