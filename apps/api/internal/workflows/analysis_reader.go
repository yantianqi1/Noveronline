package workflows

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

type SQLAnalysisRunReaderConfig struct {
	Queryer WriterEventSQLQueryer
	Limit   int
}

type SQLAnalysisRunReader struct {
	queryer WriterEventSQLQueryer
	limit   int
}

func NewSQLAnalysisRunReader(config SQLAnalysisRunReaderConfig) *SQLAnalysisRunReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLAnalysisRunReader{queryer: config.Queryer, limit: limit}
}

func (r *SQLAnalysisRunReader) ListAnalysisRuns(ctx context.Context, input ListAnalysisRunsInput) ([]AnalysisRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis run reader is not configured"}
	}
	query := `SELECT
  analysis.run_id::text,
  COALESCE(queued.payload_jsonb->>'trace_id', ''),
  analysis.project_id::text,
  analysis.mode,
  analysis.instruction,
  analysis.status,
  COALESCE(analysis.upload_id::text, ''),
  COALESCE(analysis.source_file_id::text, ''),
  COALESCE(workflow.progress, 0),
  COALESCE(workflow.message, ''),
  COALESCE(analysis.error_code, ''),
  COALESCE(analysis.error_message, ''),
  analysis.created_at::text,
  analysis.updated_at::text
FROM analysis_runs AS analysis
LEFT JOIN workflow_runs AS workflow
  ON workflow.tenant_id = analysis.tenant_id
 AND workflow.run_id = analysis.workflow_run_id
LEFT JOIN workflow_events AS queued
  ON queued.tenant_id = analysis.tenant_id
 AND queued.run_id = analysis.workflow_run_id
 AND queued.event_type = 'workflow.queued'
WHERE analysis.tenant_id::text = $1
  AND analysis.project_id::text = $2
ORDER BY analysis.created_at DESC
LIMIT $3`
	rows, err := querySeedRunRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		r.limit,
	)
	if err != nil {
		return nil, analysisRunQueryFailed()
	}
	defer rows.Close()
	items := make([]AnalysisRun, 0)
	for rows.Next() {
		var run AnalysisRun
		if err := rows.Scan(
			&run.RunID,
			&run.TraceID,
			&run.ProjectID,
			&run.Mode,
			&run.Instruction,
			&run.Status,
			&run.UploadID,
			&run.SourceFileID,
			&run.Progress,
			&run.Message,
			&run.ErrorCode,
			&run.ErrorMessage,
			&run.CreatedAt,
			&run.UpdatedAt,
		); err != nil {
			return nil, analysisRunQueryFailed()
		}
		run.TenantID = strings.TrimSpace(input.TenantID)
		run.WorkflowType = AnalysisWorkflowType
		items = append(items, run)
	}
	if err := rows.Err(); err != nil {
		return nil, analysisRunQueryFailed()
	}
	return items, nil
}

