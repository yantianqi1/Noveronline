package registration

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
)

const (
	testUserID    = "11111111-1111-4111-8111-111111111111"
	testTenantID  = "22222222-2222-4222-8222-222222222222"
	testProjectID = "33333333-3333-4333-8333-333333333333"
)

func TestServiceRegisterCreatesPersonalWorkspaceAndProjectAtomically(t *testing.T) {
	tx := &recordingTransaction{}
	service := testService(tx)

	result, err := service.Register(context.Background(), RegisterInput{
		DisplayName:           "  Lin Yan  ",
		Email:                 "  LIN.YAN@EXAMPLE.COM  ",
		Password:              "correct horse battery staple",
		ProjectTitle:          "  First Novel  ",
		InitialSessionFactory: testInitialSessionFactory,
	})
	if err != nil {
		t.Fatalf("register: code=%s err=%v", ErrorCode(err), err)
	}

	if !tx.committed || tx.rolledBack {
		t.Fatalf("registration transaction was not committed exactly once: %#v", tx)
	}
	wantOperations := []string{
		"email_lookup",
		"insert_user",
		"insert_credential",
		"insert_session",
		"insert_workspace",
		"set_context",
		"insert_workspace_membership",
		"insert_project",
		"insert_project_membership",
		"insert_distillation_settings",
		"insert_default_quota_policy",
		"commit",
	}
	if !reflect.DeepEqual(tx.operations, wantOperations) {
		t.Fatalf("unexpected transaction order:\n got: %#v\nwant: %#v", tx.operations, wantOperations)
	}

	if result.User != (UserSummary{UserID: testUserID, Email: "lin.yan@example.com", DisplayName: "Lin Yan"}) {
		t.Fatalf("unexpected user result: %#v", result.User)
	}
	if result.Workspace.TenantID != testTenantID || result.Workspace.Slug != "workspace-22222222222242228222222222222222" ||
		result.Workspace.Name != "Lin Yan 的工作区" || result.Workspace.Type != "personal" ||
		result.Workspace.Role != "owner" || result.Workspace.Status != "active" {
		t.Fatalf("unexpected workspace result: %#v", result.Workspace)
	}
	if result.Project != (ProjectSummary{
		TenantID:  testTenantID,
		ProjectID: testProjectID,
		Title:     "First Novel",
		Role:      "project_owner",
		Status:    "active",
	}) {
		t.Fatalf("unexpected project result: %#v", result.Project)
	}

	credentialArgs := tx.arguments["insert_credential"]
	if len(credentialArgs) != 2 {
		t.Fatalf("unexpected credential args: %#v", credentialArgs)
	}
	passwordHash, ok := credentialArgs[1].(string)
	if !ok || bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte("correct horse battery staple")) != nil {
		t.Fatalf("credential did not contain a matching bcrypt hash: %#v", credentialArgs)
	}
	if passwordHash == "correct horse battery staple" {
		t.Fatal("plaintext password was stored")
	}
	for operation, args := range tx.arguments {
		for _, argument := range args {
			if argument == "correct horse battery staple" {
				t.Fatalf("operation %s received the plaintext password", operation)
			}
		}
	}
	if !reflect.DeepEqual(tx.arguments["set_context"], []any{testTenantID, testUserID}) {
		t.Fatalf("unexpected RLS context args: %#v", tx.arguments["set_context"])
	}
	if !reflect.DeepEqual(tx.arguments["insert_session"], []any{testUserID, "session-token-hash", testSessionExpiry()}) {
		t.Fatalf("unexpected initial session args: %#v", tx.arguments["insert_session"])
	}
	if !reflect.DeepEqual(tx.arguments["insert_default_quota_policy"], []any{testTenantID, testUserID}) {
		t.Fatalf("unexpected default quota policy args: %#v", tx.arguments["insert_default_quota_policy"])
	}
}

func TestServiceRegisterCreatesDefaultTenantQuotaPolicy(t *testing.T) {
	tx := &recordingTransaction{}
	service := testService(tx)

	_, err := service.Register(context.Background(), validRegisterInput(nil))
	if err != nil {
		t.Fatalf("register: %v", err)
	}
	if _, ok := tx.arguments["insert_default_quota_policy"]; !ok {
		t.Fatalf("expected default quota policy insert, got operations: %#v", tx.operations)
	}
}

