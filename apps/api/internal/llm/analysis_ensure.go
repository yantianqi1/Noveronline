package llm

import (
	"context"
	"strings"
)

// AnalysisRequiredModules must be bound before Pi analysis admission.
var AnalysisRequiredModules = []string{"analysis_planner", "analysis_worker"}

// Preferred donors when analysis modules are unbound but the author already
// connected a chat-capable writing/analysis model elsewhere.
var analysisBindingDonorPreference = []string{
	"analysis_planner",
	"analysis_worker",
	"writer_orchestrator",
	"writer_composer",
	"sequential_reading",
	"story_ontology",
	"contextual_block_analysis",
	"writer_reviewer",
	"worldline_director",
}

// EnsureAnalysisModuleBindings resolves analysis_planner + analysis_worker.
// When either is unbound, it copies channel/model settings from an existing
// tools/JSON-capable project or tenant binding so authors who already connected
// a writing model do not fail mid-pipeline on newly introduced analysis keys.
func EnsureAnalysisModuleBindings(
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

	missing := make([]string, 0, len(AnalysisRequiredModules))
	var primary ModuleResolution
	for _, moduleKey := range AnalysisRequiredModules {
		resolution, err := resolver.ResolveModuleBinding(ctx, ResolveModuleInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			ModuleKey: moduleKey,
		})
		if err != nil {
			if ErrorCode(err) == "LLM_MODULE_UNBOUND" {
				missing = append(missing, moduleKey)
				continue
			}
			return ModuleResolution{}, err
		}
		if err := assertAnalysisCapable(resolution); err != nil {
			return ModuleResolution{}, err
		}
		if moduleKey == "analysis_planner" || primary.ModuleKey == "" {
			primary = resolution
		}
	}
	if len(missing) == 0 {
		return primary, nil
	}
	if store == nil {
		return ModuleResolution{}, &AppError{
			Code:    "LLM_MODULE_UNBOUND",
			Message: missing[0] + " module is not bound",
		}
	}

	donor, err := findAnalysisBindingDonor(ctx, store, tenantID, projectID)
	if err != nil {
		return ModuleResolution{}, err
	}
	if donor == nil {
		return ModuleResolution{}, &AppError{
			Code:    "LLM_MODULE_UNBOUND",
			Message: missing[0] + " module is not bound",
		}
	}

	for _, moduleKey := range missing {
		if _, upsertErr := store.UpsertProjectModuleBinding(ctx, UpsertProjectModuleBindingInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			ActorID:   strings.TrimSpace(actorID),
			ModuleKey: moduleKey,
			ChannelID: donor.ChannelID,
			ModelID:   donor.ModelID,
			Settings:  cloneSettings(donor.Settings),
		}); upsertErr != nil {
			return ModuleResolution{}, upsertErr
		}
	}

	primary = ModuleResolution{}
	for _, moduleKey := range AnalysisRequiredModules {
		resolution, err := resolver.ResolveModuleBinding(ctx, ResolveModuleInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			ModuleKey: moduleKey,
		})
		if err != nil {
			return ModuleResolution{}, err
		}
		if err := assertAnalysisCapable(resolution); err != nil {
			return ModuleResolution{}, err
		}
		if moduleKey == "analysis_planner" || primary.ModuleKey == "" {
			primary = resolution
		}
	}
	return primary, nil
}

func assertAnalysisCapable(resolution ModuleResolution) error {
	caps := EffectiveModelCapabilities(resolution.ModelID, resolution.SupportsJSON, resolution.SupportsTools)
	if !caps.SupportsTools || !caps.SupportsJSON {
		return &AppError{
			Code:    "LLM_MODULE_CAPABILITY_MISSING",
			Message: resolution.ModuleKey + " binding must support tools and JSON",
		}
	}
	return nil
}

func findAnalysisBindingDonor(
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
	for _, key := range analysisBindingDonorPreference {
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

func cloneSettings(settings map[string]any) map[string]any {
	if settings == nil {
		return map[string]any{}
	}
	cloned := make(map[string]any, len(settings))
	for key, value := range settings {
		cloned[key] = value
	}
	return cloned
}
