package workflows

import (
	"context"
	"database/sql"
	"strings"
)

type SQLDraftAdoptionStoreConfig struct {
	Queryer    DraftAdoptionSQLQueryer
	OutboxHook DraftAdoptionOutboxHook
}

type SQLDraftAdoptionStore struct {
	queryer    DraftAdoptionSQLQueryer
	outboxHook DraftAdoptionOutboxHook
}

type DraftAdoptionSQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
	Commit() error
	Rollback() error
	// ExecContext runs SQL on the same open adoption transaction (before Commit).
	ExecContext(context.Context, string, ...any) (sql.Result, error)
	// QueryRowContext runs a single-row query on the same open adoption transaction.
	QueryRowContext(context.Context, string, ...any) *sql.Row
}

type DraftAdoptionSQLQueryer interface {
	QueryDraftAdoptionContext(context.Context, string, string, ...any) (DraftAdoptionSQLRows, error)
}

// DraftAdoptionOutboxHook inserts durable post-adoption work inside the adoption transaction.
type DraftAdoptionOutboxHook interface {
	EnqueueAfterAdoptionInTx(context.Context, DraftAdoptionSQLRows, DraftAdoptionInput, DraftAdoptionResult) error
}

type sqlDBWriterDraftAdoptionQueryer struct {
	db *sql.DB
}

func NewSQLDBWriterDraftAdoptionQueryer(db *sql.DB) DraftAdoptionSQLQueryer {
	return sqlDBWriterDraftAdoptionQueryer{db: db}
}

func (q sqlDBWriterDraftAdoptionQueryer) QueryDraftAdoptionContext(ctx context.Context, tenantID string, query string, args ...any) (DraftAdoptionSQLRows, error) {
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
	return &draftAdoptionTenantRows{rows: sqlDraftAdoptionRows{rows: rows}, tx: tx}, nil
}

type draftAdoptionTenantRows struct {
	rows   DraftAdoptionSQLRows
	tx     *sql.Tx
	closed bool
	done   bool
}

func (r *draftAdoptionTenantRows) Next() bool {
	return r.rows.Next()
}

func (r *draftAdoptionTenantRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *draftAdoptionTenantRows) Close() error {
	if r.closed {
		return nil
	}
	r.closed = true
	return r.rows.Close()
}

func (r *draftAdoptionTenantRows) Err() error {
	return r.rows.Err()
}

func (r *draftAdoptionTenantRows) Commit() error {
	if r.done {
		return nil
	}
	r.done = true
	if err := r.Close(); err != nil {
		_ = r.tx.Rollback()
		return err
	}
	return r.tx.Commit()
}

func (r *draftAdoptionTenantRows) Rollback() error {
	if r.done {
		return nil
	}
	r.done = true
	closeErr := r.Close()
	rollbackErr := r.tx.Rollback()
	if closeErr != nil {
		return closeErr
	}
	return rollbackErr
}

func (r *draftAdoptionTenantRows) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	if r == nil || r.tx == nil {
		return nil, draftAdoptionWriteFailed()
	}
	return r.tx.ExecContext(ctx, query, args...)
}

func (r *draftAdoptionTenantRows) QueryRowContext(ctx context.Context, query string, args ...any) *sql.Row {
	if r == nil || r.tx == nil {
		return nil
	}
	return r.tx.QueryRowContext(ctx, query, args...)
}

type sqlDraftAdoptionRows struct {
	rows *sql.Rows
}

func (r sqlDraftAdoptionRows) Next() bool {
	return r.rows.Next()
}

func (r sqlDraftAdoptionRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r sqlDraftAdoptionRows) Close() error {
	return r.rows.Close()
}

func (r sqlDraftAdoptionRows) Err() error {
	return r.rows.Err()
}

func (r sqlDraftAdoptionRows) Commit() error {
	return nil
}

func (r sqlDraftAdoptionRows) Rollback() error {
	return nil
}

func (r sqlDraftAdoptionRows) ExecContext(context.Context, string, ...any) (sql.Result, error) {
	return nil, nil
}

func (r sqlDraftAdoptionRows) QueryRowContext(context.Context, string, ...any) *sql.Row {
	return nil
}

func NewSQLDraftAdoptionStore(config SQLDraftAdoptionStoreConfig) *SQLDraftAdoptionStore {
	return &SQLDraftAdoptionStore{queryer: config.Queryer, outboxHook: config.OutboxHook}
}

func (s *SQLDraftAdoptionStore) SetOutboxHook(hook DraftAdoptionOutboxHook) {
	if s == nil {
		return
	}
	s.outboxHook = hook
}

