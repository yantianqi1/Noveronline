package llm

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLCatalogReaderListsSanitizedChannelsForTenantAndPlatform(t *testing.T) {
	queryer := &tenantRecordingSQLQueryer{
		recordingSQLQueryer: &recordingSQLQueryer{rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Draft Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				4,
				true,
				true,
				"2026-07-04T00:00:00Z",
				"ok",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		}},
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
	if queryer.tenantReadID != "tenant-123" || queryer.rawCalls != 0 {
		t.Fatalf("catalog query bypassed tenant context: tenant=%q raw_calls=%d", queryer.tenantReadID, queryer.rawCalls)
	}
}

func TestSQLCatalogReaderListsSanitizedModelsForVisibleChannel(t *testing.T) {
	queryer := &tenantRecordingSQLQueryer{
		recordingSQLQueryer: &recordingSQLQueryer{rows: &fakeSQLRows{
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
		}},
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
	if queryer.tenantReadID != "tenant-123" || queryer.rawCalls != 0 {
		t.Fatalf("model query bypassed tenant context: tenant=%q raw_calls=%d", queryer.tenantReadID, queryer.rawCalls)
	}
}

func TestSQLCatalogReaderFailsClosedWithoutTenantQueryInterface(t *testing.T) {
	raw := &rawOnlySQLQueryer{rows: &fakeSQLRows{}}
	reader := NewSQLCatalogReader(SQLCatalogConfig{Queryer: raw})

	_, channelsErr := reader.ListChannels(context.Background(), CatalogQueryInput{TenantID: "tenant-123", ProjectID: "project-123"})
	_, modelsErr := reader.ListModels(context.Background(), ModelQueryInput{TenantID: "tenant-123", ProjectID: "project-123", ChannelID: "channel-123"})
	for _, err := range []error{channelsErr, modelsErr} {
		if code := ErrorCode(err); code != "LLM_CATALOG_BACKEND_UNCONFIGURED" {
			t.Fatalf("expected tenant query interface failure, got %s (%v)", code, err)
		}
	}
	if raw.calls != 0 {
		t.Fatalf("catalog fell back to raw QueryContext: calls=%d", raw.calls)
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
	queryer := &tenantRecordingSQLQueryer{
		recordingSQLQueryer: &recordingSQLQueryer{rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Draft Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				3,
				true,
				true,
				"",
				"",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		}},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: strings.Repeat("1", 64),
	})

	channel, err := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID:              "tenant-123",
		Name:                  "Draft Channel",
		Provider:              "openai-compatible",
		BaseURL:               "https://llm.example.test/v1",
		APIKey:                "sk-secret",
		MaxConcurrency:        3,
		ExternalProviderOptIn: true,
		Enabled:               true,
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
	if len(queryer.args) != 8 || queryer.args[0] != "tenant-123" || queryer.args[1] != "Draft Channel" || queryer.args[2] != "openai-compatible" || queryer.args[3] != "https://llm.example.test/v1" || queryer.args[5] != 3 || queryer.args[6] != true || queryer.args[7] != true {
		t.Fatalf("unexpected create args: %#v", queryer.args)
	}
	encrypted, ok := queryer.args[4].(string)
	if !ok || encrypted == "" {
		t.Fatalf("expected encrypted credential arg, got %#v", queryer.args[4])
	}
	if encrypted == "sk-secret" || !strings.HasPrefix(encrypted, "aes-256-gcm:v1:") {
		t.Fatalf("credential was not encrypted with expected envelope: %#v", encrypted)
	}
	if queryer.tenantWriteID != "tenant-123" || queryer.rawCalls != 0 {
		t.Fatalf("channel create bypassed tenant write context: tenant=%q raw_calls=%d", queryer.tenantWriteID, queryer.rawCalls)
	}
}

