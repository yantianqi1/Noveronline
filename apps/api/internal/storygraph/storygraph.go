package storygraph

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
)

const (
	defaultGraphPageSize   = 300
	maximumGraphPageSize   = 1000
	defaultClusterPageSize = 100
	maximumClusterPageSize = 500
)

type GetCurrentInput struct {
	TenantID  string
	ProjectID string
}

type GetViewInput struct {
	TenantID     string
	ProjectID    string
	ViewID       string
	Types        []string
	Offset       int
	Limit        int
	IncludeEdges bool
}

type GetNodeInput struct {
	TenantID  string
	ProjectID string
	NodeID    string
}

type GetEdgeInput struct {
	TenantID  string
	ProjectID string
	EdgeID    string
}

type GetEvidenceInput struct {
	TenantID       string
	ProjectID      string
	OwnerType      string
	OwnerID        string
	Limit          int
	IncludeSnippet bool
}

type GetLayoutInput struct {
	TenantID  string
	ProjectID string
	ViewID    string
}

type ListClustersInput struct {
	TenantID  string
	ProjectID string
	Offset    int
	Limit     int
}

type AdoptCandidateInput struct {
	TenantID   string
	ProjectID  string
	AssetID    string
	ActorID    string
	RequestID  string
	TargetKind string
}

type AdoptionResult struct {
	AssetID    string `json:"asset_id"`
	ProjectID  string `json:"project_id"`
	TargetKind string `json:"target_kind"`
	TargetID   string `json:"target_id"`
	Status     string `json:"status"`
}

type CurrentSnapshot struct {
	GraphID           string `json:"graph_id"`
	ProjectID         string `json:"project_id"`
	Version           int    `json:"version"`
	Status            string `json:"status"`
	BuildRunID        string `json:"build_run_id"`
	SourceVersionHash string `json:"source_version_hash"`
	NodeCount         int    `json:"node_count"`
	EdgeCount         int    `json:"edge_count"`
	CreatedAt         string `json:"created_at"`
	UpdatedAt         string `json:"updated_at"`
}

type GraphNodeSummary struct {
	NodeID            string         `json:"node_id"`
	GraphID           string         `json:"graph_id"`
	ProjectID         string         `json:"project_id"`
	CanonicalEntityID string         `json:"canonical_entity_id"`
	NodeType          string         `json:"node_type"`
	Title             string         `json:"title"`
	Summary           string         `json:"summary"`
	Lifecycle         string         `json:"lifecycle"`
	Importance        float64        `json:"importance"`
	ClusterID         string         `json:"cluster_id"`
	Attributes        map[string]any `json:"attributes"`
	EvidenceCount     int            `json:"evidence_count"`
	CreatedAt         string         `json:"created_at"`
	UpdatedAt         string         `json:"updated_at"`
}

type GraphEdgeSummary struct {
	EdgeID        string         `json:"edge_id"`
	GraphID       string         `json:"graph_id"`
	ProjectID     string         `json:"project_id"`
	SourceNodeID  string         `json:"source_node_id"`
	TargetNodeID  string         `json:"target_node_id"`
	EdgeType      string         `json:"edge_type"`
	Label         string         `json:"label"`
	Summary       string         `json:"summary"`
	Weight        float64        `json:"weight"`
	Lifecycle     string         `json:"lifecycle"`
	Attributes    map[string]any `json:"attributes"`
	EvidenceCount int            `json:"evidence_count"`
	CreatedAt     string         `json:"created_at"`
	UpdatedAt     string         `json:"updated_at"`
}

type GraphView struct {
	ViewID       string             `json:"view_id"`
	GraphID      string             `json:"graph_id"`
	ProjectID    string             `json:"project_id"`
	Limit        int                `json:"limit"`
	IncludeEdges bool               `json:"include_edges"`
	Nodes        []GraphNodeSummary `json:"nodes"`
	Edges        []GraphEdgeSummary `json:"edges"`
	ReadStrategy GraphReadStrategy  `json:"read_strategy"`
}

type GraphReadStrategy struct {
	Mode          string `json:"mode"`
	Offset        int    `json:"offset"`
	AppliedLimit  int    `json:"applied_limit"`
	MaxPageSize   int    `json:"max_page_size"`
	ReturnedCount int    `json:"returned_count"`
	HasMore       bool   `json:"has_more"`
	NextOffset    int    `json:"next_offset,omitempty"`
	Ordering      string `json:"ordering"`
	EdgeScope     string `json:"edge_scope,omitempty"`
}

type GraphNodeDetail struct {
	Node    GraphNodeSummary `json:"node"`
	Aliases []string         `json:"aliases"`
	Labels  []string         `json:"labels"`
}

type GraphEdgeDetail struct {
	Edge GraphEdgeSummary `json:"edge"`
}

type GraphEvidenceRecord struct {
	EvidenceID string  `json:"evidence_id"`
	GraphID    string  `json:"graph_id"`
	ProjectID  string  `json:"project_id"`
	OwnerType  string  `json:"owner_type"`
	OwnerID    string  `json:"owner_id"`
	SourceType string  `json:"source_type"`
	SourceID   string  `json:"source_id"`
	ChapterID  string  `json:"chapter_id"`
	SegmentID  string  `json:"segment_id"`
	Snippet    string  `json:"snippet,omitempty"`
	Confidence float64 `json:"confidence"`
	CreatedAt  string  `json:"created_at"`
	UpdatedAt  string  `json:"updated_at"`
}

type GraphEvidence struct {
	GraphID   string                `json:"graph_id"`
	ProjectID string                `json:"project_id"`
	OwnerType string                `json:"owner_type"`
	OwnerID   string                `json:"owner_id"`
	Limit     int                   `json:"limit"`
	Items     []GraphEvidenceRecord `json:"items"`
}

