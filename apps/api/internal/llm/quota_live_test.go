package llm

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

const (
	liveQuotaTenantA  = "71000000-0000-4000-8000-000000000001"
	liveQuotaTenantB  = "71000000-0000-4000-8000-000000000002"
	liveQuotaProjectA = "72000000-0000-4000-8000-000000000001"
	liveQuotaProjectB = "72000000-0000-4000-8000-000000000002"
	liveQuotaChannelA = "73000000-0000-4000-8000-000000000001"
	liveQuotaChannelB = "73000000-0000-4000-8000-000000000002"
	liveQuotaRunA     = "74000000-0000-4000-8000-000000000001"
)

func TestLiveQuotaReserveFinalizeReleaseConcurrencyAndRLS(t *testing.T) {
	adminURL := os.Getenv("MIROFISH_LLM_LIVE_DATABASE_URL")
	if adminURL == "" {
		adminURL = os.Getenv("MIROFISH_WORLDLINE_LIVE_DATABASE_URL")
	}
	if adminURL == "" {
		t.Skip("set MIROFISH_LLM_LIVE_DATABASE_URL to run live LLM quota/RLS tests")
	}
	prepareLiveTelemetryDatabase(t, adminURL)
	prepareLiveQuotaDatabase(t, adminURL)
	appDB, err := sql.Open("pgx", liveAppDatabaseURL(t, adminURL))
	if err != nil {
		t.Fatalf("open app database: %v", err)
	}
	defer appDB.Close()
	appDB.SetMaxOpenConns(8)
	store := NewSQLQuotaStore(appDB)
	tokens, cost, concurrency := int64(10), int64(100), 1
	concurrencyLimit := int(concurrency)
	_, err = store.UpsertPolicy(context.Background(), UpsertQuotaPolicyInput{
		TenantID: liveQuotaTenantA, ActorUserID: liveUserID, ScopeType: QuotaScopeModule,
		ProjectID: liveQuotaProjectA, ModuleKey: "writer_composer", TokenLimit: &tokens,
		CostLimitMicros: &cost, ConcurrencyLimit: &concurrencyLimit, PeriodSeconds: 3600, Enabled: true,
	})
	if err != nil {
		t.Fatalf("upsert live quota policy: %v", err)
	}

	start := make(chan struct{})
	results := make(chan struct {
		reservation QuotaReservation
		err         error
	}, 2)
	var wg sync.WaitGroup
	for index := 0; index < 2; index++ {
		wg.Add(1)
		go func(callID string) {
			defer wg.Done()
			<-start
			reservation, reserveErr := store.Reserve(context.Background(), liveReservationInput(callID, 5, 50))
			results <- struct {
				reservation QuotaReservation
				err         error
			}{reservation, reserveErr}
		}("live-provider-call-" + string(rune('a'+index)))
	}
	close(start)
	wg.Wait()
	close(results)
	var winner QuotaReservation
	limited := 0
	for result := range results {
		if result.err == nil {
			winner = result.reservation
		} else if ErrorCode(result.err) == "LLM_QUOTA_CONCURRENCY_EXCEEDED" {
			limited++
		} else {
			t.Fatalf("unexpected concurrent reserve error: %v", result.err)
		}
	}
	if winner.ReservationID == "" || limited != 1 {
		t.Fatalf("atomic concurrency gate failed: winner=%#v limited=%d", winner, limited)
	}
	actualCost := int64(40)
	if err := store.Finalize(context.Background(), QuotaFinalizeInput{
		TenantID: liveQuotaTenantA, ReservationID: winner.ReservationID,
		PromptTokens: 2, CompletionTokens: 3, CostMicros: &actualCost,
	}); err != nil {
		t.Fatalf("finalize measured live usage: %v", err)
	}
	_, err = store.Reserve(context.Background(), liveReservationInput("live-provider-call-over", 6, 1))
	if code := ErrorCode(err); code != "LLM_QUOTA_TOKENS_EXCEEDED" {
		t.Fatalf("post-finalize token limit: code=%s err=%v", code, err)
	}

	released, err := store.Reserve(context.Background(), liveReservationInput("live-provider-call-failed", 5, 50))
	if err != nil {
		t.Fatalf("reserve failed-call capacity: %v", err)
	}
	if err := store.Release(context.Background(), liveQuotaTenantA, released.ReservationID); err != nil {
		t.Fatalf("release failed-call reservation: %v", err)
	}
	reopened, err := store.Reserve(context.Background(), liveReservationInput("live-provider-call-failed", 5, 50))
	if err != nil {
		t.Fatalf("reopen released provider call reservation: %v", err)
	}
	if reopened.ReservationID != released.ReservationID {
		t.Fatalf("expected same reservation id after reopen, got %#v vs %#v", reopened, released)
	}
	if err := store.Release(context.Background(), liveQuotaTenantA, reopened.ReservationID); err != nil {
		t.Fatalf("release reopened reservation: %v", err)
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: NewSQLDBQueryer(appDB)})
	billing, err := reader.BillingUsage(context.Background(), BillingUsageQuery{
		TenantID: liveQuotaTenantA, ProjectID: liveQuotaProjectA, ModuleKey: "writer_composer",
	})
	if err != nil {
		t.Fatalf("read live billing summary: %v", err)
	}
	if len(billing) != 1 || billing[0].Tokens != 5 || billing[0].CostMicros == nil || *billing[0].CostMicros != 40 || billing[0].BillingStatus != "billing_ready" {
		t.Fatalf("failed call inflated billing or grouping is wrong: %#v", billing)
	}
	assertLiveQuotaRLS(t, appDB)
}

