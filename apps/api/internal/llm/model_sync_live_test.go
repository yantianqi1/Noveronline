package llm

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveModelSyncTenantA  = "75000000-0000-4000-8000-000000000001"
	liveModelSyncTenantB  = "75000000-0000-4000-8000-000000000002"
	liveModelSyncChannelA = "76000000-0000-4000-8000-000000000001"
	liveModelSyncChannelB = "76000000-0000-4000-8000-000000000002"
)

func TestLiveModelSyncUsesEncryptedTenantCredentialAndPersistsIsolatedCatalog(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_LLM_MODEL_SYNC_LIVE_DATABASE_URL"))
	if adminURL == "" {
		adminURL = strings.TrimSpace(os.Getenv("MIROFISH_LLM_LIVE_DATABASE_URL"))
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_LLM_MODEL_SYNC_LIVE_DATABASE_URL to run live model sync certification")
	}
	keyMaterial := strings.Repeat("9", 64)
	providerCredential := "local-model-sync-private-credential"
	encryptedCredential, err := NewSQLChannelStore(SQLChannelStoreConfig{
		Queryer: &recordingSQLQueryer{rows: &fakeSQLRows{}}, CredentialKeyMaterial: keyMaterial,
	}).encryptCredential(providerCredential)
	if err != nil {
		t.Fatalf("encrypt live provider credential: %v", err)
	}

	var providerCalls atomic.Int32
	provider := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		providerCalls.Add(1)
		if request.Method != http.MethodGet || request.URL.RequestURI() != "/v1/models" {
			t.Errorf("unexpected provider request: %s %s", request.Method, request.URL.RequestURI())
			http.Error(response, "not found", http.StatusNotFound)
			return
		}
		if request.Header.Get("Authorization") != "Bearer "+providerCredential || request.Header.Get("Accept") != "application/json" {
			t.Errorf("provider credential/header mismatch")
			http.Error(response, "unauthorized", http.StatusUnauthorized)
			return
		}
		response.Header().Set("Content-Type", "application/json")
		_, _ = response.Write([]byte(`{"data":[{"id":"local-model-a","owned_by":"local-owner"},{"id":"local-model-b","owned_by":"local-owner"}]}`))
	}))
	defer provider.Close()

	prepareLiveModelSyncDatabase(t, adminURL, provider.URL+"/v1", encryptedCredential)
	appDB, err := sql.Open("pgx", liveAppDatabaseURL(t, adminURL))
	if err != nil {
		t.Fatalf("open model sync app database: %v", err)
	}
	defer appDB.Close()
	syncer := NewSQLModelSyncer(SQLModelSyncerConfig{
		Queryer: NewSQLDBQueryer(appDB), CredentialKeyMaterial: keyMaterial,
		Provider: NewOpenAICompatibleModelProvider(provider.Client()),
	})

	result, err := syncer.SyncModels(context.Background(), ModelSyncInput{
		TenantID: liveModelSyncTenantA, ChannelID: liveModelSyncChannelA,
	})
	if err != nil {
		t.Fatalf("sync live models: %v", err)
	}
	if providerCalls.Load() != 1 || result.Channel.LastSyncStatus != "ok:2" || result.Channel.ExternalProviderOptIn {
		t.Fatalf("unexpected local sync result: calls=%d channel=%#v", providerCalls.Load(), result.Channel)
	}
	if len(result.Models) != 2 || result.Models[0].ModelID != "local-model-a" || result.Models[1].ModelID != "local-model-b" {
		t.Fatalf("unexpected synced model catalog: %#v", result.Models)
	}
	encoded, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("encode public model sync result: %v", err)
	}
	for _, forbidden := range []string{providerCredential, encryptedCredential, keyMaterial, "encrypted_api_key", "credential_ref"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("public model sync result leaked private material")
		}
	}
	assertLiveModelSyncPersistence(t, adminURL)

	_, err = syncer.SyncModels(context.Background(), ModelSyncInput{
		TenantID: liveModelSyncTenantA, ChannelID: liveModelSyncChannelB,
	})
	if ErrorCode(err) != "LLM_CHANNEL_NOT_FOUND" || providerCalls.Load() != 1 {
		t.Fatalf("cross-tenant channel reached provider: code=%s calls=%d", ErrorCode(err), providerCalls.Load())
	}
	assertLiveModelSyncRLS(t, appDB)
}

