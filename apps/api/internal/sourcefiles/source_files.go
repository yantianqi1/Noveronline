package sourcefiles

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"strings"
)

type CreateInput struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	Filename    string
	MimeType    string
	SizeBytes   int64
	SHA256      string
	Purpose     string
}

type ListInput struct {
	TenantID  string
	ProjectID string
}

type CompleteInput struct {
	TenantID string
	UploadID string
}

type GetUploadObjectInput struct {
	TenantID string
	UploadID string
}

type ValidateInput struct {
	TenantID  string
	ProjectID string
	UploadID  string
}

type Record struct {
	FileID      string `json:"file_id"`
	UploadID    string `json:"upload_id"`
	ProjectID   string `json:"project_id"`
	Filename    string `json:"filename"`
	MimeType    string `json:"mime_type"`
	SizeBytes   int64  `json:"size_bytes"`
	SHA256      string `json:"sha256"`
	Purpose     string `json:"purpose"`
	ParseStatus string `json:"parse_status"`
	CreatedAt   string `json:"created_at"`
}

type ValidatedSourceFile struct {
	FileID      string
	UploadID    string
	ProjectID   string
	ObjectKey   string
	Filename    string
	MimeType    string
	SizeBytes   int64
	SHA256      string
	ParseStatus string
}

type ObjectVerificationInput struct {
	TenantID    string
	ProjectID   string
	UploadID    string
	FileID      string
	ObjectKey   string
	SizeBytes   int64
	SHA256      string
	ParseStatus string
}

type ObjectWriteInput struct {
	TenantID    string
	ProjectID   string
	UploadID    string
	FileID      string
	ObjectKey   string
	Filename    string
	MimeType    string
	SizeBytes   int64
	SHA256      string
	ParseStatus string
}

type ObjectVerifier interface {
	VerifyObject(context.Context, ObjectVerificationInput) error
}

type ObjectWriter interface {
	WriteObject(context.Context, ObjectWriteInput, io.Reader) error
}

