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
	liveBindingTenantA   = "81000000-0000-4000-8000-000000000001"
	liveBindingTenantB   = "81000000-0000-4000-8000-000000000002"
	liveBindingProjectA1 = "82000000-0000-4000-8000-000000000001"
	liveBindingProjectA2 = "82000000-0000-4000-8000-000000000002"
	liveBindingProjectB  = "82000000-0000-4000-8000-000000000003"
	liveBindingChannelA  = "83000000-0000-4000-8000-000000000001"
	liveBindingChannelB  = "83000000-0000-4000-8000-000000000002"
	liveBindingPlatform  = "83000000-0000-4000-8000-000000000003"
	liveBindingUser      = "84000000-0000-4000-8000-000000000001"
)

func TestLiveBindingStoreAppRoleListUpsertResolveDeleteAndRLS(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_LLM_BINDINGS_LIVE_DATABASE_URL"))
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_LLM_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_LLM_BINDINGS_LIVE_DATABASE_URL to run live binding/RLS certification")
	}
	prepareLiveBindingDatabase(t, adminURL)
	appDB, err := sql.Open("pgx", liveAppDatabaseURL(t, adminURL))
	if err != nil {
		t.Fatalf("open binding app database: %v", err)
	}
	defer appDB.Close()
	queryer := NewSQLDBQueryer(appDB)
	store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: queryer})
	resolver := NewSQLResolver(SQLResolverConfig{Queryer: queryer})

	created, err := store.UpsertProjectModuleBinding(context.Background(), UpsertProjectModuleBindingInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ActorID: liveBindingUser,
		ModuleKey: "writer_composer", ChannelID: liveBindingChannelA, ModelID: "binding-model-a",
		Settings: map[string]any{"temperature": 0.4},
	})
	if err != nil {
		t.Fatalf("upsert app-role binding: %v", err)
	}
	if created.Scope != "project" || created.ChannelID != liveBindingChannelA || created.ModelID != "binding-model-a" {
		t.Fatalf("unexpected created binding: %#v", created)
	}

	bindings, err := store.ListModuleBindings(context.Background(), ListModuleBindingsInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1,
	})
	if err != nil || len(bindings) != 3 || !hasLiveBinding(bindings, "writer_composer", "project") || !hasLiveBinding(bindings, "writer_reviewer", "platform") || !hasLiveBinding(bindings, "anchor_point_summary", "platform") {
		t.Fatalf("list app-role bindings: bindings=%#v err=%v", bindings, err)
	}
	resolution, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ModuleKey: "writer_composer",
	})
	if err != nil || resolution.ChannelID != liveBindingChannelA || resolution.CredentialRef != liveBindingChannelA {
		t.Fatalf("resolve app-role binding: resolution=%#v err=%v", resolution, err)
	}
	assertLiveBindingFallbackOrder(t, store, resolver)
	assertLiveBindingPlatformTarget(t, queryer, store, resolver)

	assertLiveBindingProjectIsolation(t, store, resolver)
	assertLiveBindingTargetOwnership(t, store)

	deleted, err := store.DeleteProjectModuleBinding(context.Background(), DeleteProjectModuleBindingInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ModuleKey: "writer_composer",
	})
	if err != nil || deleted.ChannelID != liveBindingChannelA {
		t.Fatalf("delete app-role binding: deleted=%#v err=%v", deleted, err)
	}
	bindings, err = store.ListModuleBindings(context.Background(), ListModuleBindingsInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1,
	})
	if err != nil || len(bindings) < 2 {
		t.Fatalf("fallback bindings missing after project delete: bindings=%#v err=%v", bindings, err)
	}
	resolution, err = resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ModuleKey: "writer_composer",
	})
	if err != nil || resolution.ChannelID != liveBindingChannelA || resolution.ProjectID != "" {
		t.Fatalf("project delete did not fall back to tenant default: resolution=%#v err=%v", resolution, err)
	}
}

