package llm

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLResolverResolvesProjectBindingWithCredentialRef(t *testing.T) {
	queryer := &recordingTenantBindingQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"tenant-123",
				"project-123",
				"writer_composer",
				"channel-1",
				"model-1",
				"openai-compatible",
				"https://llm.example.test/v1",
				true,
				true,
				`{"temperature":0.7}`,
			}},
		},
	}
	resolver := NewSQLResolver(SQLResolverConfig{Queryer: queryer})

	resolution, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ModuleKey: "writer_composer",
	})

	if err != nil {
		t.Fatalf("resolve module binding: %v", err)
	}
	if resolution.ModuleKey != "writer_composer" || resolution.ChannelID != "channel-1" || resolution.ModelID != "model-1" {
		t.Fatalf("unexpected resolution: %#v", resolution)
	}
	if resolution.CredentialRef != "channel-1" {
		t.Fatalf("expected credential ref to be channel id, got %#v", resolution)
	}
	if resolution.Settings["temperature"] != 0.7 {
		t.Fatalf("expected settings JSON to decode, got %#v", resolution.Settings)
	}
	if !strings.Contains(queryer.query, "FROM llm_module_bindings") || !strings.Contains(queryer.query, "FROM llm_platform_module_defaults") || !strings.Contains(queryer.query, "2 AS binding_rank") || !strings.Contains(queryer.query, "ORDER BY binding_rank") || !strings.Contains(queryer.query, "LIMIT 1") {
		t.Fatalf("expected project-priority binding query, got %s", queryer.query)
	}
	if strings.Count(queryer.query, "m.enabled = TRUE") != 2 {
		t.Fatalf("all tenant/platform resolution ranks must reject disabled models: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "writer_composer"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
	if queryer.plainCalled || queryer.tenantID != "tenant-123" {
		t.Fatalf("resolver bypassed tenant query context: %#v", queryer)
	}
}

func TestSQLResolverUsesTenantContextForRLSProtectedBindings(t *testing.T) {
	queryer := &recordingTenantBindingQueryer{
		rows: &fakeSQLRows{values: [][]any{{
			"tenant-123", "project-123", "writer_composer", "channel-1", "model-1",
			"openai-compatible", "https://llm.example.test/v1", true, true, `{}`,
		}},
		}}
	resolver := NewSQLResolver(SQLResolverConfig{Queryer: queryer})

	resolution, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ModuleKey: "writer_composer",
	})

	if err != nil {
		t.Fatalf("resolve RLS-protected module binding: %v", err)
	}
	if queryer.plainCalled || queryer.tenantID != "tenant-123" {
		t.Fatalf("resolver bypassed tenant query context: %#v", queryer)
	}
	if resolution.ChannelID != "channel-1" || resolution.ModuleKey != "writer_composer" {
		t.Fatalf("unexpected resolution: %#v", resolution)
	}
}

func TestSQLResolverReturnsExplicitUnboundErrorWhenMissing(t *testing.T) {
	resolver := NewSQLResolver(SQLResolverConfig{
		Queryer: &recordingTenantBindingQueryer{rows: &fakeSQLRows{}},
	})

	_, err := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ModuleKey: "writer_composer",
	})

	if code := ErrorCode(err); code != "LLM_MODULE_UNBOUND" {
		t.Fatalf("expected unbound error, got %s (%v)", code, err)
	}
}

type recordingTenantBindingQueryer struct {
	rows          SQLRows
	tenantID      string
	writeTenantID string
	query         string
	args          []any
	plainCalled   bool
}

func (q *recordingTenantBindingQueryer) QueryContext(context.Context, string, ...any) (SQLRows, error) {
	q.plainCalled = true
	return nil, nil
}

func (q *recordingTenantBindingQueryer) QueryTenantContext(_ context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.tenantID = tenantID
	q.query = query
	q.args = append([]any(nil), args...)
	return q.rows, nil
}

func (q *recordingTenantBindingQueryer) QueryTenantWriteContext(_ context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.writeTenantID = tenantID
	q.query = query
	q.args = append([]any(nil), args...)
	return q.rows, nil
}

