package llm

import (
	"context"
	"database/sql"
	"encoding/json"
	"os"
	"strings"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveCatalogTenantA  = "77000000-0000-4000-8000-000000000001"
	liveCatalogTenantB  = "77000000-0000-4000-8000-000000000002"
	liveCatalogChannelB = "78000000-0000-4000-8000-000000000002"
	liveCatalogPlatform = "78000000-0000-4000-8000-000000000003"
)

func TestLiveCatalogAppRoleCreateListModelsUpdateDeleteAndRLS(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_LLM_CATALOG_LIVE_DATABASE_URL"))
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_LLM_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_LLM_CATALOG_LIVE_DATABASE_URL to run live catalog/RLS certification")
	}
	adminDB := prepareLiveCatalogDatabase(t, adminURL)
	defer adminDB.Close()

	appDB, err := sql.Open("pgx", liveAppDatabaseURL(t, adminURL))
	if err != nil {
		t.Fatalf("open catalog app database: %v", err)
	}
	defer appDB.Close()
	queryer := NewSQLDBQueryer(appDB)
	keyMaterial := strings.Repeat("c", 64)
	store := NewSQLChannelStore(SQLChannelStoreConfig{Queryer: queryer, CredentialKeyMaterial: keyMaterial})
	reader := NewSQLCatalogReader(SQLCatalogConfig{Queryer: queryer})

	created, err := store.CreateChannel(context.Background(), CreateChannelInput{
		TenantID: liveCatalogTenantA, Name: "Catalog Live A", Provider: "openai-compatible",
		BaseURL: "https://catalog-live.example.test/v1", APIKey: "catalog-live-private-key",
		MaxConcurrency: 2, ExternalProviderOptIn: true, Enabled: true,
	})
	if err != nil {
		t.Fatalf("create app-role channel: %v", err)
	}
	if created.ChannelID == "" || created.Scope != "tenant" || !created.ExternalProviderOptIn {
		t.Fatalf("unexpected created channel: %#v", created)
	}
	assertLiveCatalogCredentialPrivate(t, adminDB, created, keyMaterial)

	if _, err := adminDB.Exec(`INSERT INTO llm_models (
  tenant_id, channel_id, model_id, owned_by, context_window, supports_tools, supports_json, input_cost, output_cost, enabled
) VALUES ($1,$2,'catalog-live-model-a','catalog-live',128000,true,true,0.1,0.2,true)`, liveCatalogTenantA, created.ChannelID); err != nil {
		t.Fatalf("seed tenant A model: %v", err)
	}

	channels, err := reader.ListChannels(context.Background(), CatalogQueryInput{
		TenantID: liveCatalogTenantA, ProjectID: "79000000-0000-4000-8000-000000000001",
	})
	if err != nil {
		t.Fatalf("list app-role channels: %v", err)
	}
	if len(channels) != 2 || !hasLiveCatalogChannel(channels, created.ChannelID, "tenant") || !hasLiveCatalogChannel(channels, liveCatalogPlatform, "platform") {
		t.Fatalf("cross-tenant channel visible or own channel missing: %#v", channels)
	}
	models, err := reader.ListModels(context.Background(), ModelQueryInput{
		TenantID: liveCatalogTenantA, ProjectID: "79000000-0000-4000-8000-000000000001", ChannelID: created.ChannelID,
	})
	if err != nil {
		t.Fatalf("list app-role models: %v", err)
	}
	if len(models) != 1 || models[0].ModelID != "catalog-live-model-a" || !models[0].SupportsTools || !models[0].SupportsJSON {
		t.Fatalf("unexpected tenant A models: %#v", models)
	}
	crossTenantModels, err := reader.ListModels(context.Background(), ModelQueryInput{
		TenantID: liveCatalogTenantA, ProjectID: "79000000-0000-4000-8000-000000000001", ChannelID: liveCatalogChannelB,
	})
	if err != nil {
		t.Fatalf("list cross-tenant channel models: %v", err)
	}
	if len(crossTenantModels) != 0 {
		t.Fatalf("RLS exposed cross-tenant models: %#v", crossTenantModels)
	}
	platformModels, err := reader.ListModels(context.Background(), ModelQueryInput{
		TenantID: liveCatalogTenantA, ProjectID: "79000000-0000-4000-8000-000000000001", ChannelID: liveCatalogPlatform,
	})
	if err != nil || len(platformModels) != 1 || platformModels[0].ModelID != "catalog-platform-model" {
		t.Fatalf("platform model is not visible to tenant app role: models=%#v err=%v", platformModels, err)
	}
	assertLiveCatalogPlatformReadOnly(t, appDB, store, adminDB)

	updated, err := store.UpdateChannel(context.Background(), UpdateChannelInput{
		TenantID: liveCatalogTenantA, ChannelID: created.ChannelID, Name: "Catalog Live A Updated",
		BaseURL: "https://catalog-live.example.test/v1", MaxConcurrency: 4,
		ExternalProviderOptIn: true, Enabled: true,
	})
	if err != nil || updated.Name != "Catalog Live A Updated" || updated.MaxConcurrency != 4 {
		t.Fatalf("update app-role channel: channel=%#v err=%v", updated, err)
	}
	deleted, err := store.DeleteChannel(context.Background(), DeleteChannelInput{
		TenantID: liveCatalogTenantA, ChannelID: created.ChannelID,
	})
	if err != nil || deleted.Enabled {
		t.Fatalf("delete app-role channel: channel=%#v err=%v", deleted, err)
	}
}