func assertLiveBindingFallbackOrder(t *testing.T, store *SQLBindingStore, resolver *SQLResolver) {
	t.Helper()
	platform, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA2, ModuleKey: "writer_reviewer",
	})
	if err != nil || platform.ChannelID != liveBindingPlatform || platform.ProjectID != "" || platform.CredentialRef != liveBindingPlatform {
		t.Fatalf("platform default did not resolve: resolution=%#v err=%v", platform, err)
	}
	effective, err := store.ListModuleBindings(context.Background(), ListModuleBindingsInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA2,
	})
	if err != nil || !hasLiveBinding(effective, "writer_composer", "tenant") || !hasLiveBinding(effective, "writer_reviewer", "platform") {
		t.Fatalf("tenant/platform effective fallback list is wrong: bindings=%#v err=%v", effective, err)
	}
	disabledFallback, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ModuleKey: "anchor_point_summary",
	})
	if err != nil || disabledFallback.ChannelID != liveBindingPlatform {
		t.Fatalf("disabled project/tenant models did not fall through to platform: resolution=%#v err=%v", disabledFallback, err)
	}
	_, err = resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA2, ModuleKey: "unconfigured_module",
	})
	if ErrorCode(err) != "LLM_MODULE_UNBOUND" {
		t.Fatalf("missing all fallback levels did not fail explicitly: code=%s err=%v", ErrorCode(err), err)
	}
}

func assertLiveBindingPlatformTarget(t *testing.T, queryer SQLQueryer, store *SQLBindingStore, resolver *SQLResolver) {
	t.Helper()
	created, err := store.UpsertProjectModuleBinding(context.Background(), UpsertProjectModuleBindingInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ActorID: liveBindingUser,
		ModuleKey: "story_ontology", ChannelID: liveBindingPlatform, ModelID: "binding-platform-model",
	})
	if err != nil || created.ChannelID != liveBindingPlatform {
		t.Fatalf("tenant could not bind allowed platform target: binding=%#v err=%v", created, err)
	}
	resolution, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ModuleKey: "story_ontology",
	})
	if err != nil || resolution.CredentialRef != liveBindingPlatform {
		t.Fatalf("platform credential target did not resolve: resolution=%#v err=%v", resolution, err)
	}
	tenantQueryer, ok := queryer.(SQLTenantQueryer)
	if !ok {
		t.Fatal("live queryer does not support tenant context")
	}
	rows, err := tenantQueryer.QueryTenantContext(context.Background(), liveBindingTenantA,
		`SELECT encrypted_api_key,max_concurrency FROM llm_channels WHERE channel_id=$1 AND tenant_id IS NULL`, liveBindingPlatform)
	if err != nil {
		t.Fatalf("query platform credential/quota target: %v", err)
	}
	defer rows.Close()
	var encrypted string
	var maxConcurrency int
	if !rows.Next() || rows.Scan(&encrypted, &maxConcurrency) != nil || encrypted != "binding-platform-private" || maxConcurrency != 3 {
		t.Fatalf("platform credential/quota target unavailable: encrypted_present=%v max_concurrency=%d", encrypted != "", maxConcurrency)
	}
	if rows.Next() || rows.Err() != nil {
		t.Fatal("platform credential/quota query returned an invalid row set")
	}
}

func hasLiveBinding(bindings []ModuleBindingRecord, moduleKey, scope string) bool {
	for _, binding := range bindings {
		if binding.ModuleKey == moduleKey && binding.Scope == scope {
			return true
		}
	}
	return false
}

func assertLiveBindingProjectIsolation(t *testing.T, store *SQLBindingStore, resolver *SQLResolver) {
	t.Helper()
	bindings, err := store.ListModuleBindings(context.Background(), ListModuleBindingsInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA2,
	})
	if err != nil || len(bindings) != 3 || !hasLiveBinding(bindings, "writer_composer", "tenant") || !hasLiveBinding(bindings, "writer_reviewer", "platform") || !hasLiveBinding(bindings, "anchor_point_summary", "platform") {
		t.Fatalf("same-tenant project binding leaked: bindings=%#v err=%v", bindings, err)
	}
	resolution, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA2, ModuleKey: "writer_composer",
	})
	if err != nil || resolution.ProjectID != "" || resolution.ChannelID != liveBindingChannelA {
		t.Fatalf("same-tenant project did not receive tenant fallback: resolution=%#v err=%v", resolution, err)
	}
	bindings, err = store.ListModuleBindings(context.Background(), ListModuleBindingsInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectB,
	})
	if err != nil || len(bindings) != 3 || !hasLiveBinding(bindings, "writer_composer", "tenant") || !hasLiveBinding(bindings, "writer_reviewer", "platform") || !hasLiveBinding(bindings, "anchor_point_summary", "platform") {
		t.Fatalf("foreign project id changed tenant/platform fallbacks: bindings=%#v err=%v", bindings, err)
	}
	for _, binding := range bindings {
		if binding.ChannelID == liveBindingChannelB {
			t.Fatalf("cross-tenant binding leaked: %#v", bindings)
		}
	}
}

