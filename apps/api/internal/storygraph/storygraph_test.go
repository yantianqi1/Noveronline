package storygraph

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLReaderGetsNodeFromCurrentGraphOnly(t *testing.T) {
	queryer := &recordingStoryGraphQueryer{
		snapshotRows: [][]any{currentSnapshotRow("graph-current")},
		nodeRows: [][]any{{
			"node-1",
			"graph-current",
			"project-123",
			"entity-1",
			"character",
			"女主",
			"公开摘要",
			"canon",
			0.91,
			"cluster-main",
			`{"public":"ok","prompt":"secret","nested":{"snippet":"secret","safe":"visible"},"items":[{"content":"secret","name":"kept"}]}`,
			2,
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:00:01Z",
		}},
		aliasRows: [][]any{{"阿璃"}},
		labelRows: [][]any{{"主角"}},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	detail, err := reader.GetNode(context.Background(), GetNodeInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		NodeID:    "node-1",
	})

	if err != nil {
		t.Fatalf("get node: %v", err)
	}
	if detail.Node.GraphID != "graph-current" || detail.Node.NodeID != "node-1" {
		t.Fatalf("expected node from current graph, got %#v", detail.Node)
	}
	if detail.Node.CanonicalEntityID != "entity-1" {
		t.Fatalf("expected stable canonical entity identity, got %#v", detail.Node)
	}
	if detail.Node.Attributes["prompt"] != nil || detail.Node.Attributes["nested"].(map[string]any)["snippet"] != nil {
		t.Fatalf("expected sanitized attributes, got %#v", detail.Node.Attributes)
	}
	if detail.Node.Attributes["public"] != "ok" || detail.Node.Attributes["nested"].(map[string]any)["safe"] != "visible" {
		t.Fatalf("expected public attributes to remain, got %#v", detail.Node.Attributes)
	}
	if detail.Aliases[0] != "阿璃" || detail.Labels[0] != "主角" {
		t.Fatalf("expected aliases/labels scoped to current graph, got %#v / %#v", detail.Aliases, detail.Labels)
	}
	if len(queryer.calls) != 4 {
		t.Fatalf("expected current snapshot, node, aliases, labels queries, got %d", len(queryer.calls))
	}
	nodeCall := queryer.calls[1]
	if !strings.Contains(nodeCall.query, "FROM story_graph_nodes") || !strings.Contains(nodeCall.query, "graph_id::text = $3") {
		t.Fatalf("expected node detail query to constrain current graph id, got %s", nodeCall.query)
	}
	if strings.Contains(strings.ToLower(nodeCall.query), "snippet") || strings.Contains(strings.ToLower(nodeCall.query), "content_text") {
		t.Fatalf("node detail query selected sensitive fields: %s", nodeCall.query)
	}
	if !reflect.DeepEqual(nodeCall.args, []any{"tenant-123", "project-123", "graph-current", "node-1"}) {
		t.Fatalf("unexpected node query args: %#v", nodeCall.args)
	}
}

