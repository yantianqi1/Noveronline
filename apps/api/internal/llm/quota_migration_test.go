package llm

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLLMQuotaMigrationDefinesAtomicRLSProtectedBillingTables(t *testing.T) {
	path := filepath.Join("..", "..", "..", "..", "infra", "postgres", "migrations", "0003_llm_quota_billing.sql")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read quota migration: %v", err)
	}
	sql := string(raw)
	for _, expected := range []string{
		"CREATE TABLE IF NOT EXISTS llm_quota_policies",
		"scope_type IN ('tenant', 'project', 'module')",
		"token_limit BIGINT",
		"cost_limit_micros BIGINT",
		"concurrency_limit INTEGER",
		"CREATE TABLE IF NOT EXISTS llm_quota_reservations",
		"status IN ('reserved', 'finalized', 'released', 'expired')",
		"ALTER TABLE llm_quota_policies ENABLE ROW LEVEL SECURITY",
		"ALTER TABLE llm_quota_policies FORCE ROW LEVEL SECURITY",
		"CREATE POLICY tenant_isolation_llm_quota_policies",
		"ALTER TABLE llm_quota_reservations ENABLE ROW LEVEL SECURITY",
		"ALTER TABLE llm_quota_reservations FORCE ROW LEVEL SECURITY",
		"CREATE POLICY tenant_isolation_llm_quota_reservations",
		"external_provider_opt_in BOOLEAN NOT NULL DEFAULT FALSE",
	} {
		if !strings.Contains(sql, expected) {
			t.Fatalf("quota migration missing %q", expected)
		}
	}
	for _, forbidden := range []string{"api_key TEXT", "prompt TEXT", "response TEXT", "BYPASSRLS"} {
		if strings.Contains(strings.ToUpper(sql), strings.ToUpper(forbidden)) {
			t.Fatalf("quota migration contains forbidden field %q", forbidden)
		}
	}
}
