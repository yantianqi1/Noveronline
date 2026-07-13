package llmadmin

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"mirofish-novel/apps/api/internal/platformratelimit"
)

type Config struct {
	Store         Store
	Access        AccessController
	ActorResolver ActorResolver
	Health        *HealthService
	Metrics       ReconciliationMetrics
	RateLimiter   platformratelimit.Limiter
}

type ReconciliationMetrics interface {
	RecordQuotaReconciliationFailure()
}

type Handler struct {
	store         Store
	access        AccessController
	actorResolver ActorResolver
	health        *HealthService
	metrics       ReconciliationMetrics
	rateLimiter   platformratelimit.Limiter
}

func NewHandler(config Config) *Handler {
	return &Handler{store: config.Store, access: config.Access, actorResolver: config.ActorResolver, health: config.Health, metrics: config.Metrics, rateLimiter: config.RateLimiter}
}

func (h *Handler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Cache-Control", "private, no-store")
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" || h.actorResolver == nil {
		writeError(response, http.StatusUnauthorized, "UNAUTHENTICATED", "authentication is required")
		return
	}
	actorID, err := h.actorResolver.ResolveActor(request.Context(), request)
	if err != nil || strings.TrimSpace(actorID) == "" {
		writeError(response, http.StatusUnauthorized, "UNAUTHENTICATED", "authentication is required")
		return
	}
	operation, ok := operationFor(request.Method, request.URL.Path)
	if !ok {
		writeError(response, http.StatusNotFound, "NOT_FOUND", "LLM admin route was not found")
		return
	}
	if h.access == nil {
		writeError(response, http.StatusServiceUnavailable, "LLM_ADMIN_ACCESS_UNCONFIGURED", "LLM admin access backend is not configured")
		return
	}
	if err := h.access.Authorize(request.Context(), AccessInput{TenantID: tenantID, UserID: actorID, Operation: operation, RequestID: requestID(request)}); err != nil {
		status := http.StatusForbidden
		if ErrorCode(err) == "UNAUTHENTICATED" {
			status = http.StatusUnauthorized
		}
		writeError(response, status, ErrorCode(err), publicMessage(ErrorCode(err)))
		return
	}
	if h.store == nil && operation != OperationProviderHealth {
		writeError(response, http.StatusServiceUnavailable, "LLM_ADMIN_BACKEND_UNCONFIGURED", "LLM admin backend is not configured")
		return
	}
	h.dispatch(response, request, tenantID, actorID, operation)
}

func (h *Handler) dispatch(response http.ResponseWriter, request *http.Request, tenantID, actorID, operation string) {
	switch operation {
	case OperationPolicyRead:
		items, err := h.store.ListPolicies(request.Context(), tenantID, request.URL.Query().Get("project_id"))
		writeResult(response, map[string]any{"items": items}, err)
	case OperationPolicyWrite:
		h.writePolicy(response, request, tenantID, actorID)
	case OperationResolutionRead:
		result, err := h.store.PreviewResolution(request.Context(), tenantID, request.URL.Query().Get("project_id"), request.URL.Query().Get("module_key"))
		writeResult(response, result, err)
	case OperationReservationRead:
		items, err := h.store.ListReservations(request.Context(), tenantID, request.URL.Query().Get("project_id"), request.URL.Query().Get("status"), queryLimit(request))
		writeResult(response, map[string]any{"items": items}, err)
	case OperationReconciliationRead:
		items, err := h.store.Reconcile(request.Context(), tenantID, request.URL.Query().Get("project_id"), request.URL.Query().Get("module_key"), queryLimit(request))
		if err != nil && h.metrics != nil {
			h.metrics.RecordQuotaReconciliationFailure()
		}
		writeResult(response, map[string]any{"items": items}, err)
	case OperationProviderHealth:
		h.checkHealth(response, request, tenantID, actorID)
	}
}

