package llm

import (
	"context"
	"errors"
	"math"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestSQLTelemetryReaderAggregatesTenantProjectModuleRunUsageWithoutListLimit(t *testing.T) {
	queryer := &recordingSQLQueryer{rows: &fakeSQLRows{values: [][]any{{
		"project-123",
		"writer_composer",
		"550e8400-e29b-41d4-a716-446655440000",
		42.0,
		"tokens",
		2,
		0,
		0,
	}}}}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer, Limit: 1})
	periodFrom := time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC)
	periodTo := periodFrom.AddDate(0, 1, 0)

	records, err := reader.AggregateUsage(context.Background(), UsageAggregateQueryInput{
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		ModuleKey:  "writer_composer",
		RunID:      "550e8400-e29b-41d4-a716-446655440000",
		PeriodFrom: periodFrom,
		PeriodTo:   periodTo,
	})

	if err != nil {
		t.Fatalf("aggregate usage: %v", err)
	}
	if len(records) != 1 || records[0].Quantity != 42 || records[0].ProviderCalls != 2 || records[0].CallIdentityStatus != "complete" {
		t.Fatalf("unexpected aggregate: %#v", records)
	}
	for _, expected := range []string{
		"deduplicated_usage AS",
		"metadata_jsonb->>'provider_call_id'",
		"usage_type = 'llm_tokens'",
		"GROUP BY project_id, module_key, run_id, unit",
	} {
		if !strings.Contains(queryer.query, expected) {
			t.Fatalf("aggregate query missing %q: %s", expected, queryer.query)
		}
	}
	if strings.Contains(queryer.query, "LIMIT") {
		t.Fatalf("quota aggregate must not inherit telemetry list limit: %s", queryer.query)
	}
	expectedArgs := []any{
		"tenant-123",
		"project-123",
		"550e8400-e29b-41d4-a716-446655440000",
		"writer_composer",
		periodFrom,
		periodTo,
	}
	if !reflect.DeepEqual(queryer.args, expectedArgs) {
		t.Fatalf("unexpected aggregate args: %#v", queryer.args)
	}
}

func TestSQLTelemetryReaderMarksHistoricalEventsWithoutProviderCallIdentityUnavailable(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{"project-123", "worldline_director", "run-123", 19.0, "tokens", 0, 1, 0}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	records, err := reader.AggregateUsage(context.Background(), UsageAggregateQueryInput{TenantID: "tenant-123"})

	if err != nil {
		t.Fatalf("aggregate historical usage: %v", err)
	}
	if len(records) != 1 || records[0].CallIdentityStatus != "unavailable" || records[0].UnidentifiedEvents != 1 {
		t.Fatalf("historical usage identity must remain explicit: %#v", records)
	}
}

func TestSQLTelemetryReaderRejectsConflictingProviderCallUsage(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{"project-123", "writer_composer", "run-123", 34.0, "tokens", 1, 0, 1}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	_, err := reader.AggregateUsage(context.Background(), UsageAggregateQueryInput{TenantID: "tenant-123"})

	if code := ErrorCode(err); code != "LLM_USAGE_DATA_INVALID" {
		t.Fatalf("conflicting provider call usage must fail closed, got %s (%v)", code, err)
	}
}

func TestSQLTelemetryReaderListUsageDeduplicatesOnlyExplicitProviderCalls(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{"llm_tokens", 34.0, "tokens", "worldline_director", "run-123"}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	_, err := reader.ListUsage(context.Background(), UsageQueryInput{TenantID: "tenant-123", ProjectID: "project-123"})

	if err != nil {
		t.Fatalf("list usage: %v", err)
	}
	if !strings.Contains(queryer.query, "metadata_jsonb->>'provider_call_id'") ||
		!strings.Contains(queryer.query, "usage_event_id::text") {
		t.Fatalf("usage list lost explicit provider-call de-duplication: %s", queryer.query)
	}
}

func TestSQLTelemetryReaderAggregatesCompletedActivityWithoutListLimit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{"project-123", "writer_composer", "run-123", 2, 1, 1, 34.0}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer, Limit: 1})

	records, err := reader.AggregateActivity(context.Background(), UsageAggregateQueryInput{
		TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer", RunID: "run-123",
	})

	if err != nil {
		t.Fatalf("aggregate activity: %v", err)
	}
	if len(records) != 1 || records[0].CompletedCalls != 2 || records[0].TokenReportedCalls != 1 ||
		records[0].TokenUnavailableCalls != 1 || records[0].Tokens != 34 {
		t.Fatalf("unexpected activity aggregate: %#v", records)
	}
	if strings.Contains(queryer.query, "LIMIT") || !strings.Contains(queryer.query, "status = 'completed'") {
		t.Fatalf("activity reconciliation query must be complete and completed-only: %s", queryer.query)
	}
}

