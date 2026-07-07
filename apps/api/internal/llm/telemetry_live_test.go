package llm

import (
	"context"
	"database/sql"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const liveTenantID = "11111111-1111-1111-1111-111111111111"
const liveUserID = "22222222-2222-2222-2222-222222222222"
const liveProjectID = "33333333-3333-3333-3333-333333333333"
const liveRunID = "550e8400-e29b-41d4-a716-446655440000"
const liveChannelID = "66666666-6666-6666-6666-666666666666"
const liveAppRole = "mirofish_live_app"
const liveAppPassword = "mirofish_live_password"

func TestLiveSQLTelemetryReaderReadsWorldlineStepTelemetryWithTenantContext(t *testing.T) {
	adminURL := os.Getenv("MIROFISH_WORLDLINE_LIVE_DATABASE_URL")
	if adminURL == "" {
		t.Skip("set MIROFISH_WORLDLINE_LIVE_DATABASE_URL to run live LLM telemetry reader E2E")
	}
	prepareLiveTelemetryDatabase(t, adminURL)
	appURL := liveAppDatabaseURL(t, adminURL)
	db, err := sql.Open("pgx", appURL)
	if err != nil {
		t.Fatalf("open app db: %v", err)
	}
	defer db.Close()
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: NewSQLDBQueryer(db)})

	activity, err := reader.ListActivity(context.Background(), ActivityQueryInput{
		TenantID:  liveTenantID,
		ProjectID: liveProjectID,
		RunID:     liveRunID,
		ModuleKey: "worldline_director",
	})
	if err != nil {
		t.Fatalf("list activity: %v", err)
	}
	if len(activity) != 1 {
		t.Fatalf("expected one worldline activity row, got %#v", activity)
	}
	if activity[0].RunID != liveRunID || activity[0].ModuleKey != "worldline_director" || activity[0].Status != "completed" {
		t.Fatalf("unexpected activity row: %#v", activity[0])
	}
	if activity[0].PromptTokens != 13 || activity[0].CompletionTokens != 21 || activity[0].Error != nil {
		t.Fatalf("unexpected activity telemetry fields: %#v", activity[0])
	}

	usage, err := reader.ListUsage(context.Background(), UsageQueryInput{
		TenantID:  liveTenantID,
		ProjectID: liveProjectID,
		RunID:     liveRunID,
		ModuleKey: "worldline_director",
	})
	if err != nil {
		t.Fatalf("list usage: %v", err)
	}
	expectedUsage := []UsageRecord{{
		UsageType: "llm_tokens",
		Quantity:  34,
		Unit:      "tokens",
		ModuleKey: "worldline_director",
		RunID:     liveRunID,
	}}
	if !reflect.DeepEqual(usage, expectedUsage) {
		t.Fatalf("unexpected usage rows: %#v", usage)
	}
}

func prepareLiveTelemetryDatabase(t *testing.T, adminURL string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin db: %v", err)
	}
	defer db.Close()
	migrationPath := filepath.Join("..", "..", "..", "..", "infra", "postgres", "migrations", "0001_core_saas.sql")
	migrationSQL, err := os.ReadFile(migrationPath)
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	if _, err := db.Exec(string(migrationSQL)); err != nil {
		t.Fatalf("apply migration: %v", err)
	}
	if _, err := db.Exec("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_live_app') THEN CREATE ROLE mirofish_live_app LOGIN PASSWORD 'mirofish_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_live_app WITH LOGIN PASSWORD 'mirofish_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_live_app;"); err != nil {
		t.Fatalf("ensure app role: %v", err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveTenantID); err != nil {
		t.Fatalf("cleanup tenant: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO users (user_id, email, display_name)
VALUES ($1, 'worldline-live@example.test', 'Worldline Live')
ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, display_name = EXCLUDED.display_name`, liveUserID); err != nil {
		t.Fatalf("seed user: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO tenants (tenant_id, slug, name, tenant_type)
VALUES ($1, 'worldline-live', 'Worldline Live', 'personal')`, liveTenantID); err != nil {
		t.Fatalf("seed tenant: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO projects (tenant_id, project_id, title, created_by)
VALUES ($1, $2, 'Live Worldline Project', $3)`, liveTenantID, liveProjectID, liveUserID); err != nil {
		t.Fatalf("seed project: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_channels (tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled)
VALUES ($1, $2, 'Live Provider', 'openai-compatible', 'http://127.0.0.1:9/v1', 'aes-256-gcm:v1:AAECAwQFBgcICQoL:MTIzNDU2Nzg5MDEyMzQ1Ng==:Y2lwaGVy', 1, true)`, liveTenantID, liveChannelID); err != nil {
		t.Fatalf("seed channel: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_activity (tenant_id, project_id, run_id, module_key, channel_id, model_id, status, prompt_tokens, completion_tokens, latency_ms, cost_estimate, error_jsonb)
VALUES ($1, $2, $3, 'worldline_director', $4, 'model-worldline-live', 'completed', 13, 21, 17, 0.0042, NULL)`, liveTenantID, liveProjectID, liveRunID, liveChannelID); err != nil {
		t.Fatalf("seed activity: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO usage_events (tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb)
VALUES ($1, $2, $3, 'worldline_director', 'llm_tokens', 34, 'tokens', '{"provider":"openai-compatible"}'::jsonb)`, liveTenantID, liveProjectID, liveRunID); err != nil {
		t.Fatalf("seed usage: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO usage_events (tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb)
VALUES ($1, $2, $3, 'worldline_director', 'storage_bytes', 999, 'bytes', '{}'::jsonb)`, liveTenantID, liveProjectID, liveRunID); err != nil {
		t.Fatalf("seed non-llm usage: %v", err)
	}
}

func liveAppDatabaseURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatalf("parse admin database URL: %v", err)
	}
	parsed.User = url.UserPassword(liveAppRole, liveAppPassword)
	return parsed.String()
}
