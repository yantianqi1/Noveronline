package manuscriptworkspace

import (
	"context"
	"database/sql"
	"errors"
	"strings"
)

type DedupPattern struct {
	PatternID           string `json:"pattern_id"`
	ProjectID           string `json:"project_id"`
	PatternText         string `json:"pattern_text"`
	NormalizedPattern   string `json:"normalized_pattern"`
	PatternKind         string `json:"pattern_kind"`
	Lifecycle           string `json:"lifecycle"`
	Enabled             bool   `json:"enabled"`
	OccurrenceCount     int    `json:"occurrence_count"`
	SourceCommandRunID  string `json:"source_command_run_id,omitempty"`
	SourceWorkflowRunID string `json:"source_workflow_run_id,omitempty"`
	CreatedAt           string `json:"created_at"`
	UpdatedAt           string `json:"updated_at"`
}

type CreateDedupCandidateInput struct {
	Scope
	PatternText         string
	PatternKind         string
	OccurrenceCount     int
	SourceCommandRunID  string
	SourceWorkflowRunID string
}

type ReviewDedupPatternInput struct {
	Scope
	PatternID string
	Decision  string
}

type DedupStore interface {
	CreateDedupCandidate(context.Context, CreateDedupCandidateInput) (DedupPattern, bool, error)
	ListDedupPatterns(context.Context, Scope, string) ([]DedupPattern, error)
	ReviewDedupPattern(context.Context, ReviewDedupPatternInput) (DedupPattern, error)
}

func (s *SQLStore) CreateDedupCandidate(ctx context.Context, input CreateDedupCandidateInput) (DedupPattern, bool, error) {
	input.Scope = normalizeScope(input.Scope)
	input.PatternText = strings.TrimSpace(input.PatternText)
	input.PatternKind = strings.TrimSpace(input.PatternKind)
	input.SourceCommandRunID = strings.TrimSpace(input.SourceCommandRunID)
	input.SourceWorkflowRunID = strings.TrimSpace(input.SourceWorkflowRunID)
	normalized := strings.ToLower(strings.Join(strings.Fields(input.PatternText), " "))
	if err := validateScope(input.Scope, false); err != nil || normalized == "" || !validPatternKind(input.PatternKind) || input.OccurrenceCount < 0 {
		return DedupPattern{}, false, validation("valid candidate pattern fields are required")
	}
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return DedupPattern{}, false, dedupWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	result, err := tx.ExecContext(ctx, `INSERT INTO writer_dedup_patterns (
  tenant_id, project_id, pattern_text, normalized_pattern, pattern_kind,
  lifecycle, enabled, occurrence_count, source_command_run_id, source_workflow_run_id
) VALUES ($1::uuid, $2::uuid, $3, $4, $5, 'candidate', FALSE, $6,
  NULLIF($7, '')::uuid, NULLIF($8, '')::uuid)
ON CONFLICT (tenant_id, project_id, normalized_pattern) DO NOTHING`,
		input.TenantID, input.ProjectID, input.PatternText, normalized, input.PatternKind,
		input.OccurrenceCount, input.SourceCommandRunID, input.SourceWorkflowRunID)
	if err != nil {
		return DedupPattern{}, false, dedupWriteFailed()
	}
	count, _ := result.RowsAffected()
	pattern, err := getDedupByNormalized(ctx, tx, input.Scope, normalized)
	if err != nil {
		return DedupPattern{}, false, err
	}
	if err := tx.Commit(); err != nil {
		return DedupPattern{}, false, dedupWriteFailed()
	}
	return pattern, count == 0, nil
}

