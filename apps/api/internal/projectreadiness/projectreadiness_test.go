package projectreadiness

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLReaderGetsLatestSnapshotWithTenantContextAndPublicColumns(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"snapshot-1",
				"project-123",
				"seed-run-1",
				7,
				5,
				4,
				3,
				"2026-07-07T01:00:00Z",
				"2026-07-07T01:05:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	snapshot, err := reader.GetLatestSnapshot(context.Background(), GetLatestSnapshotInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("get latest snapshot: %v", err)
	}
	if snapshot.SnapshotID != "snapshot-1" || snapshot.ProjectID != "project-123" || snapshot.RunID != "seed-run-1" {
		t.Fatalf("unexpected snapshot identity: %#v", snapshot)
	}
	if snapshot.ReadyAssetCount != 7 || snapshot.ReadyEntityCount != 5 || snapshot.ReadyRelationshipCount != 4 || snapshot.ReadyWorldRuleCount != 3 {
		t.Fatalf("unexpected readiness counts: %#v", snapshot)
	}
	if queryer.tenantID != "tenant-123" {
		t.Fatalf("reader did not set tenant context: %q", queryer.tenantID)
	}
	if !strings.Contains(queryer.query, "FROM project_readiness_snapshots") ||
		!strings.Contains(queryer.query, "tenant_id::text = $1") ||
		!strings.Contains(queryer.query, "project_id::text = $2") ||
		!strings.Contains(queryer.query, "ORDER BY updated_at DESC") {
		t.Fatalf("expected latest tenant/project scoped readiness query, got %s", queryer.query)
	}
	forbidden := []string{"report", "body", "content_text", "prompt", "api_key", "credential_ref", "draft", "manuscript"}
	lowerQuery := strings.ToLower(queryer.query)
	for _, field := range forbidden {
		if strings.Contains(lowerQuery, field) {
			t.Fatalf("readiness query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLReaderReturnsNotFoundForMissingSnapshot(t *testing.T) {
	reader := NewSQLReader(SQLReaderConfig{Queryer: &recordingSQLQueryer{rows: &fakeSQLRows{}}})

	_, err := reader.GetLatestSnapshot(context.Background(), GetLatestSnapshotInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected NOT_FOUND, got %s (%v)", code, err)
	}
}

func TestSQLReaderSanitizesUnexpectedQueryFailures(t *testing.T) {
	reader := NewSQLReader(SQLReaderConfig{Queryer: &recordingSQLQueryer{
		err: errors.New("driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden readiness report body"),
	}})

	_, err := reader.GetLatestSnapshot(context.Background(), GetLatestSnapshotInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if code := ErrorCode(err); code != "PROJECT_READINESS_QUERY_FAILED" {
		t.Fatalf("expected PROJECT_READINESS_QUERY_FAILED, got %s (%v)", code, err)
	}
	if err == nil || err.Error() != "project readiness query failed" {
		t.Fatalf("expected stable public message, got %v", err)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "report body"} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("query error leaked %q: %v", forbidden, err)
		}
	}
}

func TestDisabledReaderFailsClosed(t *testing.T) {
	reader := NewDisabledReader()

	_, err := reader.GetLatestSnapshot(context.Background(), GetLatestSnapshotInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if code := ErrorCode(err); code != "PROJECT_READINESS_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected PROJECT_READINESS_BACKEND_UNCONFIGURED, got %s (%v)", code, err)
	}
}

type recordingSQLQueryer struct {
	tenantID string
	query    string
	args     []any
	rows     *fakeSQLRows
	err      error
}

func (q *recordingSQLQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.query = query
	q.args = args
	if q.err != nil {
		return nil, q.err
	}
	return q.rows, nil
}

func (q *recordingSQLQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.tenantID = tenantID
	return q.QueryContext(ctx, query, args...)
}

type fakeSQLRows struct {
	values [][]any
	index  int
	err    error
}

func (r *fakeSQLRows) Next() bool {
	if r.index >= len(r.values) {
		return false
	}
	r.index++
	return true
}

func (r *fakeSQLRows) Scan(dest ...any) error {
	row := r.values[r.index-1]
	for i := range dest {
		reflect.ValueOf(dest[i]).Elem().Set(reflect.ValueOf(row[i]))
	}
	return nil
}

func (r *fakeSQLRows) Close() error {
	return nil
}

func (r *fakeSQLRows) Err() error {
	return r.err
}