func (r *SQLAnalysisRunReader) GetAnalysisRun(ctx context.Context, input GetAnalysisRunInput) (AnalysisRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return AnalysisRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if r.queryer == nil {
		return AnalysisRun{}, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis run reader is not configured"}
	}
	query := `SELECT
  analysis.run_id::text,
  COALESCE(queued.payload_jsonb->>'trace_id', ''),
  analysis.project_id::text,
  analysis.mode,
  analysis.instruction,
  analysis.status,
  COALESCE(analysis.upload_id::text, ''),
  COALESCE(analysis.source_file_id::text, ''),
  COALESCE(workflow.progress, 0),
  COALESCE(workflow.message, ''),
  COALESCE(analysis.error_code, ''),
  COALESCE(analysis.error_message, ''),
  analysis.created_at::text,
  analysis.updated_at::text
FROM analysis_runs AS analysis
LEFT JOIN workflow_runs AS workflow
  ON workflow.tenant_id = analysis.tenant_id
 AND workflow.run_id = analysis.workflow_run_id
LEFT JOIN workflow_events AS queued
  ON queued.tenant_id = analysis.tenant_id
 AND queued.run_id = analysis.workflow_run_id
 AND queued.event_type = 'workflow.queued'
WHERE analysis.tenant_id::text = $1
  AND analysis.run_id::text = $2
LIMIT 1`
	rows, err := querySeedRunRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
	)
	if err != nil {
		return AnalysisRun{}, analysisRunQueryFailed()
	}
	defer rows.Close()
	if !rows.Next() {
		return AnalysisRun{}, &AppError{Code: "NOT_FOUND", Message: "analysis run not found"}
	}
	var run AnalysisRun
	if err := rows.Scan(
		&run.RunID,
		&run.TraceID,
		&run.ProjectID,
		&run.Mode,
		&run.Instruction,
		&run.Status,
		&run.UploadID,
		&run.SourceFileID,
		&run.Progress,
		&run.Message,
		&run.ErrorCode,
		&run.ErrorMessage,
		&run.CreatedAt,
		&run.UpdatedAt,
	); err != nil {
		return AnalysisRun{}, analysisRunQueryFailed()
	}
	run.TenantID = strings.TrimSpace(input.TenantID)
	run.WorkflowType = AnalysisWorkflowType
	return run, nil
}

type SQLAnalysisEventReaderConfig struct {
	Queryer WriterEventSQLQueryer
}

type SQLAnalysisEventReader struct {
	queryer WriterEventSQLQueryer
}

func NewSQLAnalysisEventReader(config SQLAnalysisEventReaderConfig) *SQLAnalysisEventReader {
	return &SQLAnalysisEventReader{queryer: config.Queryer}
}

func (r *SQLAnalysisEventReader) ListAnalysisEvents(ctx context.Context, input ListAnalysisEventsInput) ([]AnalysisEvent, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis event reader is not configured"}
	}
	// Ensure the run is an analysis run before replaying events.
	runReader := NewSQLAnalysisRunReader(SQLAnalysisRunReaderConfig{Queryer: r.queryer})
	if _, err := runReader.GetAnalysisRun(ctx, GetAnalysisRunInput{
		TenantID: input.TenantID,
		RunID:    input.RunID,
	}); err != nil {
		return nil, err
	}
	afterEventID := strings.TrimSpace(input.AfterEventID)
	query := `SELECT
  event_id::text,
  run_id::text,
  project_id::text,
  sequence,
  event_type,
  payload_jsonb,
  created_at::text
FROM workflow_events
WHERE tenant_id::text = $1
  AND run_id::text = $2`
	args := []any{strings.TrimSpace(input.TenantID), strings.TrimSpace(input.RunID)}
	if afterEventID != "" {
		query += `
  AND sequence > COALESCE((
    SELECT sequence FROM workflow_events
    WHERE tenant_id::text = $1 AND run_id::text = $2 AND event_id::text = $3
  ), -1)`
		args = append(args, afterEventID)
	}
	query += `
ORDER BY sequence ASC`
	rows, err := querySeedRunRows(ctx, r.queryer, strings.TrimSpace(input.TenantID), query, args...)
	if err != nil {
		return nil, analysisEventQueryFailed()
	}
	defer rows.Close()
	items := make([]AnalysisEvent, 0)
	for rows.Next() {
		var event AnalysisEvent
		var payload []byte
		if err := rows.Scan(
			&event.EventID,
			&event.RunID,
			&event.ProjectID,
			&event.Sequence,
			&event.EventType,
			&payload,
			&event.CreatedAt,
		); err != nil {
			return nil, analysisEventQueryFailed()
		}
		event.Payload = sanitizeAnalysisPublicPayload(payload)
		items = append(items, event)
	}
	if err := rows.Err(); err != nil {
		return nil, analysisEventQueryFailed()
	}
	if afterEventID != "" && len(items) == 0 {
		checkRows, err := querySeedRunRows(
			ctx,
			r.queryer,
			strings.TrimSpace(input.TenantID),
			`SELECT 1 FROM workflow_events
WHERE tenant_id::text = $1 AND run_id::text = $2 AND event_id::text = $3
LIMIT 1`,
			strings.TrimSpace(input.TenantID),
			strings.TrimSpace(input.RunID),
			afterEventID,
		)
		if err != nil {
			return nil, analysisEventQueryFailed()
		}
		exists := checkRows.Next()
		_ = checkRows.Close()
		if !exists {
			return nil, &AppError{Code: "EVENT_CURSOR_NOT_FOUND", Message: "analysis event cursor not found"}
		}
	}
	return items, nil
}

