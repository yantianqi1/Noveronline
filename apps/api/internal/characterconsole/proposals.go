package characterconsole

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
)

const characterProposalSourceKind = "character_dialogue"

type ListProposalsInput struct {
	TenantID      string
	ProjectID     string
	InteractionID string
	ActorUserID   string
}

type AdoptProposalInput struct {
	TenantID      string
	ProjectID     string
	InteractionID string
	AssetID       string
	ActorUserID   string
	RequestID     string
	Note          string
}

type RejectProposalInput struct {
	TenantID      string
	ProjectID     string
	InteractionID string
	AssetID       string
	ActorUserID   string
	RequestID     string
	Note          string
}

type ProposalRecord struct {
	AssetID       string `json:"asset_id"`
	ProjectID     string `json:"project_id"`
	InteractionID string `json:"interaction_id"`
	ProposalType  string `json:"proposal_type"`
	AssetType     string `json:"asset_type"`
	Lifecycle     string `json:"lifecycle"`
	Title         string `json:"title"`
	Summary       string `json:"summary"`
	TargetID      string `json:"target_id"`
	CreatedAt     string `json:"created_at"`
	UpdatedAt     string `json:"updated_at"`
}

type ProposalAdoption struct {
	AssetID       string `json:"asset_id"`
	ProjectID     string `json:"project_id"`
	InteractionID string `json:"interaction_id"`
	ProposalType  string `json:"proposal_type"`
	TargetID      string `json:"target_id"`
	Status        string `json:"status"`
}

type ProposalRejection struct {
	AssetID       string `json:"asset_id"`
	ProjectID     string `json:"project_id"`
	InteractionID string `json:"interaction_id"`
	ProposalType  string `json:"proposal_type"`
	Status        string `json:"status"`
}

type ProposalStore interface {
	ListProposals(context.Context, ListProposalsInput) ([]ProposalRecord, error)
	AdoptProposal(context.Context, AdoptProposalInput) (ProposalAdoption, error)
	RejectProposal(context.Context, RejectProposalInput) (ProposalRejection, error)
}

type DisabledProposalStore struct{}

func NewDisabledProposalStore() DisabledProposalStore { return DisabledProposalStore{} }

func (DisabledProposalStore) ListProposals(context.Context, ListProposalsInput) ([]ProposalRecord, error) {
	return nil, &AppError{Code: "CHARACTER_PROPOSAL_BACKEND_UNCONFIGURED", Message: "character proposal backend is not configured"}
}

func (DisabledProposalStore) AdoptProposal(context.Context, AdoptProposalInput) (ProposalAdoption, error) {
	return ProposalAdoption{}, &AppError{Code: "CHARACTER_PROPOSAL_BACKEND_UNCONFIGURED", Message: "character proposal backend is not configured"}
}

func (DisabledProposalStore) RejectProposal(context.Context, RejectProposalInput) (ProposalRejection, error) {
	return ProposalRejection{}, &AppError{Code: "CHARACTER_PROPOSAL_BACKEND_UNCONFIGURED", Message: "character proposal backend is not configured"}
}

type SQLProposalStore struct {
	db    *sql.DB
	limit int
}

func NewSQLProposalStore(db *sql.DB, limit int) *SQLProposalStore {
	if limit <= 0 {
		limit = 100
	}
	return &SQLProposalStore{db: db, limit: limit}
}

