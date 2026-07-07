package llm

import (
	"context"
	"reflect"
	"strings"
	"testing"
)

func TestSQLResolverResolvesProjectBindingWithCredentialRef(t *testing.T) {
	queryer := &recordingSQLQueryer{
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
	if !strings.Contains(queryer.query, "FROM llm_module_bindings") || !strings.Contains(queryer.query, "ORDER BY binding_rank") || !strings.Contains(queryer.query, "LIMIT 1") {
		t.Fatalf("expected project-priority binding query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "writer_composer"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLResolverReturnsExplicitUnboundErrorWhenMissing(t *testing.T) {
	resolver := NewSQLResolver(SQLResolverConfig{
		Queryer: &recordingSQLQueryer{rows: &fakeSQLRows{}},
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

func TestSQLBindingStoreListsEffectiveProjectBindings(t *testing.T) {
	queryer := &recordingSQLQueryer{
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
	if !strings.Contains(queryer.query, "DISTINCT ON (b.module_key)") || !strings.Contains(queryer.query, "FROM llm_module_bindings") {
		t.Fatalf("expected effective binding list query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", 100}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLBindingStoreUpsertsProjectBindingThroughExistingChannelModel(t *testing.T) {
	queryer := &recordingSQLQueryer{
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
	if len(queryer.args) != 7 || queryer.args[0] != "tenant-123" || queryer.args[1] != "project-123" || queryer.args[2] != "writer_composer" || queryer.args[3] != "channel-1" || queryer.args[4] != "model-1" || queryer.args[6] != "user-123" {
		t.Fatalf("unexpected upsert args: %#v", queryer.args)
	}
	settingsJSON, _ := queryer.args[5].(string)
	if !strings.Contains(settingsJSON, `"temperature":0.8`) {
		t.Fatalf("expected settings JSON arg, got %#v", queryer.args)
	}
}

func TestSQLBindingStoreDeletesProjectBindingOverride(t *testing.T) {
	queryer := &recordingSQLQueryer{
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
}

func TestSQLBindingStoreDeleteMissingProjectBindingReturnsExplicitNotFound(t *testing.T) {
	store := NewSQLBindingStore(SQLBindingStoreConfig{Queryer: &recordingSQLQueryer{rows: &fakeSQLRows{}}})

	_, err := store.DeleteProjectModuleBinding(context.Background(), DeleteProjectModuleBindingInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		ModuleKey: "writer_composer",
	})

	if code := ErrorCode(err); code != "LLM_BINDING_NOT_FOUND" {
		t.Fatalf("expected binding not found error, got %s (%v)", code, err)
	}
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