func TestSQLReaderGetsEdgeFromCurrentGraphOnly(t *testing.T) {
	queryer := &recordingStoryGraphQueryer{
		snapshotRows: [][]any{currentSnapshotRow("graph-current")},
		edgeRows: [][]any{{
			"edge-1",
			"graph-current",
			"project-123",
			"node-a",
			"node-b",
			"relationship",
			"盟友",
			"公开关系摘要",
			0.77,
			"canon",
			`{"body":"secret","confidence_note":"visible","credential_ref":"hidden"}`,
			3,
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:00:01Z",
		}},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	detail, err := reader.GetEdge(context.Background(), GetEdgeInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		EdgeID:    "edge-1",
	})

	if err != nil {
		t.Fatalf("get edge: %v", err)
	}
	if detail.Edge.GraphID != "graph-current" || detail.Edge.EdgeID != "edge-1" {
		t.Fatalf("expected edge from current graph, got %#v", detail.Edge)
	}
	if detail.Edge.Attributes["body"] != nil || detail.Edge.Attributes["credential_ref"] != nil {
		t.Fatalf("expected sanitized edge attributes, got %#v", detail.Edge.Attributes)
	}
	if detail.Edge.Attributes["confidence_note"] != "visible" {
		t.Fatalf("expected public edge attributes to remain, got %#v", detail.Edge.Attributes)
	}
	if len(queryer.calls) != 2 {
		t.Fatalf("expected current snapshot and edge queries, got %d", len(queryer.calls))
	}
	edgeCall := queryer.calls[1]
	if !strings.Contains(edgeCall.query, "FROM story_graph_edges") || !strings.Contains(edgeCall.query, "graph_id::text = $3") {
		t.Fatalf("expected edge detail query to constrain current graph id, got %s", edgeCall.query)
	}
	if !reflect.DeepEqual(edgeCall.args, []any{"tenant-123", "project-123", "graph-current", "edge-1"}) {
		t.Fatalf("unexpected edge query args: %#v", edgeCall.args)
	}
}