func (s *SQLProposalStore) ListProposals(ctx context.Context, input ListProposalsInput) ([]ProposalRecord, error) {
	input = normalizeListProposalsInput(input)
	if input.TenantID == "" || input.ProjectID == "" || input.InteractionID == "" || input.ActorUserID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, interaction_id, and actor_user_id are required"}
	}
	if s.db == nil {
		return nil, &AppError{Code: "CHARACTER_PROPOSAL_BACKEND_UNCONFIGURED", Message: "character proposal backend is not configured"}
	}
	tx, err := s.beginScopedTx(ctx, input.TenantID, input.ActorUserID)
	if err != nil {
		return nil, proposalQueryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	rows, err := tx.QueryContext(ctx, `SELECT
  asset_id::text,
  project_id::text,
  payload_jsonb->>'interaction_id',
  payload_jsonb->>'proposal_type',
  asset_type,
  lifecycle,
  title,
  COALESCE(summary, ''),
  COALESCE(payload_jsonb->>'target_id', ''),
  created_at::text,
  updated_at::text
FROM assets
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND source_kind = 'character_dialogue'
  AND payload_jsonb->>'interaction_id' = $3
  AND asset_type IN (
    'character_memory_proposal',
    'character_relation_proposal',
    'character_world_state_proposal'
  )
ORDER BY created_at, asset_id
LIMIT $4`, input.TenantID, input.ProjectID, input.InteractionID, s.limit)
	if err != nil {
		return nil, proposalQueryFailed()
	}
	defer rows.Close()
	records := []ProposalRecord{}
	for rows.Next() {
		var record ProposalRecord
		if err := rows.Scan(
			&record.AssetID, &record.ProjectID, &record.InteractionID,
			&record.ProposalType, &record.AssetType, &record.Lifecycle,
			&record.Title, &record.Summary, &record.TargetID,
			&record.CreatedAt, &record.UpdatedAt,
		); err != nil {
			return nil, proposalQueryFailed()
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, proposalQueryFailed()
	}
	if err := rows.Close(); err != nil {
		return nil, proposalQueryFailed()
	}
	if err := tx.Commit(); err != nil {
		return nil, proposalQueryFailed()
	}
	return records, nil
}

func (s *SQLProposalStore) AdoptProposal(ctx context.Context, input AdoptProposalInput) (ProposalAdoption, error) {
	input = normalizeAdoptProposalInput(input)
	if input.TenantID == "" || input.ProjectID == "" || input.InteractionID == "" || input.AssetID == "" || input.ActorUserID == "" {
		return ProposalAdoption{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, interaction_id, asset_id, and actor_user_id are required"}
	}
	if s.db == nil {
		return ProposalAdoption{}, &AppError{Code: "CHARACTER_PROPOSAL_BACKEND_UNCONFIGURED", Message: "character proposal backend is not configured"}
	}
	tx, err := s.beginScopedTx(ctx, input.TenantID, input.ActorUserID)
	if err != nil {
		return ProposalAdoption{}, proposalAdoptionFailed()
	}
	defer func() { _ = tx.Rollback() }()

	proposal, payload, err := lockProposal(ctx, tx, input)
	if err != nil {
		return ProposalAdoption{}, err
	}
	if proposal.Lifecycle != "candidate" {
		return ProposalAdoption{}, &AppError{Code: "CHARACTER_PROPOSAL_ALREADY_ADOPTED", Message: "character proposal is no longer a candidate"}
	}
	targetID, err := adoptProposalTarget(ctx, tx, input, proposal, payload)
	if err != nil {
		return ProposalAdoption{}, err
	}
	result, err := finalizeProposalAdoption(ctx, tx, input, proposal, targetID)
	if err != nil {
		return ProposalAdoption{}, err
	}
	if err := tx.Commit(); err != nil {
		return ProposalAdoption{}, proposalAdoptionFailed()
	}
	return result, nil
}

func (s *SQLProposalStore) RejectProposal(ctx context.Context, input RejectProposalInput) (ProposalRejection, error) {
	input = normalizeRejectProposalInput(input)
	if input.TenantID == "" || input.ProjectID == "" || input.InteractionID == "" || input.AssetID == "" || input.ActorUserID == "" {
		return ProposalRejection{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, interaction_id, asset_id, and actor_user_id are required"}
	}
	if s.db == nil {
		return ProposalRejection{}, &AppError{Code: "CHARACTER_PROPOSAL_BACKEND_UNCONFIGURED", Message: "character proposal backend is not configured"}
	}
	tx, err := s.beginScopedTx(ctx, input.TenantID, input.ActorUserID)
	if err != nil {
		return ProposalRejection{}, proposalRejectionFailed()
	}
	defer func() { _ = tx.Rollback() }()

	proposal, _, err := lockProposal(ctx, tx, AdoptProposalInput{
		TenantID: input.TenantID, ProjectID: input.ProjectID,
		InteractionID: input.InteractionID, AssetID: input.AssetID,
		ActorUserID: input.ActorUserID, RequestID: input.RequestID,
	})
	if err != nil {
		return ProposalRejection{}, err
	}
	if proposal.Lifecycle != "candidate" {
		return ProposalRejection{}, &AppError{Code: "CHARACTER_PROPOSAL_ALREADY_DECIDED", Message: "character proposal is no longer a candidate"}
	}

	var result ProposalRejection
	err = tx.QueryRowContext(ctx, `WITH rejected AS (
  UPDATE assets
  SET lifecycle = 'rejected',
      payload_jsonb = payload_jsonb || jsonb_build_object('rejection_note', $5::text),
      updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2
    AND asset_id::text = $3 AND lifecycle = 'candidate'
  RETURNING asset_id::text, project_id::text,
            payload_jsonb->>'interaction_id' AS interaction_id,
            payload_jsonb->>'proposal_type' AS proposal_type
), audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT $1::uuid, $6::uuid, 'character.proposal.reject', 'asset',
         rejected.asset_id::uuid, rejected.project_id::uuid, NULL, $7,
         jsonb_build_object('interaction_id', $4::text, 'proposal_type', rejected.proposal_type, 'note', $5::text)
  FROM rejected
)
SELECT asset_id, project_id, interaction_id, proposal_type, 'rejected'
FROM rejected`, input.TenantID, input.ProjectID, input.AssetID, input.InteractionID,
		input.Note, input.ActorUserID, input.RequestID).Scan(
		&result.AssetID, &result.ProjectID, &result.InteractionID,
		&result.ProposalType, &result.Status,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return ProposalRejection{}, &AppError{Code: "CHARACTER_PROPOSAL_ALREADY_DECIDED", Message: "character proposal is no longer a candidate"}
	}
	if err != nil {
		return ProposalRejection{}, proposalRejectionFailed()
	}
	if err := tx.Commit(); err != nil {
		return ProposalRejection{}, proposalRejectionFailed()
	}
	return result, nil
}

func (s *SQLProposalStore) beginScopedTx(ctx context.Context, tenantID, actorUserID string) (*sql.Tx, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", tenantID, actorUserID); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return tx, nil
}

func lockProposal(ctx context.Context, tx *sql.Tx, input AdoptProposalInput) (ProposalRecord, map[string]any, error) {
	var proposal ProposalRecord
	var payloadJSON string
	err := tx.QueryRowContext(ctx, `SELECT
  asset_id::text, project_id::text, payload_jsonb->>'interaction_id',
  payload_jsonb->>'proposal_type', asset_type, lifecycle, title,
  COALESCE(summary, ''), COALESCE(payload_jsonb->>'target_id', ''),
  created_at::text, updated_at::text, payload_jsonb::text
FROM assets
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND asset_id::text = $3
  AND source_kind = 'character_dialogue'
  AND payload_jsonb->>'interaction_id' = $4
  AND asset_type IN (
    'character_memory_proposal',
    'character_relation_proposal',
    'character_world_state_proposal'
  )
FOR UPDATE`, input.TenantID, input.ProjectID, input.AssetID, input.InteractionID).Scan(
		&proposal.AssetID, &proposal.ProjectID, &proposal.InteractionID,
		&proposal.ProposalType, &proposal.AssetType, &proposal.Lifecycle,
		&proposal.Title, &proposal.Summary, &proposal.TargetID,
		&proposal.CreatedAt, &proposal.UpdatedAt, &payloadJSON,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return ProposalRecord{}, nil, &AppError{Code: "NOT_FOUND", Message: "character proposal was not found"}
	}
	if err != nil {
		return ProposalRecord{}, nil, proposalAdoptionFailed()
	}
	payload := map[string]any{}
	if err := json.Unmarshal([]byte(payloadJSON), &payload); err != nil {
		return ProposalRecord{}, nil, proposalAdoptionFailed()
	}
	return proposal, payload, nil
}

func adoptProposalTarget(ctx context.Context, tx *sql.Tx, input AdoptProposalInput, proposal ProposalRecord, payload map[string]any) (string, error) {
	switch proposal.AssetType {
	case "character_memory_proposal":
		return adoptMemoryProposal(ctx, tx, input, proposal)
	case "character_world_state_proposal":
		return adoptWorldStateProposal(ctx, tx, input, proposal)
	case "character_relation_proposal":
		return adoptRelationProposal(ctx, tx, input, proposal, payload)
	default:
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "character proposal type is not supported"}
	}
}

func adoptMemoryProposal(ctx context.Context, tx *sql.Tx, input AdoptProposalInput, proposal ProposalRecord) (string, error) {
	if proposal.TargetID == "" {
		return "", proposalAdoptionFailed()
	}
	var targetID string
	err := tx.QueryRowContext(ctx, `UPDATE archive_memories
SET status = 'canon', updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2
  AND memory_id::text = $3 AND asset_id::text = $4 AND status = 'candidate'
RETURNING memory_id::text`, input.TenantID, input.ProjectID, proposal.TargetID, proposal.AssetID).Scan(&targetID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", &AppError{Code: "CHARACTER_PROPOSAL_TARGET_CONFLICT", Message: "character proposal target is no longer a candidate"}
	}
	if err != nil {
		return "", proposalAdoptionFailed()
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO archive_memory_events (
  tenant_id, memory_id, asset_id, project_id, event_type, status,
  payload_jsonb, actor_user_id
) VALUES (
  $1::uuid, $3::uuid, $4::uuid, $2::uuid,
  'character.memory.adopted', 'accepted',
  jsonb_build_object('proposal_asset_id', $4::text, 'interaction_id', $5::text, 'request_id', $6::text),
  $7::uuid
)`, input.TenantID, input.ProjectID, targetID, proposal.AssetID, input.InteractionID, input.RequestID, input.ActorUserID)
	if err != nil {
		return "", proposalAdoptionFailed()
	}
	return targetID, nil
}

func adoptWorldStateProposal(ctx context.Context, tx *sql.Tx, input AdoptProposalInput, proposal ProposalRecord) (string, error) {
	if proposal.TargetID == "" {
		return "", proposalAdoptionFailed()
	}
	var targetID, sessionID, runID string
	err := tx.QueryRowContext(ctx, `UPDATE worldline_events AS event
SET status = 'canon', lifecycle = 'canon_reference', updated_at = now()
FROM worldline_sessions AS session
WHERE event.tenant_id::text = $1 AND event.project_id::text = $2
  AND event.event_id::text = $3 AND event.status = 'candidate'
  AND session.tenant_id = event.tenant_id AND session.project_id = event.project_id
  AND session.session_id = event.session_id AND session.lifecycle = 'active'
RETURNING event.event_id::text, event.session_id::text, session.run_id::text`,
		input.TenantID, input.ProjectID, proposal.TargetID).Scan(&targetID, &sessionID, &runID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", &AppError{Code: "CHARACTER_PROPOSAL_TARGET_CONFLICT", Message: "character proposal target is no longer a candidate"}
	}
	if err != nil {
		return "", proposalAdoptionFailed()
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO worldline_event_adoptions (
  tenant_id, event_id, session_id, project_id, from_status, to_status,
  note, adopted_by
) VALUES ($1::uuid, $3::uuid, $4::uuid, $2::uuid, 'candidate', 'canon', $5, $6::uuid)`,
		input.TenantID, input.ProjectID, targetID, sessionID, input.Note, input.ActorUserID)
	if err != nil {
		return "", proposalAdoptionFailed()
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
) VALUES (
  $1::uuid, $3::uuid, 'worldline_session', $2::uuid,
  'worldline.event.adopted',
  (SELECT COALESCE(MAX(sequence), 0) + 1 FROM workflow_events WHERE tenant_id = $1::uuid AND run_id = $3::uuid),
  jsonb_build_object('event_id', $4::text, 'interaction_id', $5::text, 'status', 'canon', 'lifecycle', 'canon_reference')
)`, input.TenantID, input.ProjectID, runID, targetID, input.InteractionID)
	if err != nil {
		return "", proposalAdoptionFailed()
	}
	return targetID, nil
}

func adoptRelationProposal(ctx context.Context, tx *sql.Tx, input AdoptProposalInput, proposal ProposalRecord, payload map[string]any) (string, error) {
	sourceName := proposalPayloadText(payload, "source_entity_name")
	targetName := proposalPayloadText(payload, "target_entity_name")
	relationshipType := proposalPayloadText(payload, "relationship_type")
	sourceRunID := proposalPayloadText(payload, "source_run_id")
	if sourceName == "" || targetName == "" || relationshipType == "" || sourceRunID == "" {
		return "", proposalAdoptionFailed()
	}
	var targetID string
	err := tx.QueryRowContext(ctx, `INSERT INTO relationships (
  tenant_id, project_id, source_entity_name, target_entity_name,
  relationship_type, summary, source_run_id, metadata_jsonb
) VALUES (
  $1::uuid, $2::uuid, $3, $4, $5, $6, $7::uuid,
  jsonb_build_object('source_kind', 'character_dialogue', 'proposal_asset_id', $8::text, 'interaction_id', $9::text)
)
ON CONFLICT (tenant_id, project_id, source_entity_name, target_entity_name, relationship_type)
DO UPDATE SET
  summary = EXCLUDED.summary,
  source_run_id = EXCLUDED.source_run_id,
  metadata_jsonb = relationships.metadata_jsonb || EXCLUDED.metadata_jsonb,
  updated_at = now()
RETURNING relationship_id::text`, input.TenantID, input.ProjectID, sourceName, targetName,
		relationshipType, proposal.Summary, sourceRunID, proposal.AssetID, input.InteractionID).Scan(&targetID)
	if err != nil {
		return "", proposalAdoptionFailed()
	}
	return targetID, nil
}

func finalizeProposalAdoption(ctx context.Context, tx *sql.Tx, input AdoptProposalInput, proposal ProposalRecord, targetID string) (ProposalAdoption, error) {
	result := ProposalAdoption{}
	err := tx.QueryRowContext(ctx, `WITH adopted AS (
  UPDATE assets
  SET lifecycle = 'canon',
      payload_jsonb = payload_jsonb || jsonb_build_object('target_id', $5::text),
      updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2
    AND asset_id::text = $3 AND lifecycle = 'candidate'
  RETURNING asset_id::text, project_id::text,
            payload_jsonb->>'interaction_id' AS interaction_id,
            payload_jsonb->>'proposal_type' AS proposal_type
), audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT $1::uuid, $6::uuid, 'character.proposal.adopt', 'asset',
         adopted.asset_id::uuid, adopted.project_id::uuid, NULL, $7,
         jsonb_build_object('interaction_id', $4::text, 'proposal_type', adopted.proposal_type, 'target_id', $5::text)
  FROM adopted
)
SELECT asset_id, project_id, interaction_id, proposal_type, $5, 'adopted'
FROM adopted`, input.TenantID, input.ProjectID, proposal.AssetID, input.InteractionID,
		targetID, input.ActorUserID, input.RequestID).Scan(
		&result.AssetID, &result.ProjectID, &result.InteractionID,
		&result.ProposalType, &result.TargetID, &result.Status,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return ProposalAdoption{}, &AppError{Code: "CHARACTER_PROPOSAL_ALREADY_ADOPTED", Message: "character proposal is no longer a candidate"}
	}
	if err != nil {
		return ProposalAdoption{}, proposalAdoptionFailed()
	}
	return result, nil
}

func normalizeListProposalsInput(input ListProposalsInput) ListProposalsInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.InteractionID = strings.TrimSpace(input.InteractionID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	return input
}

func normalizeAdoptProposalInput(input AdoptProposalInput) AdoptProposalInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.InteractionID = strings.TrimSpace(input.InteractionID)
	input.AssetID = strings.TrimSpace(input.AssetID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Note = strings.TrimSpace(input.Note)
	return input
}

func normalizeRejectProposalInput(input RejectProposalInput) RejectProposalInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.InteractionID = strings.TrimSpace(input.InteractionID)
	input.AssetID = strings.TrimSpace(input.AssetID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Note = strings.TrimSpace(input.Note)
	return input
}

func proposalPayloadText(payload map[string]any, key string) string {
	value, _ := payload[key].(string)
	return strings.TrimSpace(value)
}

func proposalQueryFailed() *AppError {
	return &AppError{Code: "CHARACTER_PROPOSAL_QUERY_FAILED", Message: "character proposal query failed"}
}

func proposalAdoptionFailed() *AppError {
	return &AppError{Code: "CHARACTER_PROPOSAL_ADOPTION_FAILED", Message: "character proposal adoption failed"}
}

func proposalRejectionFailed() *AppError {
	return &AppError{Code: "CHARACTER_PROPOSAL_REJECTION_FAILED", Message: "character proposal rejection failed"}
}
