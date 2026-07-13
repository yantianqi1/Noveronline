package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
	"time"
)

type WriterThread struct {
	ThreadID  string `json:"thread_id"`
	ProjectID string `json:"project_id"`
	Title     string `json:"title,omitempty"`
	Status    string `json:"status"`
	UpdatedAt string `json:"updated_at"`
}

type WriterThreadMessage struct {
	MessageID string         `json:"message_id"`
	ThreadID  string         `json:"thread_id"`
	Role      string         `json:"role"`
	Body      string         `json:"body"`
	RunID     string         `json:"run_id,omitempty"`
	Sequence  int64          `json:"sequence"`
	CreatedAt string         `json:"created_at"`
	Metadata  map[string]any `json:"metadata,omitempty"`
}

type WriterApproval struct {
	ApprovalID  string `json:"approval_id"`
	ProjectID   string `json:"project_id"`
	RunID       string `json:"run_id"`
	ThreadID    string `json:"thread_id,omitempty"`
	Status      string `json:"status"`
	Action      string `json:"action"`
	Summary     string `json:"summary"`
	Consequence string `json:"consequence"`
	Reversible  bool   `json:"reversible"`
	CreatedAt   string `json:"created_at"`
}

type ListWriterThreadsInput struct {
	TenantID  string
	ProjectID string
}

type ListWriterThreadMessagesInput struct {
	TenantID  string
	ProjectID string
	ThreadID  string
}

type AppendWriterThreadMessageInput struct {
	TenantID  string
	ProjectID string
	ThreadID  string
	Role      string
	Body      string
	RunID     string
	ActorID   string
	Metadata  map[string]any
}

type EnsureWriterThreadInput struct {
	TenantID  string
	ProjectID string
	ActorID   string
	Title     string
}

type DecideWriterApprovalInput struct {
	TenantID    string
	ProjectID   string
	ApprovalID  string
	Decision    string
	ActorUserID string
}

type WriterThreadStore interface {
	EnsureThread(context.Context, EnsureWriterThreadInput) (WriterThread, error)
	ListThreads(context.Context, ListWriterThreadsInput) ([]WriterThread, error)
	ListMessages(context.Context, ListWriterThreadMessagesInput) ([]WriterThreadMessage, error)
	AppendMessage(context.Context, AppendWriterThreadMessageInput) (WriterThreadMessage, error)
	DecideApproval(context.Context, DecideWriterApprovalInput) (WriterApproval, error)
}

type SQLWriterThreadStore struct {
	db *sql.DB
}

func NewSQLWriterThreadStore(db *sql.DB) *SQLWriterThreadStore {
	return &SQLWriterThreadStore{db: db}
}

