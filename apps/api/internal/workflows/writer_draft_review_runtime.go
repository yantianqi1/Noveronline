package workflows

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	WriterReviewWorkflowName = "WriterReviewWorkflow"
	WriterReviewTaskQueue    = "writer-reviewer"
	WriterReviewerModuleKey  = "writer_reviewer"
)

type DraftReviewAdmissionStore interface {
	AdmitDraftReview(context.Context, StartDraftReviewInput, DraftReviewAdmission, string) (DraftReviewAdmission, bool, error)
	CompensateDraftReviewStart(context.Context, StartDraftReviewInput, DraftReviewAdmission) error
}

type TemporalDraftReviewConfig struct {
	Client         TemporalWorkflowClient
	TaskQueue      string
	AdmissionStore DraftReviewAdmissionStore
}

type TemporalDraftReviewStarter struct {
	client         TemporalWorkflowClient
	taskQueue      string
	admissionStore DraftReviewAdmissionStore
}

type DraftReviewStarter interface {
	StartDraftReview(context.Context, StartDraftReviewInput) (DraftReviewAdmission, error)
}

type DraftReviewReader interface {
	ListDraftReviews(context.Context, ListDraftReviewsInput) (DraftReviewList, error)
}

type DraftReviewRuntimeService struct {
	starter DraftReviewStarter
	reader  DraftReviewReader
}

func NewDraftReviewRuntimeService(starter DraftReviewStarter, reader DraftReviewReader) *DraftReviewRuntimeService {
	return &DraftReviewRuntimeService{starter: starter, reader: reader}
}

func (s *DraftReviewRuntimeService) StartDraftReview(ctx context.Context, input StartDraftReviewInput) (DraftReviewAdmission, error) {
	if s == nil || s.starter == nil {
		return DraftReviewAdmission{}, &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	return s.starter.StartDraftReview(ctx, input)
}

func (s *DraftReviewRuntimeService) ListDraftReviews(ctx context.Context, input ListDraftReviewsInput) (DraftReviewList, error) {
	if s == nil || s.reader == nil {
		return DraftReviewList{}, &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	return s.reader.ListDraftReviews(ctx, input)
}

func NewTemporalDraftReviewStarter(config TemporalDraftReviewConfig) *TemporalDraftReviewStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = WriterReviewTaskQueue
	}
	return &TemporalDraftReviewStarter{client: config.Client, taskQueue: taskQueue, admissionStore: config.AdmissionStore}
}