type SQLAnalysisWorkspaceReaderConfig struct {
	Queryer WriterEventSQLQueryer
}

type SQLAnalysisWorkspaceReader struct {
	queryer WriterEventSQLQueryer
}

func NewSQLAnalysisWorkspaceReader(config SQLAnalysisWorkspaceReaderConfig) *SQLAnalysisWorkspaceReader {
	return &SQLAnalysisWorkspaceReader{queryer: config.Queryer}
}

func (r *SQLAnalysisWorkspaceReader) ListWorkspaceFiles(ctx context.Context, input ListAnalysisWorkspaceFilesInput) ([]AnalysisWorkspaceFile, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis workspace reader is not configured"}
	}
	query := `SELECT
  file_id::text,
  run_id::text,
  project_id::text,
  path,
  kind,
  mime_type,
  size_bytes,
  content_sha256,
  COALESCE(content_text, ''),
  metadata_jsonb,
  updated_at::text
FROM analysis_workspace_files
WHERE tenant_id::text = $1
  AND run_id::text = $2
ORDER BY path ASC`
	rows, err := querySeedRunRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
	)
	if err != nil {
		return nil, analysisWorkspaceQueryFailed()
	}
	defer rows.Close()
	items := make([]AnalysisWorkspaceFile, 0)
	for rows.Next() {
		var file AnalysisWorkspaceFile
		var metadata []byte
		if err := rows.Scan(
			&file.FileID,
			&file.RunID,
			&file.ProjectID,
			&file.Path,
			&file.Kind,
			&file.MimeType,
			&file.SizeBytes,
			&file.ContentSHA256,
			&file.ContentText,
			&metadata,
			&file.UpdatedAt,
		); err != nil {
			return nil, analysisWorkspaceQueryFailed()
		}
		// List endpoint omits large bodies; keep small text only.
		if len(file.ContentText) > 8*1024 {
			file.ContentText = ""
		}
		file.Metadata = sanitizeAnalysisPublicPayload(metadata)
		items = append(items, file)
	}
	if err := rows.Err(); err != nil {
		return nil, analysisWorkspaceQueryFailed()
	}
	return items, nil
}

func (r *SQLAnalysisWorkspaceReader) GetWorkspaceFile(ctx context.Context, input GetAnalysisWorkspaceFileInput) (AnalysisWorkspaceFile, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" || strings.TrimSpace(input.Path) == "" {
		return AnalysisWorkspaceFile{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, run_id, and path are required"}
	}
	if r.queryer == nil {
		return AnalysisWorkspaceFile{}, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis workspace reader is not configured"}
	}
	query := `SELECT
  file_id::text,
  run_id::text,
  project_id::text,
  path,
  kind,
  mime_type,
  size_bytes,
  content_sha256,
  COALESCE(content_text, ''),
  metadata_jsonb,
  updated_at::text
FROM analysis_workspace_files
WHERE tenant_id::text = $1
  AND run_id::text = $2
  AND path = $3
LIMIT 1`
	rows, err := querySeedRunRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.Path),
	)
	if err != nil {
		return AnalysisWorkspaceFile{}, analysisWorkspaceQueryFailed()
	}
	defer rows.Close()
	if !rows.Next() {
		return AnalysisWorkspaceFile{}, &AppError{Code: "NOT_FOUND", Message: "analysis workspace file not found"}
	}
	var file AnalysisWorkspaceFile
	var metadata []byte
	if err := rows.Scan(
		&file.FileID,
		&file.RunID,
		&file.ProjectID,
		&file.Path,
		&file.Kind,
		&file.MimeType,
		&file.SizeBytes,
		&file.ContentSHA256,
		&file.ContentText,
		&metadata,
		&file.UpdatedAt,
	); err != nil {
		return AnalysisWorkspaceFile{}, analysisWorkspaceQueryFailed()
	}
	// Cap public text body size for API responses.
	const maxPublicText = 256 * 1024
	if len(file.ContentText) > maxPublicText {
		file.ContentText = file.ContentText[:maxPublicText]
	}
	file.Metadata = sanitizeAnalysisPublicPayload(metadata)
	return file, nil
}

