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

type SQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type SQLQueryer interface {
	QueryContext(context.Context, string, ...any) (SQLRows, error)
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

type SQLReaderConfig struct {
	Queryer SQLQueryer
}

type SQLReader struct {
	queryer SQLQueryer
}

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	return &SQLReader{queryer: config.Queryer}
}

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
