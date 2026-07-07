package workflows

import (
	"context"
	"database/sql"
	"strings"
)

type SQLDraftAdoptionStoreConfig struct {
	Queryer DraftAdoptionSQLQueryer
}

type SQLDraftAdoptionStore struct {
	queryer DraftAdoptionSQLQueryer
}

type DraftAdoptionSQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
	Commit() error
	Rollback() error
}

type DraftAdoptionSQLQueryer interface {
	QueryDraftAdoptionContext(context.Context, string, string, ...any) (DraftAdoptionSQLRows, error)
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

func NewSQLDraftAdoptionStore(config SQLDraftAdoptionStoreConfig) *SQLDraftAdoptionStore {
	return &SQLDraftAdoptionStore{queryer: config.Queryer}
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
	return `WITH candidate_draft AS (
  SELECT
    tenant_id,
    draft_id,
    run_id,
    project_id,
    COALESCE(NULLIF($6, '')::uuid, chapter_id) AS chapter_id,
    scene_id,
    content_text,
    word_count
  FROM writer_drafts
  WHERE tenant_id::text = $1
    AND draft_id::text = $2
    AND status = 'candidate'
  LIMIT 1
  FOR UPDATE
),
adoption_context AS (
  SELECT $4 AS request_id
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
    source_draft_id,
    block_order,
    content_text,
    word_count,
    created_by
  )
  SELECT
    candidate_draft.tenant_id,
    candidate_draft.project_id,
    candidate_draft.chapter_id,
    candidate_draft.draft_id,
    next_order.block_order,
    candidate_draft.content_text,
    candidate_draft.word_count,
    NULLIF($3, '')::uuid
  FROM candidate_draft
  JOIN next_order
    ON next_order.tenant_id = candidate_draft.tenant_id
   AND next_order.project_id = candidate_draft.project_id
  CROSS JOIN adoption_context
  RETURNING block_id, source_draft_id, project_id, chapter_id, block_order
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
)
SELECT
  updated_draft.draft_id::text,
  inserted_block.block_id::text,
  updated_draft.project_id::text,
  updated_draft.status,
  COALESCE(inserted_block.chapter_id::text, updated_draft.chapter_id::text, ''),
  COALESCE(updated_draft.scene_id::text, ''),
  inserted_block.block_order
FROM updated_draft
JOIN inserted_block
  ON inserted_block.block_id = updated_draft.adopted_block_id`
}
