package storygraph

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
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
	NodeID        string         `json:"node_id"`
	GraphID       string         `json:"graph_id"`
	ProjectID     string         `json:"project_id"`
	NodeType      string         `json:"node_type"`
	Title         string         `json:"title"`
	Summary       string         `json:"summary"`
	Lifecycle     string         `json:"lifecycle"`
	Importance    float64        `json:"importance"`
	ClusterID     string         `json:"cluster_id"`
	Attributes    map[string]any `json:"attributes"`
	EvidenceCount int            `json:"evidence_count"`
	CreatedAt     string         `json:"created_at"`
	UpdatedAt     string         `json:"updated_at"`
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
	GraphID   string               `json:"graph_id"`
	ProjectID string               `json:"project_id"`
	Limit     int                  `json:"limit"`
	Items     []GraphClusterRecord `json:"items"`
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
		return AdoptionResult{}, &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_FAILED", Message: err.Error()}
	}
	closeRows := true
	defer func() {
		if closeRows {
			_ = rows.Close()
		}
	}()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return AdoptionResult{}, &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_FAILED", Message: err.Error()}
		}
		closeRows = false
		if err := rows.Close(); err != nil {
			return AdoptionResult{}, &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_FAILED", Message: err.Error()}
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
		return AdoptionResult{}, &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		closeRows = false
		if aborter, ok := rows.(interface{ Abort() error }); ok {
			_ = aborter.Abort()
		} else {
			_ = rows.Close()
		}
		return AdoptionResult{}, &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_FAILED", Message: err.Error()}
	}
	closeRows = false
	if err := rows.Close(); err != nil {
		return AdoptionResult{}, &AppError{Code: "STORY_GRAPH_CANDIDATE_ADOPTION_FAILED", Message: err.Error()}
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
),
relationship_target AS (
  INSERT INTO relationships (
    tenant_id, project_id, source_entity_name, target_entity_name,
    relationship_type, summary, source_run_id, first_seen_segment_id,
    evidence_text, metadata_jsonb
  )
  SELECT
    $1::uuid,
    project_id,
    source_entity_name,
    target_entity_name,
    relationship_type,
    NULLIF(summary, ''),
    source_run_id::uuid,
    CASE WHEN first_seen_segment_id IS NULL THEN NULL ELSE first_seen_segment_id::uuid END,
    NULL,
    jsonb_strip_nulls(jsonb_build_object(
      'source_asset_id', asset_id::text,
      'source_kind', source_kind,
      'source_ref', source_ref,
      'proposal_type', 'graph_bond',
      'confidence', confidence
    ))
  FROM candidate
  WHERE $6 = 'relationship'
    AND source_entity_name IS NOT NULL
    AND target_entity_name IS NOT NULL
    AND relationship_type IS NOT NULL
    AND source_run_id IS NOT NULL
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
    $6,
    target_id::uuid,
    project_id::uuid,
    NULL,
    $5,
    jsonb_build_object(
      'asset_id', asset_id,
      'target_kind', $6,
      'target_id', target_id,
      'actor_id', $4
    )
  FROM adopted
  RETURNING audit_id
)
SELECT asset_id, project_id, $6, target_id, 'adopted'
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
),
plot_thread_target AS (
  INSERT INTO plot_threads (
    tenant_id, project_id, source_run_id, title, status,
    summary, first_seen_segment_id, evidence_text, metadata_jsonb
  )
  SELECT
    $1::uuid,
    project_id,
    source_run_id::uuid,
    title,
    COALESCE(thread_status, 'open'),
    NULLIF(summary, ''),
    CASE WHEN first_seen_segment_id IS NULL THEN NULL ELSE first_seen_segment_id::uuid END,
    NULL,
    jsonb_strip_nulls(jsonb_build_object(
      'source_asset_id', asset_id::text,
      'source_kind', source_kind,
      'source_ref', source_ref,
      'proposal_type', 'plot_thread',
      'thread_type', thread_type,
      'confidence', confidence
    ))
  FROM candidate
  WHERE source_run_id IS NOT NULL
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
    $6,
    target_id::uuid,
    project_id::uuid,
    NULL,
    $5,
    jsonb_build_object(
      'asset_id', asset_id,
      'target_kind', $6,
      'target_id', target_id,
      'actor_id', $4
    )
  FROM adopted
  RETURNING audit_id
)
SELECT asset_id, project_id, $6, target_id, 'adopted'
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
ORDER BY version DESC, created_at DESC
LIMIT 1`
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID)
	if err != nil {
		return CurrentSnapshot{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return CurrentSnapshot{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
		return CurrentSnapshot{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
	nodes, err := r.listNodes(ctx, tenantID, projectID, current.GraphID, input.Types, limit)
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
ORDER BY confidence DESC NULLS LAST, created_at DESC
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
ORDER BY confidence DESC NULLS LAST, created_at DESC
LIMIT $6`
	}
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, current.GraphID, ownerType, ownerID, limit)
	if err != nil {
		return GraphEvidence{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
				return GraphEvidence{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
				return GraphEvidence{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
			}
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return GraphEvidence{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, current.GraphID, viewID)
	if err != nil {
		return GraphLayout{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return GraphLayout{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
		}
		return GraphLayout{}, &AppError{Code: "NOT_FOUND", Message: "story graph layout not found"}
	}
	var layout GraphLayout
	var layoutText string
	if err := rows.Scan(&layout.GraphID, &layout.ProjectID, &layout.ViewID, &layoutText, &layout.CreatedAt, &layout.UpdatedAt); err != nil {
		return GraphLayout{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
ORDER BY node_count DESC, title ASC
LIMIT $4`
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, current.GraphID, limit)
	if err != nil {
		return GraphClusters{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
			return GraphClusters{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
		}
		item.Payload = parseSanitizedAttributes(payloadText)
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return GraphClusters{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	return GraphClusters{GraphID: current.GraphID, ProjectID: projectID, Limit: limit, Items: items}, nil
}

func normalizeLimit(limit int) int {
	if limit <= 0 {
		return 300
	}
	if limit > 1000 {
		return 1000
	}
	return limit
}

func normalizeClusterLimit(limit int) int {
	if limit <= 0 {
		return 100
	}
	if limit > 500 {
		return 500
	}
	return limit
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

func (r *SQLReader) listNodes(ctx context.Context, tenantID string, projectID string, graphID string, types []string, limit int) ([]GraphNodeSummary, error) {
	query := `SELECT
  node_id::text,
  graph_id::text,
  project_id::text,
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
ORDER BY importance DESC, title ASC
LIMIT $5`
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, graphID, strings.Join(cleanStrings(types), ","), limit)
	if err != nil {
		return nil, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	nodes := []GraphNodeSummary{}
	for rows.Next() {
		node, err := scanNodeSummary(rows)
		if err != nil {
			return nil, err
		}
		nodes = append(nodes, node)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	return nodes, nil
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
ORDER BY weight DESC, edge_type ASC, label ASC`
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, graphID, strings.Join(nodeIDs, ","))
	if err != nil {
		return nil, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
		return nil, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	return edges, nil
}

func (r *SQLReader) getNodeSummary(ctx context.Context, tenantID string, projectID string, graphID string, nodeID string) (GraphNodeSummary, error) {
	query := `SELECT
  node_id::text,
  graph_id::text,
  project_id::text,
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
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, graphID, nodeID)
	if err != nil {
		return GraphNodeSummary{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return GraphNodeSummary{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, graphID, edgeID)
	if err != nil {
		return GraphEdgeSummary{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return GraphEdgeSummary{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
		}
		return GraphEdgeSummary{}, &AppError{Code: "NOT_FOUND", Message: "story graph edge not found"}
	}
	return scanEdgeSummary(rows)
}

func (r *SQLReader) listNodeStrings(ctx context.Context, tableName string, columnName string, tenantID string, projectID string, graphID string, nodeID string) ([]string, error) {
	query := "SELECT " + columnName + " FROM " + tableName + " WHERE tenant_id::text = $1 AND project_id::text = $2 AND graph_id::text = $3 AND node_id::text = $4 ORDER BY " + columnName + " ASC"
	rows, err := r.queryer.QueryContext(ctx, query, tenantID, projectID, graphID, nodeID)
	if err != nil {
		return nil, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	values := []string{}
	for rows.Next() {
		var value string
		if err := rows.Scan(&value); err != nil {
			return nil, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
		}
		values = append(values, value)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
		return GraphNodeSummary{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
		return GraphEdgeSummary{}, &AppError{Code: "STORY_GRAPH_QUERY_FAILED", Message: err.Error()}
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