func TestServiceRegisterRejectsInvalidInputBeforeHashingOrSQL(t *testing.T) {
	tests := []struct {
		name  string
		input RegisterInput
		field string
	}{
		{name: "display name empty", input: validRegisterInput(func(input *RegisterInput) { input.DisplayName = "  " }), field: "display_name"},
		{name: "display name too long", input: validRegisterInput(func(input *RegisterInput) { input.DisplayName = strings.Repeat("a", 121) }), field: "display_name"},
		{name: "display name control", input: validRegisterInput(func(input *RegisterInput) { input.DisplayName = "Lin\nYan" }), field: "display_name"},
		{name: "email invalid", input: validRegisterInput(func(input *RegisterInput) { input.Email = "not-an-email" }), field: "email"},
		{name: "email display syntax", input: validRegisterInput(func(input *RegisterInput) { input.Email = "Lin <lin@example.com>" }), field: "email"},
		{name: "password too short", input: validRegisterInput(func(input *RegisterInput) { input.Password = "short" }), field: "password"},
		{name: "password too long", input: validRegisterInput(func(input *RegisterInput) { input.Password = strings.Repeat("p", 73) }), field: "password"},
		{name: "project title empty", input: validRegisterInput(func(input *RegisterInput) { input.ProjectTitle = "\t" }), field: "project_title"},
		{name: "project title too long", input: validRegisterInput(func(input *RegisterInput) { input.ProjectTitle = strings.Repeat("n", 201) }), field: "project_title"},
		{name: "project title control", input: validRegisterInput(func(input *RegisterInput) { input.ProjectTitle = "First\nNovel" }), field: "project_title"},
	}

	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			hashCalls := 0
			beginCalls := 0
			service := NewService(ServiceConfig{BcryptCost: bcrypt.MinCost})
			service.hashPassword = func([]byte, int) ([]byte, error) {
				hashCalls++
				return nil, errors.New("unexpected hash")
			}
			service.beginTx = func(context.Context) (transaction, error) {
				beginCalls++
				return &recordingTransaction{}, nil
			}

			_, err := service.Register(context.Background(), testCase.input)
			if ErrorCode(err) != CodeValidationFailed || ErrorField(err) != testCase.field {
				t.Fatalf("code=%s field=%s err=%v", ErrorCode(err), ErrorField(err), err)
			}
			if hashCalls != 0 || beginCalls != 0 {
				t.Fatalf("invalid input reached dependencies: hash=%d begin=%d", hashCalls, beginCalls)
			}
		})
	}
}

func TestServiceRegisterReturnsStableEmailConflictAndRollsBack(t *testing.T) {
	tx := &recordingTransaction{emailExists: true}
	service := testService(tx)

	_, err := service.Register(context.Background(), validRegisterInput(nil))
	if ErrorCode(err) != CodeEmailConflict || ErrorField(err) != "email" {
		t.Fatalf("code=%s field=%s err=%v", ErrorCode(err), ErrorField(err), err)
	}
	if !tx.rolledBack || tx.committed {
		t.Fatalf("email conflict did not roll back: %#v", tx)
	}
	if !reflect.DeepEqual(tx.operations, []string{"email_lookup", "rollback"}) {
		t.Fatalf("email conflict performed writes: %#v", tx.operations)
	}
}

func TestServiceRegisterMapsConcurrentUniqueEmailToStableConflict(t *testing.T) {
	tx := &recordingTransaction{
		failAt:  "insert_user",
		failErr: testSQLStateError{state: "23505"},
	}
	service := testService(tx)

	_, err := service.Register(context.Background(), validRegisterInput(nil))
	if ErrorCode(err) != CodeEmailConflict || ErrorField(err) != "email" {
		t.Fatalf("code=%s field=%s err=%v", ErrorCode(err), ErrorField(err), err)
	}
	if !tx.rolledBack || tx.committed {
		t.Fatalf("unique conflict did not roll back: %#v", tx)
	}
	if strings.Contains(err.Error(), "23505") {
		t.Fatalf("database details leaked: %v", err)
	}
}