func TestSQLChannelStorePatchesTenantChannelWithoutLeakingCredential(t *testing.T) {
	queryer := &tenantRecordingSQLQueryer{
		recordingSQLQueryer: &recordingSQLQueryer{rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Renamed Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				5,
				true,
				false,
				"",
				"",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		}},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{
		Queryer:               queryer,
		CredentialKeyMaterial: strings.Repeat("2", 64),
	})

	channel, err := store.UpdateChannel(context.Background(), UpdateChannelInput{
		TenantID:              "tenant-123",
		ChannelID:             "channel-1",
		Name:                  "Renamed Channel",
		BaseURL:               "https://llm.example.test/v1",
		MaxConcurrency:        5,
		ExternalProviderOptIn: true,
		Enabled:               false,
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
	if len(queryer.args) != 8 || queryer.args[0] != "tenant-123" || queryer.args[1] != "channel-1" || queryer.args[5] != "" {
		t.Fatalf("unexpected update args: %#v", queryer.args)
	}
	if queryer.tenantWriteID != "tenant-123" || queryer.rawCalls != 0 {
		t.Fatalf("channel update bypassed tenant write context: tenant=%q raw_calls=%d", queryer.tenantWriteID, queryer.rawCalls)
	}
}

func TestSQLChannelStoreUpdatesTenantModelMetadata(t *testing.T) {
	queryer := &tenantRecordingSQLQueryer{
		recordingSQLQueryer: &recordingSQLQueryer{rows: &fakeSQLRows{
			values: [][]any{{
				"gpt-5.5",
				"provider",
				128000,
				true,
				true,
				0.001,
				0.002,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		}},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: queryer})
	contextWindow := 128000
	inputCost := 0.001
	outputCost := 0.002

	model, err := store.UpdateModel(context.Background(), UpdateModelInput{
		TenantID:      "tenant-123",
		ChannelID:     "channel-1",
		ModelID:       "gpt-5.5",
		ContextWindow: &contextWindow,
		SupportsTools: true,
		SupportsJSON:  true,
		InputCost:     &inputCost,
		OutputCost:    &outputCost,
	})

	if err != nil {
		t.Fatalf("update model: %v", err)
	}
	if model.ModelID != "gpt-5.5" || model.ContextWindow != 128000 || !model.SupportsJSON || model.InputCost != 0.001 {
		t.Fatalf("unexpected model: %#v", model)
	}
	if !strings.Contains(queryer.query, "UPDATE llm_models") || !strings.Contains(queryer.query, "context_window") {
		t.Fatalf("expected model metadata update query, got %s", queryer.query)
	}
	if queryer.tenantWriteID != "tenant-123" || queryer.rawCalls != 0 {
		t.Fatalf("model update bypassed tenant write context: tenant=%q raw_calls=%d", queryer.tenantWriteID, queryer.rawCalls)
	}
	if len(queryer.args) != 8 || queryer.args[0] != "tenant-123" || queryer.args[1] != "channel-1" || queryer.args[2] != "gpt-5.5" {
		t.Fatalf("unexpected model update args: %#v", queryer.args)
	}
}

func TestSQLChannelStoreDeletesTenantChannel(t *testing.T) {
	queryer := &tenantRecordingSQLQueryer{
		recordingSQLQueryer: &recordingSQLQueryer{rows: &fakeSQLRows{
			values: [][]any{{
				"channel-1",
				"Draft Channel",
				"openai-compatible",
				"https://llm.example.test/v1",
				3,
				true,
				false,
				"",
				"",
				"tenant",
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		}},
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
	if queryer.tenantWriteID != "tenant-123" || queryer.rawCalls != 0 {
		t.Fatalf("channel delete bypassed tenant write context: tenant=%q raw_calls=%d", queryer.tenantWriteID, queryer.rawCalls)
	}
}

func TestSQLChannelStoreFailsClosedWithoutTenantWriteInterface(t *testing.T) {
	raw := &rawOnlySQLQueryer{rows: &fakeSQLRows{}}
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: raw, CredentialKeyMaterial: strings.Repeat("3", 64)})

	_, createErr := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID: "tenant-123", Name: "External", Provider: "openai-compatible",
		BaseURL: "https://llm.example.test/v1", APIKey: "sk-secret", MaxConcurrency: 1,
		ExternalProviderOptIn: true, Enabled: true,
	})
	_, updateErr := store.UpdateChannel(context.Background(), UpdateChannelInput{
		TenantID: "tenant-123", ChannelID: "channel-123", Name: "External",
		BaseURL: "https://llm.example.test/v1", MaxConcurrency: 1,
		ExternalProviderOptIn: true, Enabled: true,
	})
	_, deleteErr := store.DeleteChannel(context.Background(), DeleteChannelInput{TenantID: "tenant-123", ChannelID: "channel-123"})
	for _, err := range []error{createErr, updateErr, deleteErr} {
		if code := ErrorCode(err); code != "LLM_CHANNEL_BACKEND_UNCONFIGURED" {
			t.Fatalf("expected tenant write interface failure, got %s (%v)", code, err)
		}
	}
	if raw.calls != 0 {
		t.Fatalf("channel store fell back to raw QueryContext: calls=%d", raw.calls)
	}
}

func TestSQLChannelStoreCommitsOnlyAfterReturnedRowsAreExhausted(t *testing.T) {
	tx := &transactionFinalizerFixture{}
	queryer := &catalogTransactionQueryer{
		rows: &tenantScopedWriteRows{rows: channelRowsFixture(), tx: tx},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: queryer, CredentialKeyMaterial: strings.Repeat("4", 64)})

	_, err := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID: "tenant-123", Name: "External", Provider: "openai-compatible",
		BaseURL: "https://llm.example.test/v1", APIKey: "sk-secret", MaxConcurrency: 1,
		ExternalProviderOptIn: true, Enabled: true,
	})
	if err != nil {
		t.Fatalf("create channel: %v", err)
	}
	if tx.commits != 1 || tx.rollbacks != 0 {
		t.Fatalf("write transaction finalization mismatch: commits=%d rollbacks=%d", tx.commits, tx.rollbacks)
	}
}