func (s *SQLWriterThreadStore) EnsureThread(ctx context.Context, input EnsureWriterThreadInput) (WriterThread, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return WriterThread{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if s.db == nil {
		return WriterThread{}, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer thread store is not configured"}
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return WriterThread{}, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to open writer thread transaction"}
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ProjectID); err != nil {
		return WriterThread{}, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to set tenant context for writer threads"}
	}
	var thread WriterThread
	err = tx.QueryRowContext(ctx, `
SELECT thread_id::text, project_id::text, COALESCE(title, ''), status, updated_at::text
FROM writer_threads
WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND status = 'active'
ORDER BY updated_at DESC
LIMIT 1`, input.TenantID, input.ProjectID).Scan(&thread.ThreadID, &thread.ProjectID, &thread.Title, &thread.Status, &thread.UpdatedAt)
	if err == nil {
		if err := tx.Commit(); err != nil {
			return WriterThread{}, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to commit writer thread read"}
		}
		return thread, nil
	}
	if err != sql.ErrNoRows {
		return WriterThread{}, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to load writer thread"}
	}
	title := strings.TrimSpace(input.Title)
	if title == "" {
		title = "Writer thread"
	}
	err = tx.QueryRowContext(ctx, `
INSERT INTO writer_threads (tenant_id, project_id, title, status, created_by, updated_by)
VALUES ($1::uuid, $2::uuid, $3, 'active', NULLIF($4, '')::uuid, NULLIF($4, '')::uuid)
RETURNING thread_id::text, project_id::text, COALESCE(title, ''), status, updated_at::text`,
		input.TenantID, input.ProjectID, title, strings.TrimSpace(input.ActorID),
	).Scan(&thread.ThreadID, &thread.ProjectID, &thread.Title, &thread.Status, &thread.UpdatedAt)
	if err != nil {
		return WriterThread{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to create writer thread"}
	}
	if err := tx.Commit(); err != nil {
		return WriterThread{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to commit writer thread create"}
	}
	return thread, nil
}

func (s *SQLWriterThreadStore) ListThreads(ctx context.Context, input ListWriterThreadsInput) ([]WriterThread, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if s.db == nil {
		return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer thread store is not configured"}
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to open writer thread transaction"}
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ProjectID); err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to set tenant context for writer threads"}
	}
	rows, err := tx.QueryContext(ctx, `
SELECT thread_id::text, project_id::text, COALESCE(title, ''), status, updated_at::text
FROM writer_threads
WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND status = 'active'
ORDER BY updated_at DESC
LIMIT 20`, input.TenantID, input.ProjectID)
	if err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to list writer threads"}
	}
	defer rows.Close()
	items := []WriterThread{}
	for rows.Next() {
		var item WriterThread
		if err := rows.Scan(&item.ThreadID, &item.ProjectID, &item.Title, &item.Status, &item.UpdatedAt); err != nil {
			return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to scan writer thread"}
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to iterate writer threads"}
	}
	if err := tx.Commit(); err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to commit writer thread list"}
	}
	return items, nil
}

func (s *SQLWriterThreadStore) ListMessages(ctx context.Context, input ListWriterThreadMessagesInput) ([]WriterThreadMessage, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.ThreadID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and thread_id are required"}
	}
	if s.db == nil {
		return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer thread store is not configured"}
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to open writer message transaction"}
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ProjectID); err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to set tenant context for writer messages"}
	}
	rows, err := tx.QueryContext(ctx, `
SELECT message_id::text, thread_id::text, role, body, COALESCE(run_id::text, ''), sequence, created_at::text, metadata_jsonb::text
FROM writer_thread_messages
WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND thread_id = $3::uuid
ORDER BY sequence ASC
LIMIT 500`, input.TenantID, input.ProjectID, input.ThreadID)
	if err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to list writer messages"}
	}
	defer rows.Close()
	items := []WriterThreadMessage{}
	for rows.Next() {
		var item WriterThreadMessage
		var metadataJSON string
		if err := rows.Scan(&item.MessageID, &item.ThreadID, &item.Role, &item.Body, &item.RunID, &item.Sequence, &item.CreatedAt, &metadataJSON); err != nil {
			return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to scan writer message"}
		}
		_ = json.Unmarshal([]byte(metadataJSON), &item.Metadata)
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to iterate writer messages"}
	}
	if err := tx.Commit(); err != nil {
		return nil, &AppError{Code: "WRITER_THREAD_QUERY_FAILED", Message: "failed to commit writer message list"}
	}
	return items, nil
}