func TestSQLBindingStoreListsEffectiveProjectBindings(t *testing.T) {
	queryer := &recordingTenantBindingQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"writer_composer",
				"project",
				"channel-1",
				"Draft Channel",
				"model-1",
				"openai-compatible",
				"https://llm.example.test/v1",
				true,
				true,
				`{"temperature":0.8}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: queryer})

	bindings, err := store.ListModuleBindings(context.Background(), ListModuleBindingsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("list module bindings: %v", err)
	}
	if len(bindings) != 1 {
		t.Fatalf("expected one binding, got %#v", bindings)
	}
	binding := bindings[0]
	if binding.Scope != "project" || binding.ModuleKey != "writer_composer" || binding.ChannelName != "Draft Channel" {
		t.Fatalf("unexpected binding: %#v", binding)
	}
	if binding.Settings["temperature"] != 0.8 {
		t.Fatalf("expected settings JSON to decode, got %#v", binding.Settings)
	}
	if !strings.Contains(queryer.query, "DISTINCT ON (module_key)") || !strings.Contains(queryer.query, "FROM llm_module_bindings") || !strings.Contains(queryer.query, "FROM llm_platform_module_defaults") || !strings.Contains(queryer.query, "'platform' AS scope") {
		t.Fatalf("expected effective binding list query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", 100}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
	if queryer.plainCalled || queryer.tenantID != "tenant-123" {
		t.Fatalf("binding list bypassed tenant query context: %#v", queryer)
	}
}

func TestSQLBindingStoreUpsertsProjectBindingThroughExistingChannelModel(t *testing.T) {
	queryer := &recordingTenantBindingQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"writer_composer",
				"project",
				"channel-1",
				"Draft Channel",
				"model-1",
				"openai-compatible",
				"https://llm.example.test/v1",
				true,
				true,
				`{"temperature":0.8}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: queryer})

	binding, err := store.UpsertProjectModuleBinding(context.Background(), UpsertProjectModuleBindingInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ActorID:   "user-123",
		ModuleKey: "writer_composer",
		ChannelID: "channel-1",
		ModelID:   "model-1",
		Settings:  map[string]any{"temperature": 0.8},
	})

	if err != nil {
		t.Fatalf("upsert module binding: %v", err)
	}
	if binding.ModuleKey != "writer_composer" || binding.Scope != "project" || binding.ChannelID != "channel-1" {
		t.Fatalf("unexpected upserted binding: %#v", binding)
	}
	if !strings.Contains(queryer.query, "INSERT INTO llm_module_bindings") || !strings.Contains(queryer.query, "JOIN llm_models") {
		t.Fatalf("expected binding upsert through existing channel/model, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "m.enabled = TRUE") {
		t.Fatalf("binding upsert accepted disabled model target query: %s", queryer.query)
	}
	if len(queryer.args) != 7 || queryer.args[0] != "tenant-123" || queryer.args[1] != "project-123" || queryer.args[2] != "writer_composer" || queryer.args[3] != "channel-1" || queryer.args[4] != "model-1" || queryer.args[6] != "user-123" {
		t.Fatalf("unexpected upsert args: %#v", queryer.args)
	}
	settingsJSON, _ := queryer.args[5].(string)
	if !strings.Contains(settingsJSON, `"temperature":0.8`) {
		t.Fatalf("expected settings JSON arg, got %#v", queryer.args)
	}
	if queryer.plainCalled || queryer.writeTenantID != "tenant-123" {
		t.Fatalf("binding upsert bypassed tenant write context: %#v", queryer)
	}
}