type Store interface {
	CreateSourceFile(context.Context, CreateInput) (Record, error)
	GetUploadObject(context.Context, GetUploadObjectInput) (ObjectWriteInput, error)
	CompleteUpload(context.Context, CompleteInput) (Record, error)
	ListSourceFiles(context.Context, ListInput) ([]Record, error)
	ValidateSourceFile(context.Context, ValidateInput) (ValidatedSourceFile, error)
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func NewAppError(code string, message string) *AppError {
	return &AppError{Code: code, Message: message}
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "SOURCE_FILE_ERROR"
}

type DisabledStore struct{}

func NewDisabledStore() DisabledStore {
	return DisabledStore{}
}

func IsConfigured(store Store) bool {
	if store == nil {
		return false
	}
	switch store.(type) {
	case DisabledStore, *DisabledStore:
		return false
	default:
		return true
	}
}

func (DisabledStore) CreateSourceFile(context.Context, CreateInput) (Record, error) {
	return Record{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
}

func (DisabledStore) GetUploadObject(context.Context, GetUploadObjectInput) (ObjectWriteInput, error) {
	return ObjectWriteInput{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
}

func (DisabledStore) CompleteUpload(context.Context, CompleteInput) (Record, error) {
	return Record{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
}

func (DisabledStore) ListSourceFiles(context.Context, ListInput) ([]Record, error) {
	return nil, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
}

func (DisabledStore) ValidateSourceFile(context.Context, ValidateInput) (ValidatedSourceFile, error) {
	return ValidatedSourceFile{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
}

type SQLRow interface {
	Scan(...any) error
}

type SQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type SQLRowsAborter interface {
	Abort() error
}

type SQLQueryer interface {
	QueryRowContext(context.Context, string, ...any) SQLRow
	QueryContext(context.Context, string, ...any) (SQLRows, error)
}

type SQLTenantQueryer interface {
	QueryTenantContext(context.Context, string, string, ...any) (SQLRows, error)
}

type SQLStoreConfig struct {
	Queryer        SQLQueryer
	ObjectVerifier ObjectVerifier
	Limit          int
}

type SQLStore struct {
	queryer        SQLQueryer
	objectVerifier ObjectVerifier
	limit          int
}

func NewSQLStore(config SQLStoreConfig) *SQLStore {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLStore{queryer: config.Queryer, objectVerifier: config.ObjectVerifier, limit: limit}
}

type sqlDBQueryer struct {
	db *sql.DB
}

func NewSQLDBQueryer(db *sql.DB) SQLQueryer {
	return sqlDBQueryer{db: db}
}

func (q sqlDBQueryer) QueryRowContext(ctx context.Context, query string, args ...any) SQLRow {
	return q.db.QueryRowContext(ctx, query, args...)
}

func (q sqlDBQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (q sqlDBQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
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
	return &tenantScopedRows{rows: rows, tx: tx}, nil
}

type tenantScopedRows struct {
	rows SQLRows
	tx   *sql.Tx
}

func (r *tenantScopedRows) Next() bool {
	return r.rows.Next()
}

func (r *tenantScopedRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *tenantScopedRows) Close() error {
	closeErr := r.rows.Close()
	rowsErr := r.rows.Err()
	if closeErr != nil || rowsErr != nil {
		_ = r.tx.Rollback()
		if closeErr != nil {
			return closeErr
		}
		return rowsErr
	}
	return r.tx.Commit()
}

func (r *tenantScopedRows) Abort() error {
	closeErr := r.rows.Close()
	rollbackErr := r.tx.Rollback()
	if closeErr != nil {
		return closeErr
	}
	return rollbackErr
}

func (r *tenantScopedRows) Err() error {
	return r.rows.Err()
}

func (s *SQLStore) CreateSourceFile(ctx context.Context, input CreateInput) (Record, error) {
	if err := validateCreateInput(input); err != nil {
		return Record{}, err
	}
	if s.queryer == nil {
		return Record{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
	}
	fileID, err := newUUID()
	if err != nil {
		return Record{}, &AppError{Code: "SOURCE_FILE_CREATE_FAILED", Message: "failed to allocate source file id"}
	}
	uploadID, err := newUUID()
	if err != nil {
		return Record{}, &AppError{Code: "SOURCE_FILE_CREATE_FAILED", Message: "failed to allocate upload id"}
	}
	objectKey := sourceObjectKey(input.ProjectID, uploadID, input.Filename)
	query := `INSERT INTO source_files (
  tenant_id,
  file_id,
  project_id,
  upload_id,
  object_key,
  filename,
  mime_type,
  size_bytes,
  sha256,
  purpose,
  parse_status,
  created_by
)
VALUES (
  $1::uuid,
  $2::uuid,
  $3::uuid,
  $4::uuid,
  $5,
  $6,
  $7,
  $8,
  $9,
  $10,
  'pending',
  NULLIF($11, '')::uuid
)
RETURNING
  file_id::text,
  upload_id::text,
  project_id::text,
  filename,
  mime_type,
  size_bytes,
  sha256,
  purpose,
  parse_status,
  created_at::text`
	var record Record
	err = s.scanRow(
		ctx,
		strings.TrimSpace(input.TenantID),
		query,
		[]any{
			strings.TrimSpace(input.TenantID),
			fileID,
			strings.TrimSpace(input.ProjectID),
			uploadID,
			objectKey,
			strings.TrimSpace(input.Filename),
			strings.TrimSpace(input.MimeType),
			input.SizeBytes,
			strings.TrimSpace(input.SHA256),
			strings.TrimSpace(input.Purpose),
			strings.TrimSpace(input.ActorUserID),
		},
		&record.FileID,
		&record.UploadID,
		&record.ProjectID,
		&record.Filename,
		&record.MimeType,
		&record.SizeBytes,
		&record.SHA256,
		&record.Purpose,
		&record.ParseStatus,
		&record.CreatedAt,
	)
	if err != nil {
		return Record{}, sourceFileCreateFailed()
	}
	return record, nil
}

func (s *SQLStore) CompleteUpload(ctx context.Context, input CompleteInput) (Record, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.UploadID) == "" {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and upload_id are required"}
	}
	if s.queryer == nil {
		return Record{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
	}
	if s.objectVerifier == nil {
		return Record{}, &AppError{Code: "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED", Message: "object storage backend is not configured"}
	}
	metadata, err := s.lookupObjectForUpload(ctx, input)
	if err != nil {
		return Record{}, err
	}
	if !isCompletableUploadStatus(metadata.ParseStatus) {
		return Record{}, sourceFileUploadNotCompletable()
	}
	if err := s.objectVerifier.VerifyObject(ctx, metadata); err != nil {
		return Record{}, normalizeObjectVerificationError(err)
	}
	query := `UPDATE source_files
	SET parse_status = 'uploaded'
	WHERE tenant_id::text = $1
	  AND upload_id::text = $2
	  AND parse_status IN ('pending', 'uploaded')
	RETURNING
	  file_id::text,
	  upload_id::text,
	  project_id::text,
	  filename,
	  mime_type,
	  size_bytes,
	  sha256,
	  purpose,
	  parse_status,
	  created_at::text`
	var record Record
	err = s.scanRow(
		ctx,
		strings.TrimSpace(input.TenantID),
		query,
		[]any{
			strings.TrimSpace(input.TenantID),
			strings.TrimSpace(input.UploadID),
		},
		&record.FileID,
		&record.UploadID,
		&record.ProjectID,
		&record.Filename,
		&record.MimeType,
		&record.SizeBytes,
		&record.SHA256,
		&record.Purpose,
		&record.ParseStatus,
		&record.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Record{}, sourceFileUploadNotCompletable()
		}
		return Record{}, sourceFileCompleteFailed()
	}
	return record, nil
}

func (s *SQLStore) GetUploadObject(ctx context.Context, input GetUploadObjectInput) (ObjectWriteInput, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.UploadID) == "" {
		return ObjectWriteInput{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and upload_id are required"}
	}
	if s.queryer == nil {
		return ObjectWriteInput{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
	}
	query := `SELECT
  file_id::text,
  project_id::text,
  object_key,
	filename,
	mime_type,
	size_bytes,
	sha256,
	parse_status
FROM source_files
WHERE tenant_id::text = $1
  AND upload_id::text = $2
LIMIT 1`
	metadata := ObjectWriteInput{
		TenantID: strings.TrimSpace(input.TenantID),
		UploadID: strings.TrimSpace(input.UploadID),
	}
	err := s.scanRow(
		ctx,
		strings.TrimSpace(input.TenantID),
		query,
		[]any{
			strings.TrimSpace(input.TenantID),
			strings.TrimSpace(input.UploadID),
		},
		&metadata.FileID,
		&metadata.ProjectID,
		&metadata.ObjectKey,
		&metadata.Filename,
		&metadata.MimeType,
		&metadata.SizeBytes,
		&metadata.SHA256,
		&metadata.ParseStatus,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return ObjectWriteInput{}, &AppError{Code: "NOT_FOUND", Message: "source file upload not found"}
		}
		return ObjectWriteInput{}, sourceFileQueryFailed()
	}
	if !isWritableUploadStatus(metadata.ParseStatus) {
		return ObjectWriteInput{}, sourceFileUploadNotWritable()
	}
	return metadata, nil
}

func (s *SQLStore) lookupObjectForUpload(ctx context.Context, input CompleteInput) (ObjectVerificationInput, error) {
	query := `SELECT
	  file_id::text,
	  project_id::text,
	  object_key,
	  size_bytes,
	  sha256,
	  parse_status
	FROM source_files
	WHERE tenant_id::text = $1
	  AND upload_id::text = $2
	LIMIT 1`
	metadata := ObjectVerificationInput{
		TenantID: strings.TrimSpace(input.TenantID),
		UploadID: strings.TrimSpace(input.UploadID),
	}
	err := s.scanRow(
		ctx,
		strings.TrimSpace(input.TenantID),
		query,
		[]any{
			strings.TrimSpace(input.TenantID),
			strings.TrimSpace(input.UploadID),
		},
		&metadata.FileID,
		&metadata.ProjectID,
		&metadata.ObjectKey,
		&metadata.SizeBytes,
		&metadata.SHA256,
		&metadata.ParseStatus,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return ObjectVerificationInput{}, &AppError{Code: "NOT_FOUND", Message: "source file upload not found"}
		}
		return ObjectVerificationInput{}, sourceFileQueryFailed()
	}
	return metadata, nil
}

func normalizeObjectVerificationError(err error) error {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr
	}
	return &AppError{Code: "SOURCE_FILE_STORAGE_VERIFY_FAILED", Message: "source file storage verification failed"}
}

func (s *SQLStore) ListSourceFiles(ctx context.Context, input ListInput) ([]Record, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if s.queryer == nil {
		return nil, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
	}
	query := `SELECT
  file_id::text,
  upload_id::text,
  project_id::text,
  filename,
  mime_type,
  size_bytes,
  sha256,
  purpose,
  parse_status,
  created_at::text
FROM source_files
WHERE tenant_id::text = $1
  AND project_id::text = $2
ORDER BY created_at DESC, file_id::text DESC
LIMIT $3`
	rows, err := s.queryRows(ctx, strings.TrimSpace(input.TenantID), query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), s.limit)
	if err != nil {
		return nil, sourceFileQueryFailed()
	}

	items := []Record{}
	for rows.Next() {
		var record Record
		if err := rows.Scan(
			&record.FileID,
			&record.UploadID,
			&record.ProjectID,
			&record.Filename,
			&record.MimeType,
			&record.SizeBytes,
			&record.SHA256,
			&record.Purpose,
			&record.ParseStatus,
			&record.CreatedAt,
		); err != nil {
			abortRows(rows)
			return nil, sourceFileQueryFailed()
		}
		items = append(items, record)
	}
	if err := rows.Err(); err != nil {
		abortRows(rows)
		return nil, sourceFileQueryFailed()
	}
	if err := rows.Close(); err != nil {
		return nil, sourceFileQueryFailed()
	}
	return items, nil
}

func (s *SQLStore) ValidateSourceFile(ctx context.Context, input ValidateInput) (ValidatedSourceFile, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.UploadID) == "" {
		return ValidatedSourceFile{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and upload_id are required"}
	}
	if s.queryer == nil {
		return ValidatedSourceFile{}, &AppError{Code: "SOURCE_FILE_BACKEND_UNCONFIGURED", Message: "source file backend is not configured"}
	}
	query := `SELECT
  file_id::text,
  upload_id::text,
  project_id::text,
  object_key,
  filename,
  mime_type,
  size_bytes,
  sha256,
  parse_status
FROM source_files
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND upload_id::text = $3
LIMIT 1`
	var metadata ValidatedSourceFile
	err := s.scanRow(
		ctx,
		strings.TrimSpace(input.TenantID),
		query,
		[]any{
			strings.TrimSpace(input.TenantID),
			strings.TrimSpace(input.ProjectID),
			strings.TrimSpace(input.UploadID),
		},
		&metadata.FileID,
		&metadata.UploadID,
		&metadata.ProjectID,
		&metadata.ObjectKey,
		&metadata.Filename,
		&metadata.MimeType,
		&metadata.SizeBytes,
		&metadata.SHA256,
		&metadata.ParseStatus,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return ValidatedSourceFile{}, &AppError{Code: "NOT_FOUND", Message: "source file upload not found"}
		}
		return ValidatedSourceFile{}, sourceFileQueryFailed()
	}
	if strings.TrimSpace(metadata.ParseStatus) != "uploaded" {
		return ValidatedSourceFile{}, &AppError{Code: "SOURCE_FILE_NOT_UPLOADED", Message: "source file upload must be completed before seed run"}
	}
	return metadata, nil
}

func (s *SQLStore) queryRows(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := s.queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return s.queryer.QueryContext(ctx, query, args...)
}

func (s *SQLStore) scanRow(ctx context.Context, tenantID string, query string, args []any, dest ...any) error {
	if tenantQueryer, ok := s.queryer.(SQLTenantQueryer); ok {
		rows, err := tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
		if err != nil {
			return err
		}
		if !rows.Next() {
			if err := rows.Err(); err != nil {
				return err
			}
			if err := rows.Close(); err != nil {
				return err
			}
			return sql.ErrNoRows
		}
		if err := rows.Scan(dest...); err != nil {
			abortRows(rows)
			return err
		}
		if err := rows.Err(); err != nil {
			return err
		}
		if err := rows.Close(); err != nil {
			return err
		}
		return nil
	}
	return s.queryer.QueryRowContext(ctx, query, args...).Scan(dest...)
}

func abortRows(rows SQLRows) {
	if aborter, ok := rows.(SQLRowsAborter); ok {
		_ = aborter.Abort()
		return
	}
	_ = rows.Close()
}

func sourceFileCreateFailed() error {
	return &AppError{Code: "SOURCE_FILE_CREATE_FAILED", Message: "source file create failed"}
}

func sourceFileCompleteFailed() error {
	return &AppError{Code: "SOURCE_FILE_COMPLETE_FAILED", Message: "source file complete failed"}
}

func sourceFileUploadNotCompletable() error {
	return &AppError{Code: "SOURCE_FILE_UPLOAD_NOT_COMPLETABLE", Message: "source file upload cannot be completed from its current parse status"}
}

func sourceFileUploadNotWritable() error {
	return &AppError{Code: "SOURCE_FILE_UPLOAD_NOT_WRITABLE", Message: "source file object upload cannot be written from its current parse status"}
}

func sourceFileQueryFailed() error {
	return &AppError{Code: "SOURCE_FILE_QUERY_FAILED", Message: "source file query failed"}
}

func isCompletableUploadStatus(status string) bool {
	switch strings.TrimSpace(status) {
	case "pending", "uploaded":
		return true
	default:
		return false
	}
}

func isWritableUploadStatus(status string) bool {
	return strings.TrimSpace(status) == "pending"
}

func validateCreateInput(input CreateInput) error {
	if strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.Filename) == "" ||
		strings.TrimSpace(input.MimeType) == "" ||
		strings.TrimSpace(input.SHA256) == "" ||
		strings.TrimSpace(input.Purpose) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, filename, mime_type, sha256, and purpose are required"}
	}
	if input.SizeBytes < 0 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "size_bytes must be non-negative"}
	}
	if !IsSupportedSourceMime(input.MimeType) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "unsupported source MIME type"}
	}
	return nil
}