func TestQuotaEnforcerRejectsAtLimitBeforeProviderCall(t *testing.T) {
	meter := &recordingTokenUsageMeter{used: 100}
	enforcer := NewQuotaEnforcer(meter)

	decision, err := enforcer.CheckBeforeProviderCall(context.Background(), QuotaPolicy{
		Mode:  QuotaModeEnforced,
		Limit: 100,
		Scope: UsageAggregateQueryInput{TenantID: "tenant-123", ProjectID: "project-123"},
	})

	if code := ErrorCode(err); code != "LLM_QUOTA_EXCEEDED" {
		t.Fatalf("expected quota exceeded, got %s (%v)", code, err)
	}
	if decision.Status != "exceeded" || decision.Used != 100 || decision.Remaining != 0 {
		t.Fatalf("unexpected quota decision: %#v", decision)
	}
	if meter.calls != 1 {
		t.Fatalf("expected one actual usage query, got %d", meter.calls)
	}
}

func TestQuotaEnforcerFailsClosedWithoutPolicyOrMeter(t *testing.T) {
	_, err := NewQuotaEnforcer(nil).CheckBeforeProviderCall(context.Background(), QuotaPolicy{
		Mode: QuotaModeEnforced, Scope: UsageAggregateQueryInput{TenantID: "tenant-123"},
	})
	if code := ErrorCode(err); code != "LLM_QUOTA_CHECK_FAILED" {
		t.Fatalf("expected stable quota check failure, got %s (%v)", code, err)
	}

	_, err = NewQuotaEnforcer(&recordingTokenUsageMeter{}).CheckBeforeProviderCall(context.Background(), QuotaPolicy{})
	if code := ErrorCode(err); code != "LLM_QUOTA_POLICY_UNAVAILABLE" {
		t.Fatalf("expected unavailable quota policy, got %s (%v)", code, err)
	}
}

func TestQuotaEnforcerRejectsInvalidScopeLimitAndMeasuredUsage(t *testing.T) {
	meter := &recordingTokenUsageMeter{used: 1}
	enforcer := NewQuotaEnforcer(meter)

	_, err := enforcer.CheckBeforeProviderCall(context.Background(), QuotaPolicy{Mode: QuotaModeEnforced, Limit: 10})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" || meter.calls != 0 {
		t.Fatalf("missing tenant scope reached meter: code=%s calls=%d", code, meter.calls)
	}
	_, err = enforcer.CheckBeforeProviderCall(context.Background(), QuotaPolicy{
		Mode: QuotaModeEnforced, Limit: math.NaN(), Scope: UsageAggregateQueryInput{TenantID: "tenant-123"},
	})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" || meter.calls != 0 {
		t.Fatalf("non-finite quota limit reached meter: code=%s calls=%d", code, meter.calls)
	}

	enforcer = NewQuotaEnforcer(&recordingTokenUsageMeter{used: math.Inf(1)})
	_, err = enforcer.CheckBeforeProviderCall(context.Background(), QuotaPolicy{
		Mode: QuotaModeEnforced, Limit: 10, Scope: UsageAggregateQueryInput{TenantID: "tenant-123"},
	})
	if code := ErrorCode(err); code != "LLM_QUOTA_USAGE_UNAVAILABLE" {
		t.Fatalf("non-finite measured usage must fail closed, got %s (%v)", code, err)
	}
}

func TestSQLTelemetryAggregateSurfacesRowsCloseFailure(t *testing.T) {
	queryer := &recordingSQLQueryer{rows: &fakeSQLRows{closeErr: errors.New("commit failed api_key=secret prompt=private")}}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	_, err := reader.AggregateUsage(context.Background(), UsageAggregateQueryInput{TenantID: "tenant-123"})
	if code := ErrorCode(err); code != "LLM_USAGE_QUERY_FAILED" || err.Error() != "LLM usage query failed" {
		t.Fatalf("expected stable aggregate close error, got %s (%v)", code, err)
	}
}