type GraphLayout struct {
	GraphID   string         `json:"graph_id"`
	ProjectID string         `json:"project_id"`
	ViewID    string         `json:"view_id"`
	Layout    map[string]any `json:"layout"`
	CreatedAt string         `json:"created_at"`
	UpdatedAt string         `json:"updated_at"`
}

type GraphClusterRecord struct {
	ClusterID  string         `json:"cluster_id"`
	GraphID    string         `json:"graph_id"`
	ProjectID  string         `json:"project_id"`
	ClusterKey string         `json:"cluster_key"`
	Title      string         `json:"title"`
	Summary    string         `json:"summary"`
	NodeCount  int            `json:"node_count"`
	Payload    map[string]any `json:"payload"`
	CreatedAt  string         `json:"created_at"`
	UpdatedAt  string         `json:"updated_at"`
}

type GraphClusters struct {
	GraphID      string               `json:"graph_id"`
	ProjectID    string               `json:"project_id"`
	Limit        int                  `json:"limit"`
	Items        []GraphClusterRecord `json:"items"`
	ReadStrategy GraphReadStrategy    `json:"read_strategy"`
}

type Reader interface {
	GetCurrentSnapshot(context.Context, GetCurrentInput) (CurrentSnapshot, error)
	GetView(context.Context, GetViewInput) (GraphView, error)
	GetNode(context.Context, GetNodeInput) (GraphNodeDetail, error)
	GetEdge(context.Context, GetEdgeInput) (GraphEdgeDetail, error)
	GetEvidence(context.Context, GetEvidenceInput) (GraphEvidence, error)
	GetLayout(context.Context, GetLayoutInput) (GraphLayout, error)
	ListClusters(context.Context, ListClustersInput) (GraphClusters, error)
}

type CandidateAdoptionStore interface {
	AdoptCandidate(context.Context, AdoptCandidateInput) (AdoptionResult, error)
}

type EvidenceAccessInput struct {
	TenantID  string
	ProjectID string
	OwnerType string
	OwnerID   string
	ActorID   string
}

type EvidenceAccessChecker interface {
	CanViewEvidenceSnippets(context.Context, EvidenceAccessInput) error
}

type DenyEvidenceSnippetAccessChecker struct{}

func NewDenyEvidenceSnippetAccessChecker() DenyEvidenceSnippetAccessChecker {
	return DenyEvidenceSnippetAccessChecker{}
}

func (DenyEvidenceSnippetAccessChecker) CanViewEvidenceSnippets(context.Context, EvidenceAccessInput) error {
	return &AppError{
		Code:    "STORY_GRAPH_EVIDENCE_ACCESS_DENIED",
		Message: "story graph evidence snippet access is not permitted",
	}
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
	return "STORY_GRAPH_ERROR"
}

type DisabledReader struct{}

func NewDisabledReader() DisabledReader {
	return DisabledReader{}
}

func (DisabledReader) GetCurrentSnapshot(context.Context, GetCurrentInput) (CurrentSnapshot, error) {
	return CurrentSnapshot{}, &AppError{
		Code:    "STORY_GRAPH_BACKEND_UNCONFIGURED",
		Message: "story graph backend is not configured",
	}
}

func (DisabledReader) GetView(context.Context, GetViewInput) (GraphView, error) {
	return GraphView{}, &AppError{
		Code:    "STORY_GRAPH_BACKEND_UNCONFIGURED",
		Message: "story graph backend is not configured",
	}
}

func (DisabledReader) GetNode(context.Context, GetNodeInput) (GraphNodeDetail, error) {
	return GraphNodeDetail{}, &AppError{
		Code:    "STORY_GRAPH_BACKEND_UNCONFIGURED",
		Message: "story graph backend is not configured",
	}
}

func (DisabledReader) GetEdge(context.Context, GetEdgeInput) (GraphEdgeDetail, error) {
	return GraphEdgeDetail{}, &AppError{
		Code:    "STORY_GRAPH_BACKEND_UNCONFIGURED",
		Message: "story graph backend is not configured",
	}
}

func (DisabledReader) GetEvidence(context.Context, GetEvidenceInput) (GraphEvidence, error) {
	return GraphEvidence{}, &AppError{
		Code:    "STORY_GRAPH_BACKEND_UNCONFIGURED",
		Message: "story graph backend is not configured",
	}
}

func (DisabledReader) GetLayout(context.Context, GetLayoutInput) (GraphLayout, error) {
	return GraphLayout{}, &AppError{
		Code:    "STORY_GRAPH_BACKEND_UNCONFIGURED",
		Message: "story graph backend is not configured",
	}
}

func (DisabledReader) ListClusters(context.Context, ListClustersInput) (GraphClusters, error) {
	return GraphClusters{}, &AppError{
		Code:    "STORY_GRAPH_BACKEND_UNCONFIGURED",
		Message: "story graph backend is not configured",
	}
}

type DisabledCandidateAdoptionStore struct{}

func NewDisabledCandidateAdoptionStore() DisabledCandidateAdoptionStore {
	return DisabledCandidateAdoptionStore{}
}

