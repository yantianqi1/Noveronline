package httpapi

import (
	"encoding/json"
	"net/http"
	"strings"

	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/llm"
)

type upsertLLMQuotaPolicyRequest struct {
	ScopeType        string `json:"scope_type"`
	ProjectID        string `json:"project_id"`
	ModuleKey        string `json:"module_key"`
	TokenLimit       *int64 `json:"token_limit"`
	CostLimitMicros  *int64 `json:"cost_limit_micros"`
	ConcurrencyLimit *int   `json:"concurrency_limit"`
	PeriodSeconds    int    `json:"period_seconds"`
	Enabled          bool   `json:"enabled"`
}

func (s *Server) handleListLLMQuotaPolicies(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/quota-policies")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm quota policies route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	if s.llmQuotaStore == nil {
		writeLLMError(response, request, &llm.AppError{Code: "LLM_QUOTA_BACKEND_FAILED", Message: "LLM quota backend failed"})
		return
	}
	items, err := s.llmQuotaStore.ListPolicies(request.Context(), llm.QuotaPolicyQuery{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: strings.TrimSpace(request.URL.Query().Get("module_key")),
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.PersistentQuotaPolicy]{Items: items})
}

func (s *Server) handleUpsertLLMQuotaPolicy(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/quota-policies")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm quota policies route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionLLMModuleBindingManage) {
		return
	}
	if s.llmQuotaStore == nil {
		writeLLMError(response, request, &llm.AppError{Code: "LLM_QUOTA_BACKEND_FAILED", Message: "LLM quota backend failed"})
		return
	}
	var payload upsertLLMQuotaPolicyRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid llm quota policy payload", nil)
		return
	}
	policyProjectID := strings.TrimSpace(payload.ProjectID)
	if payload.ScopeType == llm.QuotaScopeTenant {
		policyProjectID = ""
	} else if policyProjectID == "" {
		policyProjectID = projectID
	}
	policy, err := s.llmQuotaStore.UpsertPolicy(request.Context(), llm.UpsertQuotaPolicyInput{
		TenantID:         tenantID,
		ActorUserID:      s.actorUserID(request),
		ScopeType:        strings.TrimSpace(payload.ScopeType),
		ProjectID:        policyProjectID,
		ModuleKey:        strings.TrimSpace(payload.ModuleKey),
		TokenLimit:       payload.TokenLimit,
		CostLimitMicros:  payload.CostLimitMicros,
		ConcurrencyLimit: payload.ConcurrencyLimit,
		PeriodSeconds:    payload.PeriodSeconds,
		Enabled:          payload.Enabled,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, policy)
}

func (s *Server) handleListLLMBillingUsage(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/billing-usage")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm billing usage route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.llmTelemetryReader.BillingUsage(request.Context(), llm.BillingUsageQuery{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: strings.TrimSpace(request.URL.Query().Get("module_key")),
	})
	if err != nil {
		writeLLMTelemetryError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.BillingUsageRecord]{Items: items})
}
