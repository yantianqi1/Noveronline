package llm

import (
	"context"
	"strings"
)

// AnalysisRequiredModules must be bound before Pi analysis admission.
var AnalysisRequiredModules = []string{"analysis_planner", "analysis_worker"}

// EnsureAnalysisModuleBindings resolves analysis_planner + analysis_worker.
// Every module must be explicitly bound; cross-module borrowing would hide a
// configuration error and make model selection unpredictable.
func EnsureAnalysisModuleBindings(
	ctx context.Context,
	resolver Resolver,
	_ BindingStore,
	tenantID, projectID, _ string,
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

	var primary ModuleResolution
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
	if !resolution.SupportsTools || !resolution.SupportsJSON {
		return &AppError{
			Code:    "LLM_MODULE_CAPABILITY_MISSING",
			Message: resolution.ModuleKey + " binding must support tools and JSON",
		}
	}
	return nil
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