func liveReservationInput(callID string, tokens, cost int64) QuotaReservationInput {
	return QuotaReservationInput{
		TenantID: liveQuotaTenantA, ProjectID: liveQuotaProjectA, RunID: liveQuotaRunA,
		ModuleKey: "writer_composer", ChannelID: liveQuotaChannelA, ModelID: "live-model-a",
		ProviderCallID: callID, ReservedTokens: tokens, ReservedCostMicros: cost, TTL: time.Minute,
	}
}

func prepareLiveQuotaDatabase(t *testing.T, adminURL string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open quota admin database: %v", err)
	}
	defer db.Close()
	prepareLiveQuotaSchema(t, db)
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id IN ($1, $2)", liveQuotaTenantA, liveQuotaTenantB); err != nil {
		t.Fatalf("clean quota tenants: %v", err)
	}
	for _, fixture := range []struct{ tenant, project, channel, slug string }{
		{liveQuotaTenantA, liveQuotaProjectA, liveQuotaChannelA, "llm-quota-live-a"},
		{liveQuotaTenantB, liveQuotaProjectB, liveQuotaChannelB, "llm-quota-live-b"},
	} {
		if _, err := db.Exec(`INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES ($1, $2, $2, 'personal')`, fixture.tenant, fixture.slug); err != nil {
			t.Fatalf("seed quota tenant: %v", err)
		}
		if _, err := db.Exec(`INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES ($1, $2, $3, $4)`, fixture.tenant, fixture.project, fixture.slug, liveUserID); err != nil {
			t.Fatalf("seed quota project: %v", err)
		}
		if _, err := db.Exec(`INSERT INTO llm_channels (tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled)
VALUES ($1, $2, $3, 'openai-compatible', 'http://127.0.0.1:9/v1', 'encrypted:test-only', 1, true)`, fixture.tenant, fixture.channel, fixture.slug); err != nil {
			t.Fatalf("seed quota channel: %v", err)
		}
	}
	if _, err := db.Exec(`INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress)
VALUES ($1, $2, 'writer_run', $3, 'running', 1)`, liveQuotaTenantA, liveQuotaRunA, liveQuotaProjectA); err != nil {
		t.Fatalf("seed quota run: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO llm_quota_policies (tenant_id, scope_type, project_id, token_limit, period_seconds)
VALUES ($1, 'project', $2, 100, 3600)`, liveQuotaTenantB, liveQuotaProjectB); err != nil {
		t.Fatalf("seed tenant B policy: %v", err)
	}
}

func prepareLiveQuotaSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	var ledgerExists bool
	if err := db.QueryRow("SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL").Scan(&ledgerExists); err != nil {
		t.Fatalf("inspect quota migration ledger: %v", err)
	}
	if ledgerExists {
		var migrationPresent bool
		var tablesPresent bool
		if err := db.QueryRow(`SELECT
  EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version = '0003_llm_quota_billing'),
  to_regclass('public.llm_quota_policies') IS NOT NULL
    AND to_regclass('public.llm_quota_reservations') IS NOT NULL`).Scan(&migrationPresent, &tablesPresent); err != nil {
			t.Fatalf("inspect upgraded quota schema: %v", err)
		}
		if !migrationPresent || !tablesPresent {
			t.Fatal("live quota database must be migrated through schema-init before fixture setup")
		}
		return
	}

	// The caller first runs the shared baseline guard. A ledgerless database can
	// reach this point only when that guard started from an empty public schema.
	migration, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "infra", "postgres", "migrations", "0003_llm_quota_billing.sql"))
	if err != nil {
		t.Fatalf("read quota migration: %v", err)
	}
	if _, err := db.Exec(string(migration)); err != nil {
		t.Fatalf("apply quota migration to fresh disposable database: %v", err)
	}
}

func assertLiveQuotaRLS(t *testing.T, db *sql.DB) {
	t.Helper()
	tx, err := db.BeginTx(context.Background(), &sql.TxOptions{ReadOnly: true})
	if err != nil {
		t.Fatalf("begin RLS assertion: %v", err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec("SELECT app_set_tenant_context($1::uuid, NULL::uuid, false)", liveQuotaTenantA); err != nil {
		t.Fatalf("set RLS tenant: %v", err)
	}
	var policies, reservations int
	if err := tx.QueryRow("SELECT COUNT(*) FROM llm_quota_policies WHERE tenant_id = $1", liveQuotaTenantB).Scan(&policies); err != nil {
		t.Fatalf("read cross-tenant policies: %v", err)
	}
	if err := tx.QueryRow("SELECT COUNT(*) FROM llm_quota_reservations WHERE tenant_id = $1", liveQuotaTenantB).Scan(&reservations); err != nil {
		t.Fatalf("read cross-tenant reservations: %v", err)
	}
	if policies != 0 || reservations != 0 {
		t.Fatalf("RLS leaked tenant B: policies=%d reservations=%d", policies, reservations)
	}
}
