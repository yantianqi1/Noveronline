package llm

import (
	"context"
	"strings"
)

// WorldlineCastRequiredModules must be bound before goal-start admission.
var WorldlineCastRequiredModules = []string{"worldline_cast_planner"}

var worldlineCastBindingDonorPreference = []string{
	"worldline_cast_planner",
	"worldline_director",
	"worldline_agent_prepare",
	"writer_orchestrator",
	"writer_composer",
	"analysis_planner",
	"sequential_reading",
	"story_ontology",
}

// EnsureWorldlineCastModuleBindings resolves worldline_cast_planner.
// When unbound, copies channel/model from an existing tools-capable binding.
func EnsureWorldlineCastModuleBindings(
	ctx context.Context,
	resolver Resolver,
	store BindingStore,
	tenantID, projectID, actorID string,
) (ModuleResolution, error) {
	tenantID = strings.TrimSpace(tenantID)
	projectID = strings.TrimSpace(projectID)
	if tenantID == "" || projectID == "" {
		return ModuleResolution{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and project_id are required",
		}
	}
	if resolver == nil {
		return ModuleResolution{}, &AppError{
			Code:    "LLM_BINDING_BACKEND_UNCONFIGURED",
			Message: "LLM binding backend is not configured",
		}
	}

	resolution, err := resolver.ResolveModuleBinding(ctx, ResolveModuleInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: "worldline_cast_planner",
	})
	if err == nil {
		if err := assertAnalysisCapable(resolution); err != nil {
			return ModuleResolution{}, err
		}
		return resolution, nil
	}
	if ErrorCode(err) != "LLM_MODULE_UNBOUND" {
		return ModuleResolution{}, err
	}
	if store == nil {
		return ModuleResolution{}, &AppError{
			Code:    "LLM_MODULE_UNBOUND",
			Message: "worldline_cast_planner module is not bound",
		}
	}

	donor, donorErr := findWorldlineCastBindingDonor(ctx, store, tenantID, projectID)
	if donorErr != nil {
		return ModuleResolution{}, donorErr
	}
	if donor == nil {
		return ModuleResolution{}, &AppError{
			Code:    "LLM_MODULE_UNBOUND",
			Message: "worldline_cast_planner module is not bound",
		}
	}
	if _, upsertErr := store.UpsertProjectModuleBinding(ctx, UpsertProjectModuleBindingInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ActorID:   strings.TrimSpace(actorID),
		ModuleKey: "worldline_cast_planner",
		ChannelID: donor.ChannelID,
		ModelID:   donor.ModelID,
		Settings:  cloneSettings(donor.Settings),
	}); upsertErr != nil {
		return ModuleResolution{}, upsertErr
	}
	resolution, err = resolver.ResolveModuleBinding(ctx, ResolveModuleInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: "worldline_cast_planner",
	})
	if err != nil {
		return ModuleResolution{}, err
	}
	if err := assertAnalysisCapable(resolution); err != nil {
		return ModuleResolution{}, err
	}
	return resolution, nil
}

func findWorldlineCastBindingDonor(
	ctx context.Context,
	store BindingStore,
	tenantID, projectID string,
) (*ModuleBindingRecord, error) {
	bindings, err := store.ListModuleBindings(ctx, ListModuleBindingsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		return nil, err
	}
	byKey := map[string]ModuleBindingRecord{}
	for _, binding := range bindings {
		key := strings.TrimSpace(binding.ModuleKey)
		if key == "" {
			continue
		}
		caps := EffectiveModelCapabilities(binding.ModelID, binding.SupportsJSON, binding.SupportsTools)
		if !caps.SupportsTools || !caps.SupportsJSON {
			continue
		}
		existing, ok := byKey[key]
		if !ok || (existing.Scope != "project" && binding.Scope == "project") {
			byKey[key] = binding
		}
	}
	for _, key := range worldlineCastBindingDonorPreference {
		if binding, ok := byKey[key]; ok {
			copy := binding
			return &copy, nil
		}
	}
	for _, binding := range bindings {
		caps := EffectiveModelCapabilities(binding.ModelID, binding.SupportsJSON, binding.SupportsTools)
		if caps.SupportsTools && caps.SupportsJSON {
			copy := binding
			return &copy, nil
		}
	}
	return nil, nil
}