func (s *SQLWriterThreadStore) AppendMessage(ctx context.Context, input AppendWriterThreadMessageInput) (WriterThreadMessage, error) {
	role := strings.TrimSpace(input.Role)
	body := strings.TrimSpace(input.Body)
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.ThreadID) == "" || role == "" || body == "" {
		return WriterThreadMessage{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, thread_id, role, and body are required"}
	}
	if role != "user" && role != "agent" && role != "system" && role != "approval" {
		return WriterThreadMessage{}, &AppError{Code: "VALIDATION_FAILED", Message: "invalid writer thread message role"}
	}
	if s.db == nil {
		return WriterThreadMessage{}, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer thread store is not configured"}
	}
	metadata := input.Metadata
	if metadata == nil {
		metadata = map[string]any{}
	}
	metadataJSON, err := json.Marshal(metadata)
	if err != nil {
		return WriterThreadMessage{}, &AppError{Code: "VALIDATION_FAILED", Message: "message metadata must be JSON serializable"}
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return WriterThreadMessage{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to open writer message transaction"}
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ProjectID); err != nil {
		return WriterThreadMessage{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to set tenant context for writer messages"}
	}
	var nextSequence int64
	if err := tx.QueryRowContext(ctx, `
SELECT COALESCE(MAX(sequence), 0) + 1
FROM writer_thread_messages
WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND thread_id = $3::uuid`,
		input.TenantID, input.ProjectID, input.ThreadID,
	).Scan(&nextSequence); err != nil {
		return WriterThreadMessage{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to allocate writer message sequence"}
	}
	var message WriterThreadMessage
	err = tx.QueryRowContext(ctx, `
INSERT INTO writer_thread_messages (
  tenant_id, project_id, thread_id, role, body, run_id, sequence, metadata_jsonb, created_by
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, $4, $5, NULLIF($6, '')::uuid, $7, $8::jsonb, NULLIF($9, '')::uuid
)
RETURNING message_id::text, thread_id::text, role, body, COALESCE(run_id::text, ''), sequence, created_at::text`,
		input.TenantID, input.ProjectID, input.ThreadID, role, body, strings.TrimSpace(input.RunID), nextSequence, string(metadataJSON), strings.TrimSpace(input.ActorID),
	).Scan(&message.MessageID, &message.ThreadID, &message.Role, &message.Body, &message.RunID, &message.Sequence, &message.CreatedAt)
	if err != nil {
		return WriterThreadMessage{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to append writer message"}
	}
	if _, err := tx.ExecContext(ctx, `
UPDATE writer_threads
SET updated_at = now(), updated_by = NULLIF($4, '')::uuid
WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND thread_id = $3::uuid`,
		input.TenantID, input.ProjectID, input.ThreadID, strings.TrimSpace(input.ActorID),
	); err != nil {
		return WriterThreadMessage{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to touch writer thread"}
	}
	if err := tx.Commit(); err != nil {
		return WriterThreadMessage{}, &AppError{Code: "WRITER_THREAD_MUTATION_FAILED", Message: "failed to commit writer message"}
	}
	message.Metadata = metadata
	return message, nil
}

func (s *SQLWriterThreadStore) DecideApproval(ctx context.Context, input DecideWriterApprovalInput) (WriterApproval, error) {
	decision := strings.TrimSpace(input.Decision)
	if decision != "approve" && decision != "reject" {
		return WriterApproval{}, &AppError{Code: "VALIDATION_FAILED", Message: "decision must be approve or reject"}
	}
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.ApprovalID) == "" {
		return WriterApproval{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and approval_id are required"}
	}
	if s.db == nil {
		return WriterApproval{}, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer thread store is not configured"}
	}
	status := "approved"
	if decision == "reject" {
		status = "rejected"
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return WriterApproval{}, &AppError{Code: "WRITER_APPROVAL_MUTATION_FAILED", Message: "failed to open writer approval transaction"}
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", input.TenantID, input.ProjectID); err != nil {
		return WriterApproval{}, &AppError{Code: "WRITER_APPROVAL_MUTATION_FAILED", Message: "failed to set tenant context for writer approval"}
	}
	var approval WriterApproval
	err = tx.QueryRowContext(ctx, `
UPDATE writer_approvals
SET status = $4,
    decided_by = NULLIF($5, '')::uuid,
    decided_at = now(),
    updated_at = now()
WHERE tenant_id = $1::uuid
  AND project_id = $2::uuid
  AND approval_id = $3::uuid
  AND status = 'pending'
RETURNING approval_id::text, project_id::text, run_id::text, COALESCE(thread_id::text, ''), status, action, summary, consequence, reversible, created_at::text`,
		input.TenantID, input.ProjectID, input.ApprovalID, status, strings.TrimSpace(input.ActorUserID),
	).Scan(
		&approval.ApprovalID, &approval.ProjectID, &approval.RunID, &approval.ThreadID,
		&approval.Status, &approval.Action, &approval.Summary, &approval.Consequence, &approval.Reversible, &approval.CreatedAt,
	)
	if err == sql.ErrNoRows {
		return WriterApproval{}, &AppError{Code: "WRITER_APPROVAL_NOT_FOUND", Message: "writer approval was not found or already decided"}
	}
	if err != nil {
		return WriterApproval{}, &AppError{Code: "WRITER_APPROVAL_MUTATION_FAILED", Message: "failed to decide writer approval"}
	}
	if err := tx.Commit(); err != nil {
		return WriterApproval{}, &AppError{Code: "WRITER_APPROVAL_MUTATION_FAILED", Message: "failed to commit writer approval"}
	}
	return approval, nil
}

// SortWriterThreadMessages is a pure helper for contract tests.
func SortWriterThreadMessages(messages []WriterThreadMessage) []WriterThreadMessage {
	sorted := append([]WriterThreadMessage(nil), messages...)
	for i := 0; i < len(sorted); i++ {
		for j := i + 1; j < len(sorted); j++ {
			if sorted[j].Sequence < sorted[i].Sequence ||
				(sorted[j].Sequence == sorted[i].Sequence && sorted[j].CreatedAt < sorted[i].CreatedAt) {
				sorted[i], sorted[j] = sorted[j], sorted[i]
			}
		}
	}
	return sorted
}

// WriterApprovalDecisionEvent builds a public-safe payload for approval resolution.
func WriterApprovalDecisionEvent(approval WriterApproval, decision string) map[string]any {
	return map[string]any{
		"approval_id": approval.ApprovalID,
		"decision":    decision,
		"status":      approval.Status,
		"action":      approval.Action,
		"decided_at":  time.Now().UTC().Format(time.RFC3339Nano),
	}
}