func TestSQLChannelStoreRollsBackWhenReturnedRowCannotBeScanned(t *testing.T) {
	tx := &transactionFinalizerFixture{}
	queryer := &catalogTransactionQueryer{
		rows: &tenantScopedWriteRows{rows: &catalogScanErrorRows{rows: channelRowsFixture(), err: errors.New("scan failed")}, tx: tx},
	}
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: queryer, CredentialKeyMaterial: strings.Repeat("5", 64)})

	_, err := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID: "tenant-123", Name: "External", Provider: "openai-compatible",
		BaseURL: "https://llm.example.test/v1", APIKey: "sk-secret", MaxConcurrency: 1,
		ExternalProviderOptIn: true, Enabled: true,
	})
	if code := ErrorCode(err); code != "LLM_CHANNEL_UPDATE_FAILED" {
		t.Fatalf("expected scan failure, got %s (%v)", code, err)
	}
	if tx.commits != 0 || tx.rollbacks != 1 {
		t.Fatalf("failed write transaction finalization mismatch: commits=%d rollbacks=%d", tx.commits, tx.rollbacks)
	}
}

func channelRowsFixture() *fakeSQLRows {
	return &fakeSQLRows{values: [][]any{{
		"channel-1", "External", "openai-compatible", "https://llm.example.test/v1",
		1, true, true, "", "", "tenant", "2026-07-11T00:00:00Z", "2026-07-11T00:00:00Z",
	}}}
}

type rawOnlySQLQueryer struct {
	rows  SQLRows
	calls int
}

type tenantRecordingSQLQueryer struct {
	*recordingSQLQueryer
	tenantReadID  string
	tenantWriteID string
	rawCalls      int
}

func (q *tenantRecordingSQLQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.rawCalls++
	return q.recordingSQLQueryer.QueryContext(ctx, query, args...)
}