func (DisabledCandidateAdoptionStore) AdoptCandidate(context.Context, AdoptCandidateInput) (AdoptionResult, error) {
	return AdoptionResult{}, &AppError{
		Code:    "STORY_GRAPH_CANDIDATE_ADOPTION_BACKEND_UNCONFIGURED",
		Message: "story graph candidate adoption backend is not configured",
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

type SQLReaderConfig struct {
	Queryer SQLQueryer
}

type SQLReader struct {
	queryer SQLQueryer
}

type SQLCandidateAdoptionStoreConfig struct {
	Queryer SQLTenantQueryer
}

type SQLCandidateAdoptionStore struct {
	queryer SQLTenantQueryer
}

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	return &SQLReader{queryer: config.Queryer}
}

func NewSQLCandidateAdoptionStore(config SQLCandidateAdoptionStoreConfig) *SQLCandidateAdoptionStore {
	return &SQLCandidateAdoptionStore{queryer: config.Queryer}
}

func (r *SQLReader) queryRows(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := r.queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, strings.TrimSpace(tenantID), query, args...)
	}
	return r.queryer.QueryContext(ctx, query, args...)
}

func queryFailed() error {
	return &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: "story graph query failed"}
}

func candidateAdoptionFailed() error {
	return &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_FAILED", Message: "story graph candidate adoption failed"}
}

func (s *SQLCandidateAdoptionStore) AdoptCandidate(ctx context.Context, input AdoptCandidateInput) (AdoptionResult, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	assetID := strings.TrimSpace(input.AssetID)
	targetKind := strings.TrimSpace(input.TargetKind)
	if tenantID == "" || projectID == "" || assetID == "" {
		return AdoptionResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and asset_id are required"}
	}
	if targetKind != "relationship" && targetKind != "plot_thread" {
		return AdoptionResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "target_kind must be relationship or plot_thread"}
	}
	if s.queryer == nil {
		return AdoptionResult{}, &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_BACKEND_UNCONFIGURED", Message: "story graph candidate adoption backend is not configured"}
	}
	query := relationshipCandidateAdoptionSQL
	if targetKind == "plot_thread" {
		query = plotThreadCandidateAdoptionSQL
	}
	rows, err := s.queryer.QueryTenantContext(
		ctx,
		tenantID,
		query,
		tenantID,
		projectID,
		assetID,
		strings.TrimSpace(input.ActorID),
		strings.TrimSpace(input.RequestID),
		targetKind,
	)
	if err != nil {
		return AdoptionResult{}, candidateAdoptionFailed()
	}
	closeRows := true
	defer func() {
		if closeRows {
			_ = rows.Close()
		}
	}()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return AdoptionResult{}, candidateAdoptionFailed()
		}
		closeRows = false
		if err := rows.Close(); err != nil {
			return AdoptionResult{}, candidateAdoptionFailed()
		}
		return AdoptionResult{}, &AppError{Code: "NOT_FOUND", Message: "story graph candidate was not found or cannot be adopted"}
	}
	var result AdoptionResult
	if err := rows.Scan(&result.AssetID, &result.ProjectID, &result.TargetKind, &result.TargetID, &result.Status); err != nil {
		closeRows = false
		if aborter, ok := rows.(interface{ Abort() error }); ok {
			_ = aborter.Abort()
		} else {
			_ = rows.Close()
		}
		return AdoptionResult{}, candidateAdoptionFailed()
	}
	if err := rows.Err(); err != nil {
		closeRows = false
		if aborter, ok := rows.(interface{ Abort() error }); ok {
			_ = aborter.Abort()
		} else {
			_ = rows.Close()
		}
		return AdoptionResult{}, candidateAdoptionFailed()
	}
	closeRows = false
	if err := rows.Close(); err != nil {
		return AdoptionResult{}, candidateAdoptionFailed()
	}
	return result, nil
}

const relationshipCandidateAdoptionSQL = `WITH candidate AS (
	SELECT
    asset_id,
    project_id,
    asset_type,
    title,
    COALESCE(summary, '') AS summary,
    source_kind,
    source_ref,
    payload_jsonb,
    NULLIF(payload_jsonb->>'source_run_id', '') AS source_run_id,
    NULLIF(payload_jsonb->>'first_seen_segment_id', '') AS first_seen_segment_id,
    NULLIF(COALESCE(payload_jsonb->>'source_entity_name', payload_jsonb->>'source_entity', payload_jsonb->>'source'), '') AS source_entity_name,
    NULLIF(COALESCE(payload_jsonb->>'target_entity_name', payload_jsonb->>'target_entity', payload_jsonb->>'target'), '') AS target_entity_name,
    NULLIF(COALESCE(payload_jsonb->>'relationship_type', payload_jsonb->>'kind'), '') AS relationship_type,
    NULLIF(COALESCE(payload_jsonb->>'status', payload_jsonb->>'thread_status'), '') AS thread_status,
    NULLIF(COALESCE(payload_jsonb->>'thread_type', payload_jsonb->>'proposal_type'), '') AS thread_type,
    NULLIF(payload_jsonb->>'confidence', '') AS confidence
  FROM assets
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND asset_id::text = $3
    AND lifecycle = 'candidate'
    AND source_kind = 'graph_bond_generation'
    AND asset_type = 'graph_bond'
  FOR UPDATE OF assets
),
source_run AS (
  SELECT workflow_runs.run_id
  FROM workflow_runs, candidate
  WHERE workflow_runs.tenant_id::text = $1
    AND workflow_runs.project_id::text = $2
    AND workflow_runs.run_id::text = candidate.source_run_id
),
relationship_target AS (
  INSERT INTO relationships (
    tenant_id, project_id, source_entity_name, target_entity_name,
    relationship_type, summary, source_run_id, first_seen_segment_id,
    evidence_text, metadata_jsonb
  )
  SELECT
    $1::uuid,
    candidate.project_id,
    candidate.source_entity_name,
    candidate.target_entity_name,
    candidate.relationship_type,
    NULLIF(candidate.summary, ''),
    source_run.run_id,
    first_segment.segment_id,
    NULL,
    jsonb_strip_nulls(jsonb_build_object(
      'source_asset_id', candidate.asset_id::text,
      'source_kind', candidate.source_kind,
      'source_ref', candidate.source_ref,
      'proposal_type', 'graph_bond',
      'confidence', candidate.confidence
    ))
  FROM candidate
  JOIN source_run ON true
  LEFT JOIN text_segments AS first_segment
    ON first_segment.tenant_id::text = $1
   AND first_segment.project_id::text = $2
   AND first_segment.segment_id::text = candidate.first_seen_segment_id
  WHERE $6 = 'relationship'
    AND candidate.source_entity_name IS NOT NULL
    AND candidate.target_entity_name IS NOT NULL
    AND candidate.relationship_type IS NOT NULL
  ON CONFLICT (tenant_id, project_id, source_entity_name, target_entity_name, relationship_type)
  DO UPDATE SET
    summary = COALESCE(EXCLUDED.summary, relationships.summary),
    metadata_jsonb = relationships.metadata_jsonb || EXCLUDED.metadata_jsonb,
    updated_at = now()
  RETURNING relationship_id::text AS target_id
),
target AS (
  SELECT target_id FROM relationship_target
),
adopted AS (
  UPDATE assets
  SET lifecycle = 'canon',
      updated_at = now()
  FROM candidate, target
  WHERE assets.tenant_id::text = $1
    AND assets.project_id::text = $2
    AND assets.asset_id = candidate.asset_id
  RETURNING assets.asset_id::text AS asset_id, assets.project_id::text AS project_id, target.target_id
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $4 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $4::uuid
      ELSE NULL
    END,
    'story_graph.candidate_adopt',
    $6::text,
    target_id::uuid,
    project_id::uuid,
    NULL,
    $5,
    jsonb_build_object(
      'asset_id', asset_id,
      'target_kind', $6::text,
      'target_id', target_id,
      'actor_id', $4
    )
  FROM adopted
  RETURNING audit_id
)
SELECT asset_id, project_id, $6::text, target_id, 'adopted'
FROM adopted`