func TestSQLBindingStoreDeletesProjectBindingOverride(t *testing.T) {
	queryer := &recordingTenantBindingQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"writer_composer",
				"project",
				"channel-1",
				"Draft Channel",
				"model-1",
				"openai-compatible",
				"https://llm.example.test/v1",
				true,
				true,
				`{"temperature":0.8}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: queryer})

	binding, err := store.DeleteProjectModuleBinding(context.Background(), DeleteProjectModuleBindingInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ModuleKey: "writer_composer",
	})

	if err != nil {
		t.Fatalf("delete module binding: %v", err)
	}
	if binding.ModuleKey != "writer_composer" || binding.Scope != "project" || binding.ChannelID != "channel-1" {
		t.Fatalf("unexpected deleted binding: %#v", binding)
	}
	if !strings.Contains(queryer.query, "DELETE FROM llm_module_bindings") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected project override delete query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "writer_composer"}) {
		t.Fatalf("unexpected delete args: %#v", queryer.args)
	}
	if queryer.plainCalled || queryer.writeTenantID != "tenant-123" {
		t.Fatalf("binding delete bypassed tenant write context: %#v", queryer)
	}
}

func TestSQLBindingStoreDeleteMissingProjectBindingReturnsExplicitNotFound(t *testing.T) {
	store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: &recordingTenantBindingQueryer{rows: &fakeSQLRows{}}})

	_, err := store.DeleteProjectModuleBinding(context.Background(), DeleteProjectModuleBindingInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ModuleKey: "writer_composer",
	})

	if code := ErrorCode(err); code != "LLM_BINDING_NOT_FOUND" {
		t.Fatalf("expected binding not found error, got %s (%v)", code, err)
	}
}

func TestSQLResolverAndBindingStoreFailClosedWithoutTenantInterfaces(t *testing.T) {
	raw := &rawOnlySQLQueryer{rows: &fakeSQLRows{}}
	resolver := NewSQLResolver(SQLResolverConfig{Queryer: raw})
	store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: raw})

	_, resolveErr := resolver.ResolveModuleBinding(context.Background(), ResolveModuleInput{TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer"})
	_, listErr := store.ListModuleBindings(context.Background(), ListModuleBindingsInput{TenantID: "tenant-123", ProjectID: "project-123"})
	_, upsertErr := store.UpsertProjectModuleBinding(context.Background(), UpsertProjectModuleBindingInput{
		TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer", ChannelID: "channel-123", ModelID: "model-123",
	})
	_, deleteErr := store.DeleteProjectModuleBinding(context.Background(), DeleteProjectModuleBindingInput{TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer"})
	for _, err := range []error{resolveErr, listErr, upsertErr, deleteErr} {
		if code := ErrorCode(err); code != "LLM_BINDING_BACKEND_UNCONFIGURED" {
			t.Fatalf("expected tenant interface failure, got %s (%v)", code, err)
		}
	}
	if raw.calls != 0 {
		t.Fatalf("binding path fell back to raw QueryContext: calls=%d", raw.calls)
	}
}

func TestSQLBindingStoreWriteRowsCommitAndRollback(t *testing.T) {
	t.Run("commit after clean exhaustion", func(t *testing.T) {
		tx := &transactionFinalizerFixture{}
		queryer := &recordingTenantBindingQueryer{rows: &tenantScopedWriteRows{rows: bindingRowsFixture(), tx: tx}}
		store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: queryer})
		_, err := store.UpsertProjectModuleBinding(context.Background(), UpsertProjectModuleBindingInput{
			TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer", ChannelID: "channel-123", ModelID: "model-123",
		})
		if err != nil {
			t.Fatalf("upsert binding: %v", err)
		}
		if tx.commits != 1 || tx.rollbacks != 0 {
			t.Fatalf("write finalization mismatch: commits=%d rollbacks=%d", tx.commits, tx.rollbacks)
		}
	})
	t.Run("rollback on scan failure", func(t *testing.T) {
		tx := &transactionFinalizerFixture{}
		badRows := &catalogScanErrorRows{rows: bindingRowsFixture(), err: errors.New("scan failed")}
		queryer := &recordingTenantBindingQueryer{rows: &tenantScopedWriteRows{rows: badRows, tx: tx}}
		store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: queryer})
		_, err := store.DeleteProjectModuleBinding(context.Background(), DeleteProjectModuleBindingInput{
			TenantID: "tenant-123", ProjectID: "project-123", ModuleKey: "writer_composer",
		})
		if code := ErrorCode(err); code != "LLM_BINDING_DELETE_FAILED" {
			t.Fatalf("expected delete scan failure, got %s (%v)", code, err)
		}
		if tx.commits != 0 || tx.rollbacks != 1 {
			t.Fatalf("failed write finalization mismatch: commits=%d rollbacks=%d", tx.commits, tx.rollbacks)
		}
	})
}

func bindingRowsFixture() *fakeSQLRows {
	return &fakeSQLRows{values: [][]any{{
		"writer_composer", "project", "channel-123", "Channel", "model-123", "openai-compatible",
		"https://llm.example.test/v1", true, true, `{}`, "2026-07-11T00:00:00Z",
	}}}
}

func TestDisabledBindingStoreFailsExplicitly(t *testing.T) {
	store := NewDisabledBindingStore()

	_, err := store.ListModuleBindings(context.Background(), ListModuleBindingsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if code := ErrorCode(err); code != "LLM_BINDING_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected binding backend error, got %s (%v)", code, err)
	}
}
