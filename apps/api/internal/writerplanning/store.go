package writerplanning

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"

	"github.com/google/uuid"
)

type SQLStore struct{ db *sql.DB }

func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db} }

func (s *SQLStore) Admit(ctx context.Context, input StartInput, proposed Admission, temporalID, payloadHash string) (Admission, bool, error) {
	if s == nil || s.db == nil {
		return Admission{}, false, appError("WRITER_PLANNING_BACKEND_UNCONFIGURED", "writer planning backend is not configured")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Admission{}, false, admissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return Admission{}, false, admissionFailed()
	}
	if existing, hash, found, err := findReplay(ctx, tx, input); err != nil {
		return Admission{}, false, err
	} else if found {
		if hash != payloadHash {
			return Admission{}, false, appError("IDEMPOTENCY_CONFLICT", "request_id was already used for a different writer planning request")
		}
		if err := tx.Commit(); err != nil {
			return Admission{}, false, admissionFailed()
		}
		return existing, true, nil
	}
	if input.Kind == KindDedup {
		if err := validateDedupSource(ctx, tx, input); err != nil {
			return Admission{}, false, err
		}
	}
	if input.Kind == KindBookPlan {
		if err := validateBookPlan(ctx, tx, input); err != nil {
			return Admission{}, false, err
		}
	}
	payload := queuedPayload(input, proposed, payloadHash)
	encoded, err := json.Marshal(payload)
	if err != nil {
		return Admission{}, false, appError("VALIDATION_FAILED", "writer planning payload is invalid")
	}
	eventID := uuid.NewString()
	result, err := tx.ExecContext(ctx, admitWorkflowSQL, admissionInsertArgs(input, proposed, temporalID, eventID, string(encoded))...)
	if err != nil {
		return Admission{}, false, admissionFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return Admission{}, false, admissionFailed()
	}
	if input.Kind == KindBookPlan {
		result, err = tx.ExecContext(ctx, `UPDATE book_plans SET last_run_id=$4::uuid,
  last_run_status='queued', updated_at=now()
WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND book_plan_id=$3::uuid
  AND status='draft' AND optimistic_version=$5`, input.TenantID, input.ProjectID, input.BookPlanID, proposed.RunID, input.ExpectedVersion)
		if err != nil {
			return Admission{}, false, admissionFailed()
		}
		if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
			return Admission{}, false, appError("BOOK_PLAN_CONFLICT", "book plan generation state changed")
		}
		if err := appendBookEvent(ctx, tx, input, proposed.RunID, "planning.admitted", "queued", 0); err != nil {
			return Admission{}, false, admissionFailed()
		}
	}
	if err := tx.Commit(); err != nil {
		return Admission{}, false, admissionFailed()
	}
	return proposed, false, nil
}

const admitWorkflowSQL = `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  ) VALUES ($1::uuid, $4::uuid, $5, $2::uuid, 'queued', 0, 'queued', $3::uuid, $6)
  RETURNING tenant_id, run_id, project_id, workflow_type
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT tenant_id, $7::uuid, run_id, workflow_type, project_id, 'workflow.queued', 1, $8::jsonb
FROM workflow_insert`

func admissionInsertArgs(input StartInput, proposed Admission, temporalID, eventID, payload string) []any {
	return []any{input.TenantID, input.ProjectID, input.ActorUserID, proposed.RunID, proposed.WorkflowType, temporalID, eventID, payload}
}

func (s *SQLStore) Compensate(ctx context.Context, input StartInput, admission Admission) error {
	if s == nil || s.db == nil {
		return admissionFailed()
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return admissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return admissionFailed()
	}
	result, err := tx.ExecContext(ctx, `UPDATE workflow_runs SET status='failed', progress=0,
  message='writer planning workflow failed to start', error_code='WORKFLOW_START_FAILED',
  error_message='writer planning workflow failed to start', updated_at=now()
WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND run_id=$3::uuid
  AND workflow_type=$4 AND status='queued'`, input.TenantID, input.ProjectID, admission.RunID, admission.WorkflowType)
	if err != nil {
		return admissionFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return admissionFailed()
	}
	if input.Kind == KindBookPlan {
		result, err = tx.ExecContext(ctx, `UPDATE book_plans SET last_run_status='failed', updated_at=now()
WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND book_plan_id=$3::uuid AND last_run_id=$4::uuid`, input.TenantID, input.ProjectID, input.BookPlanID, admission.RunID)
		if err != nil {
			return admissionFailed()
		}
		if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
			return admissionFailed()
		}
		if err := appendBookEvent(ctx, tx, input, admission.RunID, "planning.start_failed", "failed", 0); err != nil {
			return admissionFailed()
		}
	}
	payload, _ := json.Marshal(map[string]any{"status": "failed", "module_key": admission.ModuleKey, "error_code": "WORKFLOW_START_FAILED"})
	_, err = tx.ExecContext(ctx, `INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
) VALUES ($1::uuid,$3::uuid,$4,$2::uuid,'workflow.start_failed',2,$5::jsonb)`, input.TenantID, input.ProjectID, admission.RunID, admission.WorkflowType, string(payload))
	if err != nil {
		return admissionFailed()
	}
	if err := tx.Commit(); err != nil {
		return admissionFailed()
	}
	return nil
}

