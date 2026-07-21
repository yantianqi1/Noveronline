package assetdistillation

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
)

type SQLStore struct{ db *sql.DB }

func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db} }

func (s *SQLStore) GetSettings(ctx context.Context, scope Scope) (Settings, error) {
	if err := requireProjectScope(scope); err != nil {
		return Settings{}, err
	}
	var out Settings
	var typesCSV string
	var updated time.Time
	err := s.withTenant(ctx, scope, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT project_id::text, trigger_mode,
  COALESCE(array_to_string(enabled_asset_types, ','), ''), updated_at
FROM project_asset_distillation_settings
WHERE tenant_id=$1::uuid AND project_id=$2::uuid`, scope.TenantID, scope.ProjectID).Scan(
			&out.ProjectID, &out.TriggerMode, &typesCSV, &updated)
	})
	if errors.Is(err, sql.ErrNoRows) {
		return Settings{ProjectID: scope.ProjectID, TriggerMode: "manual", EnabledAssetTypes: []string{}}, nil
	}
	if err != nil {
		return Settings{}, storeFailed(err)
	}
	out.EnabledAssetTypes = splitCSV(typesCSV)
	out.UpdatedAt = updated.UTC().Format(time.RFC3339Nano)
	return out, nil
}

func (s *SQLStore) PatchSettings(ctx context.Context, scope Scope, patch SettingsPatch) (Settings, error) {
	if err := requireProjectScope(scope); err != nil {
		return Settings{}, err
	}
	mode := ""
	if patch.TriggerMode != nil {
		mode = strings.TrimSpace(*patch.TriggerMode)
		if !validTriggerMode(mode) {
			return Settings{}, appError(CodeValidationFailed, "trigger_mode is invalid")
		}
	}
	types := patch.EnabledAssetTypes
	if types == nil {
		types = []string{}
	}
	for _, t := range types {
		if strings.TrimSpace(t) == "" {
			return Settings{}, appError(CodeValidationFailed, "enabled_asset_types is invalid")
		}
	}
	err := s.withTenant(ctx, scope, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `INSERT INTO project_asset_distillation_settings(
  tenant_id, project_id, trigger_mode, enabled_asset_types, created_by, updated_by
) VALUES ($1::uuid,$2::uuid,COALESCE(NULLIF($3,''),'manual'),COALESCE($4::text[],'{}'::text[]),NULLIF($5,'')::uuid,NULLIF($5,'')::uuid)
ON CONFLICT (tenant_id, project_id) DO UPDATE SET
  trigger_mode = CASE WHEN NULLIF($3,'') IS NULL THEN project_asset_distillation_settings.trigger_mode ELSE EXCLUDED.trigger_mode END,
  enabled_asset_types = CASE WHEN $6 THEN EXCLUDED.enabled_asset_types ELSE project_asset_distillation_settings.enabled_asset_types END,
  updated_by = NULLIF($5,'')::uuid,
  updated_at = now()`,
			scope.TenantID, scope.ProjectID, mode, types, scope.ActorUserID, patch.EnabledAssetTypes != nil)
		return err
	})
	if err != nil {
		return Settings{}, storeFailed(err)
	}
	return s.GetSettings(ctx, scope)
}

func (s *SQLStore) AdmitManual(ctx context.Context, input StartManualInput) (Admission, bool, error) {
	scope := input.Scope
	if err := requireProjectScope(scope); err != nil {
		return Admission{}, false, err
	}
	if scope.RequestID == "" || scope.ActorUserID == "" {
		return Admission{}, false, appError(CodeValidationFailed, "actor and request_id are required")
	}
	sources, err := s.resolveManualSources(ctx, input)
	if err != nil {
		return Admission{}, false, err
	}
	settings, err := s.GetSettings(ctx, scope)
	if err != nil {
		return Admission{}, false, err
	}
	if settings.TriggerMode == "off" {
		return Admission{}, false, appError(CodeValidationFailed, "asset distillation is disabled for this project")
	}
	fingerprint, manifest, err := fingerprintSources(scope, "manual", sources, settings.EnabledAssetTypes, ExtractorContractV1)
	if err != nil {
		return Admission{}, false, err
	}
	return s.admitRequest(ctx, scope, "manual", sources, fingerprint, manifest)
}

func (s *SQLStore) EnqueueFromSources(ctx context.Context, scope Scope, triggerKind string, sources []SourceBlock) (Admission, bool, error) {
	if err := requireProjectScope(scope); err != nil {
		return Admission{}, false, err
	}
	if len(sources) == 0 {
		return Admission{}, false, appError(CodeValidationFailed, "distillation sources are required")
	}
	settings, err := s.GetSettings(ctx, scope)
	if err != nil {
		return Admission{}, false, err
	}
	if !shouldAutoEnqueue(settings.TriggerMode, triggerKind) {
		return Admission{}, false, nil
	}
	fingerprint, manifest, err := fingerprintSources(scope, triggerKind, sources, settings.EnabledAssetTypes, ExtractorContractV1)
	if err != nil {
		return Admission{}, false, err
	}
	return s.admitRequest(ctx, scope, triggerKind, sources, fingerprint, manifest)
}

// sqlQuerier is the subset of *sql.Tx used by in-transaction admission helpers.
type sqlQuerier interface {
	ExecContext(context.Context, string, ...any) (sql.Result, error)
	QueryRowContext(context.Context, string, ...any) *sql.Row
}

// EnqueueFromSourcesOn admits a distillation request on an already-open transaction
// (tenant context must already be set). Used for same-TX post-adoption outbox inserts.
func (s *SQLStore) EnqueueFromSourcesOn(ctx context.Context, q sqlQuerier, scope Scope, triggerKind string, sources []SourceBlock) (Admission, bool, error) {
	if err := requireProjectScope(scope); err != nil {
		return Admission{}, false, err
	}
	if q == nil {
		return Admission{}, false, appError(CodeBackendUnconfigured, "transaction is required")
	}
	if len(sources) == 0 {
		return Admission{}, false, appError(CodeValidationFailed, "distillation sources are required")
	}
	settings, err := loadSettingsOn(ctx, q, scope)
	if err != nil {
		return Admission{}, false, err
	}
	if !shouldAutoEnqueue(settings.TriggerMode, triggerKind) {
		return Admission{}, false, nil
	}
	fingerprint, manifest, err := fingerprintSources(scope, triggerKind, sources, settings.EnabledAssetTypes, ExtractorContractV1)
	if err != nil {
		return Admission{}, false, err
	}
	return admitRequestOn(ctx, q, scope, triggerKind, sources, fingerprint, manifest)
}

func (s *SQLStore) admitRequest(ctx context.Context, scope Scope, triggerKind string, sources []SourceBlock, fingerprint, manifest string) (Admission, bool, error) {
	var proposed Admission
	var replay bool
	err := s.withTenant(ctx, scope, func(tx *sql.Tx) error {
		result, wasReplay, admitErr := admitRequestOn(ctx, tx, scope, triggerKind, sources, fingerprint, manifest)
		if admitErr != nil {
			return admitErr
		}
		proposed = result
		replay = wasReplay
		return nil
	})
	if err != nil {
		if _, ok := err.(*AppError); ok {
			return Admission{}, false, err
		}
		return Admission{}, false, storeFailed(err)
	}
	return proposed, replay, nil
}

func loadSettingsOn(ctx context.Context, q sqlQuerier, scope Scope) (Settings, error) {
	var out Settings
	var typesCSV string
	var updated time.Time
	err := q.QueryRowContext(ctx, `SELECT project_id::text, trigger_mode,
  COALESCE(array_to_string(enabled_asset_types, ','), ''), updated_at
FROM project_asset_distillation_settings
WHERE tenant_id=$1::uuid AND project_id=$2::uuid`, scope.TenantID, scope.ProjectID).Scan(
		&out.ProjectID, &out.TriggerMode, &typesCSV, &updated)
	if errors.Is(err, sql.ErrNoRows) {
		return Settings{ProjectID: scope.ProjectID, TriggerMode: "manual", EnabledAssetTypes: []string{}}, nil
	}
	if err != nil {
		return Settings{}, err
	}
	out.EnabledAssetTypes = splitCSV(typesCSV)
	out.UpdatedAt = updated.UTC().Format(time.RFC3339Nano)
	return out, nil
}

func admitRequestOn(ctx context.Context, q sqlQuerier, scope Scope, triggerKind string, sources []SourceBlock, fingerprint, manifest string) (Admission, bool, error) {
	proposed := Admission{
		RunID:        uuid.NewString(),
		RequestID:    uuid.NewString(),
		ProjectID:    scope.ProjectID,
		WorkflowType: WorkflowType,
		ModuleKey:    ModuleKey,
		Status:       "queued",
		TriggerKind:  triggerKind,
	}
	temporalID := WorkflowType + "_" + proposed.RunID
	var existingRun, existingReq, status string
	err := q.QueryRowContext(ctx, `SELECT run_id::text, request_id::text, 'queued'
FROM manuscript_asset_distillation_requests
WHERE tenant_id=$1::uuid AND project_id=$2::uuid
  AND input_fingerprint=$3 AND extractor_contract_version=$4
LIMIT 1`, scope.TenantID, scope.ProjectID, fingerprint, ExtractorContractV1).Scan(&existingRun, &existingReq, &status)
	if err == nil {
		proposed.RunID = existingRun
		proposed.RequestID = existingReq
		proposed.Status = status
		return proposed, true, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return Admission{}, false, err
	}
	if scope.RequestID != "" {
		var hash string
		err = q.QueryRowContext(ctx, `SELECT workflow.run_id::text, req.request_id::text, workflow.status,
  req.input_fingerprint
FROM manuscript_asset_distillation_requests req
JOIN workflow_runs workflow ON workflow.tenant_id=req.tenant_id AND workflow.run_id=req.run_id
WHERE req.tenant_id=$1::uuid AND req.project_id=$2::uuid
  AND workflow.started_by=NULLIF($3,'')::uuid
  AND EXISTS (
    SELECT 1 FROM workflow_events ev
    WHERE ev.tenant_id=workflow.tenant_id AND ev.run_id=workflow.run_id
      AND ev.event_type='workflow.queued' AND ev.payload_jsonb->>'request_id'=$4
  )
LIMIT 1`, scope.TenantID, scope.ProjectID, scope.ActorUserID, scope.RequestID).Scan(
			&existingRun, &existingReq, &status, &hash)
		if err == nil {
			if hash != fingerprint {
				return Admission{}, false, appError(CodeIdempotencyConflict, "request_id was already used for a different distillation request")
			}
			proposed.RunID, proposed.RequestID, proposed.Status = existingRun, existingReq, status
			return proposed, true, nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return Admission{}, false, err
		}
	}
	eventPayload, _ := json.Marshal(map[string]any{
		"status": "queued", "module_key": ModuleKey, "request_id": scope.RequestID,
		"payload_hash": fingerprint, "trigger_kind": triggerKind, "source_count": len(sources),
	})
	if _, err := q.ExecContext(ctx, `INSERT INTO workflow_runs(
  tenant_id, run_id, workflow_type, project_id, status, progress, message, started_by, temporal_workflow_id
) VALUES ($1::uuid,$2::uuid,$3,$4::uuid,'queued',0,'queued',NULLIF($5,'')::uuid,$6)`,
		scope.TenantID, proposed.RunID, WorkflowType, scope.ProjectID, scope.ActorUserID, temporalID); err != nil {
		return Admission{}, false, err
	}
	if _, err := q.ExecContext(ctx, `INSERT INTO workflow_events(
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
) VALUES ($1::uuid,$2::uuid,$3,$4::uuid,'workflow.queued',1,$5::jsonb)`,
		scope.TenantID, proposed.RunID, WorkflowType, scope.ProjectID, string(eventPayload)); err != nil {
		return Admission{}, false, err
	}
	if _, err := q.ExecContext(ctx, `INSERT INTO manuscript_asset_distillation_requests(
  tenant_id, request_id, project_id, run_id, trigger_kind, source_manifest_jsonb,
  input_fingerprint, extractor_contract_version, dispatch_status, next_attempt_at, requested_by
) VALUES ($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5,$6::jsonb,$7,$8,'pending',now(),NULLIF($9,'')::uuid)`,
		scope.TenantID, proposed.RequestID, scope.ProjectID, proposed.RunID, triggerKind,
		manifest, fingerprint, ExtractorContractV1, scope.ActorUserID); err != nil {
		return Admission{}, false, err
	}
	return proposed, false, nil
}

func contentSHA256(content string) string {
	sum := sha256.Sum256([]byte(content))
	return hex.EncodeToString(sum[:])
}

func (s *SQLStore) MarkDispatched(ctx context.Context, tenantID, requestID string) error {
	return s.withTenant(ctx, Scope{TenantID: tenantID, ActorUserID: ""}, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `UPDATE manuscript_asset_distillation_requests
SET dispatch_status='dispatched', updated_at=now()
WHERE tenant_id=$1::uuid AND request_id=$2::uuid AND dispatch_status='pending'`, tenantID, requestID)
		return err
	})
}

func (s *SQLStore) MarkDispatchRetry(ctx context.Context, tenantID, requestID, errorCode string, attempt int, next time.Time) error {
	return s.withTenant(ctx, Scope{TenantID: tenantID}, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `UPDATE manuscript_asset_distillation_requests
SET attempt_count=$3, next_attempt_at=$4, last_dispatch_error_code=NULLIF($5,''), updated_at=now()
WHERE tenant_id=$1::uuid AND request_id=$2::uuid AND dispatch_status='pending'`,
			tenantID, requestID, attempt, next.UTC(), errorCode)
		return err
	})
}

func (s *SQLStore) ClaimPendingDispatch(ctx context.Context, limit int) ([]OutboxItem, error) {
	if s == nil || s.db == nil {
		return nil, appError(CodeBackendUnconfigured, "asset distillation backend is not configured")
	}
	if limit <= 0 {
		limit = 10
	}
	rows, err := s.db.QueryContext(ctx, `SELECT tenant_id::text, request_id::text, project_id::text, run_id::text,
  trigger_kind, attempt_count
FROM claim_manuscript_asset_distillation_outbox($1)`, limit)
	if err != nil {
		return nil, storeFailed(err)
	}
	defer rows.Close()
	var items []OutboxItem
	for rows.Next() {
		var item OutboxItem
		if err := rows.Scan(&item.TenantID, &item.RequestID, &item.ProjectID, &item.RunID, &item.TriggerKind, &item.Attempt); err != nil {
			return nil, storeFailed(err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *SQLStore) ListProposals(ctx context.Context, scope Scope, status string) ([]ProposalSummary, error) {
	if err := requireProjectScope(scope); err != nil {
		return nil, err
	}
	status = strings.TrimSpace(status)
	if status == "" {
		status = "pending"
	}
	var out []ProposalSummary
	err := s.withTenant(ctx, scope, func(tx *sql.Tx) error {
		rows, err := tx.QueryContext(ctx, `SELECT p.candidate_asset_id::text, p.project_id::text, p.request_id::text,
  p.operation, p.review_status, p.normalized_identity, a.title, a.asset_type, COALESCE(a.summary,''),
  COALESCE(p.target_asset_id::text,''), p.expected_target_version, p.confidence,
  (SELECT count(*) FROM asset_candidate_evidence e WHERE e.tenant_id=p.tenant_id AND e.candidate_asset_id=p.candidate_asset_id),
  p.created_at
FROM asset_candidate_proposals p
JOIN assets a ON a.tenant_id=p.tenant_id AND a.project_id=p.project_id AND a.asset_id=p.candidate_asset_id
WHERE p.tenant_id=$1::uuid AND p.project_id=$2::uuid AND p.review_status=$3
ORDER BY p.created_at DESC
LIMIT 200`, scope.TenantID, scope.ProjectID, status)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var item ProposalSummary
			var target string
			var expected sql.NullInt64
			var conf sql.NullFloat64
			var created time.Time
			if err := rows.Scan(&item.CandidateAssetID, &item.ProjectID, &item.RequestID, &item.Operation,
				&item.ReviewStatus, &item.NormalizedIdentity, &item.Title, &item.AssetType, &item.Summary,
				&target, &expected, &conf, &item.EvidenceCount, &created); err != nil {
				return err
			}
			if target != "" {
				item.TargetAssetID = target
			}
			if expected.Valid {
				v := int(expected.Int64)
				item.ExpectedTargetVersion = &v
			}
			if conf.Valid {
				v := conf.Float64
				item.Confidence = &v
			}
			item.CreatedAt = created.UTC().Format(time.RFC3339Nano)
			out = append(out, item)
		}
		return rows.Err()
	})
	if err != nil {
		return nil, storeFailed(err)
	}
	if out == nil {
		out = []ProposalSummary{}
	}
	return out, nil
}

func (s *SQLStore) GetProposal(ctx context.Context, scope Scope, candidateAssetID string, includeEvidenceText bool) (ProposalDetail, error) {
	if err := requireProjectScope(scope); err != nil {
		return ProposalDetail{}, err
	}
	candidateAssetID = strings.TrimSpace(candidateAssetID)
	if candidateAssetID == "" {
		return ProposalDetail{}, appError(CodeValidationFailed, "candidate_asset_id is required")
	}
	var detail ProposalDetail
	err := s.withTenant(ctx, scope, func(tx *sql.Tx) error {
		var target string
		var expected sql.NullInt64
		var conf sql.NullFloat64
		var accepted, note string
		var created time.Time
		var payload []byte
		err := tx.QueryRowContext(ctx, `SELECT p.candidate_asset_id::text, p.project_id::text, p.request_id::text,
  p.operation, p.review_status, p.normalized_identity, a.title, a.asset_type, COALESCE(a.summary,''),
  COALESCE(p.target_asset_id::text,''), p.expected_target_version, p.confidence,
  COALESCE(p.accepted_asset_id::text,''), COALESCE(p.decision_note,''), p.created_at, a.payload_jsonb
FROM asset_candidate_proposals p
JOIN assets a ON a.tenant_id=p.tenant_id AND a.project_id=p.project_id AND a.asset_id=p.candidate_asset_id
WHERE p.tenant_id=$1::uuid AND p.candidate_asset_id=$2::uuid`, scope.TenantID, candidateAssetID).Scan(
			&detail.CandidateAssetID, &detail.ProjectID, &detail.RequestID, &detail.Operation, &detail.ReviewStatus,
			&detail.NormalizedIdentity, &detail.Title, &detail.AssetType, &detail.Summary, &target, &expected,
			&conf, &accepted, &note, &created, &payload)
		if errors.Is(err, sql.ErrNoRows) {
			return appError(CodeNotFound, "asset proposal was not found")
		}
		if err != nil {
			return err
		}
		if scope.ProjectID != "" && detail.ProjectID != scope.ProjectID {
			return appError(CodeNotFound, "asset proposal was not found")
		}
		detail.TargetAssetID, detail.AcceptedAssetID, detail.DecisionNote = target, accepted, note
		if expected.Valid {
			v := int(expected.Int64)
			detail.ExpectedTargetVersion = &v
		}
		if conf.Valid {
			v := conf.Float64
			detail.Confidence = &v
		}
		detail.CreatedAt = created.UTC().Format(time.RFC3339Nano)
		_ = json.Unmarshal(payload, &detail.Payload)
		rows, err := tx.QueryContext(ctx, `SELECT e.evidence_id::text, e.block_id::text, e.block_version, e.start_offset, e.end_offset,
  e.evidence_text,
  EXISTS (
    SELECT 1 FROM manuscript_blocks b
    WHERE b.tenant_id=e.tenant_id AND b.project_id=e.project_id AND b.block_id=e.block_id
      AND b.status='active' AND b.version=e.block_version
  ) AS current
FROM asset_candidate_evidence e
WHERE e.tenant_id=$1::uuid AND e.candidate_asset_id=$2::uuid
ORDER BY e.created_at`, scope.TenantID, candidateAssetID)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var pub EvidencePublic
			var text string
			if err := rows.Scan(&pub.EvidenceID, &pub.BlockID, &pub.BlockVersion, &pub.StartOffset, &pub.EndOffset, &text, &pub.Current); err != nil {
				return err
			}
			detail.Evidence = append(detail.Evidence, pub)
			if includeEvidenceText {
				detail.EvidencePrivate = append(detail.EvidencePrivate, EvidencePrivate{EvidenceID: pub.EvidenceID, EvidenceText: text})
			}
		}
		detail.EvidenceCount = len(detail.Evidence)
		return rows.Err()
	})
	if err != nil {
		if ErrorCode(err) != "ASSET_DISTILLATION_FAILED" {
			return ProposalDetail{}, err
		}
		return ProposalDetail{}, storeFailed(err)
	}
	if detail.Evidence == nil {
		detail.Evidence = []EvidencePublic{}
	}
	return detail, nil
}

func (s *SQLStore) Decide(ctx context.Context, input DecisionInput) (DecisionResult, error) {
	scope := input.Scope
	if err := requireProjectScope(scope); err != nil {
		return DecisionResult{}, err
	}
	candidateID := strings.TrimSpace(input.CandidateAssetID)
	decision := strings.TrimSpace(input.Decision)
	if candidateID == "" || decision == "" {
		return DecisionResult{}, appError(CodeValidationFailed, "candidate_asset_id and decision are required")
	}
	lifecycle := strings.TrimSpace(input.TargetLifecycle)
	if lifecycle == "" {
		lifecycle = "canon"
	}
	if lifecycle != "canon" && lifecycle != "material" {
		return DecisionResult{}, appError(CodeValidationFailed, "target_lifecycle must be canon or material")
	}
	var result DecisionResult
	err := s.withTenant(ctx, scope, func(tx *sql.Tx) error {
		var reviewStatus, operation, projectID string
		var targetID sql.NullString
		var expected sql.NullInt64
		var accepted sql.NullString
		err := tx.QueryRowContext(ctx, `SELECT project_id::text, review_status, operation,
  target_asset_id::text, expected_target_version, accepted_asset_id::text
FROM asset_candidate_proposals
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid
FOR UPDATE`, scope.TenantID, candidateID).Scan(&projectID, &reviewStatus, &operation, &targetID, &expected, &accepted)
		if errors.Is(err, sql.ErrNoRows) {
			return appError(CodeNotFound, "asset proposal was not found")
		}
		if err != nil {
			return err
		}
		if scope.ProjectID != "" && projectID != scope.ProjectID {
			return appError(CodeNotFound, "asset proposal was not found")
		}
		// Idempotent replay
		if reviewStatus == "accepted" || reviewStatus == "rejected" {
			if (decision == "accept_create" || decision == "accept_update") && reviewStatus == "accepted" {
				result = DecisionResult{CandidateAssetID: candidateID, ReviewStatus: reviewStatus, AcceptedAssetID: accepted.String, Replay: true}
				return nil
			}
			if decision == "reject" && reviewStatus == "rejected" {
				result = DecisionResult{CandidateAssetID: candidateID, ReviewStatus: reviewStatus, Replay: true}
				return nil
			}
			return appError(CodeConflict, "proposal already decided; use explicit undo")
		}
		if reviewStatus != "pending" && reviewStatus != "conflict" {
			return appError(CodeConflict, "proposal is not actionable")
		}
		if err := assertSourcesCurrent(ctx, tx, scope.TenantID, candidateID); err != nil {
			return err
		}
		switch decision {
		case "accept_create":
			if operation != "create" && reviewStatus != "conflict" {
				// allow conflict path to create if user chooses create semantics via accept_create
			}
			if _, err := tx.ExecContext(ctx, `UPDATE assets SET lifecycle=$3, enabled=true, updated_at=now()
WHERE tenant_id=$1::uuid AND asset_id=$2::uuid AND lifecycle='candidate'`, scope.TenantID, candidateID, lifecycle); err != nil {
				return err
			}
			if _, err := tx.ExecContext(ctx, `UPDATE asset_candidate_proposals
SET review_status='accepted', accepted_asset_id=$2::uuid, reviewed_by=NULLIF($3,'')::uuid, reviewed_at=now(), updated_at=now()
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid`, scope.TenantID, candidateID, scope.ActorUserID); err != nil {
				return err
			}
			if err := writeAudit(ctx, tx, scope, "asset_proposal.accept_create", candidateID, map[string]any{"lifecycle": lifecycle}); err != nil {
				return err
			}
			// CONN-003: transactionally project graph-canonical types into Graph source tables.
			if err := projectAcceptedAssetToGraph(ctx, tx, scope, projectID, candidateID, candidateID); err != nil {
				return err
			}
			result = DecisionResult{CandidateAssetID: candidateID, ReviewStatus: "accepted", AcceptedAssetID: candidateID}
		case "accept_update":
			target := strings.TrimSpace(input.TargetAssetID)
			if target == "" {
				target = targetID.String
			}
			if target == "" {
				return appError(CodeValidationFailed, "target_asset_id is required for accept_update")
			}
			expectedVersion := input.ExpectedTargetVersion
			if expectedVersion <= 0 && expected.Valid {
				expectedVersion = int(expected.Int64)
			}
			if expectedVersion <= 0 {
				return appError(CodeValidationFailed, "expected_target_version is required for accept_update")
			}
			var currentVersion int
			var title, summary, sourceKind, sourceRef string
			var payload []byte
			err := tx.QueryRowContext(ctx, `SELECT
  COALESCE((SELECT max(v.version_number)+1 FROM asset_versions v
    WHERE v.tenant_id=a.tenant_id AND v.project_id=a.project_id AND v.asset_id=a.asset_id), 1),
  a.title, COALESCE(a.summary,''), a.payload_jsonb, a.source_kind, a.source_ref
FROM assets a
WHERE a.tenant_id=$1::uuid AND a.project_id=$2::uuid AND a.asset_id=$3::uuid
FOR UPDATE`, scope.TenantID, projectID, target).Scan(
				&currentVersion, &title, &summary, &payload, &sourceKind, &sourceRef)
			if errors.Is(err, sql.ErrNoRows) {
				return appError(CodeNotFound, "target asset was not found")
			}
			if err != nil {
				return err
			}
			if currentVersion != expectedVersion {
				if _, err := tx.ExecContext(ctx, `UPDATE asset_candidate_proposals SET review_status='conflict', updated_at=now()
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid`, scope.TenantID, candidateID); err != nil {
					return err
				}
				// Commit conflict status first; typed conflict is returned after withTenant succeeds.
				result = DecisionResult{CandidateAssetID: candidateID, ReviewStatus: "conflict"}
				return nil
			}
			// Snapshot current target at expected version number (catalog pattern).
			if _, err := tx.ExecContext(ctx, `INSERT INTO asset_versions(
  tenant_id, asset_id, project_id, version_number, title, summary, payload_jsonb, source_kind, source_ref, created_by
) VALUES ($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7::jsonb,$8,$9,NULLIF($10,'')::uuid)`,
				scope.TenantID, target, projectID, currentVersion, title, summary, string(payload), sourceKind, sourceRef, scope.ActorUserID); err != nil {
				return err
			}
			// Load candidate snapshot
			var cTitle, cSummary string
			var cPayload []byte
			if err := tx.QueryRowContext(ctx, `SELECT title, COALESCE(summary,''), payload_jsonb FROM assets
WHERE tenant_id=$1::uuid AND asset_id=$2::uuid FOR UPDATE`, scope.TenantID, candidateID).Scan(&cTitle, &cSummary, &cPayload); err != nil {
				return err
			}
			if _, err := tx.ExecContext(ctx, `UPDATE assets SET title=$3, summary=NULLIF($4,''), payload_jsonb=$5::jsonb,
  lifecycle=$6, enabled=true, updated_at=now()
WHERE tenant_id=$1::uuid AND asset_id=$2::uuid`, scope.TenantID, target, cTitle, cSummary, string(cPayload), lifecycle); err != nil {
				return err
			}
			if _, err := tx.ExecContext(ctx, `UPDATE assets SET lifecycle='archived', enabled=false, updated_at=now()
WHERE tenant_id=$1::uuid AND asset_id=$2::uuid`, scope.TenantID, candidateID); err != nil {
				return err
			}
			if _, err := tx.ExecContext(ctx, `UPDATE asset_candidate_proposals
SET review_status='accepted', accepted_asset_id=$3::uuid, target_asset_id=$3::uuid,
  reviewed_by=NULLIF($4,'')::uuid, reviewed_at=now(), updated_at=now()
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid`, scope.TenantID, candidateID, target, scope.ActorUserID); err != nil {
				return err
			}
			if err := writeAudit(ctx, tx, scope, "asset_proposal.accept_update", candidateID, map[string]any{
				"target_asset_id": target, "expected_target_version": expectedVersion,
			}); err != nil {
				return err
			}
			// CONN-003: project merged target into Graph source tables in the same transaction.
			if err := projectAcceptedAssetToGraph(ctx, tx, scope, projectID, candidateID, target); err != nil {
				return err
			}
			result = DecisionResult{CandidateAssetID: candidateID, ReviewStatus: "accepted", AcceptedAssetID: target}
		case "reject":
			if _, err := tx.ExecContext(ctx, `UPDATE assets SET lifecycle='archived', enabled=false, updated_at=now()
WHERE tenant_id=$1::uuid AND asset_id=$2::uuid`, scope.TenantID, candidateID); err != nil {
				return err
			}
			if _, err := tx.ExecContext(ctx, `UPDATE asset_candidate_proposals
SET review_status='rejected', decision_note=NULLIF($3,''), reviewed_by=NULLIF($4,'')::uuid, reviewed_at=now(), updated_at=now()
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid`, scope.TenantID, candidateID, input.Note, scope.ActorUserID); err != nil {
				return err
			}
			if err := writeAudit(ctx, tx, scope, "asset_proposal.reject", candidateID, map[string]any{"note": input.Note}); err != nil {
				return err
			}
			result = DecisionResult{CandidateAssetID: candidateID, ReviewStatus: "rejected"}
		default:
			return appError(CodeValidationFailed, "decision must be accept_create, accept_update, or reject")
		}
		return nil
	})
	if err != nil {
		if _, ok := err.(*AppError); ok {
			return DecisionResult{}, err
		}
		return DecisionResult{}, storeFailed(err)
	}
	if result.ReviewStatus == "conflict" {
		return result, appError(CodeTargetConflict, "target asset version changed")
	}
	return result, nil
}

func (s *SQLStore) StaleProposalsForBlock(ctx context.Context, scope Scope, blockID string) error {
	if err := requireProjectScope(scope); err != nil {
		return err
	}
	return s.withTenant(ctx, scope, func(tx *sql.Tx) error {
		return staleProposalsForBlockTx(ctx, tx, scope, blockID)
	})
}

func staleProposalsForBlockTx(ctx context.Context, tx *sql.Tx, scope Scope, blockID string) error {
	_, err := tx.ExecContext(ctx, `UPDATE asset_candidate_proposals p
SET review_status='stale', updated_at=now()
WHERE p.tenant_id=$1::uuid AND p.project_id=$2::uuid AND p.review_status IN ('pending','conflict','staging')
  AND EXISTS (
    SELECT 1 FROM asset_candidate_evidence e
    WHERE e.tenant_id=p.tenant_id AND e.candidate_asset_id=p.candidate_asset_id
      AND e.block_id=$3::uuid
  )
  AND NOT EXISTS (
    SELECT 1 FROM asset_candidate_evidence e
    JOIN manuscript_blocks b ON b.tenant_id=e.tenant_id AND b.project_id=e.project_id AND b.block_id=e.block_id
    WHERE e.tenant_id=p.tenant_id AND e.candidate_asset_id=p.candidate_asset_id
      AND b.status='active' AND b.version=e.block_version
  )`, scope.TenantID, scope.ProjectID, blockID)
	return err
}



func (s *SQLStore) LookupProposalProject(ctx context.Context, tenantID, candidateAssetID string) (string, error) {
	if s == nil || s.db == nil {
		return "", appError(CodeBackendUnconfigured, "asset distillation backend is not configured")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return "", storeFailed(err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULL::uuid, false)", tenantID); err != nil {
		return "", storeFailed(err)
	}
	var projectID string
	err = tx.QueryRowContext(ctx, `SELECT project_id::text FROM asset_candidate_proposals
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid`, tenantID, candidateAssetID).Scan(&projectID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", appError(CodeNotFound, "asset proposal was not found")
	}
	if err != nil {
		return "", storeFailed(err)
	}
	if err := tx.Commit(); err != nil {
		return "", storeFailed(err)
	}
	return projectID, nil
}

func (s *SQLStore) resolveManualSources(ctx context.Context, input StartManualInput) ([]SourceBlock, error) {
	blockIDs := uniqueNonEmpty(input.BlockIDs)
	expected := input.ExpectedVersions
	if expected == nil {
		expected = input.ExpectedBlockVersions
	}
	if len(blockIDs) == 0 && strings.TrimSpace(input.ChapterID) == "" {
		return nil, appError(CodeValidationFailed, "block_ids or chapter_id is required")
	}
	if len(blockIDs) > 0 && strings.TrimSpace(input.ChapterID) != "" {
		return nil, appError(CodeValidationFailed, "provide either block_ids or chapter_id, not both")
	}
	var sources []SourceBlock
	err := s.withTenant(ctx, input.Scope, func(tx *sql.Tx) error {
		query := `SELECT block_id::text, version, encode(digest(content_text, 'sha256'), 'hex'),
  COALESCE(chapter_id::text,''), COALESCE(scene_id::text,'')
FROM manuscript_blocks
WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND status='active'`
		args := []any{input.Scope.TenantID, input.Scope.ProjectID}
		if len(blockIDs) > 0 {
			query += ` AND block_id::text = ANY($3::text[])`
			args = append(args, blockIDs)
		} else {
			query += ` AND chapter_id = $3::uuid`
			args = append(args, input.ChapterID)
		}
		query += ` ORDER BY block_id`
		rows, err := tx.QueryContext(ctx, query, args...)
		if err != nil {
			// digest may need pgcrypto; fallback hash in app if missing
			if strings.Contains(err.Error(), "digest") || strings.Contains(err.Error(), "function") {
				return s.resolveManualSourcesFallback(ctx, tx, input, blockIDs)
			}
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var src SourceBlock
			if err := rows.Scan(&src.BlockID, &src.BlockVersion, &src.ContentSHA, &src.ChapterID, &src.SceneID); err != nil {
				return err
			}
			if expected != nil {
				if want, ok := expected[src.BlockID]; ok && want != src.BlockVersion {
					return appError(CodeConflict, "manuscript block version changed")
				}
			}
			sources = append(sources, src)
		}
		return rows.Err()
	})
	if err != nil {
		if _, ok := err.(*AppError); ok {
			return nil, err
		}
		// fallback path returns AppError or store error
		if strings.Contains(err.Error(), "digest") {
			return s.resolveManualSourcesAppHash(ctx, input, blockIDs, expected)
		}
		return nil, storeFailed(err)
	}
	if len(sources) == 0 {
		return nil, appError(CodeNotFound, "active manuscript sources were not found")
	}
	if len(blockIDs) > 0 && len(sources) != len(blockIDs) {
		return nil, appError(CodeNotFound, "one or more manuscript blocks were not found")
	}
	return sources, nil
}

func (s *SQLStore) resolveManualSourcesFallback(ctx context.Context, tx *sql.Tx, input StartManualInput, blockIDs []string) error {
	return fmt.Errorf("digest unavailable")
}

func (s *SQLStore) resolveManualSourcesAppHash(ctx context.Context, input StartManualInput, blockIDs []string, expected map[string]int) ([]SourceBlock, error) {
	var sources []SourceBlock
	err := s.withTenant(ctx, input.Scope, func(tx *sql.Tx) error {
		query := `SELECT block_id::text, version, content_text, COALESCE(chapter_id::text,''), COALESCE(scene_id::text,'')
FROM manuscript_blocks
WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND status='active'`
		args := []any{input.Scope.TenantID, input.Scope.ProjectID}
		if len(blockIDs) > 0 {
			query += ` AND block_id::text = ANY($3::text[])`
			args = append(args, blockIDs)
		} else {
			query += ` AND chapter_id = $3::uuid`
			args = append(args, input.ChapterID)
		}
		rows, err := tx.QueryContext(ctx, query, args...)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var src SourceBlock
			var content string
			if err := rows.Scan(&src.BlockID, &src.BlockVersion, &content, &src.ChapterID, &src.SceneID); err != nil {
				return err
			}
			sum := sha256.Sum256([]byte(content))
			src.ContentSHA = hex.EncodeToString(sum[:])
			if expected != nil {
				if want, ok := expected[src.BlockID]; ok && want != src.BlockVersion {
					return appError(CodeConflict, "manuscript block version changed")
				}
			}
			sources = append(sources, src)
		}
		return rows.Err()
	})
	if err != nil {
		if _, ok := err.(*AppError); ok {
			return nil, err
		}
		return nil, storeFailed(err)
	}
	if len(sources) == 0 {
		return nil, appError(CodeNotFound, "active manuscript sources were not found")
	}
	return sources, nil
}

func splitCSV(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return []string{}
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func assertSourcesCurrent(ctx context.Context, tx *sql.Tx, tenantID, candidateAssetID string) error {
	var stale int
	err := tx.QueryRowContext(ctx, `SELECT count(*) FROM asset_candidate_evidence e
LEFT JOIN manuscript_blocks b ON b.tenant_id=e.tenant_id AND b.project_id=e.project_id AND b.block_id=e.block_id
WHERE e.tenant_id=$1::uuid AND e.candidate_asset_id=$2::uuid
  AND (b.block_id IS NULL OR b.status<>'active' OR b.version<>e.block_version)`, tenantID, candidateAssetID).Scan(&stale)
	if err != nil {
		return err
	}
	if stale > 0 {
		_, _ = tx.ExecContext(ctx, `UPDATE asset_candidate_proposals SET review_status='stale', updated_at=now()
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid`, tenantID, candidateAssetID)
		return appError(CodeProposalStale, "proposal source manuscript is no longer current")
	}
	return nil
}

func writeAudit(ctx context.Context, tx *sql.Tx, scope Scope, action, resourceID string, meta map[string]any) error {
	payload, _ := json.Marshal(meta)
	_, err := tx.ExecContext(ctx, `INSERT INTO audit_logs(
  tenant_id, actor_user_id, action, resource_type, resource_id, project_id, request_id, metadata_jsonb
) VALUES ($1::uuid, NULLIF($2,'')::uuid, $3, 'asset_proposal', $4::uuid, NULLIF($5,'')::uuid, NULLIF($6,''), $7::jsonb)`,
		scope.TenantID, scope.ActorUserID, action, resourceID, scope.ProjectID, scope.RequestID, string(payload))
	return err
}

func (s *SQLStore) withTenant(ctx context.Context, scope Scope, fn func(*sql.Tx) error) error {
	if s == nil || s.db == nil {
		return appError(CodeBackendUnconfigured, "asset distillation backend is not configured")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2,'')::uuid, false)",
		scope.TenantID, scope.ActorUserID); err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func fingerprintSources(scope Scope, trigger string, sources []SourceBlock, enabledTypes []string, contract int) (string, string, error) {
	sorted := append([]SourceBlock(nil), sources...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].BlockID < sorted[j].BlockID })
	typeArr := append([]string(nil), enabledTypes...)
	sort.Strings(typeArr)
	payload := map[string]any{
		"tenant_id": scope.TenantID, "project_id": scope.ProjectID, "trigger_kind": trigger,
		"sources": sorted, "enabled_asset_types": typeArr, "extractor_contract_version": contract,
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return "", "", appError(CodeValidationFailed, "fingerprint payload is invalid")
	}
	sum := sha256.Sum256(raw)
	manifestMap := map[string]any{
		"schema_version":      1,
		"sources":             sorted,
		"enabled_asset_types": typeArr,
	}
	manifest, err := json.Marshal(manifestMap)
	if err != nil {
		return "", "", appError(CodeValidationFailed, "source manifest is invalid")
	}
	return hex.EncodeToString(sum[:]), string(manifest), nil
}

func shouldAutoEnqueue(mode, trigger string) bool {
	switch mode {
	case "after_adoption":
		return trigger == "draft_adoption" || trigger == "manuscript_update" || trigger == "manuscript_restore"
	case "chapter_complete":
		return trigger == "chapter_complete"
	case "manual", "off":
		return false
	default:
		return false
	}
}

func validTriggerMode(mode string) bool {
	switch mode {
	case "off", "manual", "after_adoption", "chapter_complete":
		return true
	default:
		return false
	}
}

func requireProjectScope(scope Scope) error {
	if strings.TrimSpace(scope.TenantID) == "" || strings.TrimSpace(scope.ProjectID) == "" {
		return appError(CodeValidationFailed, "tenant_id and project_id are required")
	}
	return nil
}

func uniqueNonEmpty(values []string) []string {
	seen := map[string]struct{}{}
	var out []string
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}

func storeFailed(err error) error {
	if err == nil {
		return appError(CodeBackendUnconfigured, "asset distillation backend is not configured")
	}
	if ae, ok := err.(*AppError); ok {
		return ae
	}
	return appError("ASSET_DISTILLATION_QUERY_FAILED", "asset distillation query failed")
}
