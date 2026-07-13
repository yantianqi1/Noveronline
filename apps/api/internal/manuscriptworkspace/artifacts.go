package manuscriptworkspace

import (
	"context"
	"database/sql"
	"errors"
	"regexp"
	"strings"
)

type ExportRecord struct {
	ExportID          string `json:"export_id"`
	ProjectID         string `json:"project_id"`
	Format            string `json:"format"`
	Status            string `json:"status"`
	ArtifactSHA256    string `json:"artifact_sha256,omitempty"`
	ArtifactSizeBytes int64  `json:"artifact_size_bytes,omitempty"`
	BlockCount        int    `json:"block_count"`
	ErrorCode         string `json:"error_code,omitempty"`
	CreatedAt         string `json:"created_at"`
	CompletedAt       string `json:"completed_at,omitempty"`
	UpdatedAt         string `json:"updated_at"`
}

type PrivateExportRecord struct {
	ExportRecord
	ArtifactObjectRef string `json:"artifact_object_ref,omitempty"`
}

type CreateExportInput struct {
	Scope
	Format string
}

type CompleteExportInput struct {
	Scope
	ExportID          string
	ArtifactSHA256    string
	ArtifactSizeBytes int64
	ArtifactObjectRef string
	BlockCount        int
}

type ExportStateStore interface {
	CreateExport(context.Context, CreateExportInput) (ExportRecord, bool, error)
	MarkExportGenerating(context.Context, Scope, string) (ExportRecord, error)
	CompleteExport(context.Context, CompleteExportInput) (PrivateExportRecord, error)
	FailExport(context.Context, Scope, string, string) (ExportRecord, error)
	ListExports(context.Context, Scope) ([]ExportRecord, error)
	GetPrivateExport(context.Context, Scope, string) (PrivateExportRecord, error)
}

type ExportArtifactGenerator interface {
	GenerateExport(context.Context, CreateExportInput) (ExportRecord, bool, error)
}

var sha256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

func (s *SQLStore) CreateExport(ctx context.Context, input CreateExportInput) (ExportRecord, bool, error) {
	input.Scope = normalizeScope(input.Scope)
	input.Format = strings.ToLower(strings.TrimSpace(input.Format))
	if err := validateScope(input.Scope, true); err != nil || !validExportFormat(input.Format) {
		return ExportRecord{}, false, validation("scope, request_id, and supported export format are required")
	}
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return ExportRecord{}, false, exportWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	result, err := tx.ExecContext(ctx, `INSERT INTO manuscript_exports (
  tenant_id, project_id, format, status, request_id, created_by
) VALUES ($1::uuid, $2::uuid, $3, 'queued', $4, $5::uuid)
ON CONFLICT (tenant_id, project_id, request_id) DO NOTHING`,
		input.TenantID, input.ProjectID, input.Format, input.RequestID, input.ActorUserID)
	if err != nil {
		return ExportRecord{}, false, exportWriteFailed()
	}
	count, _ := result.RowsAffected()
	record, err := getExportByRequest(ctx, tx, input.Scope, input.RequestID)
	if err != nil {
		return ExportRecord{}, false, err
	}
	if record.Format != input.Format {
		return ExportRecord{}, false, &AppError{Code: "IDEMPOTENCY_CONFLICT", Message: "request_id was already used for a different manuscript export"}
	}
	if err := tx.Commit(); err != nil {
		return ExportRecord{}, false, exportWriteFailed()
	}
	return record.ExportRecord, count == 0, nil
}

func (s *SQLStore) MarkExportGenerating(ctx context.Context, scope Scope, exportID string) (ExportRecord, error) {
	record, err := s.changeExportStatus(ctx, scope, exportID, "generating", "")
	return record.ExportRecord, err
}

func (s *SQLStore) FailExport(ctx context.Context, scope Scope, exportID, errorCode string) (ExportRecord, error) {
	record, err := s.changeExportStatus(ctx, scope, exportID, "failed", strings.TrimSpace(errorCode))
	return record.ExportRecord, err
}