func hasLiveCatalogChannel(channels []ChannelRecord, channelID, scope string) bool {
	for _, channel := range channels {
		if channel.ChannelID == channelID && channel.Scope == scope {
			return true
		}
	}
	return false
}

func assertLiveCatalogPlatformReadOnly(t *testing.T, appDB *sql.DB, store *SQLChannelStore, adminDB *sql.DB) {
	t.Helper()
	if _, err := store.UpdateChannel(context.Background(), UpdateChannelInput{
		TenantID: liveCatalogTenantA, ChannelID: liveCatalogPlatform, Name: "forbidden",
		BaseURL: "https://forbidden.example.test/v1", MaxConcurrency: 9, ExternalProviderOptIn: true, Enabled: false,
	}); ErrorCode(err) != "LLM_CHANNEL_NOT_FOUND" {
		t.Fatalf("tenant store updated platform channel: code=%s err=%v", ErrorCode(err), err)
	}
	if _, err := store.DeleteChannel(context.Background(), DeleteChannelInput{
		TenantID: liveCatalogTenantA, ChannelID: liveCatalogPlatform,
	}); ErrorCode(err) != "LLM_CHANNEL_NOT_FOUND" {
		t.Fatalf("tenant store deleted platform channel: code=%s err=%v", ErrorCode(err), err)
	}
	var name string
	var enabled bool
	if err := adminDB.QueryRow("SELECT name,enabled FROM llm_channels WHERE channel_id=$1", liveCatalogPlatform).Scan(&name, &enabled); err != nil || name != "Catalog Platform" || !enabled {
		t.Fatalf("platform channel changed through tenant store: name=%q enabled=%v err=%v", name, enabled, err)
	}
	tx, err := appDB.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("begin platform insert RLS probe: %v", err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec("SELECT app_set_tenant_context($1::uuid,NULL::uuid,false)", liveCatalogTenantA); err != nil {
		t.Fatalf("set platform insert tenant context: %v", err)
	}
	_, err = tx.Exec(`INSERT INTO llm_channels(tenant_id,name,provider,base_url,encrypted_api_key,max_concurrency,enabled)
VALUES(NULL,'forbidden-platform','openai-compatible','https://forbidden.invalid/v1','forbidden',1,true)`)
	if err == nil {
		t.Fatal("tenant app role inserted a platform channel")
	}
}

func prepareLiveCatalogDatabase(t *testing.T, adminURL string) *sql.DB {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open catalog admin database: %v", err)
	}
	var ready bool
	if err := db.QueryRow(`SELECT
	  EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version='0014_llm_platform_defaults')
	  AND to_regclass('public.llm_channels') IS NOT NULL
	  AND to_regclass('public.llm_models') IS NOT NULL
	  AND to_regclass('public.llm_platform_module_defaults') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		db.Close()
		t.Fatalf("live catalog database must be current schema-init output: ready=%v err=%v", ready, err)
	}
	if _, err := db.Exec("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_live_app') THEN CREATE ROLE mirofish_live_app LOGIN PASSWORD 'mirofish_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_live_app WITH LOGIN PASSWORD 'mirofish_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_live_app;"); err != nil {
		db.Close()
		t.Fatalf("ensure catalog app role: %v", err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveCatalogTenantA, liveCatalogTenantB); err != nil {
		db.Close()
		t.Fatalf("cleanup catalog tenants: %v", err)
	}
	if _, err := db.Exec("DELETE FROM llm_platform_module_defaults WHERE channel_id=$1", liveCatalogPlatform); err != nil {
		db.Close()
		t.Fatalf("cleanup catalog platform defaults: %v", err)
	}
	if _, err := db.Exec("DELETE FROM llm_channels WHERE channel_id=$1", liveCatalogPlatform); err != nil {
		db.Close()
		t.Fatalf("cleanup catalog platform channel: %v", err)
	}
	t.Cleanup(func() {
		cleanupDB, cleanupErr := sql.Open("pgx", adminURL)
		if cleanupErr == nil {
			defer cleanupDB.Close()
			_, _ = cleanupDB.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveCatalogTenantA, liveCatalogTenantB)
			_, _ = cleanupDB.Exec("DELETE FROM llm_platform_module_defaults WHERE channel_id=$1", liveCatalogPlatform)
			_, _ = cleanupDB.Exec("DELETE FROM llm_channels WHERE channel_id=$1", liveCatalogPlatform)
		}
	})
	for _, fixture := range []struct{ tenantID, slug string }{
		{liveCatalogTenantA, "catalog-live-a"},
		{liveCatalogTenantB, "catalog-live-b"},
	} {
		if _, err := db.Exec("INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES($1,$2,$2,'personal')", fixture.tenantID, fixture.slug); err != nil {
			db.Close()
			t.Fatalf("seed catalog tenant: %v", err)
		}
	}
	if _, err := db.Exec(`INSERT INTO llm_channels (
  tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, external_provider_opt_in, enabled
) VALUES ($1,$2,'Catalog Live B','openai-compatible','https://catalog-live-b.example.test/v1','private-tenant-b',1,true,true)`, liveCatalogTenantB, liveCatalogChannelB); err != nil {
		db.Close()
		t.Fatalf("seed tenant B channel: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_models(tenant_id,channel_id,model_id,owned_by,enabled)
VALUES($1,$2,'catalog-live-model-b','catalog-live-b',true)`, liveCatalogTenantB, liveCatalogChannelB); err != nil {
		db.Close()
		t.Fatalf("seed tenant B model: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_channels(
  tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency,external_provider_opt_in,enabled
) VALUES(NULL,$1,'Catalog Platform','openai-compatible','https://catalog-platform.example.test/v1','platform-private',3,true,true)`, liveCatalogPlatform); err != nil {
		db.Close()
		t.Fatalf("seed catalog platform channel: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_models(tenant_id,channel_id,model_id,owned_by,supports_tools,supports_json,enabled)
VALUES(NULL,$1,'catalog-platform-model','catalog-platform',true,true,true)`, liveCatalogPlatform); err != nil {
		db.Close()
		t.Fatalf("seed catalog platform model: %v", err)
	}
	return db
}

func assertLiveCatalogCredentialPrivate(t *testing.T, adminDB *sql.DB, channel ChannelRecord, keyMaterial string) {
	t.Helper()
	var encrypted string
	if err := adminDB.QueryRow("SELECT encrypted_api_key FROM llm_channels WHERE tenant_id=$1 AND channel_id=$2", liveCatalogTenantA, channel.ChannelID).Scan(&encrypted); err != nil {
		t.Fatalf("read persisted encrypted credential: %v", err)
	}
	if encrypted == "catalog-live-private-key" || !strings.HasPrefix(encrypted, "aes-256-gcm:v1:") {
		t.Fatalf("credential was not stored as an encrypted envelope")
	}
	encoded, err := json.Marshal(channel)
	if err != nil {
		t.Fatalf("encode public channel: %v", err)
	}
	for _, forbidden := range []string{"catalog-live-private-key", encrypted, keyMaterial, "encrypted_api_key", "credential_ref"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("public channel exposed private credential material")
		}
	}
}