func assertLiveBindingTargetOwnership(t *testing.T, store *SQLBindingStore) {
	t.Helper()
	for _, target := range []struct {
		name      string
		channelID string
		modelID   string
	}{
		{name: "cross tenant channel and model", channelID: liveBindingChannelB, modelID: "binding-model-b"},
		{name: "model not owned by selected channel", channelID: liveBindingChannelA, modelID: "binding-model-b"},
	} {
		t.Run(target.name, func(t *testing.T) {
			_, err := store.UpsertProjectModuleBinding(context.Background(), UpsertProjectModuleBindingInput{
				TenantID: liveBindingTenantA, ProjectID: liveBindingProjectA1, ActorID: liveBindingUser,
				ModuleKey: "story_ontology", ChannelID: target.channelID, ModelID: target.modelID,
			})
			if ErrorCode(err) != "LLM_BINDING_TARGET_NOT_FOUND" {
				t.Fatalf("foreign target accepted: code=%s err=%v", ErrorCode(err), err)
			}
		})
	}
	_, err := store.UpsertProjectModuleBinding(context.Background(), UpsertProjectModuleBindingInput{
		TenantID: liveBindingTenantA, ProjectID: liveBindingProjectB, ActorID: liveBindingUser,
		ModuleKey: "story_ontology", ChannelID: liveBindingChannelA, ModelID: "binding-model-a",
	})
	if ErrorCode(err) != "LLM_BINDING_UPDATE_FAILED" {
		t.Fatalf("cross-tenant project accepted: code=%s err=%v", ErrorCode(err), err)
	}
}

