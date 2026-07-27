package workflows

import (
	"context"
	"database/sql"
	"errors"
	"strings"
)

// GetWriterDraftInput identifies one writer draft for the detail read. The
// tenant boundary comes from the authenticated request; project authorization
// happens in the HTTP layer against the returned ProjectID.
type GetWriterDraftInput struct {
	TenantID       string
	DraftID        string
	ActorUserID    string
	IncludeContent bool
}

// WriterDraftDetail is the public draft projection the writer workbench polls:
// the rail needs the status (candidate/adopted/rejected) as the adoption source
// of truth, and — with IncludeContent — the drafted prose for settled turns.
type WriterDraftDetail struct {
	DraftID     string `json:"draft_id"`
	ProjectID   string `json:"project_id"`
	RunID       string `json:"run_id,omitempty"`
	ChapterID   string `json:"chapter_id,omitempty"`
	SceneID     string `json:"scene_id,omitempty"`
	Status      string `json:"status"`
	WordCount   int    `json:"word_count"`
	ContentText string `json:"content_text,omitempty"`
	CreatedAt   string `json:"created_at"`
	UpdatedAt   string `json:"updated_at"`
}

type WriterDraftReader interface {
	GetWriterDraft(context.Context, GetWriterDraftInput) (WriterDraftDetail, error)
}

// GetWriterDraft reads one draft under tenant RLS. Content rides along only on
// request (same permission surface as manuscript block bodies).
func (s *SQLDraftReviewRuntimeStore) GetWriterDraft(ctx context.Context, input GetWriterDraftInput) (WriterDraftDetail, error) {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.DraftID = strings.TrimSpace(input.DraftID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	if input.TenantID == "" || input.DraftID == "" {
		return WriterDraftDetail{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and draft_id are required"}
	}
	if s == nil || s.db == nil {
		return WriterDraftDetail{}, &AppError{Code: "WRITER_BACKEND_UNCONFIGURED", Message: "writer draft backend is not configured"}
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return WriterDraftDetail{}, writerDraftReadFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)", input.TenantID, input.ActorUserID); err != nil {
		return WriterDraftDetail{}, writerDraftReadFailed()
	}
	query := `SELECT
  draft_id::text,
  project_id::text,
  COALESCE(run_id::text, ''),
  COALESCE(chapter_id::text, ''),
  COALESCE(scene_id::text, ''),
  status,
  word_count,
  CASE WHEN $3::boolean THEN content_text ELSE '' END,
  created_at::text,
  updated_at::text
FROM writer_drafts
WHERE tenant_id::text = $1 AND draft_id::text = $2
LIMIT 1`
	var detail WriterDraftDetail
	err = tx.QueryRowContext(ctx, query, input.TenantID, input.DraftID, input.IncludeContent).Scan(
		&detail.DraftID,
		&detail.ProjectID,
		&detail.RunID,
		&detail.ChapterID,
		&detail.SceneID,
		&detail.Status,
		&detail.WordCount,
		&detail.ContentText,
		&detail.CreatedAt,
		&detail.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return WriterDraftDetail{}, &AppError{Code: "NOT_FOUND", Message: "writer draft not found"}
	}
	if err != nil {
		return WriterDraftDetail{}, writerDraftReadFailed()
	}
	if err := tx.Commit(); err != nil {
		return WriterDraftDetail{}, writerDraftReadFailed()
	}
	return detail, nil
}

func writerDraftReadFailed() *AppError {
	return &AppError{Code: "WRITER_DRAFT_QUERY_FAILED", Message: "writer draft read failed"}
}