func prepareLiveModelSyncDatabase(t *testing.T, adminURL, baseURL, encryptedCredential string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open model sync admin database: %v", err)
	}
	defer db.Close()
	var ready bool
	if err := db.QueryRow(`SELECT
  EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version='0013_legacy_object_version_convergence')
  AND to_regclass('public.llm_channels') IS NOT NULL
  AND to_regclass('public.llm_models') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		t.Fatalf("live model sync database must be current schema-init output: ready=%v err=%v", ready, err)
	}
	if _, err := db.Exec("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_live_app') THEN CREATE ROLE mirofish_live_app LOGIN PASSWORD 'mirofish_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_live_app WITH LOGIN PASSWORD 'mirofish_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_live_app;"); err != nil {
		t.Fatalf("ensure model sync app role: %v", err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveModelSyncTenantA, liveModelSyncTenantB); err != nil {
		t.Fatalf("cleanup model sync tenants: %v", err)
	}
	t.Cleanup(func() {
		cleanupDB, cleanupErr := sql.Open("pgx", adminURL)
		if cleanupErr == nil {
			defer cleanupDB.Close()
			_, _ = cleanupDB.Exec("DELETE FROM tenants WHERE tenant_id IN ($1,$2)", liveModelSyncTenantA, liveModelSyncTenantB)
		}
	})
	for _, fixture := range []struct{ tenant, channel, slug string }{
		{liveModelSyncTenantA, liveModelSyncChannelA, "model-sync-live-a"},
		{liveModelSyncTenantB, liveModelSyncChannelB, "model-sync-live-b"},
	} {
		if _, err := db.Exec("INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES($1,$2,$2,'personal')", fixture.tenant, fixture.slug); err != nil {
			t.Fatalf("seed model sync tenant: %v", err)
		}
		if _, err := db.Exec(`INSERT INTO llm_channels(tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency,external_provider_opt_in,enabled)
VALUES($1,$2,$3,'openai-compatible',$4,$5,2,false,true)`, fixture.tenant, fixture.channel, fixture.slug, baseURL, encryptedCredential); err != nil {
			t.Fatalf("seed model sync channel: %v", err)
		}
	}
	if _, err := db.Exec(`INSERT INTO llm_models(tenant_id,channel_id,model_id,owned_by,enabled)
VALUES($1,$2,'tenant-b-private-model','tenant-b',true)`, liveModelSyncTenantB, liveModelSyncChannelB); err != nil {
		t.Fatalf("seed cross-tenant model: %v", err)
	}
}

func assertLiveModelSyncPersistence(t *testing.T, adminURL string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open model sync persistence database: %v", err)
	}
	defer db.Close()
	var status string
	var enabledModels int
	if err := db.QueryRow("SELECT last_sync_status FROM llm_channels WHERE tenant_id=$1 AND channel_id=$2", liveModelSyncTenantA, liveModelSyncChannelA).Scan(&status); err != nil {
		t.Fatalf("read persisted channel sync status: %v", err)
	}
	if err := db.QueryRow("SELECT count(*) FROM llm_models WHERE tenant_id=$1 AND channel_id=$2 AND enabled", liveModelSyncTenantA, liveModelSyncChannelA).Scan(&enabledModels); err != nil {
		t.Fatalf("read persisted enabled models: %v", err)
	}
	if status != "ok:2" || enabledModels != 2 {
		t.Fatalf("model sync persistence mismatch: status=%s enabled=%d", status, enabledModels)
	}
}

func assertLiveModelSyncRLS(t *testing.T, db *sql.DB) {
	t.Helper()
	tx, err := db.BeginTx(context.Background(), &sql.TxOptions{ReadOnly: true})
	if err != nil {
		t.Fatalf("begin model sync RLS assertion: %v", err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec("SELECT app_set_tenant_context($1::uuid,NULL::uuid,false)", liveModelSyncTenantA); err != nil {
		t.Fatalf("set model sync tenant context: %v", err)
	}
	var crossTenantModels int
	if err := tx.QueryRow("SELECT count(*) FROM llm_models WHERE tenant_id=$1", liveModelSyncTenantB).Scan(&crossTenantModels); err != nil {
		t.Fatalf("query cross-tenant model catalog: %v", err)
	}
	if crossTenantModels != 0 {
		t.Fatalf("RLS exposed cross-tenant models: %d", crossTenantModels)
	}
}
