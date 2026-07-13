package llmadmin

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"mirofish-novel/apps/api/internal/llm"
)

const (
	liveAdminTenantA  = "a8100000-0000-4000-8000-000000000001"
	liveAdminTenantB  = "a8100000-0000-4000-8000-000000000002"
	liveAdminProjectA = "a8200000-0000-4000-8000-000000000001"
	liveAdminProjectB = "a8200000-0000-4000-8000-000000000002"
	liveAdminChannelA = "a8300000-0000-4000-8000-000000000001"
	liveAdminRunA     = "a8400000-0000-4000-8000-000000000001"
	liveAdminOwner    = "a8500000-0000-4000-8000-000000000001"
	liveAdminBilling  = "a8500000-0000-4000-8000-000000000002"
	liveAdminViewer   = "a8500000-0000-4000-8000-000000000003"
	liveAdminRole     = "mirofish_llm_admin_live_app"
	liveAdminPassword = "mirofish_llm_admin_live_password"
	liveCredentialKey = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)

func TestLiveLLMAdminPolicyResolutionBillingHealthRBACAndRLS(t *testing.T) {
	adminURL := os.Getenv("MIROFISH_LLM_ADMIN_LIVE_DATABASE_URL")
	if adminURL == "" {
		adminURL = os.Getenv("MIROFISH_LLM_LIVE_DATABASE_URL")
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_LLM_ADMIN_LIVE_DATABASE_URL to run app-role LLM admin live tests")
	}
	adminDB, appDB := prepareLLMAdminLive(t, adminURL)
	defer adminDB.Close()
	defer appDB.Close()
	store := NewSQLStore(appDB)

	tenantTokens, projectCost, moduleTokens, concurrency := int64(1000), int64(5000), int64(300), 2
	tenantPolicy, err := store.CreatePolicy(context.Background(), liveAdminTenantA, liveAdminOwner, PolicyWrite{ScopeType: "tenant", TokenLimit: &tenantTokens, PeriodSeconds: 3600})
	if err != nil {
		t.Fatalf("create tenant policy: %v", err)
	}
	_, err = store.CreatePolicy(context.Background(), liveAdminTenantA, liveAdminOwner, PolicyWrite{ScopeType: "project", ProjectID: liveAdminProjectA, CostLimitMicros: &projectCost, PeriodSeconds: 3600})
	if err != nil {
		t.Fatalf("create project policy: %v", err)
	}
	modulePolicy, err := store.CreatePolicy(context.Background(), liveAdminTenantA, liveAdminOwner, PolicyWrite{ScopeType: "module", ProjectID: liveAdminProjectA, ModuleKey: "writer_composer", TokenLimit: &moduleTokens, ConcurrencyLimit: &concurrency, PeriodSeconds: 3600})
	if err != nil {
		t.Fatalf("create module policy: %v", err)
	}

	enabled := true
	updated, err := store.UpdatePolicy(context.Background(), liveAdminTenantA, liveAdminOwner, modulePolicy.PolicyID, PolicyWrite{ScopeType: "module", ProjectID: liveAdminProjectA, ModuleKey: "writer_composer", TokenLimit: &moduleTokens, ConcurrencyLimit: &concurrency, PeriodSeconds: 7200, Enabled: &enabled, ExpectedVersion: modulePolicy.Version})
	if err != nil || updated.Version == modulePolicy.Version {
		t.Fatalf("optimistic update failed: %#v err=%v", updated, err)
	}
	_, err = store.UpdatePolicy(context.Background(), liveAdminTenantA, liveAdminOwner, modulePolicy.PolicyID, PolicyWrite{ScopeType: "module", ProjectID: liveAdminProjectA, ModuleKey: "writer_composer", TokenLimit: &moduleTokens, ConcurrencyLimit: &concurrency, PeriodSeconds: 7200, Enabled: &enabled, ExpectedVersion: modulePolicy.Version})
	if ErrorCode(err) != "LLM_QUOTA_POLICY_VERSION_CONFLICT" {
		t.Fatalf("stale version accepted: %v", err)
	}

	preview, err := store.PreviewResolution(context.Background(), liveAdminTenantA, liveAdminProjectA, "writer_composer")
	if err != nil || len(preview.Applicable) != 3 || preview.Applicable[0].Policy.ScopeType != "module" || preview.Applicable[2].Policy.PolicyID != tenantPolicy.PolicyID {
		t.Fatalf("resolution mismatch: %#v err=%v", preview, err)
	}
	disabled := false
	updated, err = store.UpdatePolicy(context.Background(), liveAdminTenantA, liveAdminOwner, modulePolicy.PolicyID, PolicyWrite{ScopeType: "module", ProjectID: liveAdminProjectA, ModuleKey: "writer_composer", TokenLimit: &moduleTokens, ConcurrencyLimit: &concurrency, PeriodSeconds: 7200, Enabled: &disabled, ExpectedVersion: updated.Version})
	if err != nil || updated.Enabled {
		t.Fatalf("disable policy failed: %#v err=%v", updated, err)
	}

	reservations, err := store.ListReservations(context.Background(), liveAdminTenantA, liveAdminProjectA, "", 100)
	if err != nil || len(reservations) != 4 {
		t.Fatalf("reservation states unavailable: %#v err=%v", reservations, err)
	}
	seen := map[string]bool{}
	for _, item := range reservations {
		seen[item.Status] = true
	}
	for _, status := range []string{"reserved", "finalized", "released", "expired"} {
		if !seen[status] {
			t.Fatalf("missing reservation status %s: %#v", status, reservations)
		}
	}

	reconciled, err := store.Reconcile(context.Background(), liveAdminTenantA, liveAdminProjectA, "writer_composer", 100)
	if err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	var priced, unavailable, orphan bool
	for _, item := range reconciled {
		if item.ProviderCallID == "admin-call-finalized" {
			priced = item.BillingStatus == "reconciled"
		}
		if item.ProviderCallID == "admin-call-released" {
			unavailable = item.PricingStatus == "unavailable"
		}
		if item.ProviderCallID == "admin-call-orphan" {
			orphan = item.ReservationID == "" && item.BillingStatus == "attention_required"
		}
	}
	if !priced || !unavailable || !orphan {
		t.Fatalf("billing truth mismatch: %#v", reconciled)
	}

	access := NewSQLAccessController(appDB)
	for _, input := range []struct {
		user, op string
		allowed  bool
	}{{liveAdminOwner, OperationPolicyWrite, true}, {liveAdminBilling, OperationReconciliationRead, true}, {liveAdminBilling, OperationPolicyWrite, false}, {liveAdminViewer, OperationPolicyRead, false}} {
		err := access.Authorize(context.Background(), AccessInput{TenantID: liveAdminTenantA, UserID: input.user, Operation: input.op})
		if (err == nil) != input.allowed {
			t.Fatalf("RBAC mismatch %#v err=%v", input, err)
		}
	}
	if err := access.Authorize(context.Background(), AccessInput{TenantID: liveAdminTenantB, UserID: liveAdminOwner, Operation: OperationPolicyRead}); err == nil {
		t.Fatal("cross-tenant membership was accepted")
	}
	other, err := store.ListPolicies(context.Background(), liveAdminTenantA, liveAdminProjectB)
	if err != nil {
		t.Fatalf("cross tenant query failed: %v", err)
	}
	for _, policy := range other {
		if policy.ProjectID == liveAdminProjectB {
			t.Fatalf("RLS leaked tenant B: %#v", other)
		}
	}

	provider := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/v1/chat/completions" || request.Header.Get("Authorization") != "Bearer live-health-key" {
			t.Errorf("unsafe health request: %s %#v", request.URL.Path, request.Header)
			response.WriteHeader(http.StatusBadRequest)
			return
		}
		var body map[string]any
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Errorf("decode health body: %v", err)
		}
		if body["max_tokens"] != float64(1) || strings.Contains(strings.ToLower(stringMustJSON(body)), "novel") {
			t.Errorf("health request contains content: %#v", body)
		}
		response.Header().Set("Content-Type", "application/json")
		_, _ = response.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	defer provider.Close()
	_, err = adminDB.Exec(`UPDATE llm_channels SET base_url=$1 WHERE tenant_id=$2 AND channel_id=$3`, provider.URL+"/v1", liveAdminTenantA, liveAdminChannelA)
	if err != nil {
		t.Fatalf("point live channel at provider: %v", err)
	}
	resolver, err := NewSQLHealthCredentialResolver(SQLHealthCredentialResolverConfig{
		Queryer: llm.NewSQLDBQueryer(appDB), CredentialKeyMaterial: liveCredentialKey,
	})
	if err != nil {
		t.Fatalf("construct production health resolver: %v", err)
	}
	health := NewHealthService(resolver, NewHTTPHealthExecutor(provider.Client(), time.Second, 4096), NewSQLHealthRecorder(appDB))
	result, err := health.Check(context.Background(), liveAdminTenantA, liveAdminOwner, liveAdminProjectA, liveAdminChannelA, "live-model", "live-health-request")
	if err != nil || result.Status != "healthy" || result.StatusCode != 200 {
		t.Fatalf("local provider health failed: %#v err=%v", result, err)
	}
	var metadata string
	if err := adminDB.QueryRow(`SELECT metadata_jsonb::text FROM audit_logs WHERE tenant_id=$1 AND action='llm.provider_health.checked' ORDER BY created_at DESC LIMIT 1`, liveAdminTenantA).Scan(&metadata); err != nil {
		t.Fatalf("read health audit: %v", err)
	}
	for _, forbidden := range []string{"live-health-key", "prompt", "body", "content"} {
		if strings.Contains(strings.ToLower(metadata), forbidden) {
			t.Fatalf("health audit leaked %q: %s", forbidden, metadata)
		}
	}
	if _, err := resolver.ResolveHealthTarget(context.Background(), liveAdminTenantB, liveAdminProjectB, liveAdminChannelA, "live-model"); ErrorCode(err) != "LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE" {
		t.Fatalf("cross-tenant credential target was visible: %v", err)
	}
	if _, err := adminDB.Exec(`UPDATE llm_models SET enabled=false WHERE tenant_id=$1 AND channel_id=$2 AND model_id='live-model'`, liveAdminTenantA, liveAdminChannelA); err != nil {
		t.Fatalf("disable live model: %v", err)
	}
	if _, err := resolver.ResolveHealthTarget(context.Background(), liveAdminTenantA, liveAdminProjectA, liveAdminChannelA, "live-model"); ErrorCode(err) != "LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE" {
		t.Fatalf("disabled model remained health-checkable: %v", err)
	}
	if err := store.DeletePolicy(context.Background(), liveAdminTenantA, liveAdminOwner, tenantPolicy.PolicyID, tenantPolicy.Version); err != nil {
		t.Fatalf("delete policy: %v", err)
	}
}