const plotThreadCandidateAdoptionSQL = `WITH candidate AS (
  SELECT
    asset_id,
    project_id,
    asset_type,
    title,
    COALESCE(summary, '') AS summary,
    source_kind,
    source_ref,
    payload_jsonb,
    NULLIF(payload_jsonb->>'source_run_id', '') AS source_run_id,
    NULLIF(payload_jsonb->>'first_seen_segment_id', '') AS first_seen_segment_id,
    NULLIF(COALESCE(payload_jsonb->>'status', payload_jsonb->>'thread_status'), '') AS thread_status,
    NULLIF(COALESCE(payload_jsonb->>'thread_type', payload_jsonb->>'proposal_type'), '') AS thread_type,
    NULLIF(payload_jsonb->>'confidence', '') AS confidence
  FROM assets
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND asset_id::text = $3
    AND lifecycle = 'candidate'
    AND source_kind = 'graph_bond_generation'
    AND asset_type = 'plot_thread'
  FOR UPDATE OF assets
),
source_run AS (
  SELECT workflow_runs.run_id
  FROM workflow_runs, candidate
  WHERE workflow_runs.tenant_id::text = $1
    AND workflow_runs.project_id::text = $2
    AND workflow_runs.run_id::text = candidate.source_run_id
),
plot_thread_target AS (
  INSERT INTO plot_threads (
    tenant_id, project_id, source_run_id, title, status,
    summary, first_seen_segment_id, evidence_text, metadata_jsonb
  )
  SELECT
    $1::uuid,
    candidate.project_id,
    source_run.run_id,
    candidate.title,
    CASE candidate.thread_status
      WHEN 'open' THEN 'open'
      WHEN 'resolved' THEN 'resolved'
      WHEN 'abandoned' THEN 'abandoned'
      ELSE 'open'
    END,
    NULLIF(candidate.summary, ''),
    first_segment.segment_id,
    NULL,
    jsonb_strip_nulls(jsonb_build_object(
      'source_asset_id', candidate.asset_id::text,
      'source_kind', candidate.source_kind,
      'source_ref', candidate.source_ref,
      'proposal_type', 'plot_thread',
      'thread_type', candidate.thread_type,
      'confidence', candidate.confidence
    ))
  FROM candidate
  JOIN source_run ON true
  LEFT JOIN text_segments AS first_segment
    ON first_segment.tenant_id::text = $1
   AND first_segment.project_id::text = $2
   AND first_segment.segment_id::text = candidate.first_seen_segment_id
  ON CONFLICT (tenant_id, project_id, title)
  DO UPDATE SET
    status = COALESCE(EXCLUDED.status, plot_threads.status),
    summary = COALESCE(EXCLUDED.summary, plot_threads.summary),
    metadata_jsonb = plot_threads.metadata_jsonb || EXCLUDED.metadata_jsonb,
    updated_at = now()
  RETURNING thread_id::text AS target_id
),
target AS (
  SELECT target_id FROM plot_thread_target
),
adopted AS (
  UPDATE assets
  SET lifecycle = 'canon',
      updated_at = now()
  FROM candidate, target
  WHERE assets.tenant_id::text = $1
    AND assets.project_id::text = $2
    AND assets.asset_id = candidate.asset_id
  RETURNING assets.asset_id::text AS asset_id, assets.project_id::text AS project_id, target.target_id
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $4 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $4::uuid
      ELSE NULL
    END,
    'story_graph.candidate_adopt',
    $6::text,
    target_id::uuid,
    project_id::uuid,
    NULL,
    $5,
    jsonb_build_object(
      'asset_id', asset_id,
      'target_kind', $6::text,
      'target_id', target_id,
      'actor_id', $4
    )
  FROM adopted
  RETURNING audit_id
)
SELECT asset_id, project_id, $6::text, target_id, 'adopted'
FROM adopted`

