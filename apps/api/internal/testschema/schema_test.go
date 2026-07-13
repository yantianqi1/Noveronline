package testschema

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestUpgradedLedgerSkipsRawBaselineAndPreservesRecoveryDirectGrants(t *testing.T) {
	probe := &recordingSchemaProbe{
		ledger:   true,
		versions: map[string]bool{baselineVersion: true, "0010_auth_recovery_privilege_convergence": true},
		tables:   map[string]bool{"password_reset_tokens": true, "password_reset_delivery_outbox": true},
	}

	err := ensureLiveSchema(context.Background(), probe, "/must/not/be/read.sql", []string{"password_reset_tokens", "password_reset_delivery_outbox"})

	if err != nil {
		t.Fatalf("validate upgraded ledger: %v", err)
	}
	if probe.applyCalls != 0 {
		t.Fatalf("upgraded ledger executed raw baseline %d times; direct recovery grants could be revoked", probe.applyCalls)
	}
}

func TestExistingSchemaWithoutLedgerFailsClosed(t *testing.T) {
	probe := &recordingSchemaProbe{publicTables: 1}
	err := ensureLiveSchema(context.Background(), probe, "/must/not/be/read.sql", nil)
	if err == nil || !strings.Contains(err.Error(), "refusing raw baseline") || probe.applyCalls != 0 {
		t.Fatalf("expected fail-closed existing schema, err=%v apply=%d", err, probe.applyCalls)
	}
}

func TestFreshDatabaseMayApplyRawBaseline(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "0001.sql")
	if err := os.WriteFile(path, []byte("SELECT 'fresh';"), 0o600); err != nil {
		t.Fatal(err)
	}
	probe := &recordingSchemaProbe{tables: map[string]bool{"projects": true}}
	if err := ensureLiveSchema(context.Background(), probe, path, []string{"projects"}); err != nil {
		t.Fatalf("apply fresh baseline: %v", err)
	}
	if probe.applyCalls != 1 || probe.appliedSQL != "SELECT 'fresh';" {
		t.Fatalf("unexpected fresh baseline application: %#v", probe)
	}
}

func TestDisposableLiveDatabaseIdentityFailsClosed(t *testing.T) {
	for _, testCase := range []struct {
		name     string
		database string
		marker   string
		wantErr  bool
	}{
		{name: "dedicated", database: "mirofish_test_123_456", marker: "on"},
		{name: "runtime database", database: "mirofish", marker: "on", wantErr: true},
		{name: "missing marker", database: "mirofish_test_123", wantErr: true},
		{name: "lookalike", database: "mirofish_test", marker: "on", wantErr: true},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			err := validateDisposableLiveDatabase(testCase.database, testCase.marker)
			if (err != nil) != testCase.wantErr {
				t.Fatalf("validateDisposableLiveDatabase() error=%v wantErr=%v", err, testCase.wantErr)
			}
		})
	}
}

type recordingSchemaProbe struct {
	ledger       bool
	versions     map[string]bool
	publicTables int
	tables       map[string]bool
	applyCalls   int
	appliedSQL   string
}

func (p *recordingSchemaProbe) ledgerExists(context.Context) (bool, error) { return p.ledger, nil }
func (p *recordingSchemaProbe) hasVersion(_ context.Context, version string) (bool, error) {
	return p.versions[version], nil
}
func (p *recordingSchemaProbe) publicTableCount(context.Context) (int, error) {
	return p.publicTables, nil
}
func (p *recordingSchemaProbe) hasTable(_ context.Context, table string) (bool, error) {
	return p.tables[table], nil
}
func (p *recordingSchemaProbe) applyBaseline(_ context.Context, sql string) error {
	p.applyCalls++
	p.appliedSQL = sql
	return nil
}