func prepareLLMAdminLive(t *testing.T, adminURL string) (*sql.DB, *sql.DB) {
	t.Helper()
	adminDB, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	_, err = adminDB.Exec(`DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mirofish_llm_admin_live_app') THEN CREATE ROLE mirofish_llm_admin_live_app LOGIN PASSWORD 'mirofish_llm_admin_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_llm_admin_live_app WITH LOGIN PASSWORD 'mirofish_llm_admin_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_llm_admin_live_app`)
	if err != nil {
		t.Fatalf("app role: %v", err)
	}
	_, _ = adminDB.Exec(`DELETE FROM tenants WHERE tenant_id IN ($1,$2)`, liveAdminTenantA, liveAdminTenantB)
	for _, u := range []struct{ id, email string }{{liveAdminOwner, "llm-admin-owner@example.test"}, {liveAdminBilling, "llm-admin-billing@example.test"}, {liveAdminViewer, "llm-admin-viewer@example.test"}} {
		_, err = adminDB.Exec(`INSERT INTO users(user_id,email,display_name) VALUES($1,$2,$2) ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email`, u.id, u.email)
		if err != nil {
			t.Fatalf("user: %v", err)
		}
	}
	for _, tenant := range []struct{ id, slug, project string }{{liveAdminTenantA, "llm-admin-live-a", liveAdminProjectA}, {liveAdminTenantB, "llm-admin-live-b", liveAdminProjectB}} {
		_, err = adminDB.Exec(`INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES($1,$2,$2,'personal')`, tenant.id, tenant.slug)
		if err != nil {
			t.Fatal(err)
		}
		_, err = adminDB.Exec(`INSERT INTO projects(tenant_id,project_id,title,created_by) VALUES($1,$2,$3,$4)`, tenant.id, tenant.project, tenant.slug, liveAdminOwner)
		if err != nil {
			t.Fatal(err)
		}
	}
	for _, membership := range []struct{ user, role string }{{liveAdminOwner, "owner"}, {liveAdminBilling, "billing"}, {liveAdminViewer, "viewer"}} {
		_, err = adminDB.Exec(`INSERT INTO tenant_memberships(tenant_id,user_id,role,status) VALUES($1,$2,$3,'active')`, liveAdminTenantA, membership.user, membership.role)
		if err != nil {
			t.Fatal(err)
		}
	}
	encryptedHealthKey := credentialEnvelope(t, liveCredentialKey, "live-health-key")
	_, err = adminDB.Exec(`INSERT INTO llm_channels(tenant_id,channel_id,name,provider,base_url,encrypted_api_key,enabled,external_provider_opt_in) VALUES($1,$2,'admin-live','openai-compatible','http://127.0.0.1:9/v1',$3,true,false)`, liveAdminTenantA, liveAdminChannelA, encryptedHealthKey)
	if err != nil {
		t.Fatal(err)
	}
	_, err = adminDB.Exec(`INSERT INTO llm_models(tenant_id,channel_id,model_id,supports_tools,supports_json,input_cost,output_cost,enabled) VALUES($1,$2,'live-model',true,true,1,2,true)`, liveAdminTenantA, liveAdminChannelA)
	if err != nil {
		t.Fatal(err)
	}
	_, err = adminDB.Exec(`INSERT INTO workflow_runs(tenant_id,run_id,workflow_type,project_id,status,progress) VALUES($1,$2,'writer_run',$3,'completed',100)`, liveAdminTenantA, liveAdminRunA, liveAdminProjectA)
	if err != nil {
		t.Fatal(err)
	}
	seedLLMAdminCalls(t, adminDB)
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatal(err)
	}
	parsed.User = url.UserPassword(liveAdminRole, liveAdminPassword)
	appDB, err := sql.Open("pgx", parsed.String())
	if err != nil {
		t.Fatal(err)
	}
	return adminDB, appDB
}

