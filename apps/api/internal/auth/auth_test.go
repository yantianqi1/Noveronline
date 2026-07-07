package auth

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"
)

func TestSQLReaderReturnsPublicCurrentUserWithActiveTenantsAndProjects(t *testing.T) {
	queryer := &fakeAuthQueryer{
		rows: []SQLRows{
			&fakeAuthRows{rows: [][]any{{
				"user-123",
				"author@example.test",
				"Author",
				"https://cdn.example.test/avatar.png",
			}}},
			&fakeAuthRows{rows: [][]any{
				{"tenant-123", "Studio", "owner", "active"},
				{"tenant-456", "Side Studio", "writer", "active"},
			}},
			&fakeAuthRows{rows: [][]any{
				{"tenant-123", "project-123", "Long Novel", "editor", "owner", "active"},
				{"tenant-456", "project-456", "Side Story", nil, "writer", "active"},
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	currentUser, err := reader.GetCurrentUser(context.Background(), GetCurrentUserInput{UserID: " user-123 "})

	if err != nil {
		t.Fatalf("GetCurrentUser returned error: %v", err)
	}
	if currentUser.User != (UserSummary{
		UserID:      "user-123",
		Email:       "author@example.test",
		DisplayName: "Author",
		AvatarURL:   "https://cdn.example.test/avatar.png",
	}) {
		t.Fatalf("unexpected user summary: %#v", currentUser.User)
	}
	if len(currentUser.ActiveTenants) != 2 {
		t.Fatalf("expected two active tenants, got %#v", currentUser.ActiveTenants)
	}
	if currentUser.ActiveTenants[0] != (TenantMembershipSummary{TenantID: "tenant-123", Name: "Studio", Role: "owner", Status: "active"}) {
		t.Fatalf("unexpected first tenant: %#v", currentUser.ActiveTenants[0])
	}
	if len(currentUser.ActiveProjects) != 2 {
		t.Fatalf("expected two active projects, got %#v", currentUser.ActiveProjects)
	}
	if currentUser.ActiveProjects[0] != (ProjectMembershipSummary{TenantID: "tenant-123", ProjectID: "project-123", Name: "Long Novel", Role: "editor", Status: "active"}) {
		t.Fatalf("unexpected explicit project role: %#v", currentUser.ActiveProjects[0])
	}
	if currentUser.ActiveProjects[1] != (ProjectMembershipSummary{TenantID: "tenant-456", ProjectID: "project-456", Name: "Side Story", Role: "writer", Status: "active"}) {
		t.Fatalf("unexpected inherited tenant role: %#v", currentUser.ActiveProjects[1])
	}
	for _, query := range queryer.queries {
		for _, forbidden := range []string{
			"api_key",
			"encrypted",
			"credential_ref",
			"object_key",
			"content_text",
			"body",
			"draft",
			"manuscript",
			"prompt",
			"response",
		} {
			if strings.Contains(strings.ToLower(query), forbidden) {
				t.Fatalf("auth lookup query selected forbidden field name %q: %s", forbidden, query)
			}
		}
	}
}

func TestSQLReaderMapsInactiveOrMissingUserToUserNotFound(t *testing.T) {
	queryer := &fakeAuthQueryer{
		rows: []SQLRows{&fakeAuthRows{}},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	_, err := reader.GetCurrentUser(context.Background(), GetCurrentUserInput{UserID: "user-missing"})

	assertAuthError(t, err, CodeUserNotFound, "current user was not found")
}

func TestSQLReaderSanitizesQueryScanRowsAndCloseFailures(t *testing.T) {
	maliciousErr := errors.New("driver leaked prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/private content_text=secret body=secret draft=private manuscript=private response=raw")
	tests := []struct {
		name    string
		queryer *fakeAuthQueryer
	}{
		{
			name: "query",
			queryer: &fakeAuthQueryer{
				errs: []error{maliciousErr},
			},
		},
		{
			name: "scan",
			queryer: &fakeAuthQueryer{
				rows: []SQLRows{&fakeAuthRows{rows: [][]any{{"user-123"}}, scanErr: maliciousErr}},
			},
		},
		{
			name: "rows",
			queryer: &fakeAuthQueryer{
				rows: []SQLRows{&fakeAuthRows{err: maliciousErr}},
			},
		},
		{
			name: "close",
			queryer: &fakeAuthQueryer{
				rows: []SQLRows{&fakeAuthRows{closeErr: maliciousErr}},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			reader := NewSQLReader(SQLReaderConfig{Queryer: tt.queryer})

			_, err := reader.GetCurrentUser(context.Background(), GetCurrentUserInput{UserID: "user-123"})

			assertAuthError(t, err, CodeLookupFailed, "auth lookup failed")
			for _, forbidden := range []string{
				"prompt",
				"api_key",
				"sk-hidden",
				"credential_ref",
				"object_key",
				"content_text",
				"body",
				"draft",
				"manuscript",
				"response",
			} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("sanitized auth error leaked %q: %v", forbidden, err)
				}
			}
		})
	}
}

type fakeAuthQueryer struct {
	queries []string
	rows    []SQLRows
	errs    []error
}

func (q *fakeAuthQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.queries = append(q.queries, query)
	if len(q.errs) > 0 {
		err := q.errs[0]
		q.errs = q.errs[1:]
		if err != nil {
			return nil, err
		}
	}
	if len(q.rows) == 0 {
		return nil, fmt.Errorf("unexpected query: %s", query)
	}
	rows := q.rows[0]
	q.rows = q.rows[1:]
	return rows, nil
}

type fakeAuthRows struct {
	rows     [][]any
	index    int
	scanErr  error
	err      error
	closeErr error
}

func (r *fakeAuthRows) Next() bool {
	return r.index < len(r.rows)
}

func (r *fakeAuthRows) Scan(dest ...any) error {
	if r.scanErr != nil {
		return r.scanErr
	}
	if r.index >= len(r.rows) {
		return errors.New("scan without row")
	}
	values := r.rows[r.index]
	r.index++
	if len(values) != len(dest) {
		return fmt.Errorf("scan destination count mismatch: got %d want %d", len(dest), len(values))
	}
	for i := range values {
		switch target := dest[i].(type) {
		case *string:
			if values[i] == nil {
				*target = ""
				continue
			}
			value, ok := values[i].(string)
			if !ok {
				return fmt.Errorf("value %d is %T, not string", i, values[i])
			}
			*target = value
		case *sql.NullString:
			if values[i] == nil {
				*target = sql.NullString{}
				continue
			}
			value, ok := values[i].(string)
			if !ok {
				return fmt.Errorf("value %d is %T, not string", i, values[i])
			}
			*target = sql.NullString{String: value, Valid: true}
		default:
			return fmt.Errorf("unsupported scan destination %T", dest[i])
		}
	}
	return nil
}

func (r *fakeAuthRows) Err() error {
	return r.err
}

func (r *fakeAuthRows) Close() error {
	return r.closeErr
}

func assertAuthError(t *testing.T, err error, code string, message string) {
	t.Helper()
	if err == nil {
		t.Fatal("expected error")
	}
	var appErr *AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected AppError, got %T: %v", err, err)
	}
	if appErr.Code != code || appErr.Message != message || appErr.Error() != message {
		t.Fatalf("unexpected auth error: %#v", appErr)
	}
}
