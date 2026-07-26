package projectreadiness

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
)

type GetLatestSnapshotInput struct {
	TenantID  string
	ProjectID string
}

// SegmentCoverage summarizes whole-book reading coverage for the latest seed
// run: how many segments exist, how many produced reading notes, and which
// segment ids were skipped (so the overview can surface them instead of
// silently dropping chapters).
type SegmentCoverage struct {
	TotalSegmentCount     int      `json:"total_segment_count"`
	SucceededSegmentCount int      `json:"succeeded_segment_count"`
	FailedSegmentIDs      []string `json:"failed_segment_ids"`
}

type Snapshot struct {
	SnapshotID             string           `json:"project_readiness_snapshot_id"`
	ProjectID              string           `json:"project_id"`
	RunID                  string           `json:"run_id"`
	ReadyAssetCount        int              `json:"ready_asset_count"`
	ReadyEntityCount       int              `json:"ready_entity_count"`
	ReadyRelationshipCount int              `json:"ready_relationship_count"`
	ReadyWorldRuleCount    int              `json:"ready_world_rule_count"`
	Coverage               *SegmentCoverage `json:"coverage,omitempty"`
	CreatedAt              string           `json:"created_at"`
	UpdatedAt              string           `json:"updated_at"`
}

type Reader interface {
	GetLatestSnapshot(context.Context, GetLatestSnapshotInput) (Snapshot, error)
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "PROJECT_READINESS_FAILED"
}

type DisabledReader struct{}

func NewDisabledReader() *DisabledReader {
	return &DisabledReader{}
}

func (r *DisabledReader) GetLatestSnapshot(context.Context, GetLatestSnapshotInput) (Snapshot, error) {
	return Snapshot{}, &AppError{
		Code:    "PROJECT_READINESS_BACKEND_UNCONFIGURED",
		Message: "project readiness reader is not configured",
	}
}

type SQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type SQLQueryer interface {
	QueryContext(context.Context, string, ...any) (SQLRows, error)
}

type SQLTenantQueryer interface {
	QueryTenantContext(context.Context, string, string, ...any) (SQLRows, error)
}

type SQLDBQueryer struct {
	db *sql.DB
}

func NewSQLDBQueryer(db *sql.DB) *SQLDBQueryer {
	return &SQLDBQueryer{db: db}
}

func (q *SQLDBQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (q *SQLDBQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	tx, err := q.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
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

func (r *tenantScopedRows) Err() error {
	return r.rows.Err()
}

type SQLReaderConfig struct {
	Queryer SQLQueryer
}

type SQLReader struct {
	queryer SQLQueryer
}

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	return &SQLReader{queryer: config.Queryer}
}

func (r *SQLReader) GetLatestSnapshot(ctx context.Context, input GetLatestSnapshotInput) (Snapshot, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return Snapshot{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return Snapshot{}, &AppError{Code: "PROJECT_READINESS_BACKEND_UNCONFIGURED", Message: "project readiness reader is not configured"}
	}
	query := `SELECT
  project_readiness_snapshot_id::text,
  project_id::text,
  run_id::text,
  ready_asset_count,
  ready_entity_count,
  ready_relationship_count,
  ready_world_rule_count,
  COALESCE(metadata_jsonb::text, '{}'),
  created_at::text,
  updated_at::text
FROM project_readiness_snapshots
WHERE tenant_id::text = $1
  AND project_id::text = $2
ORDER BY updated_at DESC
LIMIT 1`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID)
	if err != nil {
		return Snapshot{}, queryFailed()
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return Snapshot{}, queryFailed()
		}
		return Snapshot{}, &AppError{Code: "NOT_FOUND", Message: "project readiness snapshot not found"}
	}
	var snapshot Snapshot
	var metadataRaw string
	if err := rows.Scan(
		&snapshot.SnapshotID,
		&snapshot.ProjectID,
		&snapshot.RunID,
		&snapshot.ReadyAssetCount,
		&snapshot.ReadyEntityCount,
		&snapshot.ReadyRelationshipCount,
		&snapshot.ReadyWorldRuleCount,
		&metadataRaw,
		&snapshot.CreatedAt,
		&snapshot.UpdatedAt,
	); err != nil {
		return Snapshot{}, queryFailed()
	}
	if err := rows.Err(); err != nil {
		return Snapshot{}, queryFailed()
	}
	snapshot.Coverage = parseSegmentCoverage(metadataRaw)
	return snapshot, nil
}

func parseSegmentCoverage(metadataRaw string) *SegmentCoverage {
	var metadata struct {
		TotalSegmentCount     *int             `json:"total_segment_count"`
		SucceededSegmentCount *int             `json:"succeeded_segment_count"`
		FailedSegmentIDs      json.RawMessage  `json:"failed_segment_ids"`
	}
	if err := json.Unmarshal([]byte(metadataRaw), &metadata); err != nil {
		return nil
	}
	if metadata.TotalSegmentCount == nil && metadata.SucceededSegmentCount == nil {
		return nil
	}
	coverage := &SegmentCoverage{FailedSegmentIDs: []string{}}
	if metadata.TotalSegmentCount != nil {
		coverage.TotalSegmentCount = *metadata.TotalSegmentCount
	}
	if metadata.SucceededSegmentCount != nil {
		coverage.SucceededSegmentCount = *metadata.SucceededSegmentCount
	}
	if len(metadata.FailedSegmentIDs) > 0 && string(metadata.FailedSegmentIDs) != "null" {
		_ = json.Unmarshal(metadata.FailedSegmentIDs, &coverage.FailedSegmentIDs)
	}
	return coverage
}

func (r *SQLReader) queryRows(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := r.queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return r.queryer.QueryContext(ctx, query, args...)
}

func queryFailed() *AppError {
	return &AppError{Code: "PROJECT_READINESS_QUERY_FAILED", Message: "project readiness query failed"}
}