func (r *SQLReader) GetCurrentSnapshot(ctx context.Context, input GetCurrentInput) (CurrentSnapshot, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return CurrentSnapshot{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return CurrentSnapshot{}, &AppError{Code: "STORY_GRAPH_BACKEND_UNCONFIGURED", Message: "story graph backend is not configured"}
	}
	query := `SELECT
  graph_id::text,
  project_id::text,
  version,
  status,
  COALESCE(build_run_id::text, ''),
  COALESCE(source_version_hash, ''),
  node_count,
  edge_count,
  created_at::text,
  updated_at::text
FROM story_graph_snapshots
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND status IN ('ready', 'building', 'failed')
ORDER BY version DESC, created_at DESC, graph_id ASC
LIMIT 1`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID)
	if err != nil {
		return CurrentSnapshot{}, queryFailed()
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return CurrentSnapshot{}, queryFailed()
		}
		return CurrentSnapshot{}, &AppError{Code: "NOT_FOUND", Message: "story graph snapshot not found"}
	}
	var snapshot CurrentSnapshot
	if err := rows.Scan(
		&snapshot.GraphID,
		&snapshot.ProjectID,
		&snapshot.Version,
		&snapshot.Status,
		&snapshot.BuildRunID,
		&snapshot.SourceVersionHash,
		&snapshot.NodeCount,
		&snapshot.EdgeCount,
		&snapshot.CreatedAt,
		&snapshot.UpdatedAt,
	); err != nil {
		return CurrentSnapshot{}, queryFailed()
	}
	return snapshot, nil
}

