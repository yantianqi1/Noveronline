package storygraph

import (
	"context"
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

type storyGraphQueryCall struct {
	query string
	args  []any
}

type recordingStoryGraphQueryer struct {
	snapshotRows [][]any
	nodeRows     [][]any
	edgeRows     [][]any
	aliasRows    [][]any
	labelRows    [][]any
	calls        []storyGraphQueryCall
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
	default:
		return &fakeStoryGraphRows{}, nil
	}
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
