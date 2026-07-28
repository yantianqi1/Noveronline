package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
)

type SQLDraftReviewStoreConfig struct {
	Execer  WriterAdmissionSQLExecer
	Queryer WriterEventSQLQueryer
}

type SQLDraftReviewStore struct {
	execer  WriterAdmissionSQLExecer
	queryer WriterEventSQLQueryer
}

func NewSQLDraftReviewStore(config SQLDraftReviewStoreConfig) *SQLDraftReviewStore {
	return &SQLDraftReviewStore{execer: config.Execer, queryer: config.Queryer}
}

func (s *SQLDraftReviewStore) StartDraftReview(ctx context.Context, input StartDraftReviewInput) (DraftReviewAdmission, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	draftID := strings.TrimSpace(input.DraftID)
	if tenantID == "" || projectID == "" || draftID == "" {
		return DraftReviewAdmission{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and draft_id are required"}
	}
	if s.execer == nil {
		return DraftReviewAdmission{}, &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	runID := strings.TrimSpace(input.RunID)
	if runID == "" {
		allocatedRunID, err := newRunID()
		if err != nil {
			return DraftReviewAdmission{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to allocate writer review run id"}
		}
		runID = allocatedRunID
	}
	reviewID, err := newRunID()
	if err != nil {
		return DraftReviewAdmission{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to allocate writer review id"}
	}
	moduleKey := strings.TrimSpace(input.ModuleKey)
	if moduleKey == "" {
		moduleKey = "writer_reviewer"
	}
	optionsJSON, err := json.Marshal(sanitizeDraftReviewOptions(input.Options))
	if err != nil {
		return DraftReviewAdmission{}, &AppError{Code: "VALIDATION_FAILED", Message: "writer review options must be JSON serializable"}
	}
	eventPayload, err := json.Marshal(map[string]any{
		"status":        "queued",
		"workflow_type": WriterReviewWorkflowType,
		"request_id":    strings.TrimSpace(input.RequestID),
		"draft_id":      draftID,
		"review_id":     reviewID,
		"module_key":    moduleKey,
	})
	if err != nil {
		return DraftReviewAdmission{}, &AppError{Code: "VALIDATION_FAILED", Message: "writer review admission payload must be JSON serializable"}
	}
	query := `WITH draft_scope AS (
  SELECT
    tenant_id,
    draft_id,
    project_id
  FROM writer_drafts
	  WHERE tenant_id::text = $1
	    AND draft_id::text = $2
	    AND project_id::text = $11
	  LIMIT 1
	),
workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id,
    run_id,
    workflow_type,
    project_id,
    status,
    progress,
    message,
    started_by,
    temporal_workflow_id
  )
  SELECT
    draft_scope.tenant_id,
    $3::uuid,
    $4,
    draft_scope.project_id,
    'queued',
    0,
    'queued',
    NULLIF($5, '')::uuid,
    NULL
  FROM draft_scope
  RETURNING run_id, project_id
),
review_insert AS (
  INSERT INTO draft_reviews (
    tenant_id,
    project_id,
    draft_id,
    review_id,
    run_id,
    status,
    module_key,
    note,
    options_jsonb,
    created_by
  )
  SELECT
    draft_scope.tenant_id,
    draft_scope.project_id,
    draft_scope.draft_id,
    $6::uuid,
    workflow_insert.run_id,
	    'queued',
	    $7,
	    NULL,
	    $9::jsonb,
	    NULLIF($5, '')::uuid
  FROM draft_scope
  JOIN workflow_insert ON true
  RETURNING review_id, run_id, draft_id, project_id, status
),
event_insert AS (
  INSERT INTO workflow_events (
    tenant_id,
    run_id,
    workflow_type,
    project_id,
    event_type,
    sequence,
    payload_jsonb
  )
  SELECT
    $1::uuid,
    review_insert.run_id,
    $4,
    review_insert.project_id,
    'workflow.queued',
    1,
    $10::jsonb
  FROM review_insert
  RETURNING run_id
)
SELECT 1 FROM event_insert`
	result, err := execAdmissionSQL(
		ctx,
		s.execer,
		tenantID,
		projectID,
		query,
		tenantID,
		draftID,
		runID,
		WriterReviewWorkflowType,
		strings.TrimSpace(input.ActorUserID),
		reviewID,
		moduleKey,
		"",
		string(optionsJSON),
		string(eventPayload),
		projectID,
	)
	if err != nil {
		return DraftReviewAdmission{}, &AppError{Code: "WRITER_REVIEW_ADMISSION_FAILED", Message: "writer review admission failed"}
	}
	if rowsAffected, err := result.RowsAffected(); err == nil && rowsAffected == 0 {
		return DraftReviewAdmission{}, &AppError{Code: "NOT_FOUND", Message: "draft not found"}
	}
	return DraftReviewAdmission{
		ReviewID:     reviewID,
		RunID:        runID,
		DraftID:      draftID,
		ProjectID:    projectID,
		Status:       "queued",
		WorkflowType: WriterReviewWorkflowType,
	}, nil
}

func (s *SQLDraftReviewStore) ListDraftReviews(ctx context.Context, input ListDraftReviewsInput) (DraftReviewList, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	draftID := strings.TrimSpace(input.DraftID)
	if tenantID == "" || draftID == "" {
		return DraftReviewList{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and draft_id are required"}
	}
	if s.queryer == nil {
		return DraftReviewList{}, &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	query := `SELECT
  reviews.review_id::text,
  reviews.run_id::text,
  reviews.draft_id::text,
  reviews.project_id::text,
  reviews.status,
  issues.issue_id::text,
  issues.severity,
  issues.category,
  issues.summary,
  issues.suggestion,
  issues.status,
  issues.created_at::text,
  issues.updated_at::text,
  reviews.created_at::text,
  reviews.updated_at::text
FROM draft_reviews reviews
	LEFT JOIN draft_review_issues issues
	  ON issues.tenant_id = reviews.tenant_id
	 AND issues.review_id = reviews.review_id
	 AND issues.project_id = reviews.project_id
	 AND issues.draft_id = reviews.draft_id
WHERE reviews.tenant_id::text = $1
  AND reviews.draft_id::text = $2
ORDER BY reviews.created_at DESC, issues.created_at ASC`
	rows, err := queryWorkflowEventRows(ctx, s.queryer, tenantID, query, tenantID, draftID)
	if err != nil {
		return DraftReviewList{}, draftReviewQueryFailed()
	}
	defer rows.Close()

	result := DraftReviewList{DraftID: draftID, Reviews: []DraftReviewRecord{}}
	indexByReviewID := map[string]int{}
	for rows.Next() {
		var reviewID string
		var runID string
		var rowDraftID string
		var projectID string
		var status string
		var issueID sql.NullString
		var severity sql.NullString
		var category sql.NullString
		var summary sql.NullString
		var suggestion sql.NullString
		var issueStatus sql.NullString
		var issueCreatedAt sql.NullString
		var issueUpdatedAt sql.NullString
		var createdAt string
		var updatedAt string
		if err := rows.Scan(
			&reviewID,
			&runID,
			&rowDraftID,
			&projectID,
			&status,
			&issueID,
			&severity,
			&category,
			&summary,
			&suggestion,
			&issueStatus,
			&issueCreatedAt,
			&issueUpdatedAt,
			&createdAt,
			&updatedAt,
		); err != nil {
			return DraftReviewList{}, draftReviewQueryFailed()
		}
		if result.ProjectID == "" {
			result.ProjectID = projectID
		}
		index, exists := indexByReviewID[reviewID]
		if !exists {
			result.Reviews = append(result.Reviews, DraftReviewRecord{
				ReviewID:  reviewID,
				RunID:     runID,
				DraftID:   rowDraftID,
				ProjectID: projectID,
				Status:    status,
				CreatedAt: createdAt,
				UpdatedAt: updatedAt,
				Issues:    []DraftReviewIssue{},
			})
			index = len(result.Reviews) - 1
			indexByReviewID[reviewID] = index
		}
		if issueID.Valid {
			result.Reviews[index].Issues = append(result.Reviews[index].Issues, DraftReviewIssue{
				IssueID:    issueID.String,
				Severity:   severity.String,
				Category:   category.String,
				Summary:    publicDraftReviewText(summary.String),
				Suggestion: publicDraftReviewText(suggestion.String),
				Status:     issueStatus.String,
				CreatedAt:  issueCreatedAt.String,
				UpdatedAt:  issueUpdatedAt.String,
			})
		}
	}
	if err := rows.Err(); err != nil {
		return DraftReviewList{}, draftReviewQueryFailed()
	}
	return result, nil
}

func draftReviewQueryFailed() *AppError {
	return &AppError{Code: "WRITER_REVIEW_QUERY_FAILED", Message: "writer review query failed"}
}

// ListProjectReviewIssues powers the 审校 canvas view: every draft in the
// project that has issues in the requested status (default "open"), grouped per
// draft with the draft's chapter + the run's instruction for queue context. It
// joins draft → run so the queue can show "which chapter / what prompt" without
// a second round-trip.
func (s *SQLDraftReviewStore) ListProjectReviewIssues(ctx context.Context, input ListProjectReviewIssuesInput) (ProjectDraftReviewQueue, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "open"
	}
	if tenantID == "" || projectID == "" {
		return ProjectDraftReviewQueue{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if s.queryer == nil {
		return ProjectDraftReviewQueue{}, &AppError{Code: "WRITER_REVIEW_BACKEND_UNCONFIGURED", Message: "writer review backend is not configured"}
	}
	query := `SELECT
  issues.issue_id::text,
  issues.draft_id::text,
  issues.severity,
  issues.category,
  issues.summary,
  issues.suggestion,
  issues.status,
  issues.created_at::text,
  issues.updated_at::text,
  drafts.chapter_id::text,
  drafts.word_count,
  runs.instruction
FROM draft_review_issues issues
JOIN writer_drafts drafts
  ON drafts.tenant_id = issues.tenant_id
 AND drafts.draft_id = issues.draft_id
JOIN writer_runs runs
  ON runs.tenant_id = drafts.tenant_id
 AND runs.run_id = drafts.run_id
WHERE issues.tenant_id::text = $1
  AND issues.project_id::text = $2
  AND issues.status = $3
ORDER BY drafts.created_at DESC, issues.created_at ASC`
	rows, err := queryWorkflowEventRows(ctx, s.queryer, tenantID, query, tenantID, projectID, status)
	if err != nil {
		return ProjectDraftReviewQueue{}, draftReviewQueryFailed()
	}
	defer rows.Close()

	result := ProjectDraftReviewQueue{ProjectID: projectID, Items: []ProjectDraftReviewBucket{}}
	indexByDraftID := map[string]int{}
	for rows.Next() {
		var issueID, draftID, severity, category, summary string
		var suggestion, issueStatus, createdAt, updatedAt string
		var chapterID sql.NullString
		var wordCount int
		var instruction sql.NullString
		if err := rows.Scan(
			&issueID,
			&draftID,
			&severity,
			&category,
			&summary,
			&suggestion,
			&issueStatus,
			&createdAt,
			&updatedAt,
			&chapterID,
			&wordCount,
			&instruction,
		); err != nil {
			return ProjectDraftReviewQueue{}, draftReviewQueryFailed()
		}
		index, exists := indexByDraftID[draftID]
		if !exists {
			result.Items = append(result.Items, ProjectDraftReviewBucket{
				DraftID:        draftID,
				ChapterID:      chapterID.String,
				Instruction:    instruction.String,
				DraftWordCount: wordCount,
				Issues:         []ProjectReviewIssue{},
			})
			index = len(result.Items) - 1
			indexByDraftID[draftID] = index
		}
		result.Items[index].OpenCount++
		result.Items[index].Issues = append(result.Items[index].Issues, ProjectReviewIssue{
			DraftReviewIssue: DraftReviewIssue{
				IssueID:    issueID,
				Severity:   severity,
				Category:   category,
				Summary:    publicDraftReviewText(summary),
				Suggestion: publicDraftReviewText(suggestion),
				Status:     issueStatus,
				CreatedAt:  createdAt,
				UpdatedAt:  updatedAt,
			},
			DraftID:   draftID,
			ChapterID: chapterID.String,
		})
	}
	if err := rows.Err(); err != nil {
		return ProjectDraftReviewQueue{}, draftReviewQueryFailed()
	}
	return result, nil
}

func sanitizeDraftReviewOptions(options map[string]any) map[string]any {
	value := sanitizeWriterAdmissionValue(options)
	typed, ok := value.(map[string]any)
	if !ok {
		return map[string]any{}
	}
	return stripDraftReviewRoutingMetadata(typed)
}

func stripDraftReviewRoutingMetadata(options map[string]any) map[string]any {
	clean := map[string]any{}
	for key, value := range options {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if isDraftReviewRoutingMetadataKey(normalizedKey) {
			continue
		}
		switch typed := value.(type) {
		case map[string]any:
			clean[key] = stripDraftReviewRoutingMetadata(typed)
		case []any:
			items := make([]any, 0, len(typed))
			for _, item := range typed {
				if nested, ok := item.(map[string]any); ok {
					items = append(items, stripDraftReviewRoutingMetadata(nested))
					continue
				}
				items = append(items, item)
			}
			clean[key] = items
		default:
			clean[key] = value
		}
	}
	return clean
}

func isDraftReviewRoutingMetadataKey(key string) bool {
	switch key {
	case "llm_resolution", "provider", "base_url", "baseurl", "channel_id", "channelid", "model_id", "modelid", "settings":
		return true
	default:
		return false
	}
}

func publicDraftReviewText(value string) string {
	value = strings.TrimSpace(value)
	lowered := strings.ToLower(value)
	for _, marker := range []string{
		"api_key",
		"apikey",
		"encrypted_api_key",
		"credential_ref",
		"credential-ref",
		"sk-",
		"prompt",
		"response",
		"body_text",
		"content_text",
		"source_text",
		"source_material",
		"raw_text",
		"raw_body",
		"raw_content",
		"draft text",
		"manuscript text",
	} {
		if strings.Contains(lowered, marker) {
			return ""
		}
	}
	return value
}
