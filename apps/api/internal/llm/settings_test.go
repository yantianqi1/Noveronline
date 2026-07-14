package llm

import (
	"context"
	"strings"
	"testing"
)

func TestSQLSettingsReaderReturnsSanitizedTenantSnapshot(t *testing.T) {
	queryer := &settingsTenantQueryer{sequenceSQLQueryer: &sequenceSQLQueryer{
		rows: []*fakeSQLRows{
			{
				values: [][]any{
					{
						"channel-1",
						"Draft Channel",
						"openai-compatible",
						"https://llm.example.test/v1",
						2,
						true,
						"2026-07-05T01:00:00Z",
						"ok:2",
						"tenant",
						"2026-07-05T00:00:00Z",
						"2026-07-05T01:00:00Z",
					},
				},
			},
			{
				values: [][]any{
					{
						"writer_composer",
						"channel-1",
						"Draft Channel",
						"openai-compatible",
						"https://llm.example.test/v1",
						"gpt-4.1-mini",
						true,
						true,
						`{"max_concurrency":1,"api_key":"sk-leak","credential_ref":"secret-ref"}`,
						"tenant",
						"2026-07-05T01:00:00Z",
					},
				},
			},
		},
	}}
	reader := NewSQLSettingsReader(SQLSettingsReaderConfig{Queryer: queryer})

	snapshot, err := reader.GetSettings(context.Background(), SettingsInput{TenantID: "tenant-123"})

	if err != nil {
		t.Fatalf("get settings: %v", err)
	}
	if len(snapshot.Modules) != 30 {
		t.Fatalf("expected documented modules in settings snapshot, got %d", len(snapshot.Modules))
	}
	if len(snapshot.Channels) != 1 || snapshot.Channels[0].ChannelID != "channel-1" {
		t.Fatalf("unexpected channels: %#v", snapshot.Channels)
	}
	if len(snapshot.TenantBindings) != 1 || snapshot.TenantBindings[0].ModuleKey != "writer_composer" {
		t.Fatalf("unexpected tenant bindings: %#v", snapshot.TenantBindings)
	}
	if _, ok := snapshot.TenantBindings[0].Settings["api_key"]; ok {
		t.Fatalf("settings snapshot leaked api_key: %#v", snapshot.TenantBindings[0].Settings)
	}
	if _, ok := snapshot.TenantBindings[0].Settings["credential_ref"]; ok {
		t.Fatalf("settings snapshot leaked credential_ref: %#v", snapshot.TenantBindings[0].Settings)
	}
	if snapshot.TenantBindings[0].Settings["max_concurrency"] != float64(1) {
		t.Fatalf("settings snapshot lost public max_concurrency: %#v", snapshot.TenantBindings[0].Settings)
	}
	if len(queryer.queries) != 2 {
		t.Fatalf("expected channel and tenant binding queries, got %#v", queryer.queries)
	}
	if queryer.rawCalls != 0 || len(queryer.tenantIDs) != 2 || queryer.tenantIDs[0] != "tenant-123" || queryer.tenantIDs[1] != "tenant-123" {
		t.Fatalf("settings queries bypassed tenant context: raw=%d tenant_ids=%#v", queryer.rawCalls, queryer.tenantIDs)
	}
	joinedQueries := strings.ToLower(strings.Join(queryer.queries, "\n"))
	if strings.Contains(joinedQueries, "encrypted_api_key") || strings.Contains(joinedQueries, "api_key") || strings.Contains(joinedQueries, "credential_ref") {
		t.Fatalf("settings queries should not select credential material: %s", joinedQueries)
	}
}

func TestSQLSettingsReaderFailsClosedWithoutTenantQueryInterface(t *testing.T) {
	raw := &rawOnlySQLQueryer{rows: &fakeSQLRows{}}
	reader := NewSQLSettingsReader(SQLSettingsReaderConfig{Queryer: raw})

	_, err := reader.GetSettings(context.Background(), SettingsInput{TenantID: "tenant-123"})

	if code := ErrorCode(err); code != "LLM_SETTINGS_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected tenant query interface failure, got %s (%v)", code, err)
	}
	if raw.calls != 0 {
		t.Fatalf("settings reader fell back to raw query context: calls=%d", raw.calls)
	}
}

type settingsTenantQueryer struct {
	*sequenceSQLQueryer
	tenantIDs []string
	rawCalls  int
}

func (q *settingsTenantQueryer) QueryContext(context.Context, string, ...any) (SQLRows, error) {
	q.rawCalls++
	return nil, nil
}

func (q *settingsTenantQueryer) QueryTenantContext(ctx context.Context, tenantID, query string, args ...any) (SQLRows, error) {
	q.tenantIDs = append(q.tenantIDs, tenantID)
	return q.sequenceSQLQueryer.QueryContext(ctx, query, args...)
}

func TestDisabledSettingsReaderFailsExplicitly(t *testing.T) {
	reader := NewDisabledSettingsReader()

	_, err := reader.GetSettings(context.Background(), SettingsInput{TenantID: "tenant-123"})

	if code := ErrorCode(err); code != "LLM_SETTINGS_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected disabled settings error, got %s (%v)", code, err)
	}
}