func (r *SQLReader) GetView(ctx context.Context, input GetViewInput) (GraphView, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	viewID := strings.TrimSpace(input.ViewID)
	if tenantID == "" || projectID == "" || viewID == "" {
		return GraphView{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and view_id are required"}
	}
	if r.queryer == nil {
		return GraphView{}, &AppError{Code: "STORY_GRAPH_BACKEND_UNCONFIGURED", Message: "story graph backend is not configured"}
	}
	current, err := r.GetCurrentSnapshot(ctx, GetCurrentInput{TenantID: tenantID, ProjectID: projectID})
	if err != nil {
		return GraphView{}, err
	}
	limit := normalizeLimit(input.Limit)
	offset := normalizeOffset(input.Offset)
	nodes, hasMore, err := r.listNodes(ctx, tenantID, projectID, current.GraphID, input.Types, offset, limit)
	if err != nil {
		return GraphView{}, err
	}
	edges := []GraphEdgeSummary{}
	if input.IncludeEdges && len(nodes) > 0 {
		edges, err = r.listEdgesForNodes(ctx, tenantID, projectID, current.GraphID, nodes)
		if err != nil {
			return GraphView{}, err
		}
	}
	return GraphView{
		ViewID:       viewID,
		GraphID:      current.GraphID,
		ProjectID:    projectID,
		Limit:        limit,
		IncludeEdges: input.IncludeEdges,
		Nodes:        nodes,
		Edges:        edges,
		ReadStrategy: graphViewReadStrategy(offset, limit, len(nodes), hasMore, input.IncludeEdges),
	}, nil
}

func (r *SQLReader) GetNode(ctx context.Context, input GetNodeInput) (GraphNodeDetail, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	nodeID := strings.TrimSpace(input.NodeID)
	if tenantID == "" || projectID == "" || nodeID == "" {
		return GraphNodeDetail{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and node_id are required"}
	}
	if r.queryer == nil {
		return GraphNodeDetail{}, &AppError{Code: "STORY_GRAPH_BACKEND_UNCONFIGURED", Message: "story graph backend is not configured"}
	}
	current, err := r.GetCurrentSnapshot(ctx, GetCurrentInput{TenantID: tenantID, ProjectID: projectID})
	if err != nil {
		return GraphNodeDetail{}, err
	}
	node, err := r.getNodeSummary(ctx, tenantID, projectID, current.GraphID, nodeID)
	if err != nil {
		return GraphNodeDetail{}, err
	}
	aliases, err := r.listNodeStrings(ctx, "story_graph_node_aliases", "alias", tenantID, projectID, node.GraphID, nodeID)
	if err != nil {
		return GraphNodeDetail{}, err
	}
	labels, err := r.listNodeStrings(ctx, "story_graph_node_labels", "label", tenantID, projectID, node.GraphID, nodeID)
	if err != nil {
		return GraphNodeDetail{}, err
	}
	return GraphNodeDetail{Node: node, Aliases: aliases, Labels: labels}, nil
}

func (r *SQLReader) GetEdge(ctx context.Context, input GetEdgeInput) (GraphEdgeDetail, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	edgeID := strings.TrimSpace(input.EdgeID)
	if tenantID == "" || projectID == "" || edgeID == "" {
		return GraphEdgeDetail{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and edge_id are required"}
	}
	if r.queryer == nil {
		return GraphEdgeDetail{}, &AppError{Code: "STORY_GRAPH_BACKEND_UNCONFIGURED", Message: "story graph backend is not configured"}
	}
	current, err := r.GetCurrentSnapshot(ctx, GetCurrentInput{TenantID: tenantID, ProjectID: projectID})
	if err != nil {
		return GraphEdgeDetail{}, err
	}
	edge, err := r.getEdgeSummary(ctx, tenantID, projectID, current.GraphID, edgeID)
	if err != nil {
		return GraphEdgeDetail{}, err
	}
	return GraphEdgeDetail{Edge: edge}, nil
}

func (r *SQLReader) GetEvidence(ctx context.Context, input GetEvidenceInput) (GraphEvidence, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	ownerType := normalizeOwnerType(input.OwnerType)
	ownerID := strings.TrimSpace(input.OwnerID)
	if tenantID == "" || projectID == "" || ownerType == "" || ownerID == "" {
		return GraphEvidence{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, owner_type, and owner_id are required"}
	}
	if r.queryer == nil {
		return GraphEvidence{}, &AppError{Code: "STORY_GRAPH_BACKEND_UNCONFIGURED", Message: "story graph backend is not configured"}
	}
	current, err := r.GetCurrentSnapshot(ctx, GetCurrentInput{TenantID: tenantID, ProjectID: projectID})
	if err != nil {
		return GraphEvidence{}, err
	}
	limit := normalizeLimit(input.Limit)
	query := `SELECT
  evidence_id::text,
  graph_id::text,
  project_id::text,
  owner_type,
  owner_id::text,
  source_type,
  source_id,
  COALESCE(chapter_id::text, ''),
  COALESCE(segment_id::text, ''),
  COALESCE(confidence::float8, 0),
  created_at::text,
  updated_at::text
FROM story_graph_evidence
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
  AND owner_type = $4
  AND owner_id::text = $5
ORDER BY confidence DESC NULLS LAST, created_at DESC, evidence_id ASC
LIMIT $6`
	if input.IncludeSnippet {
		query = `SELECT
  evidence_id::text,
  graph_id::text,
  project_id::text,
  owner_type,
  owner_id::text,
  source_type,
  source_id,
  COALESCE(chapter_id::text, ''),
  COALESCE(segment_id::text, ''),
  COALESCE(snippet, ''),
  COALESCE(confidence::float8, 0),
  created_at::text,
  updated_at::text
FROM story_graph_evidence
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
  AND owner_type = $4
  AND owner_id::text = $5
ORDER BY confidence DESC NULLS LAST, created_at DESC, evidence_id ASC
LIMIT $6`
	}
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, current.GraphID, ownerType, ownerID, limit)
	if err != nil {
		return GraphEvidence{}, queryFailed()
	}
	defer rows.Close()
	items := []GraphEvidenceRecord{}
	for rows.Next() {
		var item GraphEvidenceRecord
		if input.IncludeSnippet {
			if err := rows.Scan(
				&item.EvidenceID,
				&item.GraphID,
				&item.ProjectID,
				&item.OwnerType,
				&item.OwnerID,
				&item.SourceType,
				&item.SourceID,
				&item.ChapterID,
				&item.SegmentID,
				&item.Snippet,
				&item.Confidence,
				&item.CreatedAt,
				&item.UpdatedAt,
			); err != nil {
				return GraphEvidence{}, queryFailed()
			}
		} else {
			if err := rows.Scan(
				&item.EvidenceID,
				&item.GraphID,
				&item.ProjectID,
				&item.OwnerType,
				&item.OwnerID,
				&item.SourceType,
				&item.SourceID,
				&item.ChapterID,
				&item.SegmentID,
				&item.Confidence,
				&item.CreatedAt,
				&item.UpdatedAt,
			); err != nil {
				return GraphEvidence{}, queryFailed()
			}
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return GraphEvidence{}, queryFailed()
	}
	return GraphEvidence{GraphID: current.GraphID, ProjectID: projectID, OwnerType: ownerType, OwnerID: ownerID, Limit: limit, Items: items}, nil
}

func (r *SQLReader) GetLayout(ctx context.Context, input GetLayoutInput) (GraphLayout, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	viewID := strings.TrimSpace(input.ViewID)
	if tenantID == "" || projectID == "" || viewID == "" {
		return GraphLayout{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and view_id are required"}
	}
	if r.queryer == nil {
		return GraphLayout{}, &AppError{Code: "STORY_GRAPH_BACKEND_UNCONFIGURED", Message: "story graph backend is not configured"}
	}
	current, err := r.GetCurrentSnapshot(ctx, GetCurrentInput{TenantID: tenantID, ProjectID: projectID})
	if err != nil {
		return GraphLayout{}, err
	}
	query := `SELECT
  graph_id::text,
  project_id::text,
  view_id,
  layout_jsonb::text,
  created_at::text,
  updated_at::text
FROM story_graph_layouts
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
  AND view_id = $4
LIMIT 1`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, current.GraphID, viewID)
	if err != nil {
		return GraphLayout{}, queryFailed()
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return GraphLayout{}, queryFailed()
		}
		return GraphLayout{}, &AppError{Code: "NOT_FOUND", Message: "story graph layout not found"}
	}
	var layout GraphLayout
	var layoutText string
	if err := rows.Scan(&layout.GraphID, &layout.ProjectID, &layout.ViewID, &layoutText, &layout.CreatedAt, &layout.UpdatedAt); err != nil {
		return GraphLayout{}, queryFailed()
	}
	layout.Layout = parseSanitizedAttributes(layoutText)
	return layout, nil
}

func (r *SQLReader) ListClusters(ctx context.Context, input ListClustersInput) (GraphClusters, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return GraphClusters{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return GraphClusters{}, &AppError{Code: "STORY_GRAPH_BACKEND_UNCONFIGURED", Message: "story graph backend is not configured"}
	}
	current, err := r.GetCurrentSnapshot(ctx, GetCurrentInput{TenantID: tenantID, ProjectID: projectID})
	if err != nil {
		return GraphClusters{}, err
	}
	limit := normalizeClusterLimit(input.Limit)
	offset := normalizeOffset(input.Offset)
	query := `SELECT
  cluster_id::text,
  graph_id::text,
  project_id::text,
  cluster_key,
  title,
  COALESCE(summary, ''),
  node_count,
  payload_jsonb::text,
  created_at::text,
  updated_at::text
FROM story_graph_clusters
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
ORDER BY node_count DESC, title ASC, cluster_key ASC, cluster_id ASC
LIMIT $4 OFFSET $5`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, current.GraphID, limit+1, offset)
	if err != nil {
		return GraphClusters{}, queryFailed()
	}
	defer rows.Close()
	items := []GraphClusterRecord{}
	for rows.Next() {
		var item GraphClusterRecord
		var payloadText string
		if err := rows.Scan(
			&item.ClusterID,
			&item.GraphID,
			&item.ProjectID,
			&item.ClusterKey,
			&item.Title,
			&item.Summary,
			&item.NodeCount,
			&payloadText,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return GraphClusters{}, queryFailed()
		}
		item.Payload = parseSanitizedAttributes(payloadText)
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return GraphClusters{}, queryFailed()
	}
	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	return GraphClusters{
		GraphID:      current.GraphID,
		ProjectID:    projectID,
		Limit:        limit,
		Items:        items,
		ReadStrategy: clusterReadStrategy(offset, limit, len(items), hasMore),
	}, nil
}

func normalizeLimit(limit int) int {
	if limit <= 0 {
		return defaultGraphPageSize
	}
	if limit > maximumGraphPageSize {
		return maximumGraphPageSize
	}
	return limit
}

func normalizeClusterLimit(limit int) int {
	if limit <= 0 {
		return defaultClusterPageSize
	}
	if limit > maximumClusterPageSize {
		return maximumClusterPageSize
	}
	return limit
}

func normalizeOffset(offset int) int {
	if offset < 0 {
		return 0
	}
	return offset
}

func graphViewReadStrategy(offset int, limit int, returned int, hasMore bool, includeEdges bool) GraphReadStrategy {
	strategy := GraphReadStrategy{
		Mode:          "stable_ranked_page",
		Offset:        offset,
		AppliedLimit:  limit,
		MaxPageSize:   maximumGraphPageSize,
		ReturnedCount: returned,
		HasMore:       hasMore,
		Ordering:      "importance_desc,title_asc,node_id_asc",
	}
	if hasMore {
		strategy.Mode = "stable_ranked_page_with_cluster_summaries"
		strategy.NextOffset = offset + returned
	}
	if includeEdges {
		strategy.EdgeScope = "induced_returned_nodes"
	}
	return strategy
}

func clusterReadStrategy(offset int, limit int, returned int, hasMore bool) GraphReadStrategy {
	strategy := GraphReadStrategy{
		Mode:          "stable_cluster_page",
		Offset:        offset,
		AppliedLimit:  limit,
		MaxPageSize:   maximumClusterPageSize,
		ReturnedCount: returned,
		HasMore:       hasMore,
		Ordering:      "node_count_desc,title_asc,cluster_key_asc,cluster_id_asc",
	}
	if hasMore {
		strategy.NextOffset = offset + returned
	}
	return strategy
}

func normalizeOwnerType(ownerType string) string {
	switch strings.ToLower(strings.TrimSpace(ownerType)) {
	case "node", "nodes":
		return "node"
	case "edge", "edges":
		return "edge"
	default:
		return ""
	}
}

func (r *SQLReader) listNodes(ctx context.Context, tenantID string, projectID string, graphID string, types []string, offset int, limit int) ([]GraphNodeSummary, bool, error) {
	query := `SELECT
  node_id::text,
  graph_id::text,
  project_id::text,
  COALESCE(canonical_entity_id::text, ''),
  node_type,
  title,
  COALESCE(summary, ''),
  lifecycle,
  importance::float8,
  COALESCE(cluster_id::text, ''),
  attributes_jsonb::text,
  evidence_count,
  created_at::text,
  updated_at::text
FROM story_graph_nodes
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
  AND ($4 = '' OR node_type = ANY(string_to_array($4, ',')))
ORDER BY importance DESC, title ASC, node_id ASC
LIMIT $5 OFFSET $6`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, graphID, strings.Join(cleanStrings(types), ","), limit+1, offset)
	if err != nil {
		return nil, false, queryFailed()
	}
	defer rows.Close()
	nodes := []GraphNodeSummary{}
	for rows.Next() {
		node, err := scanNodeSummary(rows)
		if err != nil {
			return nil, false, err
		}
		nodes = append(nodes, node)
	}
	if err := rows.Err(); err != nil {
		return nil, false, queryFailed()
	}
	hasMore := len(nodes) > limit
	if hasMore {
		nodes = nodes[:limit]
	}
	return nodes, hasMore, nil
}

func (r *SQLReader) listEdgesForNodes(ctx context.Context, tenantID string, projectID string, graphID string, nodes []GraphNodeSummary) ([]GraphEdgeSummary, error) {
	nodeIDs := make([]string, 0, len(nodes))
	for _, node := range nodes {
		nodeIDs = append(nodeIDs, node.NodeID)
	}
	query := `SELECT
  edge_id::text,
  graph_id::text,
  project_id::text,
  source_node_id::text,
  target_node_id::text,
  edge_type,
  COALESCE(label, ''),
  COALESCE(summary, ''),
  weight::float8,
  lifecycle,
  attributes_jsonb::text,
  evidence_count,
  created_at::text,
  updated_at::text
FROM story_graph_edges
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
  AND source_node_id::text = ANY(string_to_array($4, ','))
  AND target_node_id::text = ANY(string_to_array($4, ','))
ORDER BY weight DESC, edge_type ASC, label ASC, source_node_id ASC, target_node_id ASC, edge_id ASC`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, graphID, strings.Join(nodeIDs, ","))
	if err != nil {
		return nil, queryFailed()
	}
	defer rows.Close()
	edges := []GraphEdgeSummary{}
	for rows.Next() {
		edge, err := scanEdgeSummary(rows)
		if err != nil {
			return nil, err
		}
		edges = append(edges, edge)
	}
	if err := rows.Err(); err != nil {
		return nil, queryFailed()
	}
	return edges, nil
}

