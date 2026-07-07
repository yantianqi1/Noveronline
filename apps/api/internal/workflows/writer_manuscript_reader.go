package workflows

import (
	"context"
	"database/sql"
	"strings"
	"time"
)

type SQLManuscriptReaderConfig struct {
	Queryer WriterEventSQLQueryer
}

type SQLManuscriptReader struct {
	queryer WriterEventSQLQueryer
}

type DisabledManuscriptReader struct{}

func NewDisabledManuscriptReader() *DisabledManuscriptReader {
	return &DisabledManuscriptReader{}
}

func (r *DisabledManuscriptReader) GetManuscript(context.Context, GetManuscriptInput) (Manuscript, error) {
	return Manuscript{}, &AppError{Code: "MANUSCRIPT_BACKEND_UNCONFIGURED", Message: "manuscript backend is not configured"}
}

func (r *DisabledManuscriptReader) GetManuscriptExport(context.Context, GetManuscriptExportInput) (ManuscriptExportManifest, error) {
	return ManuscriptExportManifest{}, &AppError{Code: "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", Message: "manuscript export backend is not configured"}
}

func NewSQLManuscriptReader(config SQLManuscriptReaderConfig) *SQLManuscriptReader {
	return &SQLManuscriptReader{queryer: config.Queryer}
}

func (r *SQLManuscriptReader) GetManuscript(ctx context.Context, input GetManuscriptInput) (Manuscript, error) {
	tenantID, projectID := strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return Manuscript{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return Manuscript{}, &AppError{Code: "MANUSCRIPT_BACKEND_UNCONFIGURED", Message: "manuscript backend is not configured"}
	}
	blocks, err := r.queryBlocks(ctx, tenantID, projectID)
	if err != nil {
		return Manuscript{}, manuscriptQueryFailed()
	}
	return Manuscript{ProjectID: projectID, Blocks: blocks}, nil
}

func (r *SQLManuscriptReader) GetManuscriptExport(ctx context.Context, input GetManuscriptExportInput) (ManuscriptExportManifest, error) {
	tenantID, projectID := strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return ManuscriptExportManifest{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return ManuscriptExportManifest{}, &AppError{Code: "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", Message: "manuscript export backend is not configured"}
	}
	blocks, err := r.queryBlocks(ctx, tenantID, projectID)
	if err != nil {
		return ManuscriptExportManifest{}, manuscriptExportQueryFailed()
	}
	return manuscriptExportManifest(projectID, input.Format, blocks), nil
}

func (r *SQLManuscriptReader) queryBlocks(ctx context.Context, tenantID string, projectID string) ([]ManuscriptBlock, error) {
	rows, err := queryWorkflowEventRows(ctx, r.queryer, tenantID, manuscriptBlocksMetadataQuery(), tenantID, projectID)
	if err != nil {
		return nil, err
	}
	closed := false
	defer func() {
		if !closed {
			_ = rows.Close()
		}
	}()

	blocks := []ManuscriptBlock{}
	for rows.Next() {
		block, err := scanManuscriptBlock(rows)
		if err != nil {
			return nil, err
		}
		blocks = append(blocks, block)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if err := rows.Close(); err != nil {
		return nil, err
	}
	closed = true
	return blocks, nil
}

func scanManuscriptBlock(rows WriterEventSQLRows) (ManuscriptBlock, error) {
	var block ManuscriptBlock
	var chapterID sql.NullString
	var sourceDraftID sql.NullString
	var status sql.NullString
	var createdAt sql.NullString
	var updatedAt sql.NullString
	if err := rows.Scan(
		&block.BlockID,
		&block.ProjectID,
		&chapterID,
		&sourceDraftID,
		&block.BlockOrder,
		&status,
		&block.WordCount,
		&createdAt,
		&updatedAt,
	); err != nil {
		return ManuscriptBlock{}, err
	}
	block.ChapterID = optionalSQLString(chapterID)
	block.SourceDraftID = optionalSQLString(sourceDraftID)
	block.Status = optionalSQLString(status)
	block.CreatedAt = optionalSQLString(createdAt)
	block.UpdatedAt = optionalSQLString(updatedAt)
	return block, nil
}

func optionalSQLString(value sql.NullString) string {
	if !value.Valid {
		return ""
	}
	return value.String
}

func manuscriptExportManifest(projectID string, format string, blocks []ManuscriptBlock) ManuscriptExportManifest {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	manifest := ManuscriptExportManifest{
		ProjectID:   projectID,
		Format:      safeManuscriptExportFormat(format),
		Status:      "ready",
		BlockCount:  len(blocks),
		GeneratedAt: now,
		Blocks:      make([]ManuscriptExportBlock, 0, len(blocks)),
	}
	for _, block := range blocks {
		manifest.TotalWordCount += block.WordCount
		manifest.Blocks = append(manifest.Blocks, ManuscriptExportBlock{
			BlockID:    block.BlockID,
			BlockOrder: block.BlockOrder,
			WordCount:  block.WordCount,
		})
	}
	return manifest
}

func safeManuscriptExportFormat(format string) string {
	format = strings.ToLower(strings.TrimSpace(format))
	if format == "metadata_manifest" {
		return format
	}
	return "metadata_manifest"
}

func manuscriptBlocksMetadataQuery() string {
	return `SELECT
  block_id::text,
  project_id::text,
  chapter_id::text,
  source_draft_id::text,
  block_order,
  'available' AS status,
  word_count,
  created_at::text,
  updated_at::text
FROM manuscript_blocks
WHERE tenant_id::text = $1
  AND project_id::text = $2
ORDER BY block_order ASC, created_at ASC`
}

func manuscriptQueryFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_QUERY_FAILED", Message: "manuscript query failed"}
}

func manuscriptExportQueryFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_EXPORT_QUERY_FAILED", Message: "manuscript export query failed"}
}