func (s *SQLStore) changeExportStatus(ctx context.Context, scope Scope, exportID, status, errorCode string) (PrivateExportRecord, error) {
	scope = normalizeScope(scope)
	exportID = strings.TrimSpace(exportID)
	if err := validateScope(scope, true); err != nil || exportID == "" {
		return PrivateExportRecord{}, validation("export_id is required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return PrivateExportRecord{}, exportWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	result, err := tx.ExecContext(ctx, `UPDATE manuscript_exports SET status = $4, error_code = NULLIF($5, ''), updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND export_id::text = $3
  AND (($4 = 'generating' AND status = 'queued') OR ($4 = 'failed' AND status IN ('queued', 'generating')))`,
		scope.TenantID, scope.ProjectID, exportID, status, errorCode)
	if err != nil {
		return PrivateExportRecord{}, exportWriteFailed()
	}
	count, _ := result.RowsAffected()
	if count != 1 {
		return PrivateExportRecord{}, &AppError{Code: "EXPORT_STATE_CONFLICT", Message: "manuscript export state changed"}
	}
	record, err := getExportTx(ctx, tx, scope, exportID)
	if err != nil {
		return PrivateExportRecord{}, err
	}
	if err := tx.Commit(); err != nil {
		return PrivateExportRecord{}, exportWriteFailed()
	}
	return record, nil
}

func (s *SQLStore) CompleteExport(ctx context.Context, input CompleteExportInput) (PrivateExportRecord, error) {
	input.Scope = normalizeScope(input.Scope)
	input.ExportID = strings.TrimSpace(input.ExportID)
	input.ArtifactSHA256 = strings.ToLower(strings.TrimSpace(input.ArtifactSHA256))
	input.ArtifactObjectRef = strings.TrimSpace(input.ArtifactObjectRef)
	if err := validateScope(input.Scope, true); err != nil || input.ExportID == "" ||
		!sha256Pattern.MatchString(input.ArtifactSHA256) || input.ArtifactSizeBytes <= 0 ||
		input.ArtifactObjectRef == "" || input.BlockCount <= 0 {
		return PrivateExportRecord{}, validation("completed export requires real artifact hash, size, object reference, and block count")
	}
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return PrivateExportRecord{}, exportWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	result, err := tx.ExecContext(ctx, `UPDATE manuscript_exports SET
  status = 'completed', artifact_sha256 = $4, artifact_size_bytes = $5,
  artifact_object_ref = $6, block_count = $7, error_code = NULL,
  completed_at = now(), updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND export_id::text = $3
  AND status IN ('queued', 'generating')`, input.TenantID, input.ProjectID, input.ExportID,
		input.ArtifactSHA256, input.ArtifactSizeBytes, input.ArtifactObjectRef, input.BlockCount)
	if err != nil {
		return PrivateExportRecord{}, exportWriteFailed()
	}
	count, _ := result.RowsAffected()
	if count != 1 {
		return PrivateExportRecord{}, &AppError{Code: "EXPORT_STATE_CONFLICT", Message: "manuscript export state changed"}
	}
	record, err := getExportTx(ctx, tx, input.Scope, input.ExportID)
	if err != nil {
		return PrivateExportRecord{}, err
	}
	if err := tx.Commit(); err != nil {
		return PrivateExportRecord{}, exportWriteFailed()
	}
	return record, nil
}

func (s *SQLStore) ListExports(ctx context.Context, scope Scope) ([]ExportRecord, error) {
	scope = normalizeScope(scope)
	if err := validateScope(scope, false); err != nil {
		return nil, err
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return nil, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	rows, err := tx.QueryContext(ctx, exportSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 ORDER BY created_at DESC, export_id`, scope.TenantID, scope.ProjectID)
	if err != nil {
		return nil, queryFailed()
	}
	defer rows.Close()
	records := []ExportRecord{}
	for rows.Next() {
		record, err := scanExport(rows)
		if err != nil {
			return nil, queryFailed()
		}
		records = append(records, record.ExportRecord)
	}
	if err := rows.Err(); err != nil {
		return nil, queryFailed()
	}
	if err := rows.Close(); err != nil {
		return nil, queryFailed()
	}
	if err := tx.Commit(); err != nil {
		return nil, queryFailed()
	}
	return records, nil
}

func (s *SQLStore) GetPrivateExport(ctx context.Context, scope Scope, exportID string) (PrivateExportRecord, error) {
	scope = normalizeScope(scope)
	if err := validateScope(scope, false); err != nil || strings.TrimSpace(exportID) == "" {
		return PrivateExportRecord{}, validation("export_id is required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return PrivateExportRecord{}, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	record, err := getExportTx(ctx, tx, scope, exportID)
	if err != nil {
		return PrivateExportRecord{}, err
	}
	if err := tx.Commit(); err != nil {
		return PrivateExportRecord{}, queryFailed()
	}
	return record, nil
}

const exportSelect = `SELECT export_id::text, project_id::text, format, status,
  COALESCE(artifact_sha256, ''), COALESCE(artifact_size_bytes, 0), COALESCE(artifact_object_ref, ''),
  block_count, COALESCE(error_code, ''), created_at::text, COALESCE(completed_at::text, ''), updated_at::text
FROM manuscript_exports`

func scanExport(row scanner) (PrivateExportRecord, error) {
	var record PrivateExportRecord
	err := row.Scan(&record.ExportID, &record.ProjectID, &record.Format, &record.Status,
		&record.ArtifactSHA256, &record.ArtifactSizeBytes, &record.ArtifactObjectRef,
		&record.BlockCount, &record.ErrorCode, &record.CreatedAt, &record.CompletedAt, &record.UpdatedAt)
	return record, err
}

func getExportTx(ctx context.Context, tx *sql.Tx, scope Scope, exportID string) (PrivateExportRecord, error) {
	record, err := scanExport(tx.QueryRowContext(ctx, exportSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND export_id::text = $3`, scope.TenantID, scope.ProjectID, exportID))
	if errors.Is(err, sql.ErrNoRows) {
		return PrivateExportRecord{}, notFound("manuscript export not found")
	}
	if err != nil {
		return PrivateExportRecord{}, queryFailed()
	}
	return record, nil
}

func getExportByRequest(ctx context.Context, tx *sql.Tx, scope Scope, requestID string) (PrivateExportRecord, error) {
	record, err := scanExport(tx.QueryRowContext(ctx, exportSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND request_id = $3 FOR UPDATE`, scope.TenantID, scope.ProjectID, requestID))
	if err != nil {
		return PrivateExportRecord{}, exportWriteFailed()
	}
	return record, nil
}

func validExportFormat(format string) bool {
	switch format {
	case "txt", "docx", "pdf", "epub":
		return true
	default:
		return false
	}
}

func exportWriteFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_EXPORT_STATE_FAILED", Message: "manuscript export state update failed"}
}