func TestServiceRegisterRollsBackEveryWriteFailure(t *testing.T) {
	for _, operation := range []string{
		"email_lookup",
		"insert_user",
		"insert_credential",
		"insert_session",
		"insert_workspace",
		"set_context",
		"insert_workspace_membership",
		"insert_project",
		"insert_project_membership",
		"insert_distillation_settings",
		"insert_default_quota_policy",
		"commit",
	} {
		t.Run(operation, func(t *testing.T) {
			tx := &recordingTransaction{failAt: operation, failErr: errors.New("private database failure")}
			service := testService(tx)

			_, err := service.Register(context.Background(), validRegisterInput(nil))
			if ErrorCode(err) != CodeRegistrationFailed || err.Error() != "registration failed" {
				t.Fatalf("code=%s err=%v", ErrorCode(err), err)
			}
			if !tx.rolledBack || tx.committed {
				t.Fatalf("operation %s did not roll back: %#v", operation, tx)
			}
			if strings.Contains(err.Error(), "private") {
				t.Fatalf("operation %s leaked database error: %v", operation, err)
			}
		})
	}
}

func TestServiceRegisterFailsClosedWhenDependenciesFail(t *testing.T) {
	t.Run("backend unconfigured", func(t *testing.T) {
		_, err := NewService(ServiceConfig{}).Register(context.Background(), validRegisterInput(nil))
		if ErrorCode(err) != CodeBackendUnconfigured {
			t.Fatalf("code=%s err=%v", ErrorCode(err), err)
		}
	})

	t.Run("password hash", func(t *testing.T) {
		beginCalls := 0
		service := NewService(ServiceConfig{})
		service.beginTx = func(context.Context) (transaction, error) {
			beginCalls++
			return &recordingTransaction{}, nil
		}
		service.hashPassword = func([]byte, int) ([]byte, error) {
			return nil, errors.New("private hash failure")
		}
		_, err := service.Register(context.Background(), validRegisterInput(nil))
		if ErrorCode(err) != CodeRegistrationFailed || beginCalls != 0 {
			t.Fatalf("code=%s begin=%d err=%v", ErrorCode(err), beginCalls, err)
		}
	})

	t.Run("identity generation", func(t *testing.T) {
		beginCalls := 0
		service := NewService(ServiceConfig{BcryptCost: bcrypt.MinCost})
		service.beginTx = func(context.Context) (transaction, error) {
			beginCalls++
			return &recordingTransaction{}, nil
		}
		service.newUUID = func() (uuid.UUID, error) {
			return uuid.Nil, errors.New("private entropy failure")
		}
		_, err := service.Register(context.Background(), validRegisterInput(nil))
		if ErrorCode(err) != CodeRegistrationFailed || beginCalls != 0 {
			t.Fatalf("code=%s begin=%d err=%v", ErrorCode(err), beginCalls, err)
		}
	})

	t.Run("begin transaction", func(t *testing.T) {
		service := NewService(ServiceConfig{BcryptCost: bcrypt.MinCost})
		service.beginTx = func(context.Context) (transaction, error) {
			return nil, errors.New("private connection failure")
		}
		service.newUUID = fixedUUIDGenerator()
		_, err := service.Register(context.Background(), validRegisterInput(nil))
		if ErrorCode(err) != CodeRegistrationFailed || strings.Contains(err.Error(), "private") {
			t.Fatalf("code=%s err=%v", ErrorCode(err), err)
		}
	})
}

func testService(tx transaction) *Service {
	service := NewService(ServiceConfig{BcryptCost: bcrypt.MinCost})
	service.beginTx = func(context.Context) (transaction, error) { return tx, nil }
	service.newUUID = fixedUUIDGenerator()
	return service
}

func fixedUUIDGenerator() func() (uuid.UUID, error) {
	values := []uuid.UUID{
		uuid.MustParse(testUserID),
		uuid.MustParse(testTenantID),
		uuid.MustParse(testProjectID),
	}
	index := 0
	return func() (uuid.UUID, error) {
		if index >= len(values) {
			return uuid.Nil, errors.New("fixed UUIDs exhausted")
		}
		value := values[index]
		index++
		return value, nil
	}
}