func TestSQLReaderReturnsStableRankedPageWithExplicitContinuation(t *testing.T) {
	queryer := &recordingStoryGraphQueryer{
		snapshotRows: [][]any{currentSnapshotRow("graph-current")},
		nodeRows: [][]any{
			graphNodeRow("node-a", "entity-a", "甲", 0.9),
			graphNodeRow("node-b", "entity-b", "乙", 0.8),
			graphNodeRow("node-c", "entity-c", "丙", 0.7),
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	view, err := reader.GetView(context.Background(), GetViewInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ViewID:    "world",
		Offset:    4,
		Limit:     2,
	})

	if err != nil {
		t.Fatalf("get stable graph page: %v", err)
	}
	if len(view.Nodes) != 2 || view.Nodes[0].NodeID != "node-a" || view.Nodes[1].NodeID != "node-b" {
		t.Fatalf("unexpected graph page: %#v", view.Nodes)
	}
	strategy := view.ReadStrategy
	if strategy.Mode != "stable_ranked_page_with_cluster_summaries" || !strategy.HasMore || strategy.NextOffset != 6 {
		t.Fatalf("unexpected graph read strategy: %#v", strategy)
	}
	if strategy.Offset != 4 || strategy.AppliedLimit != 2 || strategy.ReturnedCount != 2 || strategy.MaxPageSize != 1000 {
		t.Fatalf("unexpected graph pagination metadata: %#v", strategy)
	}
	if strategy.Ordering != "importance_desc,title_asc,node_id_asc" || strategy.EdgeScope != "" {
		t.Fatalf("unexpected graph ordering metadata: %#v", strategy)
	}
	if len(queryer.calls) != 2 {
		t.Fatalf("expected snapshot and node queries, got %d", len(queryer.calls))
	}
	nodeCall := queryer.calls[1]
	if !strings.Contains(nodeCall.query, "ORDER BY importance DESC, title ASC, node_id ASC") || !strings.Contains(nodeCall.query, "LIMIT $5 OFFSET $6") {
		t.Fatalf("graph page query is not deterministically ordered: %s", nodeCall.query)
	}
	if !reflect.DeepEqual(nodeCall.args, []any{"tenant-123", "project-123", "graph-current", "", 3, 4}) {
		t.Fatalf("unexpected graph page args: %#v", nodeCall.args)
	}
}

func TestSQLCandidateAdoptionStoreAdoptsGraphBondCandidateToRelationship(t *testing.T) {
	queryer := &recordingStoryGraphQueryer{
		adoptionRows: [][]any{{
			"asset-graph-bond",
			"project-123",
			"relationship",
			"relationship-123",
			"adopted",
		}},
	}
	store := NewSQLCandidateAdoptionStore(SQLCandidateAdoptionStoreConfig{Queryer: queryer})

	result, err := store.AdoptCandidate(context.Background(), AdoptCandidateInput{
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		AssetID:    "asset-graph-bond",
		ActorID:    "user-123",
		RequestID:  "req-adopt-graph",
		TargetKind: "relationship",
	})

	if err != nil {
		t.Fatalf("adopt candidate: %v", err)
	}
	if result.AssetID != "asset-graph-bond" || result.ProjectID != "project-123" || result.TargetKind != "relationship" || result.TargetID != "relationship-123" || result.Status != "adopted" {
		t.Fatalf("unexpected adoption result: %#v", result)
	}
	if !strings.Contains(queryer.calls[0].query, "lifecycle = 'candidate'") || !strings.Contains(queryer.calls[0].query, "source_kind = 'graph_bond_generation'") {
		t.Fatalf("expected candidate/source constrained adoption, got %s", queryer.calls[0].query)
	}
	for _, expected := range []string{"FOR UPDATE OF assets", "FROM workflow_runs, candidate", "INSERT INTO relationships", "source_entity_name", "target_entity_name", "relationship_type", "UPDATE assets", "lifecycle = 'canon'", "INSERT INTO audit_logs", "story_graph.candidate_adopt"} {
		if !strings.Contains(queryer.calls[0].query, expected) {
			t.Fatalf("adoption query missing %q: %s", expected, queryer.calls[0].query)
		}
	}
	for _, forbidden := range []string{"content_text", "api_key", "encrypted_api_key", "credential_ref", "prompt", "provider", "raw", "object_key", "draft", "manuscript"} {
		if strings.Contains(strings.ToLower(queryer.calls[0].query), forbidden) {
			t.Fatalf("adoption query leaked forbidden field %q: %s", forbidden, queryer.calls[0].query)
		}
	}
	if !reflect.DeepEqual(queryer.calls[0].args, []any{"tenant-123", "project-123", "asset-graph-bond", "user-123", "req-adopt-graph", "relationship"}) {
		t.Fatalf("unexpected adoption args: %#v", queryer.calls[0].args)
	}
	if queryer.tenantContext != "tenant-123" {
		t.Fatalf("expected adoption to set tenant context, got %q", queryer.tenantContext)
	}
}

func TestSQLCandidateAdoptionStoreAdoptsPlotThreadCandidateToPlotThread(t *testing.T) {
	queryer := &recordingStoryGraphQueryer{
		adoptionRows: [][]any{{
			"asset-thread",
			"project-123",
			"plot_thread",
			"thread-123",
			"adopted",
		}},
	}
	store := NewSQLCandidateAdoptionStore(SQLCandidateAdoptionStoreConfig{Queryer: queryer})

	result, err := store.AdoptCandidate(context.Background(), AdoptCandidateInput{
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		AssetID:    "asset-thread",
		ActorID:    "user-123",
		RequestID:  "req-adopt-thread",
		TargetKind: "plot_thread",
	})

	if err != nil {
		t.Fatalf("adopt plot thread candidate: %v", err)
	}
	if result.TargetKind != "plot_thread" || result.TargetID != "thread-123" || result.Status != "adopted" {
		t.Fatalf("unexpected adoption result: %#v", result)
	}
	for _, expected := range []string{"FOR UPDATE OF assets", "FROM workflow_runs, candidate", "INSERT INTO plot_threads", "source_run_id", "UPDATE assets", "lifecycle = 'canon'", "INSERT INTO audit_logs"} {
		if !strings.Contains(queryer.calls[0].query, expected) {
			t.Fatalf("plot thread adoption query missing %q: %s", expected, queryer.calls[0].query)
		}
	}
	if strings.Contains(queryer.calls[0].query, "INSERT INTO relationships") {
		t.Fatalf("plot thread adoption should not write relationships: %s", queryer.calls[0].query)
	}
	if queryer.tenantContext != "tenant-123" {
		t.Fatalf("expected plot thread adoption to set tenant context, got %q", queryer.tenantContext)
	}
}

func TestSQLCandidateAdoptionStoreReturnsNotFoundWhenCandidateCannotBeAdopted(t *testing.T) {
	queryer := &recordingStoryGraphQueryer{}
	store := NewSQLCandidateAdoptionStore(SQLCandidateAdoptionStoreConfig{Queryer: queryer})

	_, err := store.AdoptCandidate(context.Background(), AdoptCandidateInput{
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		AssetID:    "asset-missing",
		ActorID:    "user-123",
		RequestID:  "req-adopt-missing",
		TargetKind: "relationship",
	})

	var appErr *AppError
	if !errors.As(err, &appErr) || appErr.Code != "NOT_FOUND" {
		t.Fatalf("expected NOT_FOUND for no adoption row, got %v", err)
	}
	if queryer.tenantContext != "tenant-123" {
		t.Fatalf("expected missing candidate lookup to set tenant context, got %q", queryer.tenantContext)
	}
}

func currentSnapshotRow(graphID string) []any {
	return []any{
		graphID,
		"project-123",
		2,
		"ready",
		"run-graph",
		"hash-2",
		4,
		5,
		"2026-07-05T00:00:00Z",
		"2026-07-05T00:00:01Z",
	}
}

func graphNodeRow(nodeID string, entityID string, title string, importance float64) []any {
	return []any{
		nodeID,
		"graph-current",
		"project-123",
		entityID,
		"character",
		title,
		"公开摘要",
		"seed",
		importance,
		"cluster-main",
		`{"stable_identity":"entity:` + entityID + `"}`,
		1,
		"2026-07-05T00:00:00Z",
		"2026-07-05T00:00:01Z",
	}
}

type storyGraphQueryCall struct {
	query string
	args  []any
}

type recordingStoryGraphQueryer struct {
	snapshotRows  [][]any
	nodeRows      [][]any
	edgeRows      [][]any
	aliasRows     [][]any
	labelRows     [][]any
	adoptionRows  [][]any
	calls         []storyGraphQueryCall
	tenantContext string
}

func (q *recordingStoryGraphQueryer) QueryContext(_ context.Context, query string, args ...any) (SQLRows, error) {
	q.calls = append(q.calls, storyGraphQueryCall{query: query, args: append([]any{}, args...)})
	switch {
	case strings.Contains(query, "FROM story_graph_snapshots"):
		return &fakeStoryGraphRows{values: q.snapshotRows}, nil
	case strings.Contains(query, "FROM story_graph_nodes"):
		return &fakeStoryGraphRows{values: q.nodeRows}, nil
	case strings.Contains(query, "FROM story_graph_edges"):
		return &fakeStoryGraphRows{values: q.edgeRows}, nil
	case strings.Contains(query, "FROM story_graph_node_aliases"):
		return &fakeStoryGraphRows{values: q.aliasRows}, nil
	case strings.Contains(query, "FROM story_graph_node_labels"):
		return &fakeStoryGraphRows{values: q.labelRows}, nil
	case strings.Contains(query, "story_graph.candidate_adopt"):
		return &fakeStoryGraphRows{values: q.adoptionRows}, nil
	default:
		return &fakeStoryGraphRows{}, nil
	}
}

func (q *recordingStoryGraphQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.tenantContext = tenantID
	return q.QueryContext(ctx, query, args...)
}

type fakeStoryGraphRows struct {
	values [][]any
	index  int
}

func (r *fakeStoryGraphRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeStoryGraphRows) Scan(dest ...any) error {
	row := r.values[r.index]
	r.index++
	for index, target := range dest {
		reflect.ValueOf(target).Elem().Set(reflect.ValueOf(row[index]))
	}
	return nil
}

func (r *fakeStoryGraphRows) Close() error {
	return nil
}

func (r *fakeStoryGraphRows) Err() error {
	return nil
}
