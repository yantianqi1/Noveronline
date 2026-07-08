package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
)

type ListWorkflowEventsInput struct {
	TenantID     string
	RunID        string
	AfterEventID string
}

type WorkflowEvent struct {
	EventID   string         `json:"event_id"`
	RunID     string         `json:"run_id"`
	ProjectID string         `json:"project_id"`
	Sequence  int            `json:"sequence"`
	EventType string         `json:"event_type"`
	Payload   map[string]any `json:"payload"`
	CreatedAt string         `json:"created_at"`
}

type WorkflowEventReader interface {
	ListWorkflowEvents(context.Context, ListWorkflowEventsInput) ([]WorkflowEvent, error)
}

type DisabledWorkflowEventReader struct{}

func NewDisabledWorkflowEventReader() *DisabledWorkflowEventReader {
	return &DisabledWorkflowEventReader{}
}

func (r *DisabledWorkflowEventReader) ListWorkflowEvents(_ context.Context, _ ListWorkflowEventsInput) ([]WorkflowEvent, error) {
	return nil, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "workflow event reader is not configured",
	}
}

type SQLWorkflowEventReaderConfig struct {
	Queryer WriterEventSQLQueryer
	Limit   int
}

type SQLWorkflowEventReader struct {
	queryer WriterEventSQLQueryer
	limit   int
}

func NewSQLWorkflowEventReader(config SQLWorkflowEventReaderConfig) *SQLWorkflowEventReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLWorkflowEventReader{queryer: config.Queryer, limit: limit}
}

func (r *SQLWorkflowEventReader) ListWorkflowEvents(ctx context.Context, input ListWorkflowEventsInput) ([]WorkflowEvent, error) {
	if input.TenantID == "" || input.RunID == "" {
		return nil, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "workflow event reader is not configured",
		}
	}
	query := `WITH after_cursor AS (
  SELECT sequence
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND run_id::text = $2
    AND event_id::text = $3
  LIMIT 1
),
cursor_state AS (
  SELECT ($3 = '' OR EXISTS (SELECT 1 FROM after_cursor)) AS cursor_found
),
event_rows AS (
  SELECT
    event_id::text,
    run_id::text,
    project_id::text,
    sequence,
    event_type,
    payload_jsonb::text,
    created_at::text
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND run_id::text = $2
    AND ($3 = '' OR sequence > COALESCE((SELECT sequence FROM after_cursor), -1))
  ORDER BY sequence ASC
  LIMIT $4
)
SELECT
  cursor_state.cursor_found,
  event_rows.event_id,
  event_rows.run_id,
  event_rows.project_id,
  event_rows.sequence,
  event_rows.event_type,
  event_rows.payload_jsonb,
  event_rows.created_at
FROM cursor_state
LEFT JOIN event_rows ON true
ORDER BY event_rows.sequence ASC NULLS LAST`
	rows, err := queryWorkflowEventRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.AfterEventID),
		r.limit,
	)
	if err != nil {
		return nil, workflowEventQueryFailed()
	}
	defer rows.Close()

	records := []WorkflowEvent{}
	for rows.Next() {
		var cursorFound bool
		var eventID sql.NullString
		var runID sql.NullString
		var projectID sql.NullString
		var sequence sql.NullInt64
		var eventType sql.NullString
		var payloadJSON sql.NullString
		var createdAt sql.NullString
		if err := rows.Scan(
			&cursorFound,
			&eventID,
			&runID,
			&projectID,
			&sequence,
			&eventType,
			&payloadJSON,
			&createdAt,
		); err != nil {
			return nil, workflowEventQueryFailed()
		}
		if !cursorFound {
			return nil, &AppError{
				Code:    "EVENT_CURSOR_NOT_FOUND",
				Message: "workflow event cursor not found",
			}
		}
		if !eventID.Valid {
			continue
		}
		records = append(records, WorkflowEvent{
			EventID:   eventID.String,
			RunID:     runID.String,
			ProjectID: projectID.String,
			Sequence:  int(sequence.Int64),
			EventType: eventType.String,
			Payload:   SanitizeWorkflowEventPayload(decodeWorkflowEventPayload(payloadJSON.String)),
			CreatedAt: createdAt.String,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, workflowEventQueryFailed()
	}
	return records, nil
}

func queryWorkflowEventRows(ctx context.Context, queryer WriterEventSQLQueryer, tenantID string, query string, args ...any) (WriterEventSQLRows, error) {
	if tenantQueryer, ok := queryer.(WriterEventSQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return queryer.QueryContext(ctx, query, args...)
}

func workflowEventQueryFailed() *AppError {
	return &AppError{Code: "WORKFLOW_EVENT_QUERY_FAILED", Message: "workflow event query failed"}
}

func decodeWorkflowEventPayload(raw string) map[string]any {
	var payload map[string]any
	if err := json.Unmarshal([]byte(raw), &payload); err != nil || payload == nil {
		return map[string]any{}
	}
	return payload
}

func SanitizeWorkflowEventPayload(payload map[string]any) map[string]any {
	sanitized, _ := sanitizeWorkflowValue(payload).(map[string]any)
	if sanitized == nil {
		return map[string]any{}
	}
	return sanitized
}

func sanitizeWorkflowValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		result := map[string]any{}
		for key, item := range typed {
			if isSensitiveWorkflowPayloadKey(key) {
				continue
			}
			result[key] = sanitizeWorkflowValue(item)
		}
		return result
	case []any:
		result := make([]any, 0, len(typed))
		for _, item := range typed {
			result = append(result, sanitizeWorkflowValue(item))
		}
		return result
	default:
		return value
	}
}

func isSensitiveWorkflowPayloadKey(key string) bool {
	normalized := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(key), "-", "_"))
	switch normalized {
	case "api_key", "apikey", "encrypted_api_key", "encryptedapikey",
		"credential_ref", "credentialref", "credential", "credentials",
		"provider", "provider_response", "providerresponse", "provider_secret", "secret", "key_material",
		"object_key", "objectkey", "source_object_key", "sourceobjectkey",
		"artifact_object_key", "artifactobjectkey", "segment_object_key", "segmentobjectkey",
		"storage_key", "storagekey", "bucket_key", "bucketkey",
		"hash", "sha256", "source_sha256", "sourcesha256", "file_hash", "filehash", "checksum",
		"prompt", "response", "body", "content", "draft", "manuscript",
		"raw_body", "rawbody", "raw_content", "rawcontent", "raw_text", "rawtext",
		"body_text", "bodytext", "content_text", "contenttext",
		"input_text", "inputtext", "output_text", "outputtext",
		"material_text", "materialtext", "source_material", "sourcematerial",
		"source_text", "sourcetext", "parsed_text", "parsedtext":
		return true
	default:
		return false
	}
}
