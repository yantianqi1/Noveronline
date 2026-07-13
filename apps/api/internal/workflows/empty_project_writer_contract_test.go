package workflows

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

// Z0 contract: Writer admission and draft adoption must not require Seed
// source files, text segments, ontology, graph, or worldline rows.

func TestEmptyProjectWriterAdmissionSQLDoesNotDependOnSeedArtifacts(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLWriterAdmissionStore(SQLWriterAdmissionStoreConfig{Execer: execer})

	_, _, err := store.AdmitWriterRun(context.Background(), WriterAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace-empty-project",
		WorkflowType:       WriterWorkflowType,
		TemporalWorkflowID: "writer_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-empty-project",
		Mode:               "draft",
		Status:             "queued",
		ModuleKey:          "writer_composer",
		Instruction:        "从一个想法开始写第一章",
		Options:            map[string]any{"chapter_id": "chapter-1"},
	})
	if err != nil {
		t.Fatalf("admit empty-project writer run: %v", err)
	}
	if execer.query == "" {
		t.Fatal("expected writer admission SQL")
	}
	assertSQLOmitsSeedPrerequisites(t, execer.query, "writer admission")
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") ||
		!strings.Contains(execer.query, "INSERT INTO writer_runs") {
		t.Fatalf("admission SQL missing writer/workflow inserts: %s", execer.query)
	}
}

func TestEmptyProjectDraftAdoptionSQLDoesNotDependOnSeedArtifacts(t *testing.T) {
	queryer := &recordingDraftAdoptionQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"33333333-3333-4333-8333-333333333333",
				"55555555-5555-4555-8555-555555555555",
				"22222222-2222-4222-8222-222222222222",
				"adopted",
				"66666666-6666-4666-8666-666666666666",
				"77777777-7777-4777-8777-777777777777",
				1,
			}},
		},
	}
	store := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{Queryer: queryer})

	result, err := store.AdoptDraft(context.Background(), DraftAdoptionInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-empty-adopt",
		ChapterID:   "66666666-6666-4666-8666-666666666666",
		BlockOrder:  1,
	})
	if err != nil {
		t.Fatalf("adopt empty-project draft: %v", err)
	}
	if result.Status != "adopted" || result.BlockID == "" {
		t.Fatalf("unexpected adoption result: %#v", result)
	}
	assertSQLOmitsSeedPrerequisites(t, queryer.query, "draft adoption")
	if !strings.Contains(queryer.query, "INSERT INTO manuscript_blocks") ||
		!strings.Contains(queryer.query, "source_draft_id") {
		t.Fatalf("adoption SQL missing manuscript insert: %s", queryer.query)
	}

	resultJSON, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal adoption result: %v", err)
	}
	for _, forbidden := range []string{"content_text", "source_file", "text_segment", "seed"} {
		if strings.Contains(strings.ToLower(string(resultJSON)), forbidden) {
			t.Fatalf("adoption result leaked %q: %s", forbidden, resultJSON)
		}
	}
}

func TestEmptyProjectLocalWriterStarterDoesNotRequireSeedContext(t *testing.T) {
	starter := NewLocalWriterStarter()
	run, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID:    "tenant-empty",
		ProjectID:   "project-empty",
		ActorUserID: "user-empty",
		RequestID:   "req-empty",
		Mode:        "draft",
		Instruction: "从故事前提写开篇",
		Options: map[string]any{
			// Empty-project options intentionally omit assets, graph, and seed refs.
			"selected_asset_ids": []any{},
			"graph_node_ids":     []any{},
			"worldline_path_ids": []any{},
		},
	})
	if err != nil {
		t.Fatalf("start empty-project writer run: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-empty" || run.Status != "queued" {
		t.Fatalf("unexpected empty-project writer run: %#v", run)
	}
}

func assertSQLOmitsSeedPrerequisites(t *testing.T, query string, label string) {
	t.Helper()
	lower := strings.ToLower(query)
	for _, forbidden := range []string{
		"source_files",
		"text_segments",
		"project_text_artifacts",
		"seed_tasks",
		"graph_nodes",
		"graph_edges",
		"worldline_sessions",
		"ontology",
	} {
		if strings.Contains(lower, forbidden) {
			t.Fatalf("%s SQL must not depend on %s: %s", label, forbidden, query)
		}
	}
}