func (s *SQLStore) ListDedupPatterns(ctx context.Context, scope Scope, lifecycle string) ([]DedupPattern, error) {
	scope = normalizeScope(scope)
	lifecycle = strings.TrimSpace(lifecycle)
	if err := validateScope(scope, false); err != nil || (lifecycle != "" && lifecycle != "candidate" && lifecycle != "accepted" && lifecycle != "rejected") {
		return nil, validation("valid scope and lifecycle are required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return nil, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	rows, err := tx.QueryContext(ctx, dedupSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND ($3 = '' OR lifecycle = $3)
ORDER BY created_at DESC, pattern_id`, scope.TenantID, scope.ProjectID, lifecycle)
	if err != nil {
		return nil, queryFailed()
	}
	defer rows.Close()
	patterns := []DedupPattern{}
	for rows.Next() {
		pattern, err := scanDedup(rows)
		if err != nil {
			return nil, queryFailed()
		}
		patterns = append(patterns, pattern)
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
	return patterns, nil
}

func (s *SQLStore) ReviewDedupPattern(ctx context.Context, input ReviewDedupPatternInput) (DedupPattern, error) {
	input.Scope = normalizeScope(input.Scope)
	input.PatternID = strings.TrimSpace(input.PatternID)
	input.Decision = strings.TrimSpace(input.Decision)
	if err := validateScope(input.Scope, true); err != nil || input.PatternID == "" || (input.Decision != "accepted" && input.Decision != "rejected") {
		return DedupPattern{}, validation("pattern_id and accepted or rejected decision are required")
	}
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return DedupPattern{}, dedupWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	enabled := input.Decision == "accepted"
	query := `UPDATE writer_dedup_patterns SET lifecycle = $4, enabled = $5,
  accepted_by = CASE WHEN $5 THEN $6::uuid ELSE NULL END,
  accepted_at = CASE WHEN $5 THEN now() ELSE NULL END, updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND pattern_id::text = $3 AND lifecycle = 'candidate'
RETURNING ` + dedupColumns
	pattern, err := scanDedup(tx.QueryRowContext(ctx, query, input.TenantID, input.ProjectID,
		input.PatternID, input.Decision, enabled, input.ActorUserID))
	if errors.Is(err, sql.ErrNoRows) {
		return DedupPattern{}, &AppError{Code: "DEDUP_PATTERN_STATE_CONFLICT", Message: "dedup pattern is no longer a candidate"}
	}
	if err != nil {
		return DedupPattern{}, dedupWriteFailed()
	}
	if err := tx.Commit(); err != nil {
		return DedupPattern{}, dedupWriteFailed()
	}
	return pattern, nil
}

const dedupColumns = `pattern_id::text, project_id::text, pattern_text, normalized_pattern,
  pattern_kind, lifecycle, enabled, occurrence_count, COALESCE(source_command_run_id::text, ''),
  COALESCE(source_workflow_run_id::text, ''), created_at::text, updated_at::text`
const dedupSelect = `SELECT ` + dedupColumns + ` FROM writer_dedup_patterns`

func scanDedup(row scanner) (DedupPattern, error) {
	var pattern DedupPattern
	err := row.Scan(&pattern.PatternID, &pattern.ProjectID, &pattern.PatternText,
		&pattern.NormalizedPattern, &pattern.PatternKind, &pattern.Lifecycle, &pattern.Enabled,
		&pattern.OccurrenceCount, &pattern.SourceCommandRunID, &pattern.SourceWorkflowRunID,
		&pattern.CreatedAt, &pattern.UpdatedAt)
	return pattern, err
}

func getDedupByNormalized(ctx context.Context, tx *sql.Tx, scope Scope, normalized string) (DedupPattern, error) {
	pattern, err := scanDedup(tx.QueryRowContext(ctx, dedupSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND normalized_pattern = $3 FOR UPDATE`,
		scope.TenantID, scope.ProjectID, normalized))
	if err != nil {
		return DedupPattern{}, dedupWriteFailed()
	}
	return pattern, nil
}

func validPatternKind(kind string) bool {
	switch kind {
	case "phrase", "sentence_shape", "transition", "description":
		return true
	default:
		return false
	}
}

func dedupWriteFailed() *AppError {
	return &AppError{Code: "DEDUP_PATTERN_WRITE_FAILED", Message: "dedup candidate update failed"}
}