func (r *SQLReader) getNodeSummary(ctx context.Context, tenantID string, projectID string, graphID string, nodeID string) (GraphNodeSummary, error) {
	query := `SELECT
  node_id::text,
  graph_id::text,
  project_id::text,
  COALESCE(canonical_entity_id::text, ''),
  node_type,
  title,
  COALESCE(summary, ''),
  lifecycle,
  importance::float8,
  COALESCE(cluster_id::text, ''),
  attributes_jsonb::text,
  evidence_count,
  created_at::text,
  updated_at::text
FROM story_graph_nodes
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
  AND node_id::text = $4
LIMIT 1`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, graphID, nodeID)
	if err != nil {
		return GraphNodeSummary{}, queryFailed()
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return GraphNodeSummary{}, queryFailed()
		}
		return GraphNodeSummary{}, &AppError{Code: "NOT_FOUND", Message: "story graph node not found"}
	}
	return scanNodeSummary(rows)
}

func (r *SQLReader) getEdgeSummary(ctx context.Context, tenantID string, projectID string, graphID string, edgeID string) (GraphEdgeSummary, error) {
	query := `SELECT
  edge_id::text,
  graph_id::text,
  project_id::text,
  source_node_id::text,
  target_node_id::text,
  edge_type,
  COALESCE(label, ''),
  COALESCE(summary, ''),
  weight::float8,
  lifecycle,
  attributes_jsonb::text,
  evidence_count,
  created_at::text,
  updated_at::text
FROM story_graph_edges
WHERE tenant_id::text = $1
  AND project_id::text = $2
  AND graph_id::text = $3
  AND edge_id::text = $4
LIMIT 1`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, graphID, edgeID)
	if err != nil {
		return GraphEdgeSummary{}, queryFailed()
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return GraphEdgeSummary{}, queryFailed()
		}
		return GraphEdgeSummary{}, &AppError{Code: "NOT_FOUND", Message: "story graph edge not found"}
	}
	return scanEdgeSummary(rows)
}

