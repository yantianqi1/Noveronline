package projectadmin

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
)

// ActorResolver resolves the authenticated actor for a request.
type ActorResolver interface {
	ResolveActor(context.Context, *http.Request) (string, error)
}

// CSRFVerifier verifies CSRF protection for state-changing requests.
type CSRFVerifier interface {
	VerifyCSRF(context.Context, *http.Request) error
}

// HandlerConfig configures the HTTP handler.
type HandlerConfig struct {
	Service       *Service
	ActorResolver ActorResolver
	CSRFVerifier  CSRFVerifier
}

// Handler serves tenant-scoped novel (project) administration routes.
type Handler struct {
	service       *Service
	actorResolver ActorResolver
	csrfVerifier  CSRFVerifier
}

// NewHandler builds a Handler from config.
func NewHandler(config HandlerConfig) *Handler {
	return &Handler{service: config.Service, actorResolver: config.ActorResolver, csrfVerifier: config.CSRFVerifier}
}

// IsRoute reports whether the method/path pair is a project-admin route.
//
//	POST  /v1/tenants/{tenantId}/projects
//	PATCH /v1/tenants/{tenantId}/projects/{projectId}
func IsRoute(method, path string) bool {
	p := pathSegments(path)
	if len(p) < 4 || p[0] != "v1" || p[1] != "tenants" || p[3] != "projects" {
		return false
	}
	switch {
	case len(p) == 4:
		return method == http.MethodPost
	case len(p) == 5:
		return method == http.MethodPatch
	default:
		return false
	}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if hasMalformedPath(r.URL.Path) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "project route not found", requestID(r))
		return
	}
	p := pathSegments(r.URL.Path)
	if len(p) >= 4 && p[0] == "v1" && p[1] == "tenants" && p[3] == "projects" {
		tenantID := p[2]
		if len(p) == 4 && r.Method == http.MethodPost {
			h.create(w, r, tenantID)
			return
		}
		if len(p) == 5 && r.Method == http.MethodPatch {
			h.rename(w, r, tenantID, p[4])
			return
		}
	}
	writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method is not allowed", requestID(r))
}

func (h *Handler) create(w http.ResponseWriter, r *http.Request, tenantID string) {
	actor, ok := h.authorizedMutation(w, r)
	if !ok {
		return
	}
	var body struct {
		Title string `json:"title"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	project, err := h.service.CreateProject(r.Context(), CreateInput{TenantID: tenantID, Title: body.Title, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"ok": true, "project": project})
}

func (h *Handler) rename(w http.ResponseWriter, r *http.Request, tenantID, projectID string) {
	actor, ok := h.authorizedMutation(w, r)
	if !ok {
		return
	}
	var body struct {
		Title string `json:"title"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	project, err := h.service.RenameProject(r.Context(), RenameInput{TenantID: tenantID, ProjectID: projectID, Title: body.Title, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "project": project})
}

func (h *Handler) actor(w http.ResponseWriter, r *http.Request) (string, bool) {
	if h.service == nil || h.actorResolver == nil {
		writeError(w, http.StatusServiceUnavailable, CodeBackendUnavailable, "project administration backend is not configured", requestID(r))
		return "", false
	}
	actor, err := h.actorResolver.ResolveActor(r.Context(), r)
	if err != nil || strings.TrimSpace(actor) == "" {
		writeError(w, http.StatusUnauthorized, CodeUnauthenticated, "authentication is required", requestID(r))
		return "", false
	}
	return strings.TrimSpace(actor), true
}

func (h *Handler) authorizedMutation(w http.ResponseWriter, r *http.Request) (string, bool) {
	actor, ok := h.actor(w, r)
	if !ok {
		return "", false
	}
	if h.csrfVerifier == nil || h.csrfVerifier.VerifyCSRF(r.Context(), r) != nil {
		writeError(w, http.StatusForbidden, "CSRF_VALIDATION_FAILED", "CSRF validation failed", requestID(r))
		return "", false
	}
	return actor, true
}

func writeDomainError(w http.ResponseWriter, err error, requestID string) {
	code := ErrorCode(err)
	status := http.StatusInternalServerError
	details := map[string]any(nil)
	switch code {
	case CodeValidationFailed:
		status = http.StatusBadRequest
		if field := ErrorField(err); field != "" {
			details = map[string]any{"field": field}
		}
	case CodeUnauthenticated:
		status = http.StatusUnauthorized
	case CodeAccessDenied:
		status = http.StatusForbidden
	case CodeProjectNotFound:
		status = http.StatusNotFound
	}
	payload := map[string]any{"code": code, "message": err.Error(), "request_id": requestID}
	if details != nil {
		payload["details"] = details
	}
	writeJSON(w, status, map[string]any{"ok": false, "error": payload})
}

func writeError(w http.ResponseWriter, status int, code, message, requestID string) {
	writeJSON(w, status, map[string]any{"ok": false, "error": map[string]string{"code": code, "message": message, "request_id": requestID}})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func decodeJSON(w http.ResponseWriter, r *http.Request, target any) bool {
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeError(w, http.StatusBadRequest, CodeValidationFailed, "request body is invalid", requestID(r))
		return false
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeError(w, http.StatusBadRequest, CodeValidationFailed, "request body is invalid", requestID(r))
		return false
	}
	return true
}

func pathSegments(path string) []string {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		if part != "" {
			result = append(result, part)
		}
	}
	return result
}

func hasMalformedPath(path string) bool {
	return !strings.HasPrefix(path, "/") || strings.Contains(path, "//")
}

func requestID(r *http.Request) string { return strings.TrimSpace(r.Header.Get("X-Request-Id")) }