func (s *TemporalDraftReviewStarter) StartDraftReview(ctx context.Context, input StartDraftReviewInput) (DraftReviewAdmission, error) {
	input = normalizeDraftReviewInput(input)
	if input.TenantID == "" || input.ProjectID == "" || input.DraftID == "" || input.ActorUserID == "" || input.RequestID == "" {
		return DraftReviewAdmission{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, draft_id, actor_user_id, and request_id are required"}
	}
	if input.ModuleKey != "" && input.ModuleKey != WriterReviewerModuleKey {
		return DraftReviewAdmission{}, &AppError{Code: "VALIDATION_FAILED", Message: "writer review module_key must be writer_reviewer"}
	}
	if s.client == nil || s.admissionStore == nil {
		return DraftReviewAdmission{}, &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	runID, err := newRunID()
	if err != nil {
		return DraftReviewAdmission{}, writerReviewAdmissionFailed()
	}
	reviewID, err := newRunID()
	if err != nil {
		return DraftReviewAdmission{}, writerReviewAdmissionFailed()
	}
	proposed := DraftReviewAdmission{
		ReviewID: reviewID, RunID: runID, DraftID: input.DraftID, ProjectID: input.ProjectID,
		Status: "queued", WorkflowType: WriterReviewWorkflowType,
	}
	temporalWorkflowID := "writer_review_" + reviewID
	admitted, replayed, err := s.admissionStore.AdmitDraftReview(ctx, input, proposed, temporalWorkflowID)
	if err != nil {
		return DraftReviewAdmission{}, err
	}
	if replayed {
		return admitted, nil
	}
	payload := map[string]any{
		"context": map[string]any{
			"tenant_id": input.TenantID, "project_id": input.ProjectID,
			"run_id": admitted.RunID, "workflow_type": WriterReviewWorkflowType,
			"actor_user_id": input.ActorUserID, "module_key": WriterReviewerModuleKey,
			"trace_id":    traceIDForRun(admitted.RunID),
			"permissions": map[string][]string{WriterReviewerModuleKey: {"run"}},
		},
		"review_id": admitted.ReviewID,
		"draft_id":  admitted.DraftID,
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID: temporalWorkflowID, TaskQueue: s.taskQueue,
		WorkflowExecutionTimeout: time.Hour, WorkflowRunTimeout: time.Hour,
	}, WriterReviewWorkflowName, payload)
	if err != nil {
		compensationCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		if compensationErr := s.admissionStore.CompensateDraftReviewStart(compensationCtx, input, admitted); compensationErr != nil {
			return DraftReviewAdmission{}, compensationErr
		}
		return DraftReviewAdmission{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to start writer review workflow"}
	}
	return admitted, nil
}

func (s *TemporalDraftReviewStarter) ListDraftReviews(context.Context, ListDraftReviewsInput) (DraftReviewList, error) {
	return DraftReviewList{}, &AppError{Code: "WRITER_REVIEW_QUERY_FAILED", Message: "writer review query backend is not configured"}
}

type SQLDraftReviewRuntimeStore struct{ db *sql.DB }

func NewSQLDraftReviewRuntimeStore(db *sql.DB) *SQLDraftReviewRuntimeStore {
	return &SQLDraftReviewRuntimeStore{db: db}
}

type DraftReviewOwnerLookupInput struct {
	TenantID    string
	DraftID     string
	IssueID     string
	ActorUserID string
}

type DraftReviewOwnerLookup interface {
	LookupDraftReviewProject(context.Context, DraftReviewOwnerLookupInput) (string, error)
}

func (s *SQLDraftReviewRuntimeStore) LookupDraftReviewProject(ctx context.Context, input DraftReviewOwnerLookupInput) (string, error) {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.DraftID = strings.TrimSpace(input.DraftID)
	input.IssueID = strings.TrimSpace(input.IssueID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	if input.TenantID == "" || input.ActorUserID == "" || (input.DraftID == "" && input.IssueID == "") || (input.DraftID != "" && input.IssueID != "") {
		return "", &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, actor_user_id, and exactly one review resource id are required"}
	}
	if s == nil || s.db == nil {
		return "", &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return "", draftReviewQueryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return "", draftReviewQueryFailed()
	}
	query := `SELECT project_id::text FROM writer_drafts
WHERE tenant_id::text = $1 AND draft_id::text = $2`
	resourceID := input.DraftID
	if input.IssueID != "" {
		query = `SELECT project_id::text FROM draft_review_issues
WHERE tenant_id::text = $1 AND issue_id::text = $2`
		resourceID = input.IssueID
	}
	var projectID string
	if err := tx.QueryRowContext(ctx, query, input.TenantID, resourceID).Scan(&projectID); errors.Is(err, sql.ErrNoRows) {
		return "", &AppError{Code: "NOT_FOUND", Message: "writer review resource not found"}
	} else if err != nil {
		return "", draftReviewQueryFailed()
	}
	if err := tx.Commit(); err != nil {
		return "", draftReviewQueryFailed()
	}
	return strings.TrimSpace(projectID), nil
}

func (s *SQLDraftReviewRuntimeStore) AdmitDraftReview(
	ctx context.Context,
	input StartDraftReviewInput,
	proposed DraftReviewAdmission,
	temporalWorkflowID string,
) (DraftReviewAdmission, bool, error) {
	if s == nil || s.db == nil {
		return DraftReviewAdmission{}, false, writerReviewAdmissionFailed()
	}
	input = normalizeDraftReviewInput(input)
	payloadHash, optionsJSON, err := draftReviewPayloadHash(input)
	if err != nil {
		return DraftReviewAdmission{}, false, err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return DraftReviewAdmission{}, false, writerReviewAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setDraftReviewTenantContext(ctx, tx, input); err != nil {
		return DraftReviewAdmission{}, false, err
	}
	if err := lockCandidateDraftForReview(ctx, tx, input); err != nil {
		return DraftReviewAdmission{}, false, err
	}
	if existing, existingHash, found, replayErr := findDraftReviewReplay(ctx, tx, input); replayErr != nil {
		return DraftReviewAdmission{}, false, replayErr
	} else if found {
		if existingHash != payloadHash {
			return DraftReviewAdmission{}, false, &AppError{Code: "IDEMPOTENCY_CONFLICT", Message: "request_id was already used with a different writer review request"}
		}
		if err := tx.Commit(); err != nil {
			return DraftReviewAdmission{}, false, writerReviewAdmissionFailed()
		}
		return existing, true, nil
	}
	eventID, err := newRunID()
	if err != nil {
		return DraftReviewAdmission{}, false, writerReviewAdmissionFailed()
	}
	payload, err := json.Marshal(map[string]any{
		"status": "queued", "workflow_type": WriterReviewWorkflowType,
		"request_id": input.RequestID, "payload_hash": payloadHash,
		"draft_id": input.DraftID, "review_id": proposed.ReviewID,
		"module_key": WriterReviewerModuleKey,
	})
	if err != nil {
		return DraftReviewAdmission{}, false, &AppError{Code: "VALIDATION_FAILED", Message: "writer review admission payload must be JSON serializable"}
	}
	result, err := tx.ExecContext(ctx, `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  ) VALUES ($1::uuid, $4::uuid, 'writer_review', $2::uuid, 'queued', 0,
            'queued', $3::uuid, $8)
  RETURNING tenant_id, run_id, project_id
), review_insert AS (
  INSERT INTO draft_reviews (
    tenant_id, project_id, draft_id, review_id, run_id, status, module_key,
    note, options_jsonb, created_by
  )
  SELECT tenant_id, project_id, $5::uuid, $6::uuid, run_id, 'queued',
         'writer_reviewer', NULL, $9::jsonb, $3::uuid
  FROM workflow_insert
  RETURNING tenant_id, project_id, run_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT tenant_id, $7::uuid, run_id, 'writer_review', project_id,
       'workflow.queued', 1, $10::jsonb FROM review_insert`,
		input.TenantID, input.ProjectID, input.ActorUserID, proposed.RunID,
		input.DraftID, proposed.ReviewID, eventID, temporalWorkflowID,
		string(optionsJSON), string(payload),
	)
	if err != nil {
		return DraftReviewAdmission{}, false, writerReviewAdmissionFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return DraftReviewAdmission{}, false, writerReviewAdmissionFailed()
	}
	if err := tx.Commit(); err != nil {
		return DraftReviewAdmission{}, false, writerReviewAdmissionFailed()
	}
	return proposed, false, nil
}

func (s *SQLDraftReviewRuntimeStore) CompensateDraftReviewStart(ctx context.Context, input StartDraftReviewInput, review DraftReviewAdmission) error {
	if s == nil || s.db == nil {
		return writerReviewAdmissionFailed()
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return writerReviewAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setDraftReviewTenantContext(ctx, tx, input); err != nil {
		return err
	}
	eventID, err := newRunID()
	if err != nil {
		return writerReviewAdmissionFailed()
	}
	payload, _ := json.Marshal(map[string]any{
		"status": "failed", "workflow_type": WriterReviewWorkflowType,
		"review_id": review.ReviewID, "draft_id": review.DraftID,
		"module_key": WriterReviewerModuleKey, "error_code": "WORKFLOW_START_FAILED",
	})
	result, err := tx.ExecContext(ctx, `WITH failed_review AS (
  UPDATE draft_reviews SET status = 'failed', error_code = 'WORKFLOW_START_FAILED',
    error_message = 'writer review workflow failed to start', updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND review_id::text = $3
    AND draft_id::text = $4 AND run_id::text = $5 AND status = 'queued'
  RETURNING tenant_id, project_id, run_id
), failed_workflow AS (
  UPDATE workflow_runs SET status = 'failed', progress = 0,
    message = 'writer review workflow failed to start', error_code = 'WORKFLOW_START_FAILED',
    error_message = 'writer review workflow failed to start', updated_at = now()
  FROM failed_review
  WHERE workflow_runs.tenant_id = failed_review.tenant_id
    AND workflow_runs.run_id = failed_review.run_id
    AND workflow_runs.workflow_type = 'writer_review'
    AND workflow_runs.status = 'queued'
  RETURNING failed_review.tenant_id, failed_review.project_id, failed_review.run_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT tenant_id, $6::uuid, run_id, 'writer_review', project_id,
       'workflow.start_failed', 2, $7::jsonb FROM failed_workflow`,
		input.TenantID, input.ProjectID, review.ReviewID, review.DraftID, review.RunID,
		eventID, string(payload),
	)
	if err != nil {
		return writerReviewAdmissionFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return writerReviewAdmissionFailed()
	}
	if err := tx.Commit(); err != nil {
		return writerReviewAdmissionFailed()
	}
	return nil
}

func setDraftReviewTenantContext(ctx context.Context, tx *sql.Tx, input StartDraftReviewInput) error {
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return writerReviewAdmissionFailed()
	}
	return nil
}

func lockCandidateDraftForReview(ctx context.Context, tx *sql.Tx, input StartDraftReviewInput) error {
	var status string
	err := tx.QueryRowContext(ctx, `SELECT status FROM writer_drafts
WHERE tenant_id::text = $1 AND project_id::text = $2 AND draft_id::text = $3
FOR UPDATE`, input.TenantID, input.ProjectID, input.DraftID).Scan(&status)
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "NOT_FOUND", Message: "draft not found"}
	}
	if err != nil {
		return writerReviewAdmissionFailed()
	}
	if status != "candidate" {
		return &AppError{Code: "DRAFT_NOT_CANDIDATE", Message: "writer review requires a candidate draft"}
	}
	return nil
}

func findDraftReviewReplay(ctx context.Context, tx *sql.Tx, input StartDraftReviewInput) (DraftReviewAdmission, string, bool, error) {
	var review DraftReviewAdmission
	var payloadHash string
	err := tx.QueryRowContext(ctx, `SELECT review.review_id::text, review.run_id::text,
  review.draft_id::text, review.project_id::text, review.status,
  workflow.workflow_type, queued.payload_jsonb->>'payload_hash'
FROM draft_reviews AS review
JOIN workflow_runs AS workflow ON workflow.tenant_id = review.tenant_id AND workflow.run_id = review.run_id
JOIN workflow_events AS queued ON queued.tenant_id = workflow.tenant_id
 AND queued.run_id = workflow.run_id AND queued.event_type = 'workflow.queued'
WHERE review.tenant_id::text = $1 AND review.project_id::text = $2
  AND review.draft_id::text = $3 AND review.created_by::text = $4
  AND queued.payload_jsonb->>'request_id' = $5
ORDER BY queued.created_at ASC LIMIT 1`, input.TenantID, input.ProjectID, input.DraftID,
		input.ActorUserID, input.RequestID).Scan(
		&review.ReviewID, &review.RunID, &review.DraftID, &review.ProjectID,
		&review.Status, &review.WorkflowType, &payloadHash,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return DraftReviewAdmission{}, "", false, nil
	}
	if err != nil {
		return DraftReviewAdmission{}, "", false, writerReviewAdmissionFailed()
	}
	return review, payloadHash, true, nil
}

func draftReviewPayloadHash(input StartDraftReviewInput) (string, []byte, error) {
	optionsJSON, err := json.Marshal(sanitizeDraftReviewOptions(input.Options))
	if err != nil {
		return "", nil, &AppError{Code: "VALIDATION_FAILED", Message: "writer review options must be JSON serializable"}
	}
	payload, err := json.Marshal(map[string]any{
		"tenant_id": input.TenantID, "project_id": input.ProjectID,
		"draft_id": input.DraftID, "actor_user_id": input.ActorUserID,
		"module_key": WriterReviewerModuleKey, "options": json.RawMessage(optionsJSON),
	})
	if err != nil {
		return "", nil, &AppError{Code: "VALIDATION_FAILED", Message: "writer review request must be JSON serializable"}
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), optionsJSON, nil
}

func normalizeDraftReviewInput(input StartDraftReviewInput) StartDraftReviewInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.DraftID = strings.TrimSpace(input.DraftID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.ModuleKey = strings.TrimSpace(input.ModuleKey)
	return input
}

func writerReviewAdmissionFailed() *AppError {
	return &AppError{Code: "WRITER_REVIEW_ADMISSION_FAILED", Message: "writer review admission failed"}
}

type UpdateDraftReviewIssueInput struct {
	TenantID    string
	ProjectID   string
	IssueID     string
	ActorUserID string
	RequestID   string
	Status      string
	Version     string
}

type DraftReviewIssueMutation struct {
	IssueID   string `json:"issue_id"`
	ReviewID  string `json:"review_id"`
	ProjectID string `json:"project_id"`
	Status    string `json:"status"`
	Version   string `json:"version"`
}

type SQLDraftReviewIssueStore struct{ db *sql.DB }

type DraftReviewIssueStore interface {
	UpdateIssueStatus(context.Context, UpdateDraftReviewIssueInput) (DraftReviewIssueMutation, error)
}

func NewSQLDraftReviewIssueStore(db *sql.DB) *SQLDraftReviewIssueStore {
	return &SQLDraftReviewIssueStore{db: db}
}

func (s *SQLDraftReviewIssueStore) UpdateIssueStatus(ctx context.Context, input UpdateDraftReviewIssueInput) (DraftReviewIssueMutation, error) {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.IssueID = strings.TrimSpace(input.IssueID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Status = strings.TrimSpace(input.Status)
	input.Version = strings.TrimSpace(input.Version)
	if input.TenantID == "" || input.ProjectID == "" || input.IssueID == "" || input.ActorUserID == "" || input.Version == "" {
		return DraftReviewIssueMutation{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, issue_id, actor_user_id, and version are required"}
	}
	if input.Status != "accepted" && input.Status != "dismissed" && input.Status != "resolved" {
		return DraftReviewIssueMutation{}, &AppError{Code: "VALIDATION_FAILED", Message: "issue status must be accepted, dismissed, or resolved"}
	}
	if s == nil || s.db == nil {
		return DraftReviewIssueMutation{}, &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return DraftReviewIssueMutation{}, draftReviewIssueWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return DraftReviewIssueMutation{}, draftReviewIssueWriteFailed()
	}
	var current DraftReviewIssueMutation
	err = tx.QueryRowContext(ctx, `SELECT issue_id::text, review_id::text, project_id::text, status, updated_at::text
FROM draft_review_issues
WHERE tenant_id::text = $1 AND project_id::text = $2 AND issue_id::text = $3
FOR UPDATE`, input.TenantID, input.ProjectID, input.IssueID).Scan(
		&current.IssueID, &current.ReviewID, &current.ProjectID, &current.Status, &current.Version,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return DraftReviewIssueMutation{}, &AppError{Code: "NOT_FOUND", Message: "writer review issue not found"}
	}
	if err != nil {
		return DraftReviewIssueMutation{}, draftReviewIssueWriteFailed()
	}
	if current.Status == input.Status {
		if err := tx.Commit(); err != nil {
			return DraftReviewIssueMutation{}, draftReviewIssueWriteFailed()
		}
		return current, nil
	}
	if current.Status != "open" || current.Version != input.Version {
		return DraftReviewIssueMutation{}, &AppError{Code: "WRITER_REVIEW_ISSUE_CONFLICT", Message: "writer review issue was updated concurrently"}
	}
	var updated DraftReviewIssueMutation
	err = tx.QueryRowContext(ctx, `WITH updated AS (
  UPDATE draft_review_issues SET status = $4, updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND issue_id::text = $3
    AND status = 'open' AND updated_at::text = $5
  RETURNING issue_id, review_id, project_id, status, updated_at
), audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, request_id, metadata_jsonb
  )
  SELECT $1::uuid, $6::uuid, 'writer.review_issue_status_changed',
    'draft_review_issue', issue_id, project_id, NULLIF($7, ''),
    jsonb_build_object('from_status', 'open', 'to_status', status,
      'version_before', $5, 'version_after', updated_at::text)
  FROM updated RETURNING resource_id
)
SELECT updated.issue_id::text, updated.review_id::text, updated.project_id::text,
       updated.status, updated.updated_at::text
FROM updated JOIN audit ON audit.resource_id = updated.issue_id`,
		input.TenantID, input.ProjectID, input.IssueID, input.Status, input.Version,
		input.ActorUserID, input.RequestID,
	).Scan(&updated.IssueID, &updated.ReviewID, &updated.ProjectID, &updated.Status, &updated.Version)
	if errors.Is(err, sql.ErrNoRows) {
		return DraftReviewIssueMutation{}, &AppError{Code: "WRITER_REVIEW_ISSUE_CONFLICT", Message: "writer review issue was updated concurrently"}
	}
	if err != nil {
		return DraftReviewIssueMutation{}, draftReviewIssueWriteFailed()
	}
	if err := tx.Commit(); err != nil {
		return DraftReviewIssueMutation{}, draftReviewIssueWriteFailed()
	}
	return updated, nil
}

func draftReviewIssueWriteFailed() *AppError {
	return &AppError{Code: "WRITER_REVIEW_ISSUE_WRITE_FAILED", Message: "writer review issue update failed"}
}