func sanitizeAnalysisPublicPayload(raw []byte) map[string]any {
	if len(raw) == 0 {
		return map[string]any{}
	}
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		return map[string]any{}
	}
	return sanitizeAnalysisMap(payload)
}

type SQLAnalysisCandidateReaderConfig struct {
	Queryer WriterEventSQLQueryer
	Limit   int
}

type SQLAnalysisCandidateReader struct {
	queryer WriterEventSQLQueryer
	limit   int
}

func NewSQLAnalysisCandidateReader(config SQLAnalysisCandidateReaderConfig) *SQLAnalysisCandidateReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 200
	}
	return &SQLAnalysisCandidateReader{queryer: config.Queryer, limit: limit}
}

func (r *SQLAnalysisCandidateReader) ListAnalysisCandidates(ctx context.Context, input ListAnalysisCandidatesInput) ([]AnalysisCandidate, error) {
	if strings.TrimSpace(input.TenantID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id is required"}
	}
	if strings.TrimSpace(input.RunID) == "" && strings.TrimSpace(input.ProjectID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "run_id or project_id is required"}
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis candidate reader is not configured"}
	}
	query := `SELECT
  candidate_id::text,
  run_id::text,
  project_id::text,
  candidate_type,
  name,
  status,
  COALESCE(workspace_path, ''),
  payload_jsonb,
  created_at::text,
  updated_at::text
FROM analysis_candidates
WHERE tenant_id::text = $1`
	args := []any{strings.TrimSpace(input.TenantID)}
	argN := 2
	if strings.TrimSpace(input.ProjectID) != "" {
		query += fmt.Sprintf(`
  AND project_id::text = $%d`, argN)
		args = append(args, strings.TrimSpace(input.ProjectID))
		argN++
	}
	if strings.TrimSpace(input.RunID) != "" {
		query += fmt.Sprintf(`
  AND run_id::text = $%d`, argN)
		args = append(args, strings.TrimSpace(input.RunID))
		argN++
	}
	query += fmt.Sprintf(`
ORDER BY created_at DESC
LIMIT $%d`, argN)
	args = append(args, r.limit)

	rows, err := querySeedRunRows(ctx, r.queryer, strings.TrimSpace(input.TenantID), query, args...)
	if err != nil {
		return nil, analysisCandidateQueryFailed()
	}
	defer rows.Close()
	items := make([]AnalysisCandidate, 0)
	for rows.Next() {
		var item AnalysisCandidate
		var payload []byte
		if err := rows.Scan(
			&item.CandidateID,
			&item.RunID,
			&item.ProjectID,
			&item.CandidateType,
			&item.Name,
			&item.Status,
			&item.WorkspacePath,
			&payload,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return nil, analysisCandidateQueryFailed()
		}
		item.Payload = sanitizeAnalysisPublicPayload(payload)
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, analysisCandidateQueryFailed()
	}
	return items, nil
}

func analysisRunQueryFailed() error {
	return &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: "analysis run query failed"}
}

func analysisEventQueryFailed() error {
	return &AppError{Code: "WORKFLOW_EVENT_QUERY_FAILED", Message: "analysis event query failed"}
}

func analysisWorkspaceQueryFailed() error {
	return &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: "analysis workspace query failed"}
}

func analysisCandidateQueryFailed() error {
	return &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: "analysis candidate query failed"}
}
