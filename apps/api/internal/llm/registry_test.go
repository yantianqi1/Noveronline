package llm

import (
	"context"
	"strings"
	"testing"
)

func TestStaticModuleRegistryListsAllDocumentedModules(t *testing.T) {
	registry := NewStaticModuleRegistry()

	modules, err := registry.ListModules(context.Background(), ModuleRegistryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("list modules: %v", err)
	}
	if len(modules) != 24 {
		t.Fatalf("expected 24 documented modules, got %d: %#v", len(modules), modules)
	}
	byKey := map[string]ModuleRecord{}
	for _, module := range modules {
		if module.ModuleKey == "" || module.Group == "" || module.Label == "" {
			t.Fatalf("module record missing public metadata: %#v", module)
		}
		byKey[module.ModuleKey] = module
	}
	for _, key := range []string{"story_ontology", "asset_ingestion", "worldline_director", "writer_composer", "writer_reviewer"} {
		if _, ok := byKey[key]; !ok {
			t.Fatalf("expected module %s in registry: %#v", key, byKey)
		}
	}
	if byKey["writer_composer"].Group != "Writer" {
		t.Fatalf("expected writer_composer in Writer group, got %#v", byKey["writer_composer"])
	}
	if strings.Contains(strings.ToLower(strings.Join(moduleKeys(modules), ",")), "api_key") {
		t.Fatalf("module registry leaked credential material: %#v", modules)
	}
}

func TestStaticModuleRegistryRejectsMissingTenantProject(t *testing.T) {
	registry := NewStaticModuleRegistry()

	_, err := registry.ListModules(context.Background(), ModuleRegistryInput{TenantID: "tenant-123"})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error, got %s (%v)", code, err)
	}
}

func moduleKeys(modules []ModuleRecord) []string {
	keys := make([]string, 0, len(modules))
	for _, module := range modules {
		keys = append(keys, module.ModuleKey)
	}
	return keys
}
