package llm

import (
	"context"
	"reflect"
	"strings"
	"testing"
)

func TestSQLCatalogReaderListsSanitizedChannelsForTenantAndPlatform(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Draft Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				4,
				true,
				"2026-07-04T00:00:00Z",
				"ok",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLCatalogReader(SQLCatalogConfig{Queryer: queryer, Limit: 25})

	channels, err := reader.ListChannels(context.Background(), CatalogQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("list channels: %v", err)
	}
	if len(channels) != 1 {
		t.Fatalf("expected one channel, got %#v", channels)
	}
	channel := channels[0]
	if channel.ChannelID != "channel-1" || channel.Name != "Draft Channel" || channel.Scope != "tenant" {
		t.Fatalf("unexpected channel: %#v", channel)
	}
	if channel.Provider != "openai-compatible" || channel.MaxConcurrency != 4 || !channel.Enabled {
		t.Fatalf("unexpected channel metadata: %#v", channel)
	}
	if !strings.Contains(queryer.query, "FROM llm_channels") {
		t.Fatalf("expected channel query over llm_channels, got %s", queryer.query)
	}
	if strings.Contains(strings.ToLower(queryer.query), "encrypted_api_key") {
		t.Fatalf("catalog query must not select encrypted_api_key: %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "(tenant_id::text = $1 OR tenant_id IS NULL)") {
		t.Fatalf("expected tenant/platform visibility filter, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLCatalogReaderListsSanitizedModelsForVisibleChannel(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"model-1",
				"provider-owner",
				128000,
				true,
				true,
				0.25,
				1.25,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLCatalogReader(SQLCatalogConfig{Queryer: queryer})

	models, err := reader.ListModels(context.Background(), ModelQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ChannelID: "channel-1",
	})

	if err != nil {
		t.Fatalf("list models: %v", err)
	}
	if len(models) != 1 {
		t.Fatalf("expected one model, got %#v", models)
	}
	model := models[0]
	if model.ModelID != "model-1" || model.OwnedBy != "provider-owner" || model.ContextWindow != 128000 {
		t.Fatalf("unexpected model: %#v", model)
	}
	if !model.SupportsTools || !model.SupportsJSON || model.InputCost != 0.25 || model.OutputCost != 1.25 {
		t.Fatalf("unexpected model metadata: %#v", model)
	}
	if !strings.Contains(queryer.query, "FROM llm_models") || !strings.Contains(queryer.query, "JOIN llm_channels") {
		t.Fatalf("expected model query to validate visible channel, got %s", queryer.query)
	}
	if strings.Contains(queryer.query, "raw_payload_jsonb") {
		t.Fatalf("model catalog must not expose raw provider payloads: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "channel-1", 100}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLCatalogReaderRejectsMissingContext(t *testing.T) {
	reader := NewSQLCatalogReader(SQLCatalogConfig{Queryer: &recordingSQLQueryer{}})

	_, err := reader.ListChannels(context.Background(), CatalogQueryInput{TenantID: "", ProjectID: "project-123"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for channels, got %s (%v)", code, err)
	}

	_, err = reader.ListModels(context.Background(), ModelQueryInput{TenantID: "tenant-123", ProjectID: "project-123"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for models, got %s (%v)", code, err)
	}
}

func TestSQLChannelStoreCreatesTenantChannelWithEncryptedCredential(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Draft Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				3,
				true,
				"",
				"",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: strings.Repeat("1", 64),
	})

	channel, err := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID:       "tenant-123",
		Name:           "Draft Channel",
		Provider:       "openai-compatible",
		BaseURL:        "https://llm.example.test/v1",
		APIKey:         "sk-secret",
		MaxConcurrency: 3,
		Enabled:        true,
	})

	if err != nil {
		t.Fatalf("create channel: %v", err)
	}
	if channel.ChannelID != "channel-1" || channel.Name != "Draft Channel" || channel.Scope != "tenant" {
		t.Fatalf("unexpected channel: %#v", channel)
	}
	if !strings.Contains(queryer.query, "INSERT INTO llm_channels") || !strings.Contains(queryer.query, "encrypted_api_key") {
		t.Fatalf("expected channel insert with encrypted credential, got %s", queryer.query)
	}
	if len(queryer.args) != 7 || queryer.args[0] != "tenant-123" || queryer.args[1] != "Draft Channel" || queryer.args[2] != "openai-compatible" || queryer.args[3] != "https://llm.example.test/v1" || queryer.args[5] != 3 || queryer.args[6] != true {
		t.Fatalf("unexpected create args: %#v", queryer.args)
	}
	encrypted, ok := queryer.args[4].(string)
	if !ok || encrypted == "" {
		t.Fatalf("expected encrypted credential arg, got %#v", queryer.args[4])
	}
	if encrypted == "sk-secret" || !strings.HasPrefix(encrypted, "aes-256-gcm:v1:") {
		t.Fatalf("credential was not encrypted with expected envelope: %#v", encrypted)
	}
}

func TestSQLChannelStorePatchesTenantChannelWithoutLeakingCredential(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Renamed Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				5,
				false,
				"",
				"",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: strings.Repeat("2", 64),
	})

	channel, err := store.UpdateChannel(context.Background(), UpdateChannelInput{
		TenantID:       "tenant-123",
		ChannelID:      "channel-1",
		Name:           "Renamed Channel",
		BaseURL:        "https://llm.example.test/v1",
		MaxConcurrency: 5,
		Enabled:        false,
	})

	if err != nil {
		t.Fatalf("update channel: %v", err)
	}
	if channel.Name != "Renamed Channel" || channel.Enabled {
		t.Fatalf("unexpected channel: %#v", channel)
	}
	if !strings.Contains(queryer.query, "UPDATE llm_channels") || !strings.Contains(queryer.query, "COALESCE(NULLIF($6, ''), encrypted_api_key)") {
		t.Fatalf("expected patch to preserve credential when api key omitted, got %s", queryer.query)
	}
	if len(queryer.args) != 7 || queryer.args[0] != "tenant-123" || queryer.args[1] != "channel-1" || queryer.args[5] != "" {
		t.Fatalf("unexpected update args: %#v", queryer.args)
	}
}