func seedLLMAdminCalls(t *testing.T, db *sql.DB) {
	t.Helper()
	now := time.Now().UTC()
	for index, status := range []string{"reserved", "finalized", "released", "expired"} {
		call := "admin-call-" + status
		expires := now.Add(time.Hour)
		if status == "expired" {
			expires = now.Add(-time.Hour)
		}
		var prompt, completion, cost any
		var finalized any
		if status == "finalized" {
			prompt = int64(3)
			completion = int64(2)
			cost = int64(9)
			finalized = now
		}
		_, err := db.Exec(`INSERT INTO llm_quota_reservations(tenant_id,provider_call_id,project_id,run_id,module_key,channel_id,model_id,reserved_tokens,reserved_cost_micros,actual_prompt_tokens,actual_completion_tokens,actual_cost_micros,status,expires_at,finalized_at,created_at) VALUES($1,$2,$3,$4,'writer_composer',$5,'live-model',10,20,$6,$7,$8,$9,$10,$11,$12)`, liveAdminTenantA, call, liveAdminProjectA, liveAdminRunA, liveAdminChannelA, prompt, completion, cost, status, expires, finalized, now.Add(time.Duration(index)*time.Second))
		if err != nil {
			t.Fatal(err)
		}
	}
	_, err := db.Exec(`INSERT INTO usage_events(tenant_id,project_id,run_id,module_key,usage_type,quantity,unit,metadata_jsonb) VALUES($1,$2,$3,'writer_composer','llm_tokens',5,'tokens','{"provider_call_id":"admin-call-finalized","model_id":"live-model"}'),($1,$2,$3,'writer_composer','llm_cost_micros',9,'micros','{"provider_call_id":"admin-call-finalized","model_id":"live-model"}')`, liveAdminTenantA, liveAdminProjectA, liveAdminRunA)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(`INSERT INTO usage_events(tenant_id,project_id,run_id,module_key,usage_type,quantity,unit,metadata_jsonb) VALUES($1,$2,$3,'writer_composer','llm_tokens',7,'tokens','{"provider_call_id":"admin-call-orphan","model_id":"live-model"}')`, liveAdminTenantA, liveAdminProjectA, liveAdminRunA)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(`INSERT INTO llm_activity(tenant_id,project_id,run_id,module_key,channel_id,model_id,status,prompt_tokens,completion_tokens,error_jsonb) VALUES($1,$2,$3,'writer_composer',$4,'live-model','completed',3,2,'{"provider_call_id":"admin-call-finalized"}')`, liveAdminTenantA, liveAdminProjectA, liveAdminRunA, liveAdminChannelA)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(`INSERT INTO llm_quota_policies(tenant_id,scope_type,project_id,token_limit,period_seconds) VALUES($1,'project',$2,50,3600)`, liveAdminTenantB, liveAdminProjectB)
	if err != nil {
		t.Fatal(err)
	}
}

func stringMustJSON(value any) string { raw, _ := json.Marshal(value); return string(raw) }
