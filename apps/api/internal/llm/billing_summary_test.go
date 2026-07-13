package llm

import (
	"context"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestBillingUsageGroupsTenantProjectModuleModelWithoutInventingCost(t *testing.T) {
	queryer := &recordingSQLQueryer{rows: &fakeSQLRows{values: [][]any{
		{"project-1", "writer_composer", "model-a", 2, int64(80), int64(1200), "billing_ready"},
		{"project-1", "writer_reviewer", "model-b", 1, int64(20), nil, "pricing_unavailable"},
	}}}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})
	from := time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC)
	to := from.AddDate(0, 1, 0)

	records, err := reader.BillingUsage(context.Background(), BillingUsageQuery{
		TenantID: "tenant-1", ProjectID: "project-1", PeriodFrom: from, PeriodTo: to,
	})
	if err != nil {
		t.Fatalf("billing usage: %v", err)
	}
	if len(records) != 2 || records[0].CostMicros == nil || *records[0].CostMicros != 1200 ||
		records[1].CostMicros != nil || records[1].BillingStatus != "pricing_unavailable" {
		t.Fatalf("unexpected billing truth: %#v", records)
	}
	for _, expected := range []string{"provider_call_id", "model_id", "llm_cost_micros", "billing_ready", "GROUP BY project_id, module_key, model_id"} {
		if !strings.Contains(queryer.query, expected) {
			t.Fatalf("billing query missing %q: %s", expected, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "project-1", from, to}) {
		t.Fatalf("unexpected billing args: %#v", queryer.args)
	}
}

func TestBillingUsageRejectsInvalidPeriodAndSanitizesBackendErrors(t *testing.T) {
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: &recordingSQLQueryer{}})
	now := time.Now()
	_, err := reader.BillingUsage(context.Background(), BillingUsageQuery{TenantID: "tenant-1", PeriodFrom: now, PeriodTo: now})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("invalid period: code=%s err=%v", code, err)
	}

	reader = NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: &recordingSQLQueryer{err: context.Canceled}})
	_, err = reader.BillingUsage(context.Background(), BillingUsageQuery{TenantID: "tenant-1"})
	if code := ErrorCode(err); code != "LLM_BILLING_USAGE_QUERY_FAILED" || strings.Contains(err.Error(), "context") {
		t.Fatalf("backend error was not stable: code=%s err=%v", code, err)
	}
}
