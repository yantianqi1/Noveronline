package llm

import (
	"context"
	"reflect"
	"strings"
	"testing"
)

func TestSQLModelSyncerSyncsOpenAICompatibleModelsWithDecryptedCredential(t *testing.T) {
	keyMaterial := strings.Repeat("3", 64)
	encryptedKey, err := NewSQLChannelStore(SQLChannelStoreConfig{
		Queryer:               &recordingSQLQueryer{rows: &fakeSQLRows{}},
		CredentialKeyMaterial: keyMaterial,
	}).encryptCredential("sk-live")
	if err != nil {
		t.Fatalf("encrypt fixture credential: %v", err)
	}
	queryer := &sequenceSQLQueryer{
		rows: []*fakeSQLRows{
			{
				values: [][]any{{
					"channel-1",
					"Draft Channel",
					"openai-compatible",
					"https://llm.example.test/v1",
					encryptedKey,
					4,
					true,
					"2026-07-04T00:00:00Z",
					"2026-07-04T00:00:00Z",
				}},
			},
			{
				values: [][]any{
					{
						"channel-1",
						"Draft Channel",
						"openai-compatible",
						"https://llm.example.test/v1",
						4,
						true,
						"2026-07-04T01:00:00Z",
						"ok:2",
						"tenant",
						"2026-07-04T00:00:00Z",
						"2026-07-04T01:00:00Z",
						"gpt-4.1",
						"openai",
						0,
						false,
						false,
						0.0,
						0.0,
						"2026-07-04T01:00:00Z",
						"2026-07-04T01:00:00Z",
					},
					{
						"channel-1",
						"Draft Channel",
						"openai-compatible",
						"https://llm.example.test/v1",
						4,
						true,
						"2026-07-04T01:00:00Z",
						"ok:2",
						"tenant",
						"2026-07-04T00:00:00Z",
						"2026-07-04T01:00:00Z",
						"gpt-4.1-mini",
						"openai",
						0,
						false,
						false,
						0.0,
						0.0,
						"2026-07-04T01:00:00Z",
						"2026-07-04T01:00:00Z",
					},
				},
			},
		},
	}
	provider := &recordingModelProvider{
		models: []ProviderModel{
			{ModelID: "gpt-4.1", OwnedBy: "openai"},
			{ModelID: "gpt-4.1-mini", OwnedBy: "openai"},
		},
	}
	syncer := NewSQLModelSyncer(SQLModelSyncerConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: keyMaterial,
		Provider:              provider,
	})

	result, err := syncer.SyncModels(context.Background(), ModelSyncInput{
		TenantID:  "tenant-123",
		ChannelID: "channel-1",
	})

	if err != nil {
		t.Fatalf("sync models: %v", err)
	}
	if provider.input.APIKey != "sk-live" || provider.input.BaseURL != "https://llm.example.test/v1" || provider.input.Provider != "openai-compatible" {
		t.Fatalf("provider did not receive explicit channel credential/context: %#v", provider.input)
	}
	if result.Channel.ChannelID != "channel-1" || result.Channel.LastSyncStatus != "ok:2" {
		t.Fatalf("unexpected synced channel: %#v", result.Channel)
	}
	if got := []string{result.Models[0].ModelID, result.Models[1].ModelID}; !reflect.DeepEqual(got, []string{"gpt-4.1", "gpt-4.1-mini"}) {
		t.Fatalf("unexpected synced models: %#v", result.Models)
	}
	if len(queryer.queries) != 2 {
		t.Fatalf("expected channel credential query and upsert query, got %#v", queryer.queries)
	}
	if strings.Contains(strings.ToLower(queryer.queries[1]), "api_key") {
		t.Fatalf("model upsert query should not write plaintext api key: %s", queryer.queries[1])
	}
	if !strings.Contains(queryer.queries[1], "INSERT INTO llm_models") || !strings.Contains(queryer.queries[1], "last_sync_status") {
		t.Fatalf("expected model upsert and channel sync status update, got %s", queryer.queries[1])
	}
	if !strings.Contains(queryer.args[1][2].(string), "gpt-4.1") {
		t.Fatalf("expected sanitized provider models JSON as upsert arg, got %#v", queryer.args[1])
	}
}

