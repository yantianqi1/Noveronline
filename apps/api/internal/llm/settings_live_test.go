package llm

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveSettingsTenantA  = "85000000-0000-4000-8000-000000000001"
	liveSettingsTenantB  = "85000000-0000-4000-8000-000000000002"
	liveSettingsChannelA = "86000000-0000-4000-8000-000000000001"
	liveSettingsChannelB = "86000000-0000-4000-8000-000000000002"
	liveSettingsPlatform = "86000000-0000-4000-8000-000000000003"
)

func TestLiveSettingsReaderUsesTenantContextAndIncludesPlatformReadOnlyCatalog(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_LLM_SETTINGS_LIVE_DATABASE_URL"))
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_LLM_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_LLM_SETTINGS_LIVE_DATABASE_URL to run live settings/RLS certification")
	}
	adminDB := prepareLiveSettingsDatabase(t, adminURL)
	defer adminDB.Close()
	appDB, err := sql.Open("pgx", liveAppDatabaseURL(t, adminURL))
	if err != nil {
		t.Fatalf("open settings app database: %v", err)
	}
	defer appDB.Close()

	reader := NewSQLSettingsReader(SQLSettingsReaderConfig{Queryer: NewSQLDBQueryer(appDB)})
	snapshot, err := reader.GetSettings(context.Background(), SettingsInput{TenantID: liveSettingsTenantA})
	if err != nil {
		t.Fatalf("read app-role settings: %v", err)
	}
	if len(snapshot.Channels) != 2 || !hasLiveCatalogChannel(snapshot.Channels, liveSettingsChannelA, "tenant") || !hasLiveCatalogChannel(snapshot.Channels, liveSettingsPlatform, "platform") {
		t.Fatalf("settings did not return exactly own and platform channels: %#v", snapshot.Channels)
	}
	if len(snapshot.TenantBindings) != 1 || snapshot.TenantBindings[0].ModuleKey != "writer_composer" || snapshot.TenantBindings[0].Scope != "tenant" {
		t.Fatalf("settings tenant defaults are wrong: %#v", snapshot.TenantBindings)
	}
}

func prepareLiveSettingsDatabase(t *testing.T, adminURL string) *sql.DB {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open settings admin database: %v", err)
	}
	var ready bool
	if err := db.QueryRow(`SELECT EXISTS (
  SELECT 1 FROM mirofish_schema_migrations WHERE version='0014_llm_platform_defaults'
) AND to_regclass('public.llm_platform_module_defaults') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		db.Close()
		t.Fatalf("live settings database must include 0014: ready=%v err=%v", ready, err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveSettingsTenantA, liveSettingsTenantB); err != nil {
		db.Close()
		t.Fatalf("cleanup settings tenants: %v", err)
	}
	if _, err := db.Exec("DELETE FROM llm_platform_module_defaults WHERE channel_id=$1", liveSettingsPlatform); err != nil {
		db.Close()
		t.Fatalf("cleanup settings platform defaults: %v", err)
	}
	if _, err := db.Exec("DELETE FROM llm_channels WHERE channel_id=$1", liveSettingsPlatform); err != nil {
		db.Close()
		t.Fatalf("cleanup settings platform channel: %v", err)
	}
	t.Cleanup(func() {
		cleanupDB, cleanupErr := sql.Open("pgx", adminURL)
		if cleanupErr == nil {
			defer cleanupDB.Close()
			_, _ = cleanupDB.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveSettingsTenantA, liveSettingsTenantB)
			_, _ = cleanupDB.Exec("DELETE FROM llm_platform_module_defaults WHERE channel_id=$1", liveSettingsPlatform)
			_, _ = cleanupDB.Exec("DELETE FROM llm_channels WHERE channel_id=$1", liveSettingsPlatform)
		}
	})
	for _, tenant := range []struct{ id, slug string }{
		{liveSettingsTenantA, "settings-live-a"}, {liveSettingsTenantB, "settings-live-b"},
	} {
		if _, err := db.Exec("INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES($1,$2,$2,'personal')", tenant.id, tenant.slug); err != nil {
			db.Close()
			t.Fatalf("seed settings tenant: %v", err)
		}
	}
	for _, channel := range []struct{ tenantID, channelID, name string }{
		{liveSettingsTenantA, liveSettingsChannelA, "Settings A"},
		{liveSettingsTenantB, liveSettingsChannelB, "Settings B"},
	} {
		if _, err := db.Exec(`INSERT INTO llm_channels(tenant_id,channel_id,name,provider,base_url,encrypted_api_key,enabled)
VALUES($1,$2,$3,'openai-compatible','https://settings.example.test/v1','settings-private',true)`, channel.tenantID, channel.channelID, channel.name); err != nil {
			db.Close()
			t.Fatalf("seed settings channel: %v", err)
		}
		if _, err := db.Exec(`INSERT INTO llm_models(tenant_id,channel_id,model_id,enabled) VALUES($1,$2,'settings-model',true)`, channel.tenantID, channel.channelID); err != nil {
			db.Close()
			t.Fatalf("seed settings model: %v", err)
		}
	}
	if _, err := db.Exec(`INSERT INTO llm_channels(tenant_id,channel_id,name,provider,base_url,encrypted_api_key,enabled)
VALUES(NULL,$1,'Settings Platform','openai-compatible','https://settings-platform.example.test/v1','settings-platform-private',true)`, liveSettingsPlatform); err != nil {
		db.Close()
		t.Fatalf("seed settings platform channel: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_models(tenant_id,channel_id,model_id,enabled) VALUES(NULL,$1,'settings-platform-model',true)`, liveSettingsPlatform); err != nil {
		db.Close()
		t.Fatalf("seed settings platform model: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_module_bindings(tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb)
VALUES($1,NULL,'writer_composer',$2,'settings-model','{"max_concurrency":2}'::jsonb)`, liveSettingsTenantA, liveSettingsChannelA); err != nil {
		db.Close()
		t.Fatalf("seed settings tenant default: %v", err)
	}
	return db
}
