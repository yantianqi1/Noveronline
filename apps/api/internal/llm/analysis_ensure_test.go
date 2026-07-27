package llm

import (
	"context"
	"testing"
)

func TestEnsureAnalysisModuleBindingsDoesNotBorrowWriterBinding(t *testing.T) {
	resolver := NewStaticResolver([]ModuleResolution{
		{
			TenantID:      "tenant-1",
			ProjectID:     "project-1",
			ModuleKey:     "writer_composer",
			ChannelID:     "channel-1",
			ModelID:       "deepseek-v4-flash",
			SupportsTools: true,
			SupportsJSON:  true,
			Settings:      map[string]any{"max_tokens": 2048},
		},
	})
	store := &memoryBindingStore{
		bindings: []ModuleBindingRecord{
			{
				ModuleKey:     "writer_composer",
				Scope:         "project",
				ChannelID:     "channel-1",
				ModelID:       "deepseek-v4-flash",
				SupportsTools: true,
				SupportsJSON:  true,
				Settings:      map[string]any{"max_tokens": 2048},
			},
		},
	}

	_, err := EnsureAnalysisModuleBindings(
		context.Background(),
		&ensureAwareResolver{inner: resolver, store: store},
		store,
		"tenant-1",
		"project-1",
		"actor-1",
	)
	if ErrorCode(err) != "LLM_MODULE_UNBOUND" {
		t.Fatalf("expected explicit unbound error, got %s (%v)", ErrorCode(err), err)
	}
	if len(store.upserts) != 0 {
		t.Fatalf("analysis binding must not be inferred from writer modules: %#v", store.upserts)
	}
}

func TestEnsureAnalysisModuleBindingsFailsClosedWithoutDonor(t *testing.T) {
	resolver := NewStaticResolver(nil)
	store := &memoryBindingStore{}
	_, err := EnsureAnalysisModuleBindings(
		context.Background(),
		resolver,
		store,
		"tenant-1",
		"project-1",
		"actor-1",
	)
	if ErrorCode(err) != "LLM_MODULE_UNBOUND" {
		t.Fatalf("expected LLM_MODULE_UNBOUND, got %s (%v)", ErrorCode(err), err)
	}
	if len(store.upserts) != 0 {
		t.Fatalf("unbound path must not upsert: %#v", store.upserts)
	}
}

type memoryBindingStore struct {
	bindings []ModuleBindingRecord
	upserts  []UpsertProjectModuleBindingInput
}

func (s *memoryBindingStore) ListModuleBindings(context.Context, ListModuleBindingsInput) ([]ModuleBindingRecord, error) {
	return append([]ModuleBindingRecord(nil), s.bindings...), nil
}

func (s *memoryBindingStore) UpsertProjectModuleBinding(_ context.Context, input UpsertProjectModuleBindingInput) (ModuleBindingRecord, error) {
	s.upserts = append(s.upserts, input)
	record := ModuleBindingRecord{
		ModuleKey:     input.ModuleKey,
		Scope:         "project",
		ChannelID:     input.ChannelID,
		ModelID:       input.ModelID,
		SupportsTools: true,
		SupportsJSON:  true,
		Settings:      cloneSettings(input.Settings),
	}
	replaced := false
	for index := range s.bindings {
		if s.bindings[index].ModuleKey == input.ModuleKey && s.bindings[index].Scope == "project" {
			s.bindings[index] = record
			replaced = true
			break
		}
	}
	if !replaced {
		s.bindings = append(s.bindings, record)
	}
	return record, nil
}

func (s *memoryBindingStore) DeleteProjectModuleBinding(context.Context, DeleteProjectModuleBindingInput) (ModuleBindingRecord, error) {
	return ModuleBindingRecord{}, &AppError{Code: "NOT_FOUND", Message: "not found"}
}

// ensureAwareResolver mirrors StaticResolver for unbound keys, then reads from the
// in-memory store after Ensure upserts so the second resolve pass succeeds.
type ensureAwareResolver struct {
	inner *StaticResolver
	store *memoryBindingStore
}

func (r *ensureAwareResolver) ResolveModuleBinding(ctx context.Context, input ResolveModuleInput) (ModuleResolution, error) {
	if resolution, err := r.inner.ResolveModuleBinding(ctx, input); err == nil {
		return resolution, nil
	} else if ErrorCode(err) != "LLM_MODULE_UNBOUND" {
		return ModuleResolution{}, err
	}
	for _, binding := range r.store.bindings {
		if binding.ModuleKey != input.ModuleKey {
			continue
		}
		return ModuleResolution{
			TenantID:      input.TenantID,
			ProjectID:     input.ProjectID,
			ModuleKey:     binding.ModuleKey,
			ChannelID:     binding.ChannelID,
			ModelID:       binding.ModelID,
			SupportsTools: binding.SupportsTools,
			SupportsJSON:  binding.SupportsJSON,
			Settings:      cloneSettings(binding.Settings),
		}, nil
	}
	return ModuleResolution{}, &AppError{
		Code:    "LLM_MODULE_UNBOUND",
		Message: input.ModuleKey + " module is not bound",
	}
}