func TestQuotaEnforcerDoesNotEstimateProspectiveProviderUsage(t *testing.T) {
	enforcer := NewQuotaEnforcer(&recordingTokenUsageMeter{used: 80})

	decision, err := enforcer.CheckBeforeProviderCall(context.Background(), QuotaPolicy{
		Mode: QuotaModeEnforced, Limit: 100, Scope: UsageAggregateQueryInput{TenantID: "tenant-123"},
	})

	if err != nil || decision.Status != "allowed" || decision.Used != 80 || decision.Remaining != 20 {
		t.Fatalf("quota decision must contain measured usage only: decision=%#v err=%v", decision, err)
	}
}

func TestReconcileTelemetryReportsMatchedAndIdentityUnavailableTruth(t *testing.T) {
	activity := []ActivityAggregateRecord{{
		ProjectID: "project-123", RunID: "run-123", ModuleKey: "writer_composer",
		CompletedCalls: 1, TokenReportedCalls: 1, Tokens: 34,
	}}
	usage := []UsageAggregateRecord{{
		ProjectID: "project-123", RunID: "run-123", ModuleKey: "writer_composer", Quantity: 34,
		Unit: "tokens", ProviderCalls: 1, CallIdentityStatus: "complete",
	}}

	reconciled := ReconcileTelemetry(activity, usage)
	if len(reconciled) != 1 || reconciled[0].Status != "matched" || reconciled[0].ActivityCalls != 1 {
		t.Fatalf("unexpected exact reconciliation: %#v", reconciled)
	}
	usage[0].CallIdentityStatus = "unavailable"
	reconciled = ReconcileTelemetry(activity, usage)
	if reconciled[0].Status != "matched_identity_unavailable" {
		t.Fatalf("missing provider identity must not be presented as exact: %#v", reconciled)
	}
}

func TestReconcileTelemetryReportsMissingAndMismatchStates(t *testing.T) {
	result := ReconcileTelemetry(
		[]ActivityAggregateRecord{{ProjectID: "project-123", RunID: "run-a", ModuleKey: "writer_composer", CompletedCalls: 1, TokenReportedCalls: 1, Tokens: 10}},
		[]UsageAggregateRecord{{ProjectID: "project-123", RunID: "run-b", ModuleKey: "writer_composer", Quantity: 12, Unit: "tokens", CallIdentityStatus: "complete"}},
	)
	if len(result) != 2 || result[0].Status != "missing_usage" || result[1].Status != "missing_activity" {
		t.Fatalf("unexpected reconciliation boundaries: %#v", result)
	}
}

type recordingTokenUsageMeter struct {
	used   float64
	status string
	err    error
	calls  int
}

func (m *recordingTokenUsageMeter) MeasureTokens(context.Context, UsageAggregateQueryInput) (TokenUsageMeasurement, error) {
	m.calls++
	if m.err != nil {
		return TokenUsageMeasurement{}, m.err
	}
	status := m.status
	if status == "" {
		status = "available"
	}
	return TokenUsageMeasurement{Used: m.used, Status: status}, nil
}

func TestQuotaEnforcerSanitizesMeterFailure(t *testing.T) {
	enforcer := NewQuotaEnforcer(&recordingTokenUsageMeter{err: errors.New("api_key=secret prompt=private")})
	_, err := enforcer.CheckBeforeProviderCall(context.Background(), QuotaPolicy{
		Mode: QuotaModeEnforced, Limit: 1, Scope: UsageAggregateQueryInput{TenantID: "tenant-123"},
	})
	if err == nil || err.Error() != "LLM quota check failed" {
		t.Fatalf("expected stable quota error, got %v", err)
	}
}

func TestQuotaEnforcerRejectsUnavailableTelemetryBeforeProviderCall(t *testing.T) {
	enforcer := NewQuotaEnforcer(&recordingTokenUsageMeter{used: 80, status: "unavailable"})
	_, err := enforcer.CheckBeforeProviderCall(context.Background(), QuotaPolicy{
		Mode: QuotaModeEnforced, Limit: 100, Scope: UsageAggregateQueryInput{TenantID: "tenant-123"},
	})
	if code := ErrorCode(err); code != "LLM_QUOTA_USAGE_UNAVAILABLE" {
		t.Fatalf("unreconciled telemetry must fail closed, got %s (%v)", code, err)
	}
}
