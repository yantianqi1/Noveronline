package projectadmin

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"reflect"
	"strings"
	"testing"
)

const (
	testTenantID  = "22222222-2222-4222-8222-222222222222"
	testProjectID = "33333333-3333-4333-8333-333333333333"
	testActorID   = "11111111-1111-4111-8111-111111111111"
)

func TestCreateProjectInsertsNovelAtomically(t *testing.T) {
	tx := &recordingTx{managerAllowed: true, returnedProject: []string{testTenantID, testProjectID, "Second Novel", "active"}}
	service := testService(tx)

	project, err := service.CreateProject(context.Background(), CreateInput{
		TenantID: "  " + testTenantID + "  ",
		Title:    "  Second Novel  ",
		ActorID:  testActorID,
	})
	if err != nil {
		t.Fatalf("create: code=%s err=%v", ErrorCode(err), err)
	}
	if !tx.committed || tx.rolledBack {
		t.Fatalf("create transaction was not committed exactly once: %#v", tx)
	}
	want := []string{"set_context", "require_manager", "insert_project", "insert_project_membership", "insert_distillation_settings", "audit", "commit"}
	if !reflect.DeepEqual(tx.operations, want) {
		t.Fatalf("unexpected transaction order:\n got: %#v\nwant: %#v", tx.operations, want)
	}
	if project != (Project{TenantID: testTenantID, ProjectID: testProjectID, Title: "Second Novel", Status: "active", Role: "project_owner"}) {
		t.Fatalf("unexpected project result: %#v", project)
	}
	if got := tx.arguments["insert_project"]; len(got) != 3 || got[1] != "Second Novel" {
		t.Fatalf("expected trimmed title passed to insert: %#v", got)
	}
}

func TestCreateProjectRequiresTenantManager(t *testing.T) {
	tx := &recordingTx{managerAllowed: false}
	service := testService(tx)

	_, err := service.CreateProject(context.Background(), CreateInput{TenantID: testTenantID, Title: "Second Novel", ActorID: testActorID})
	if ErrorCode(err) != CodeAccessDenied {
		t.Fatalf("expected access denied, got code=%s err=%v", ErrorCode(err), err)
	}
	if tx.committed || !tx.rolledBack {
		t.Fatalf("expected rollback without commit: %#v", tx)
	}
	for _, operation := range tx.operations {
		if strings.HasPrefix(operation, "insert_") {
			t.Fatalf("no writes should occur after denied authorization: %#v", tx.operations)
		}
	}
}

func TestCreateProjectRejectsInvalidTitleBeforeSQL(t *testing.T) {
	beginCalls := 0
	service := NewService(ServiceConfig{})
	service.beginTx = func(context.Context) (transaction, error) {
		beginCalls++
		return &recordingTx{}, nil
	}
	for _, title := range []string{"", "   ", strings.Repeat("字", maxProjectTitleRunes+1), "bad\x07title"} {
		_, err := service.CreateProject(context.Background(), CreateInput{TenantID: testTenantID, Title: title, ActorID: testActorID})
		if ErrorCode(err) != CodeValidationFailed || ErrorField(err) != "title" {
			t.Fatalf("title %q: expected validation error, got code=%s field=%s", title, ErrorCode(err), ErrorField(err))
		}
	}
	if beginCalls != 0 {
		t.Fatalf("validation must precede any transaction, began %d times", beginCalls)
	}
}

func TestCreateProjectRequiresTenantAndActor(t *testing.T) {
	service := testService(&recordingTx{managerAllowed: true})
	if _, err := service.CreateProject(context.Background(), CreateInput{Title: "Novel", ActorID: testActorID}); ErrorCode(err) != CodeValidationFailed {
		t.Fatalf("expected validation error for missing tenant, got %s", ErrorCode(err))
	}
	if _, err := service.CreateProject(context.Background(), CreateInput{TenantID: testTenantID, Title: "Novel"}); ErrorCode(err) != CodeValidationFailed {
		t.Fatalf("expected validation error for missing actor, got %s", ErrorCode(err))
	}
}

func TestRenameProjectUpdatesTitle(t *testing.T) {
	tx := &recordingTx{managerAllowed: true, returnedProject: []string{testTenantID, testProjectID, "Renamed Novel", "active"}}
	service := testService(tx)

	project, err := service.RenameProject(context.Background(), RenameInput{TenantID: testTenantID, ProjectID: testProjectID, Title: "  Renamed Novel  ", ActorID: testActorID})
	if err != nil {
		t.Fatalf("rename: code=%s err=%v", ErrorCode(err), err)
	}
	if !tx.committed || tx.rolledBack {
		t.Fatalf("rename transaction was not committed exactly once: %#v", tx)
	}
	want := []string{"set_context", "require_manager", "update_project", "audit", "commit"}
	if !reflect.DeepEqual(tx.operations, want) {
		t.Fatalf("unexpected transaction order:\n got: %#v\nwant: %#v", tx.operations, want)
	}
	if project.Title != "Renamed Novel" || project.ProjectID != testProjectID {
		t.Fatalf("unexpected rename result: %#v", project)
	}
}