func findReplay(ctx context.Context, tx *sql.Tx, input StartInput) (Admission, string, bool, error) {
	var result Admission
	var hash string
	err := tx.QueryRowContext(ctx, `SELECT workflow.run_id::text, workflow.project_id::text,
  workflow.workflow_type, queued.payload_jsonb->>'module_key', workflow.status,
  COALESCE(queued.payload_jsonb->>'book_plan_id',''), queued.payload_jsonb->>'payload_hash'
FROM workflow_runs workflow
JOIN workflow_events queued ON queued.tenant_id=workflow.tenant_id AND queued.run_id=workflow.run_id AND queued.event_type='workflow.queued'
WHERE workflow.tenant_id=$1::uuid AND workflow.project_id=$2::uuid
	AND workflow.workflow_type=$3 AND workflow.started_by=$4::uuid
  AND queued.payload_jsonb->>'request_id'=$5
ORDER BY workflow.created_at LIMIT 1`, input.TenantID, input.ProjectID, WorkflowType(input.Kind), input.ActorUserID, input.RequestID).Scan(
		&result.RunID, &result.ProjectID, &result.WorkflowType, &result.ModuleKey, &result.Status, &result.BookPlanID, &hash)
	if errors.Is(err, sql.ErrNoRows) {
		return Admission{}, "", false, nil
	}
	if err != nil {
		return Admission{}, "", false, admissionFailed()
	}
	return result, hash, true, nil
}

func validateDedupSource(ctx context.Context, tx *sql.Tx, input StartInput) error {
	var count int
	err := tx.QueryRowContext(ctx, `SELECT count(*) FROM manuscript_blocks block
JOIN writer_drafts draft ON draft.tenant_id=block.tenant_id AND draft.project_id=block.project_id
  AND draft.draft_id=block.source_draft_id AND draft.status='adopted'
WHERE block.tenant_id=$1::uuid AND block.project_id=$2::uuid AND block.status='active'
	AND ($3='' OR block.chapter_id=NULLIF($3,'')::uuid)
  AND (cardinality($4::uuid[])=0 OR block.block_id=ANY($4::uuid[]))`, input.TenantID, input.ProjectID, input.ChapterID, input.BlockIDs).Scan(&count)
	if err != nil {
		return admissionFailed()
	}
	if count == 0 || (len(input.BlockIDs) > 0 && count != len(input.BlockIDs)) {
		return appError("WRITER_DEDUP_SOURCE_NOT_FOUND", "selected adopted manuscript source was not found")
	}
	return nil
}

func validateBookPlan(ctx context.Context, tx *sql.Tx, input StartInput) error {
	var status, lastStatus string
	var version int64
	err := tx.QueryRowContext(ctx, `SELECT status, optimistic_version, COALESCE(last_run_status,'') FROM book_plans
WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND book_plan_id=$3::uuid FOR UPDATE`, input.TenantID, input.ProjectID, input.BookPlanID).Scan(&status, &version, &lastStatus)
	if errors.Is(err, sql.ErrNoRows) {
		return appError("BOOK_PLAN_NOT_FOUND", "book plan was not found")
	}
	if err != nil {
		return admissionFailed()
	}
	if status != "draft" || version != input.ExpectedVersion || lastStatus == "queued" || lastStatus == "running" {
		return appError("BOOK_PLAN_CONFLICT", "book plan generation state changed")
	}
	return nil
}

func queuedPayload(input StartInput, admission Admission, payloadHash string) map[string]any {
	payload := map[string]any{"status": "queued", "request_id": input.RequestID, "payload_hash": payloadHash, "module_key": admission.ModuleKey}
	if input.Kind == KindDedup {
		payload["block_ids"], payload["chapter_id"] = input.BlockIDs, input.ChapterID
	}
	if input.Kind == KindBookPlan {
		payload["book_plan_id"], payload["expected_version"] = input.BookPlanID, input.ExpectedVersion
	}
	return payload
}

func appendBookEvent(ctx context.Context, tx *sql.Tx, input StartInput, runID, eventType, status string, itemCount int) error {
	_, err := tx.ExecContext(ctx, appendBookEventSQL, input.TenantID, input.ProjectID, input.BookPlanID, runID, eventType, status, itemCount)
	return err
}

const appendBookEventSQL = `INSERT INTO book_run_events (
  tenant_id,project_id,book_plan_id,run_id,sequence,event_type,status,item_count
) VALUES ($1::uuid,$2::uuid,$3::uuid,$4::uuid,
  (SELECT COALESCE(max(sequence),0)+1 FROM book_run_events
   WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND book_plan_id=$3::uuid),$5,$6,$7)`

func admissionFailed() *AppError {
	return appError("WRITER_PLANNING_ADMISSION_FAILED", "writer planning admission failed")
}