func (h *Handler) writePolicy(response http.ResponseWriter, request *http.Request, tenantID, actorID string) {
	policyID := policyIDFromPath(request.URL.Path)
	if request.Method == http.MethodDelete {
		if !h.allowRateLimit(response, request, platformratelimit.Input{
			Class:    platformratelimit.ClassLLMAdminMutation,
			KeyParts: []string{tenantID, actorID, OperationPolicyWrite}, Cost: 1,
		}) {
			return
		}
		err := h.store.DeletePolicy(request.Context(), tenantID, actorID, policyID, request.URL.Query().Get("expected_version"))
		if err != nil {
			writeAppError(response, err)
			return
		}
		writeJSON(response, http.StatusOK, map[string]any{"ok": true, "policy_id": policyID})
		return
	}
	var input PolicyWrite
	if err := decodeJSON(request, &input); err != nil {
		writeError(response, http.StatusBadRequest, "VALIDATION_FAILED", "LLM admin request is invalid")
		return
	}
	if !h.allowRateLimit(response, request, platformratelimit.Input{
		Class:    platformratelimit.ClassLLMAdminMutation,
		KeyParts: []string{tenantID, actorID, OperationPolicyWrite}, Cost: 1,
	}) {
		return
	}
	var result Policy
	var err error
	status := http.StatusOK
	if request.Method == http.MethodPost {
		result, err = h.store.CreatePolicy(request.Context(), tenantID, actorID, input)
		status = http.StatusCreated
	} else {
		result, err = h.store.UpdatePolicy(request.Context(), tenantID, actorID, policyID, input)
	}
	if err != nil {
		writeAppError(response, err)
		return
	}
	writeJSON(response, status, result)
}

func (h *Handler) checkHealth(response http.ResponseWriter, request *http.Request, tenantID, actorID string) {
	if h.health == nil {
		writeError(response, http.StatusServiceUnavailable, "LLM_PROVIDER_HEALTH_UNCONFIGURED", "LLM provider health check is not configured")
		return
	}
	var input struct {
		ProjectID string `json:"project_id"`
		ChannelID string `json:"channel_id"`
		ModelID   string `json:"model_id"`
	}
	if err := decodeJSON(request, &input); err != nil {
		writeError(response, http.StatusBadRequest, "VALIDATION_FAILED", "LLM admin request is invalid")
		return
	}
	if strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.ChannelID) == "" || strings.TrimSpace(input.ModelID) == "" {
		writeError(response, http.StatusBadRequest, "VALIDATION_FAILED", "LLM admin request is invalid")
		return
	}
	if !h.allowRateLimit(response, request, platformratelimit.Input{
		Class:    platformratelimit.ClassLLMProviderHealth,
		KeyParts: []string{tenantID, actorID, strings.TrimSpace(input.ChannelID), strings.TrimSpace(input.ModelID)}, Cost: 1,
	}) {
		return
	}
	result, err := h.health.Check(request.Context(), tenantID, actorID, input.ProjectID, input.ChannelID, input.ModelID, requestID(request))
	writeResult(response, result, err)
}

func (h *Handler) allowRateLimit(response http.ResponseWriter, request *http.Request, input platformratelimit.Input) bool {
	if h.rateLimiter == nil {
		writeError(response, http.StatusServiceUnavailable, "RATE_LIMIT_BACKEND_UNAVAILABLE", "rate-limit backend is unavailable")
		return false
	}
	decision, err := h.rateLimiter.Allow(request.Context(), input)
	if err != nil {
		code := platformratelimit.ErrorCode(err)
		if code != "RATE_LIMIT_POLICY_UNCONFIGURED" {
			code = "RATE_LIMIT_BACKEND_UNAVAILABLE"
		}
		writeError(response, http.StatusServiceUnavailable, code, "rate-limit backend is unavailable")
		return false
	}
	if decision.Allowed {
		return true
	}
	retryAfter := int64((decision.RetryAfter + time.Second - 1) / time.Second)
	if retryAfter < 1 {
		retryAfter = 1
	}
	response.Header().Set("Retry-After", strconv.FormatInt(retryAfter, 10))
	writeError(response, http.StatusTooManyRequests, "RATE_LIMIT_EXCEEDED", "request rate limit exceeded")
	return false
}