func validRegisterInput(mutate func(*RegisterInput)) RegisterInput {
	input := RegisterInput{
		DisplayName:           "Lin Yan",
		Email:                 "lin.yan@example.com",
		Password:              "correct horse battery staple",
		ProjectTitle:          "First Novel",
		InitialSessionFactory: testInitialSessionFactory,
	}
	if mutate != nil {
		mutate(&input)
	}
	return input
}

func testInitialSessionFactory(userID string) (InitialSession, error) {
	if userID != testUserID {
		return InitialSession{}, errors.New("unexpected initial session user")
	}
	return InitialSession{TokenHash: "session-token-hash", ExpiresAt: testSessionExpiry()}, nil
}

func testSessionExpiry() time.Time {
	return time.Date(2030, 1, 2, 3, 4, 5, 0, time.UTC)
}

type recordingTransaction struct {
	operations  []string
	arguments   map[string][]any
	emailExists bool
	failAt      string
	failErr     error
	committed   bool
	rolledBack  bool
}

func (t *recordingTransaction) QueryRowContext(_ context.Context, query string, args ...any) rowScanner {
	operation := operationForQuery(query)
	t.record(operation, args)
	if operation == t.failAt {
		return recordingRow{err: t.failure()}
	}
	return recordingRow{value: t.emailExists}
}

func (t *recordingTransaction) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	operation := operationForQuery(query)
	t.record(operation, args)
	if operation == t.failAt {
		return nil, t.failure()
	}
	return driver.RowsAffected(1), nil
}

func (t *recordingTransaction) Commit() error {
	t.operations = append(t.operations, "commit")
	if t.failAt == "commit" {
		return t.failure()
	}
	t.committed = true
	return nil
}

func (t *recordingTransaction) Rollback() error {
	if t.committed || t.rolledBack {
		return sql.ErrTxDone
	}
	t.operations = append(t.operations, "rollback")
	t.rolledBack = true
	return nil
}

func (t *recordingTransaction) record(operation string, args []any) {
	if t.arguments == nil {
		t.arguments = make(map[string][]any)
	}
	t.operations = append(t.operations, operation)
	t.arguments[operation] = append([]any(nil), args...)
}

func (t *recordingTransaction) failure() error {
	if t.failErr != nil {
		return t.failErr
	}
	return errors.New("transaction operation failed")
}

type recordingRow struct {
	value bool
	err   error
}

func (r recordingRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	if len(dest) != 1 {
		return errors.New("unexpected scan target count")
	}
	target, ok := dest[0].(*bool)
	if !ok {
		return errors.New("unexpected scan target")
	}
	*target = r.value
	return nil
}

type testSQLStateError struct {
	state string
}

func (e testSQLStateError) Error() string    { return "private SQL state " + e.state }
func (e testSQLStateError) SQLState() string { return e.state }

func operationForQuery(query string) string {
	normalized := strings.ToLower(strings.Join(strings.Fields(query), " "))
	switch {
	case strings.HasPrefix(normalized, "select exists"):
		return "email_lookup"
	case strings.HasPrefix(normalized, "insert into users"):
		return "insert_user"
	case strings.HasPrefix(normalized, "insert into user_password_credentials"):
		return "insert_credential"
	case strings.HasPrefix(normalized, "insert into user_sessions"):
		return "insert_session"
	case strings.HasPrefix(normalized, "insert into tenants"):
		return "insert_workspace"
	case strings.HasPrefix(normalized, "select app_set_tenant_context"):
		return "set_context"
	case strings.HasPrefix(normalized, "insert into tenant_memberships"):
		return "insert_workspace_membership"
	case strings.HasPrefix(normalized, "insert into projects"):
		return "insert_project"
	case strings.HasPrefix(normalized, "insert into project_members"):
		return "insert_project_membership"
	case strings.HasPrefix(normalized, "insert into project_asset_distillation_settings"):
		return "insert_distillation_settings"
	case strings.HasPrefix(normalized, "insert into llm_quota_policies"):
		return "insert_default_quota_policy"
	default:
		return "unknown"
	}
}
