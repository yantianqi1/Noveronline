package workflows

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"strings"
	"time"
)

const ManuscriptArtifactFormatTXT = "txt"

type ExportManuscriptArtifactInput struct {
	TenantID  string
	ProjectID string
	Format    string
}

type ManuscriptArtifact struct {
	ProjectID   string
	Format      string
	FileName    string
	ContentType string
	Content     []byte
	SizeBytes   int64
	SHA256      string
	BlockCount  int
	GeneratedAt string
}

type ManuscriptArtifactExporter interface {
	ExportManuscriptArtifact(context.Context, ExportManuscriptArtifactInput) (ManuscriptArtifact, error)
}

type SQLManuscriptArtifactExporterConfig struct {
	Queryer WriterEventSQLQueryer
	Now     func() time.Time
}

type SQLManuscriptArtifactExporter struct {
	queryer WriterEventSQLQueryer
	now     func() time.Time
}

func NewSQLManuscriptArtifactExporter(config SQLManuscriptArtifactExporterConfig) *SQLManuscriptArtifactExporter {
	now := config.Now
	if now == nil {
		now = time.Now
	}
	return &SQLManuscriptArtifactExporter{queryer: config.Queryer, now: now}
}

func (e *SQLManuscriptArtifactExporter) ExportManuscriptArtifact(ctx context.Context, input ExportManuscriptArtifactInput) (ManuscriptArtifact, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	format := normalizedArtifactFormat(input.Format)
	if tenantID == "" || projectID == "" {
		return ManuscriptArtifact{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if format == "" {
		return ManuscriptArtifact{}, &AppError{Code: "MANUSCRIPT_EXPORT_FORMAT_UNSUPPORTED", Message: "manuscript export format is not supported"}
	}
	if e.queryer == nil {
		return ManuscriptArtifact{}, &AppError{Code: "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", Message: "manuscript export backend is not configured"}
	}

	blocks, err := e.queryContentBlocks(ctx, tenantID, projectID)
	if err != nil {
		return ManuscriptArtifact{}, manuscriptArtifactQueryFailed()
	}
	if len(blocks) == 0 {
		return ManuscriptArtifact{}, &AppError{Code: "MANUSCRIPT_EMPTY", Message: "manuscript has no adopted content to export"}
	}

	content := renderTXTManuscript(blocks)
	digest := sha256.Sum256(content)
	return ManuscriptArtifact{
		ProjectID:   projectID,
		Format:      format,
		FileName:    safeArtifactFileName(projectID),
		ContentType: "text/plain; charset=utf-8",
		Content:     content,
		SizeBytes:   int64(len(content)),
		SHA256:      hex.EncodeToString(digest[:]),
		BlockCount:  len(blocks),
		GeneratedAt: e.now().UTC().Format(time.RFC3339Nano),
	}, nil
}

type manuscriptContentBlock struct {
	blockID string
	order   int
	content string
}

func (e *SQLManuscriptArtifactExporter) queryContentBlocks(ctx context.Context, tenantID string, projectID string) ([]manuscriptContentBlock, error) {
	rows, err := queryWorkflowEventRows(ctx, e.queryer, tenantID, manuscriptArtifactContentQuery(), tenantID, projectID)
	if err != nil {
		return nil, err
	}
	closed := false
	defer func() {
		if !closed {
			_ = rows.Close()
		}
	}()

	blocks := []manuscriptContentBlock{}
	for rows.Next() {
		var block manuscriptContentBlock
		var content sql.NullString
		if err := rows.Scan(&block.blockID, &block.order, &content); err != nil {
			return nil, err
		}
		if content.Valid && strings.TrimSpace(content.String) != "" {
			block.content = normalizeTXTContent(content.String)
			blocks = append(blocks, block)
		}
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

func renderTXTManuscript(blocks []manuscriptContentBlock) []byte {
	parts := make([]string, 0, len(blocks))
	for _, block := range blocks {
		parts = append(parts, block.content)
	}
	return []byte(strings.Join(parts, "\n\n") + "\n")
}

func normalizeTXTContent(content string) string {
	content = strings.ReplaceAll(content, "\r\n", "\n")
	content = strings.ReplaceAll(content, "\r", "\n")
	return strings.TrimSpace(content)
}

func normalizedArtifactFormat(format string) string {
	format = strings.ToLower(strings.TrimSpace(format))
	if format == "" || format == ManuscriptArtifactFormatTXT {
		return ManuscriptArtifactFormatTXT
	}
	return ""
}

func safeArtifactFileName(projectID string) string {
	var builder strings.Builder
	for _, character := range strings.TrimSpace(projectID) {
		switch {
		case character >= 'a' && character <= 'z':
			builder.WriteRune(character)
		case character >= 'A' && character <= 'Z':
			builder.WriteRune(character)
		case character >= '0' && character <= '9':
			builder.WriteRune(character)
		case character == '-', character == '_':
			builder.WriteRune(character)
		default:
			builder.WriteRune('-')
		}
	}
	base := strings.Trim(builder.String(), "-")
	if base == "" {
		base = "project"
	}
	return base + "-manuscript.txt"
}

func manuscriptArtifactContentQuery() string {
	return `SELECT
  block_id::text,
  block_order,
  content_text
FROM manuscript_blocks
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND status = 'active'
ORDER BY block_order ASC, created_at ASC`
}

func manuscriptArtifactQueryFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_EXPORT_QUERY_FAILED", Message: "manuscript export query failed"}
}
