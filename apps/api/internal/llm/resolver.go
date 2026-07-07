package llm

import (
	"context"
	"errors"
	"strings"
)

type ResolveModuleInput struct {
	TenantID  string
	ProjectID string
	ModuleKey string
}

type ModuleResolution struct {
	TenantID      string
	ProjectID     string
	ModuleKey     string
	ChannelID     string
	ModelID       string
	Provider      string
	BaseURL       string
	CredentialRef string
	SupportsTools bool
	SupportsJSON  bool
	Settings      map[string]any
}

type Resolver interface {
	ResolveModuleBinding(context.Context, ResolveModuleInput) (ModuleResolution, error)
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "LLM_PROVIDER_ERROR"
}

type StaticResolver struct {
	resolutions []ModuleResolution
}

func NewStaticResolver(resolutions []ModuleResolution) *StaticResolver {
	return &StaticResolver{resolutions: append([]ModuleResolution(nil), resolutions...)}
}

func (r *StaticResolver) ResolveModuleBinding(_ context.Context, input ResolveModuleInput) (ModuleResolution, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	moduleKey := strings.TrimSpace(input.ModuleKey)
	if tenantID == "" || moduleKey == "" {
		return ModuleResolution{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and module_key are required",
		}
	}
	var tenantDefault *ModuleResolution
	var platformDefault *ModuleResolution
	for index := range r.resolutions {
		resolution := r.resolutions[index]
		if resolution.ModuleKey != moduleKey {
			continue
		}
		if resolution.TenantID == tenantID && resolution.ProjectID == projectID && projectID != "" {
			return sanitized(resolution), nil
		}
		if resolution.TenantID == tenantID && resolution.ProjectID == "" {
			tenantDefault = &resolution
			continue
		}
		if resolution.TenantID == "" && resolution.ProjectID == "" {
			platformDefault = &resolution
		}
	}
	if tenantDefault != nil {
		return sanitized(*tenantDefault), nil
	}
	if platformDefault != nil {
		return sanitized(*platformDefault), nil
	}
	return ModuleResolution{}, &AppError{
		Code:    "LLM_MODULE_UNBOUND",
		Message: moduleKey + " module is not bound",
	}
}

func sanitized(resolution ModuleResolution) ModuleResolution {
	if resolution.Settings == nil {
		resolution.Settings = map[string]any{}
	}
	return resolution
}