func TestRenameProjectReportsMissingNovel(t *testing.T) {
	tx := &recordingTx{managerAllowed: true, updateNoRows: true}
	service := testService(tx)

	_, err := service.RenameProject(context.Background(), RenameInput{TenantID: testTenantID, ProjectID: testProjectID, Title: "Renamed Novel", ActorID: testActorID})
	if ErrorCode(err) != CodeProjectNotFound {
		t.Fatalf("expected project not found, got code=%s err=%v", ErrorCode(err), err)
	}
	if tx.committed || !tx.rolledBack {
		t.Fatalf("expected rollback without commit: %#v", tx)
	}
}

func TestRenameProjectRequiresManager(t *testing.T) {
	tx := &recordingTx{managerAllowed: false}
	service := testService(tx)

	_, err := service.RenameProject(context.Background(), RenameInput{TenantID: testTenantID, ProjectID: testProjectID, Title: "Renamed Novel", ActorID: testActorID})
	if ErrorCode(err) != CodeAccessDenied {
		t.Fatalf("expected access denied, got code=%s err=%v", ErrorCode(err), err)
	}
	if tx.committed || !tx.rolledBack {
		t.Fatalf("expected rollback without commit: %#v", tx)
	}
}

func testService(tx transaction) *Service {
	service := NewService(ServiceConfig{})
	service.beginTx = func(context.Context) (transaction, error) { return tx, nil }
	return service
}

type recordingTx struct {
	operations      []string
	arguments       map[string][]any
	managerAllowed  bool
	returnedProject []string
	updateNoRows    bool
	committed       bool
	rolledBack      bool
}

func (t *recordingTx) QueryRowContext(_ context.Context, query string, args ...any) rowScanner {
	operation := operationForQuery(query)
	t.record(operation, args)
	switch operation {
	case "require_manager":
		return recordingRow{boolValue: t.managerAllowed, hasBool: true}
	case "insert_project":
		return recordingRow{stringValues: t.returnedProject}
	case "update_project":
		if t.updateNoRows {
			return recordingRow{err: sql.ErrNoRows}
		}
		return recordingRow{stringValues: t.returnedProject}
	default:
		return recordingRow{err: errors.New("unexpected query")}
	}
}

func (t *recordingTx) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	t.record(operationForQuery(query), args)
	return driver.RowsAffected(1), nil
}

func (t *recordingTx) Commit() error {
	t.operations = append(t.operations, "commit")
	t.committed = true
	return nil
}

func (t *recordingTx) Rollback() error {
	if t.committed || t.rolledBack {
		return sql.ErrTxDone
	}
	t.operations = append(t.operations, "rollback")
	t.rolledBack = true
	return nil
}

func (t *recordingTx) record(operation string, args []any) {
	if t.arguments == nil {
		t.arguments = make(map[string][]any)
	}
	t.operations = append(t.operations, operation)
	t.arguments[operation] = append([]any(nil), args...)
}

type recordingRow struct {
	boolValue    bool
	hasBool      bool
	stringValues []string
	err          error
}

func (r recordingRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	if r.hasBool {
		if len(dest) != 1 {
			return errors.New("unexpected scan target count")
		}
		target, ok := dest[0].(*bool)
		if !ok {
			return errors.New("unexpected scan target")
		}
		*target = r.boolValue
		return nil
	}
	if len(dest) != len(r.stringValues) {
		return errors.New("unexpected scan target count")
	}
	for index, value := range r.stringValues {
		target, ok := dest[index].(*string)
		if !ok {
			return errors.New("unexpected scan target")
		}
		*target = value
	}
	return nil
}

func operationForQuery(query string) string {
	normalized := strings.ToLower(strings.Join(strings.Fields(query), " "))
	switch {
	case strings.HasPrefix(normalized, "select app_set_tenant_context"):
		return "set_context"
	case strings.HasPrefix(normalized, "select exists"):
		return "require_manager"
	case strings.HasPrefix(normalized, "insert into projects"):
		return "insert_project"
	case strings.HasPrefix(normalized, "insert into project_members"):
		return "insert_project_membership"
	case strings.HasPrefix(normalized, "insert into project_asset_distillation_settings"):
		return "insert_distillation_settings"
	case strings.HasPrefix(normalized, "insert into audit_logs"):
		return "audit"
	case strings.HasPrefix(normalized, "update projects"):
		return "update_project"
	default:
		return "unknown"
	}
}