func (r *SQLReader) listNodeStrings(ctx context.Context, tableName string, columnName string, tenantID string, projectID string, graphID string, nodeID string) ([]string, error) {
	query := "SELECT " + columnName + " FROM " + tableName + " WHERE tenant_id::text = $1 AND project_id::text = $2 AND graph_id::text = $3 AND node_id::text = $4 ORDER BY " + columnName + " ASC"
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID, graphID, nodeID)
	if err != nil {
		return nil, queryFailed()
	}
	defer rows.Close()
	values := []string{}
	for rows.Next() {
		var value string
		if err := rows.Scan(&value); err != nil {
			return nil, queryFailed()
		}
		values = append(values, value)
	}
	if err := rows.Err(); err != nil {
		return nil, queryFailed()
	}
	return values, nil
}

func scanNodeSummary(rows SQLRows) (GraphNodeSummary, error) {
	var node GraphNodeSummary
	var attributesText string
	if err := rows.Scan(
		&node.NodeID,
		&node.GraphID,
		&node.ProjectID,
		&node.CanonicalEntityID,
		&node.NodeType,
		&node.Title,
		&node.Summary,
		&node.Lifecycle,
		&node.Importance,
		&node.ClusterID,
		&attributesText,
		&node.EvidenceCount,
		&node.CreatedAt,
		&node.UpdatedAt,
	); err != nil {
		return GraphNodeSummary{}, queryFailed()
	}
	node.Attributes = parseSanitizedAttributes(attributesText)
	return node, nil
}

func scanEdgeSummary(rows SQLRows) (GraphEdgeSummary, error) {
	var edge GraphEdgeSummary
	var attributesText string
	if err := rows.Scan(
		&edge.EdgeID,
		&edge.GraphID,
		&edge.ProjectID,
		&edge.SourceNodeID,
		&edge.TargetNodeID,
		&edge.EdgeType,
		&edge.Label,
		&edge.Summary,
		&edge.Weight,
		&edge.Lifecycle,
		&attributesText,
		&edge.EvidenceCount,
		&edge.CreatedAt,
		&edge.UpdatedAt,
	); err != nil {
		return GraphEdgeSummary{}, queryFailed()
	}
	edge.Attributes = parseSanitizedAttributes(attributesText)
	return edge, nil
}

func parseSanitizedAttributes(raw string) map[string]any {
	if strings.TrimSpace(raw) == "" {
		return map[string]any{}
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return map[string]any{}
	}
	return sanitizeGraphMap(decoded)
}

func sanitizeGraphMap(input map[string]any) map[string]any {
	output := map[string]any{}
	for key, value := range input {
		normalized := strings.ToLower(strings.TrimSpace(key))
		if normalized == "" || sensitiveGraphKey(normalized) {
			continue
		}
		output[key] = sanitizeGraphValue(value)
	}
	return output
}

func sanitizeGraphValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeGraphMap(typed)
	case []any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, sanitizeGraphValue(item))
		}
		return items
	default:
		return value
	}
}

func sensitiveGraphKey(key string) bool {
	switch key {
	case "api_key", "body", "content", "credential_ref", "draft", "encrypted_api_key", "manuscript", "prompt", "raw_content", "raw_text", "response", "seed_analysis_body", "snippet", "source_text", "text":
		return true
	default:
		return false
	}
}

func cleanStrings(values []string) []string {
	cleaned := []string{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			cleaned = append(cleaned, value)
		}
	}
	return cleaned
}