func IsSupportedSourceMime(mimeType string) bool {
	normalized := normalizeSourceMime(mimeType)
	switch normalized {
	case "text/plain", "text/markdown", "text/x-markdown", "application/x-markdown", "application/pdf":
		return true
	default:
		return false
	}
}

func normalizeSourceMime(mimeType string) string {
	normalized := strings.ToLower(strings.TrimSpace(mimeType))
	if index := strings.Index(normalized, ";"); index >= 0 {
		normalized = strings.TrimSpace(normalized[:index])
	}
	return normalized
}

func sourceObjectKey(projectID string, uploadID string, filename string) string {
	return fmt.Sprintf("projects/%s/source-files/%s/%s", strings.TrimSpace(projectID), uploadID, sanitizeObjectKeyPart(filename))
}

func sanitizeObjectKeyPart(value string) string {
	replacer := strings.NewReplacer("/", "_", "\\", "_", "\x00", "")
	cleaned := strings.TrimSpace(replacer.Replace(value))
	if cleaned == "" {
		return "source"
	}
	return cleaned
}

func newUUID() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	encoded := hex.EncodeToString(b[:])
	return fmt.Sprintf("%s-%s-%s-%s-%s", encoded[0:8], encoded[8:12], encoded[12:16], encoded[16:20], encoded[20:32]), nil
}