func (s *SQLDraftAdoptionStore) AdoptDraft(ctx context.Context, input DraftAdoptionInput) (DraftAdoptionResult, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	draftID := strings.TrimSpace(input.DraftID)
	if tenantID == "" || draftID == "" {
		return DraftAdoptionResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and draft_id are required"}
	}
	if input.BlockOrder < 0 {
		return DraftAdoptionResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "block_order must be non-negative"}
	}
	if s.queryer == nil {
		return DraftAdoptionResult{}, &AppError{Code: "DRAFT_ADOPTION_BACKEND_UNCONFIGURED", Message: "draft adoption backend is not configured"}
	}

	rows, err := s.queryer.QueryDraftAdoptionContext(
		ctx,
		tenantID,
		adoptDraftReturningQuery(),
		tenantID,
		draftID,
		strings.TrimSpace(input.ActorUserID),
		strings.TrimSpace(input.RequestID),
		input.BlockOrder,
		strings.TrimSpace(input.ChapterID),
	)
	if err != nil {
		return DraftAdoptionResult{}, draftAdoptionWriteFailed()
	}
	committed := false
	defer func() {
		if !committed {
			_ = rows.Rollback()
		}
	}()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return DraftAdoptionResult{}, draftAdoptionWriteFailed()
		}
		return DraftAdoptionResult{}, &AppError{Code: "NOT_FOUND", Message: "candidate draft not found"}
	}
	var result DraftAdoptionResult
	var chapterID sql.NullString
	var sceneID sql.NullString
	if err := rows.Scan(
		&result.DraftID,
		&result.BlockID,
		&result.ProjectID,
		&result.Status,
		&chapterID,
		&sceneID,
		&result.BlockOrder,
	); err != nil {
		return DraftAdoptionResult{}, draftAdoptionWriteFailed()
	}
	if chapterID.Valid {
		result.ChapterID = chapterID.String
	}
	if sceneID.Valid {
		result.SceneID = sceneID.String
	}
	if err := rows.Err(); err != nil {
		return DraftAdoptionResult{}, draftAdoptionWriteFailed()
	}
	// CONN-004/005: durable distillation outbox must share the adoption transaction so
	// "adopted but enqueue failed" cannot leave manuscript without a recoverable request.
	if s.outboxHook != nil && strings.TrimSpace(result.BlockID) != "" {
		if err := s.outboxHook.EnqueueAfterAdoptionInTx(ctx, rows, input, result); err != nil {
			return DraftAdoptionResult{}, err
		}
	}
	if err := rows.Commit(); err != nil {
		return DraftAdoptionResult{}, draftAdoptionWriteFailed()
	}
	committed = true
	return result, nil
}

func draftAdoptionWriteFailed() *AppError {
	return &AppError{Code: "DRAFT_ADOPTION_WRITE_FAILED", Message: "draft adoption write failed"}
}