func prepareLiveBindingDatabase(t *testing.T, adminURL string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open binding admin database: %v", err)
	}
	defer db.Close()
	var ready bool
	if err := db.QueryRow(`SELECT
	  EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version='0014_llm_platform_defaults')
	  AND to_regclass('public.llm_module_bindings') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		t.Fatalf("live binding database must be current schema-init output: ready=%v err=%v", ready, err)
	}
	if _, err := db.Exec("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_live_app') THEN CREATE ROLE mirofish_live_app LOGIN PASSWORD 'mirofish_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_live_app WITH LOGIN PASSWORD 'mirofish_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_live_app;"); err != nil {
		t.Fatalf("ensure binding app role: %v", err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveBindingTenantA, liveBindingTenantB); err != nil {
		t.Fatalf("cleanup binding tenants: %v", err)
	}
	if _, err := db.Exec("DELETE FROM llm_platform_module_defaults WHERE channel_id=$1", liveBindingPlatform); err != nil {
		t.Fatalf("cleanup binding platform defaults: %v", err)
	}
	if _, err := db.Exec("DELETE FROM llm_channels WHERE channel_id=$1", liveBindingPlatform); err != nil {
		t.Fatalf("cleanup binding platform channel: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO users(user_id,email,display_name)
VALUES($1,'binding-live@example.test','Binding Live')
ON CONFLICT(user_id) DO UPDATE SET display_name=EXCLUDED.display_name`, liveBindingUser); err != nil {
		t.Fatalf("seed binding user: %v", err)
	}
	t.Cleanup(func() {
		cleanupDB, cleanupErr := sql.Open("pgx", adminURL)
		if cleanupErr == nil {
			defer cleanupDB.Close()
			_, _ = cleanupDB.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveBindingTenantA, liveBindingTenantB)
			_, _ = cleanupDB.Exec("DELETE FROM llm_platform_module_defaults WHERE channel_id=$1", liveBindingPlatform)
			_, _ = cleanupDB.Exec("DELETE FROM llm_channels WHERE channel_id=$1", liveBindingPlatform)
			_, _ = cleanupDB.Exec("DELETE FROM users WHERE user_id=$1", liveBindingUser)
		}
	})
	for _, tenant := range []struct{ id, slug string }{
		{liveBindingTenantA, "binding-live-a"}, {liveBindingTenantB, "binding-live-b"},
	} {
		if _, err := db.Exec("INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES($1,$2,$2,'personal')", tenant.id, tenant.slug); err != nil {
			t.Fatalf("seed binding tenant: %v", err)
		}
	}
	for _, project := range []struct{ tenantID, projectID, title string }{
		{liveBindingTenantA, liveBindingProjectA1, "Binding A1"},
		{liveBindingTenantA, liveBindingProjectA2, "Binding A2"},
		{liveBindingTenantB, liveBindingProjectB, "Binding B"},
	} {
		if _, err := db.Exec("INSERT INTO projects(tenant_id,project_id,title,created_by) VALUES($1,$2,$3,$4)", project.tenantID, project.projectID, project.title, liveBindingUser); err != nil {
			t.Fatalf("seed binding project: %v", err)
		}
	}
	for _, channel := range []struct{ tenantID, channelID, name, model string }{
		{liveBindingTenantA, liveBindingChannelA, "Binding Channel A", "binding-model-a"},
		{liveBindingTenantB, liveBindingChannelB, "Binding Channel B", "binding-model-b"},
	} {
		if _, err := db.Exec(`INSERT INTO llm_channels(
  tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency,external_provider_opt_in,enabled
) VALUES($1,$2,$3,'openai-compatible','https://binding-live.example.test/v1','binding-live-private',1,true,true)`, channel.tenantID, channel.channelID, channel.name); err != nil {
			t.Fatalf("seed binding channel: %v", err)
		}
		if _, err := db.Exec(`INSERT INTO llm_models(
  tenant_id,channel_id,model_id,owned_by,supports_tools,supports_json,enabled
) VALUES($1,$2,$3,'binding-live',true,true,true)`, channel.tenantID, channel.channelID, channel.model); err != nil {
			t.Fatalf("seed binding model: %v", err)
		}
	}
	if _, err := db.Exec(`INSERT INTO llm_channels(
  tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency,external_provider_opt_in,enabled
) VALUES(NULL,$1,'Binding Platform','openai-compatible','https://binding-platform.example.test/v1','binding-platform-private',3,true,true)`, liveBindingPlatform); err != nil {
		t.Fatalf("seed binding platform channel: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_models(
  tenant_id,channel_id,model_id,owned_by,supports_tools,supports_json,enabled
) VALUES(NULL,$1,'binding-platform-model','binding-platform',true,true,true)`, liveBindingPlatform); err != nil {
		t.Fatalf("seed binding platform model: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_models(
  tenant_id,channel_id,model_id,owned_by,supports_tools,supports_json,enabled
) VALUES($1,$2,'binding-disabled-model','binding-live',true,true,false)`, liveBindingTenantA, liveBindingChannelA); err != nil {
		t.Fatalf("seed disabled tenant model: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_platform_module_defaults(module_key,channel_id,model_id,settings_jsonb,updated_by)
VALUES('writer_composer',$1,'binding-platform-model','{"temperature":0.1}'::jsonb,$2),
      ('writer_reviewer',$1,'binding-platform-model','{"temperature":0.2}'::jsonb,$2),
      ('anchor_point_summary',$1,'binding-platform-model','{"temperature":0.2}'::jsonb,$2)`, liveBindingPlatform, liveBindingUser); err != nil {
		t.Fatalf("seed platform defaults: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_module_bindings(
  tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb,updated_by
) VALUES($1,NULL,'writer_composer',$2,'binding-model-a','{"temperature":0.3}'::jsonb,$3)`, liveBindingTenantA, liveBindingChannelA, liveBindingUser); err != nil {
		t.Fatalf("seed tenant default: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_module_bindings(
  tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb,updated_by
) VALUES($1,NULL,'anchor_point_summary',$2,'binding-disabled-model','{}'::jsonb,$3),
        ($1,$4,'anchor_point_summary',$2,'binding-disabled-model','{}'::jsonb,$3)`, liveBindingTenantA, liveBindingChannelA, liveBindingUser, liveBindingProjectA1); err != nil {
		t.Fatalf("seed disabled project/tenant bindings: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_module_bindings(
  tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb,updated_by
) VALUES($1,$2,'writer_composer',$3,'binding-model-b','{}'::jsonb,$4)`, liveBindingTenantB, liveBindingProjectB, liveBindingChannelB, liveBindingUser); err != nil {
		t.Fatalf("seed cross-tenant binding: %v", err)
	}
}
