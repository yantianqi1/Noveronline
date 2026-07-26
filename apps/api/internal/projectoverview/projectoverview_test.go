package projectoverview

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLReaderGetsProjectOverviewWithTenantContextAndPublicColumns(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"project-123",
				"analyzing",
				2,
				3,
				"workflow-1",
				"seed_pipeline",
				"running",
				"snapshot-1",
				"seed-run-1",
				7,
				5,
				4,
				3,
				12,
				11,
				`["seg-9"]`,
				11,
				9,
				8,
				6,
				4,
				5,
				2,
				13,
				377,
				2,
				6,
				3,
				1,
				1,
				0,
				"2026-07-07T01:03:00Z",
				true,
				"failed-run-1",
				"seed_pipeline",
				"LLM_MODULE_UNBOUND",
				"2026-07-07T01:04:00Z",
				"2026-07-07T01:05:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	overview, err := reader.GetProjectOverview(context.Background(), GetProjectOverviewInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("get project overview: %v", err)
	}
	if overview.ProjectID != "project-123" || overview.Status != "analyzing" {
		t.Fatalf("unexpected project identity/status: %#v", overview)
	}
	if overview.SourceFileCount != 2 || overview.SeedRunCount != 3 {
		t.Fatalf("unexpected source/seed counts: %#v", overview)
	}
	if overview.ActiveWorkflowRunID != "workflow-1" || overview.ActiveWorkflowType != "seed_pipeline" || overview.ActiveWorkflowStatus != "running" {
		t.Fatalf("unexpected active workflow: %#v", overview)
	}
	if overview.ReadinessSnapshotID != "snapshot-1" || overview.ReadinessRunID != "seed-run-1" {
		t.Fatalf("unexpected readiness identity: %#v", overview)
	}
	if overview.ReadyAssetCount != 7 || overview.ReadyEntityCount != 5 || overview.ReadyRelationshipCount != 4 || overview.ReadyWorldRuleCount != 3 {
		t.Fatalf("unexpected readiness counts: %#v", overview)
	}
	if overview.TotalSegmentCount != 12 || overview.SucceededSegmentCount != 11 {
		t.Fatalf("unexpected segment coverage counts: %#v", overview)
	}
	if len(overview.FailedSegmentIDs) != 1 || overview.FailedSegmentIDs[0] != "seg-9" {
		t.Fatalf("unexpected failed segment ids: %#v", overview)
	}
	if overview.AssetCount != 11 || overview.GraphNodeCount != 9 || overview.GraphEdgeCount != 8 {
		t.Fatalf("unexpected asset/graph health counts: %#v", overview)
	}
	if overview.WorldlineSessionCount != 6 || overview.WorldlineEventCount != 4 || overview.CharacterInteractionCount != 5 {
		t.Fatalf("unexpected worldline/character health counts: %#v", overview)
	}
	if overview.WriterRunCount != 2 || overview.LLMActivityCount != 13 || overview.LLMTokenCount != 377 {
		t.Fatalf("unexpected writer/LLM health counts: %#v", overview)
	}
	if overview.LLMEnabledChannelCount != 2 || overview.LLMBoundModuleCount != 6 || overview.LLMMissingCoreModuleCount != 3 {
		t.Fatalf("unexpected LLM configuration health counts: %#v", overview)
	}
	if overview.LLMSyncOKChannelCount != 1 ||
		overview.LLMSyncFailedChannelCount != 1 ||
		overview.LLMSyncPendingChannelCount != 0 ||
		overview.LLMLatestSyncAt != "2026-07-07T01:03:00Z" {
		t.Fatalf("unexpected LLM model sync health counts: %#v", overview)
	}
	if !overview.LLMHasQuotaPolicy {
		t.Fatalf("expected llm_has_quota_policy=true, got %#v", overview)
	}
	if overview.LatestFailedWorkflowRunID != "failed-run-1" ||
		overview.LatestFailedWorkflowType != "seed_pipeline" ||
		overview.LatestFailedWorkflowErrorCode != "LLM_MODULE_UNBOUND" ||
		overview.LatestFailedWorkflowUpdatedAt != "2026-07-07T01:04:00Z" {
		t.Fatalf("unexpected latest failed workflow diagnostics: %#v", overview)
	}
	if queryer.tenantID != "tenant-123" {
		t.Fatalf("reader did not set tenant context: %q", queryer.tenantID)
	}
	if !strings.Contains(queryer.query, "FROM source_files") ||
		!strings.Contains(queryer.query, "FROM workflow_runs") ||
		!strings.Contains(queryer.query, "FROM project_readiness_snapshots") ||
		!strings.Contains(queryer.query, "FROM assets") ||
		!strings.Contains(queryer.query, "FROM story_graph_snapshots") ||
		!strings.Contains(queryer.query, "FROM worldline_sessions") ||
		!strings.Contains(queryer.query, "FROM worldline_events") ||
		!strings.Contains(queryer.query, "FROM character_interaction_sessions") ||
		!strings.Contains(queryer.query, "FROM writer_runs") ||
		!strings.Contains(queryer.query, "FROM llm_activity") ||
		!strings.Contains(queryer.query, "FROM usage_events") ||
		!strings.Contains(queryer.query, "FROM llm_channels") ||
		!strings.Contains(queryer.query, "FROM llm_module_bindings") ||
		!strings.Contains(queryer.query, "JOIN llm_models") ||
		!strings.Contains(queryer.query, "c.enabled = TRUE") ||
		!strings.Contains(queryer.query, "required_llm_modules") ||
		!strings.Contains(queryer.query, "analysis_planner") ||
		!strings.Contains(queryer.query, "analysis_worker") ||
		!strings.Contains(queryer.query, "writer_composer") ||
		!strings.Contains(queryer.query, "writer_orchestrator") ||
		!strings.Contains(queryer.query, "llm_model_sync_health") ||
		!strings.Contains(queryer.query, "llm_quota_policy_counts") ||
		!strings.Contains(queryer.query, "llm_quota_policies") ||
		!strings.Contains(queryer.query, "last_sync_status LIKE 'ok:%'") ||
		!strings.Contains(queryer.query, "last_sync_at") ||
		!strings.Contains(queryer.query, "latest_failed_workflow") ||
		!strings.Contains(queryer.query, "error_code") ||
		!strings.Contains(queryer.query, "status = 'failed'") ||
		!strings.Contains(queryer.query, "usage_type = 'llm_tokens'") ||
		!strings.Contains(queryer.query, "tenant_id::text = $1") ||
		!strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected tenant/project scoped overview query, got %s", queryer.query)
	}
	forbidden := []string{"object_key", "raw_text", "parsed_text", "content_text", "body_text", "prompt", "api_key", "encrypted_api_key", "base_url", "credential_ref", "draft", "manuscript", "report_body", "error_message"}
	lowerQuery := strings.ToLower(queryer.query)
	for _, field := range forbidden {
		if strings.Contains(lowerQuery, field) {
			t.Fatalf("overview query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestDisabledReaderFailsClosed(t *testing.T) {
	reader := NewDisabledReader()

	_, err := reader.GetProjectOverview(context.Background(), GetProjectOverviewInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if code := ErrorCode(err); code != "PROJECT_OVERVIEW_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected PROJECT_OVERVIEW_BACKEND_UNCONFIGURED, got %s (%v)", code, err)
	}
}

func TestSQLReaderSanitizesUnexpectedQueryFailures(t *testing.T) {
	reader := NewSQLReader(SQLReaderConfig{Queryer: &recordingSQLQueryer{
		err: errors.New("driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden readiness report body draft manuscript"),
	}})

	_, err := reader.GetProjectOverview(context.Background(), GetProjectOverviewInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if code := ErrorCode(err); code != "PROJECT_OVERVIEW_QUERY_FAILED" {
		t.Fatalf("expected PROJECT_OVERVIEW_QUERY_FAILED, got %s (%v)", code, err)
	}
	if err == nil || err.Error() != "project overview query failed" {
		t.Fatalf("expected stable public message, got %v", err)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "report body", "draft", "manuscript"} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("query error leaked %q: %v", forbidden, err)
		}
	}
}

type recordingSQLQueryer struct {
	tenantID string
	query    string
	args     []any
	rows     *fakeSQLRows
	err      error
}

func (q *recordingSQLQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.query = query
	q.args = args
	if q.err != nil {
		return nil, q.err
	}
	return q.rows, nil
}

func (q *recordingSQLQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.tenantID = tenantID
	return q.QueryContext(ctx, query, args...)
}

type fakeSQLRows struct {
	values [][]any
	index  int
	err    error
}

func (r *fakeSQLRows) Next() bool {
	if r.index >= len(r.values) {
		return false
	}
	r.index++
	return true
}

func (r *fakeSQLRows) Scan(dest ...any) error {
	row := r.values[r.index-1]
	for i := range dest {
		reflect.ValueOf(dest[i]).Elem().Set(reflect.ValueOf(row[i]))
	}
	return nil
}

func (r *fakeSQLRows) Close() error {
	return nil
}

func (r *fakeSQLRows) Err() error {
	return r.err
}