func adoptDraftReturningQuery() string {
	return `WITH draft_scope AS (
  SELECT
    tenant_id,
    draft_id,
    run_id,
    project_id,
    COALESCE(NULLIF($6, '')::uuid, chapter_id) AS chapter_id,
    scene_id,
    content_text,
    word_count,
    status,
    adopted_block_id
  FROM writer_drafts
  WHERE tenant_id::text = $1
    AND draft_id::text = $2
    AND status IN ('candidate', 'adopted')
  LIMIT 1
  FOR UPDATE
),
candidate_draft AS (
  SELECT *
  FROM draft_scope
  WHERE status = 'candidate'
),
existing_adoption AS (
  SELECT
    draft_scope.draft_id::text AS draft_id,
    existing.block_id::text AS block_id,
    draft_scope.project_id::text AS project_id,
    draft_scope.status,
    COALESCE(existing.chapter_id::text, draft_scope.chapter_id::text, '') AS chapter_id,
    COALESCE(existing.scene_id::text, draft_scope.scene_id::text, '') AS scene_id,
    existing.block_order
  FROM draft_scope
  JOIN manuscript_blocks existing
    ON existing.tenant_id = draft_scope.tenant_id
   AND existing.project_id = draft_scope.project_id
   AND existing.block_id = draft_scope.adopted_block_id
   AND existing.source_draft_id = draft_scope.draft_id
  WHERE draft_scope.status = 'adopted'
),
next_order AS (
  SELECT
    candidate_draft.tenant_id,
    candidate_draft.project_id,
    COALESCE(NULLIF($5::integer, 0), (
      SELECT COALESCE(MAX(block_order), 0) + 1
      FROM manuscript_blocks existing
      WHERE existing.tenant_id = candidate_draft.tenant_id
        AND existing.project_id = candidate_draft.project_id
    )) AS block_order
  FROM candidate_draft
),
inserted_block AS (
  INSERT INTO manuscript_blocks (
    tenant_id,
    project_id,
    chapter_id,
    scene_id,
    source_draft_id,
    source_writer_run_id,
    block_order,
    content_text,
    word_count,
    version,
    status,
    created_by,
    updated_by
  )
  SELECT
    candidate_draft.tenant_id,
    candidate_draft.project_id,
    candidate_draft.chapter_id,
    candidate_draft.scene_id,
    candidate_draft.draft_id,
    candidate_draft.run_id,
    next_order.block_order,
    candidate_draft.content_text,
    candidate_draft.word_count,
    1,
    'active',
    NULLIF($3, '')::uuid,
    NULLIF($3, '')::uuid
  FROM candidate_draft
  JOIN next_order
    ON next_order.tenant_id = candidate_draft.tenant_id
   AND next_order.project_id = candidate_draft.project_id
  RETURNING block_id, source_draft_id, project_id, chapter_id, scene_id, block_order, content_text, word_count, version, status, tags, source_writer_run_id
),
inserted_version AS (
  INSERT INTO manuscript_block_versions (
    tenant_id,
    project_id,
    block_id,
    version_number,
    chapter_id,
    scene_id,
    status,
    tags,
    block_order,
    content_text,
    word_count,
    source_draft_id,
    source_writer_run_id,
    snapshot_reason,
    created_by
  )
  SELECT
    candidate_draft.tenant_id,
    inserted_block.project_id,
    inserted_block.block_id,
    1,
    inserted_block.chapter_id,
    inserted_block.scene_id,
    inserted_block.status,
    inserted_block.tags,
    inserted_block.block_order,
    inserted_block.content_text,
    inserted_block.word_count,
    inserted_block.source_draft_id,
    inserted_block.source_writer_run_id,
    'adopt',
    NULLIF($3, '')::uuid
  FROM candidate_draft
  JOIN inserted_block
    ON inserted_block.source_draft_id = candidate_draft.draft_id
  RETURNING block_id
),
updated_draft AS (
  UPDATE writer_drafts
  SET
    status = 'adopted',
    adopted_block_id = inserted_block.block_id,
    updated_at = now()
  FROM inserted_block
  WHERE writer_drafts.tenant_id = $1::uuid
    AND writer_drafts.draft_id = inserted_block.source_draft_id
    AND writer_drafts.status = 'candidate'
  RETURNING
    writer_drafts.draft_id,
    writer_drafts.project_id,
    writer_drafts.chapter_id,
    writer_drafts.scene_id,
    writer_drafts.status,
    writer_drafts.adopted_block_id
),
audit_insert AS (
  INSERT INTO audit_logs (
    tenant_id,
    actor_user_id,
    action,
    resource_type,
    resource_id,
    project_id,
    run_id,
    request_id,
    metadata_jsonb
  )
  SELECT
    candidate_draft.tenant_id,
    NULLIF($3, '')::uuid,
    'writer.draft_adopted',
    'writer_draft',
    candidate_draft.draft_id,
    candidate_draft.project_id,
    candidate_draft.run_id,
    NULLIF($4, ''),
    jsonb_build_object(
      'block_id', inserted_block.block_id,
      'block_order', inserted_block.block_order
    )
  FROM candidate_draft
  JOIN inserted_block
    ON inserted_block.source_draft_id = candidate_draft.draft_id
  JOIN updated_draft
    ON updated_draft.draft_id = candidate_draft.draft_id
  JOIN inserted_version
    ON inserted_version.block_id = inserted_block.block_id
  RETURNING resource_id
),
new_adoption AS (
  SELECT
    updated_draft.draft_id::text AS draft_id,
    inserted_block.block_id::text AS block_id,
    updated_draft.project_id::text AS project_id,
    updated_draft.status,
    COALESCE(inserted_block.chapter_id::text, updated_draft.chapter_id::text, '') AS chapter_id,
    COALESCE(inserted_block.scene_id::text, updated_draft.scene_id::text, '') AS scene_id,
    inserted_block.block_order
  FROM updated_draft
  JOIN inserted_block
    ON inserted_block.block_id = updated_draft.adopted_block_id
)
SELECT
  draft_id,
  block_id,
  project_id,
  status,
  chapter_id,
  scene_id,
  block_order
FROM new_adoption
UNION ALL
SELECT
  draft_id,
  block_id,
  project_id,
  status,
  chapter_id,
  scene_id,
  block_order
FROM existing_adoption
LIMIT 1`
}