func TestSQLChannelStoreDeletesTenantChannel(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Draft Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				3,
				false,
				"",
				"",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: queryer})

	channel, err := store.DeleteChannel(context.Background(), DeleteChannelInput{
		TenantID:  "tenant-123",
		ChannelID: "channel-1",
	})

	if err != nil {
		t.Fatalf("delete channel: %v", err)
	}
	if channel.ChannelID != "channel-1" || channel.Enabled {
		t.Fatalf("unexpected deleted channel: %#v", channel)
	}
	if !strings.Contains(queryer.query, "UPDATE llm_channels") || !strings.Contains(queryer.query, "enabled = FALSE") {
		t.Fatalf("expected soft delete update, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "channel-1"}) {
		t.Fatalf("unexpected delete args: %#v", queryer.args)
	}
}

func TestSQLChannelStoreFailsClosedWithoutCredentialKey(t *testing.T) {
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: &recordingSQLQueryer{rows: &fakeSQLRows{}}})

	_, err := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID:       "tenant-123",
		Name:           "Draft Channel",
		Provider:       "openai-compatible",
		BaseURL:        "https://llm.example.test/v1",
		APIKey:         "sk-secret",
		MaxConcurrency: 1,
		Enabled:        true,
	})

	if code := ErrorCode(err); code != "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED" {
		t.Fatalf("expected credential encryption error, got %s (%v)", code, err)
	}
}

func TestDisabledCatalogReaderFailsExplicitly(t *testing.T) {
	reader := NewDisabledCatalogReader()

	_, err := reader.ListChannels(context.Background(), CatalogQueryInput{TenantID: "tenant-123", ProjectID: "project-123"})
	if code := ErrorCode(err); code != "LLM_CATALOG_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected disabled catalog error, got %s (%v)", code, err)
	}

	_, err = reader.ListModels(context.Background(), ModelQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ChannelID: "channel-1",
	})
	if code := ErrorCode(err); code != "LLM_CATALOG_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected disabled catalog error, got %s (%v)", code, err)
	}
}