func (q *tenantRecordingSQLQueryer) QueryTenantContext(ctx context.Context, tenantID, query string, args ...any) (SQLRows, error) {
	q.tenantReadID = tenantID
	return q.recordingSQLQueryer.QueryContext(ctx, query, args...)
}

func (q *tenantRecordingSQLQueryer) QueryTenantWriteContext(ctx context.Context, tenantID, query string, args ...any) (SQLRows, error) {
	q.tenantWriteID = tenantID
	return q.recordingSQLQueryer.QueryContext(ctx, query, args...)
}

type catalogScanErrorRows struct {
	rows SQLRows
	err  error
}

func (r *catalogScanErrorRows) Next() bool        { return r.rows.Next() }
func (r *catalogScanErrorRows) Scan(...any) error { return r.err }
func (r *catalogScanErrorRows) Close() error      { return r.rows.Close() }
func (r *catalogScanErrorRows) Err() error        { return r.rows.Err() }

func (q *rawOnlySQLQueryer) QueryContext(context.Context, string, ...any) (SQLRows, error) {
	q.calls++
	return q.rows, nil
}

type catalogTransactionQueryer struct {
	rows SQLRows
}

func (q *catalogTransactionQueryer) QueryContext(context.Context, string, ...any) (SQLRows, error) {
	return nil, errors.New("raw QueryContext must not be called")
}

func (q *catalogTransactionQueryer) QueryTenantWriteContext(context.Context, string, string, ...any) (SQLRows, error) {
	return q.rows, nil
}

func TestSQLChannelStoreFailsClosedWithoutCredentialKey(t *testing.T) {
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: &tenantRecordingSQLQueryer{recordingSQLQueryer: &recordingSQLQueryer{rows: &fakeSQLRows{}}}})

	_, err := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID:              "tenant-123",
		Name:                  "Draft Channel",
		Provider:              "openai-compatible",
		BaseURL:               "https://llm.example.test/v1",
		APIKey:                "sk-secret",
		MaxConcurrency:        1,
		ExternalProviderOptIn: true,
		Enabled:               true,
	})

	if code := ErrorCode(err); code != "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED" {
		t.Fatalf("expected credential encryption error, got %s (%v)", code, err)
	}
}

func TestCredentialDecryptorRequiresConfiguredKeyAndDecryptsStoredEnvelope(t *testing.T) {
	if _, err := NewCredentialDecryptor(""); ErrorCode(err) != "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED" {
		t.Fatalf("missing credential key did not fail closed: %v", err)
	}
	if _, err := NewCredentialDecryptor("not-a-key"); ErrorCode(err) != "LLM_CREDENTIAL_KEY_INVALID" {
		t.Fatalf("invalid credential key was accepted: %v", err)
	}

	keyMaterial := strings.Repeat("7", 64)
	store := NewSQLChannelStore(SQLChannelStoreConfig{CredentialKeyMaterial: keyMaterial})
	envelope, err := store.encryptCredential("sk-production-health")
	if err != nil {
		t.Fatalf("encrypt fixture credential: %v", err)
	}
	decryptor, err := NewCredentialDecryptor(keyMaterial)
	if err != nil {
		t.Fatalf("construct decryptor: %v", err)
	}
	plaintext, err := decryptor.Decrypt(envelope)
	if err != nil || plaintext != "sk-production-health" {
		t.Fatalf("decrypt stored envelope: plaintext=%q err=%v", plaintext, err)
	}
}

func TestHealthCapabilityDiscoveryDoesNotOverwriteOperatorFlags(t *testing.T) {
	queryer := &recordingSQLQueryer{rows: &fakeSQLRows{}}
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: queryer})

	if err := store.UpgradeModelCapabilities(context.Background(), "tenant-1", "channel-1", "model-1", true, true); err != nil {
		t.Fatalf("capability discovery: %v", err)
	}
	if queryer.query != "" {
		t.Fatalf("health discovery mutated operator-managed capability flags: %s", queryer.query)
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
