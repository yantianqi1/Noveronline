package testschema

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"regexp"
	"strings"
)

const baselineVersion = "0001_core_saas"

var disposableDatabaseName = regexp.MustCompile(`^mirofish_test_[a-z0-9_]+$`)

type schemaProbe interface {
	ledgerExists(context.Context) (bool, error)
	hasVersion(context.Context, string) (bool, error)
	publicTableCount(context.Context) (int, error)
	hasTable(context.Context, string) (bool, error)
	applyBaseline(context.Context, string) error
}

type sqlSchemaProbe struct {
	db *sql.DB
}

func EnsureLiveSchema(ctx context.Context, db *sql.DB, migrationPath string, requiredTables ...string) error {
	if err := RequireDisposableLiveDatabase(ctx, db); err != nil {
		return err
	}
	return ensureLiveSchema(ctx, &sqlSchemaProbe{db: db}, migrationPath, requiredTables)
}

func RequireDisposableLiveDatabase(ctx context.Context, db *sql.DB) error {
	if db == nil {
		return fmt.Errorf("live test database is not configured")
	}
	var databaseName, liveTestMarker string
	if err := db.QueryRowContext(ctx, `SELECT current_database(), COALESCE(current_setting('mirofish.live_test', true), '')`).Scan(&databaseName, &liveTestMarker); err != nil {
		return fmt.Errorf("inspect live test database identity: %w", err)
	}
	return validateDisposableLiveDatabase(databaseName, liveTestMarker)
}

func validateDisposableLiveDatabase(databaseName, liveTestMarker string) error {
	databaseName = strings.ToLower(strings.TrimSpace(databaseName))
	if !disposableDatabaseName.MatchString(databaseName) || strings.TrimSpace(liveTestMarker) != "on" {
		return fmt.Errorf("refusing live test database %q without disposable database name and marker", databaseName)
	}
	return nil
}

func ensureLiveSchema(ctx context.Context, probe schemaProbe, migrationPath string, requiredTables []string) error {
	ledgerExists, err := probe.ledgerExists(ctx)
	if err != nil {
		return fmt.Errorf("inspect schema migration ledger: %w", err)
	}
	if ledgerExists {
		hasBaseline, err := probe.hasVersion(ctx, baselineVersion)
		if err != nil {
			return fmt.Errorf("inspect baseline migration ledger: %w", err)
		}
		if !hasBaseline {
			return fmt.Errorf("schema migration ledger is present without %s", baselineVersion)
		}
		return validateRequiredTables(ctx, probe, requiredTables)
	}

	tableCount, err := probe.publicTableCount(ctx)
	if err != nil {
		return fmt.Errorf("inspect public schema: %w", err)
	}
	if tableCount != 0 {
		return fmt.Errorf("refusing raw baseline without migration ledger: public schema already has %d base tables", tableCount)
	}
	baselineSQL, err := os.ReadFile(migrationPath)
	if err != nil {
		return fmt.Errorf("read raw baseline: %w", err)
	}
	if err := probe.applyBaseline(ctx, string(baselineSQL)); err != nil {
		return fmt.Errorf("apply raw baseline to fresh database: %w", err)
	}
	return validateRequiredTables(ctx, probe, requiredTables)
}

func validateRequiredTables(ctx context.Context, probe schemaProbe, requiredTables []string) error {
	for _, table := range requiredTables {
		exists, err := probe.hasTable(ctx, table)
		if err != nil {
			return fmt.Errorf("inspect required table %s: %w", table, err)
		}
		if !exists {
			return fmt.Errorf("required live-test table %s is missing", table)
		}
	}
	return nil
}

func (p *sqlSchemaProbe) ledgerExists(ctx context.Context) (bool, error) {
	var exists bool
	err := p.db.QueryRowContext(ctx, "SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL").Scan(&exists)
	return exists, err
}

func (p *sqlSchemaProbe) hasVersion(ctx context.Context, version string) (bool, error) {
	var exists bool
	err := p.db.QueryRowContext(ctx, "SELECT EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version = $1)", version).Scan(&exists)
	return exists, err
}

func (p *sqlSchemaProbe) publicTableCount(ctx context.Context) (int, error) {
	var count int
	err := p.db.QueryRowContext(ctx, "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'").Scan(&count)
	return count, err
}

func (p *sqlSchemaProbe) hasTable(ctx context.Context, table string) (bool, error) {
	var exists bool
	err := p.db.QueryRowContext(ctx, "SELECT to_regclass($1) IS NOT NULL", "public."+table).Scan(&exists)
	return exists, err
}

func (p *sqlSchemaProbe) applyBaseline(ctx context.Context, baselineSQL string) error {
	_, err := p.db.ExecContext(ctx, baselineSQL)
	return err
}