func operationFor(method, path string) (string, bool) {
	switch {
	case path == "/v1/llm-admin/policies" && method == http.MethodGet:
		return OperationPolicyRead, true
	case path == "/v1/llm-admin/policies" && method == http.MethodPost:
		return OperationPolicyWrite, true
	case strings.HasPrefix(path, "/v1/llm-admin/policies/") && (method == http.MethodPut || method == http.MethodDelete) && policyIDFromPath(path) != "":
		return OperationPolicyWrite, true
	case path == "/v1/llm-admin/resolution" && method == http.MethodGet:
		return OperationResolutionRead, true
	case path == "/v1/llm-admin/reservations" && method == http.MethodGet:
		return OperationReservationRead, true
	case path == "/v1/llm-admin/reconciliation" && method == http.MethodGet:
		return OperationReconciliationRead, true
	case path == "/v1/llm-admin/provider-health" && method == http.MethodPost:
		return OperationProviderHealth, true
	default:
		return "", false
	}
}

func policyIDFromPath(path string) string {
	value := strings.TrimPrefix(path, "/v1/llm-admin/policies/")
	if value == path || value == "" || strings.Contains(value, "/") {
		return ""
	}
	return value
}

func decodeJSON(request *http.Request, target any) error {
	reader := io.LimitReader(request.Body, 64<<10)
	decoder := json.NewDecoder(reader)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("extra JSON value")
	}
	return nil
}

func queryLimit(request *http.Request) int {
	value, _ := strconv.Atoi(request.URL.Query().Get("limit"))
	return value
}
func requestID(request *http.Request) string {
	return strings.TrimSpace(request.Header.Get("X-Request-Id"))
}

func writeResult(response http.ResponseWriter, value any, err error) {
	if err != nil {
		writeAppError(response, err)
		return
	}
	writeJSON(response, http.StatusOK, value)
}

func writeAppError(response http.ResponseWriter, err error) {
	code := ErrorCode(err)
	status := http.StatusInternalServerError
	switch code {
	case "VALIDATION_FAILED":
		status = http.StatusBadRequest
	case "LLM_QUOTA_POLICY_NOT_FOUND":
		status = http.StatusNotFound
	case "LLM_QUOTA_POLICY_VERSION_CONFLICT", "LLM_QUOTA_POLICY_SCOPE_CONFLICT":
		status = http.StatusConflict
	case "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED", "LLM_EXTERNAL_PROVIDER_OPT_IN_REQUIRED", "LLM_PROVIDER_URL_INVALID", "LLM_PROVIDER_HEALTH_TARGET_INVALID", "LLM_PROVIDER_NETWORK_TARGET_FORBIDDEN":
		status = http.StatusUnprocessableEntity
	case "LLM_PROVIDER_HEALTH_UNCONFIGURED", "LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE":
		status = http.StatusServiceUnavailable
	case "LLM_PROVIDER_HEALTH_FAILED":
		status = http.StatusBadGateway
	}
	writeError(response, status, code, publicMessage(code))
}

func publicMessage(code string) string {
	messages := map[string]string{
		"AUTH_ACCESS_DENIED": "LLM admin access is denied", "UNAUTHENTICATED": "authentication is required",
		"VALIDATION_FAILED": "LLM admin request is invalid", "LLM_QUOTA_POLICY_NOT_FOUND": "LLM quota policy was not found",
		"LLM_QUOTA_POLICY_VERSION_CONFLICT":     "LLM quota policy changed; reload before saving",
		"LLM_QUOTA_POLICY_SCOPE_CONFLICT":       "A quota policy already exists for this scope",
		"LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED":  "External LLM providers require HTTPS",
		"LLM_EXTERNAL_PROVIDER_OPT_IN_REQUIRED": "External LLM provider access is not enabled",
		"LLM_PROVIDER_URL_INVALID":              "LLM provider URL is invalid", "LLM_PROVIDER_HEALTH_FAILED": "LLM provider health check failed",
		"LLM_PROVIDER_NETWORK_TARGET_FORBIDDEN":  "LLM provider network target is not allowed",
		"LLM_PROVIDER_HEALTH_UNCONFIGURED":       "LLM provider health check is not configured",
		"LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE": "LLM provider health target is unavailable",
		"LLM_PROVIDER_HEALTH_TARGET_INVALID":     "LLM provider health target is invalid",
	}
	if message := messages[code]; message != "" {
		return message
	}
	return "LLM admin request failed"
}

func writeError(response http.ResponseWriter, status int, code, message string) {
	writeJSON(response, status, map[string]any{"error": map[string]any{"code": code, "message": message, "details": map[string]any{}}})
}

func writeJSON(response http.ResponseWriter, status int, value any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(value)
}