func TestSQLModelSyncerRecordsExplicitFailureStatusWhenProviderFails(t *testing.T) {
	keyMaterial := strings.Repeat("4", 64)
	encryptedKey, err := NewSQLChannelStore(SQLChannelStoreConfig{
		Queryer:               &recordingSQLQueryer{rows: &fakeSQLRows{}},
		CredentialKeyMaterial: keyMaterial,
	}).encryptCredential("sk-live")
	if err != nil {
		t.Fatalf("encrypt fixture credential: %v", err)
	}
	queryer := &sequenceSQLQueryer{
		rows: []*fakeSQLRows{
			{
				values: [][]any{{
					"channel-1",
					"Draft Channel",
					"openai-compatible",
					"https://llm.example.test/v1",
					encryptedKey,
					4,
					true,
					"2026-07-04T00:00:00Z",
					"2026-07-04T00:00:00Z",
				}},
			},
			{
				values: [][]any{{
					"channel-1",
					"Draft Channel",
					"openai-compatible",
					"https://llm.example.test/v1",
					4,
					true,
					"2026-07-04T01:00:00Z",
					"failed:LLM_PROVIDER_ERROR",
					"tenant",
					"2026-07-04T00:00:00Z",
					"2026-07-04T01:00:00Z",
				}},
			},
		},
	}
	syncer := NewSQLModelSyncer(SQLModelSyncerConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: keyMaterial,
		Provider:              &recordingModelProvider{err: &AppError{Code: "LLM_PROVIDER_ERROR", Message: "provider unavailable"}},
	})

	_, err = syncer.SyncModels(context.Background(), ModelSyncInput{TenantID: "tenant-123", ChannelID: "channel-1"})

	if code := ErrorCode(err); code != "LLM_PROVIDER_ERROR" {
		t.Fatalf("expected provider error, got %s (%v)", code, err)
	}
	if len(queryer.queries) != 2 {
		t.Fatalf("expected failure status update after provider error, got %#v", queryer.queries)
	}
	if !strings.Contains(queryer.queries[1], "last_sync_status") || strings.Contains(queryer.queries[1], "INSERT INTO llm_models") {
		t.Fatalf("expected only failure sync status update, got %s", queryer.queries[1])
	}
	if queryer.args[1][2] != "failed:LLM_PROVIDER_ERROR" {
		t.Fatalf("expected stable failed sync status, got %#v", queryer.args[1])
	}
}

func TestDisabledModelSyncerFailsExplicitly(t *testing.T) {
	syncer := NewDisabledModelSyncer()

	_, err := syncer.SyncModels(context.Background(), ModelSyncInput{TenantID: "tenant-123", ChannelID: "channel-1"})

	if code := ErrorCode(err); code != "LLM_MODEL_SYNC_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected disabled model sync error, got %s (%v)", code, err)
	}
}

type recordingModelProvider struct {
	input  ProviderListModelsInput
	models []ProviderModel
	err    error
}

func (p *recordingModelProvider) ListModels(ctx context.Context, input ProviderListModelsInput) ([]ProviderModel, error) {
	p.input = input
	return p.models, p.err
}

type sequenceSQLQueryer struct {
	queries []string
	args    [][]any
	rows    []*fakeSQLRows
}

func (q *sequenceSQLQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.queries = append(q.queries, query)
	q.args = append(q.args, append([]any(nil), args...))
	if len(q.rows) == 0 {
		return &fakeSQLRows{}, nil
	}
	rows := q.rows[0]
	q.rows = q.rows[1:]
	return rows, nil
}
