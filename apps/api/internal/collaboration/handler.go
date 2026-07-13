package collaboration

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"mirofish-novel/apps/api/internal/platformratelimit"
)

type ActorResolver interface {
	ResolveActor(context.Context, *http.Request) (string, error)
}

type CSRFVerifier interface {
	VerifyCSRF(context.Context, *http.Request) error
}

type TrustedClientKeyResolver interface {
	ResolveTrustedClientKey(context.Context, *http.Request) (string, error)
}

type HandlerConfig struct {
	Service                  *Service
	ActorResolver            ActorResolver
	CSRFVerifier             CSRFVerifier
	RateLimiter              platformratelimit.Limiter
	TrustedClientKeyResolver TrustedClientKeyResolver
}

type Handler struct {
	service                  *Service
	actorResolver            ActorResolver
	csrfVerifier             CSRFVerifier
	rateLimiter              platformratelimit.Limiter
	trustedClientKeyResolver TrustedClientKeyResolver
}

func NewHandler(config HandlerConfig) *Handler {
	return &Handler{
		service: config.Service, actorResolver: config.ActorResolver, csrfVerifier: config.CSRFVerifier,
		rateLimiter: config.RateLimiter, trustedClientKeyResolver: config.TrustedClientKeyResolver,
	}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if hasMalformedPath(r.URL.Path) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "collaboration route not found", requestID(r))
		return
	}
	segments := pathSegments(r.URL.Path)
	if len(segments) == 4 && segments[0] == "v1" && segments[1] == "collaboration" && segments[2] == "invitations" && segments[3] == "accept" {
		h.accept(w, r)
		return
	}
	if len(segments) >= 4 && segments[0] == "v1" && segments[1] == "tenants" {
		h.tenantRoute(w, r, segments)
		return
	}
	writeError(w, http.StatusNotFound, "NOT_FOUND", "collaboration route not found", requestID(r))
}

func (h *Handler) tenantRoute(w http.ResponseWriter, r *http.Request, p []string) {
	tenantID := p[2]
	if len(p) == 4 && p[3] == "invitations" {
		if r.Method == http.MethodGet {
			h.listInvitations(w, r, tenantID)
			return
		}
		if r.Method == http.MethodPost {
			h.create(w, r, tenantID)
			return
		}
	}
	if len(p) == 5 && p[3] == "invitations" {
		if r.Method == http.MethodDelete {
			h.revoke(w, r, tenantID, p[4])
			return
		}
	}
	if len(p) == 6 && p[3] == "invitations" && p[5] == "resend" && r.Method == http.MethodPost {
		h.resend(w, r, tenantID, p[4])
		return
	}
	if len(p) == 4 && p[3] == "members" && r.Method == http.MethodGet {
		h.list(w, r, tenantID, "")
		return
	}
	if len(p) == 5 && p[3] == "members" {
		if r.Method == http.MethodPatch {
			h.change(w, r, tenantID, "", p[4])
			return
		}
		if r.Method == http.MethodDelete {
			h.remove(w, r, tenantID, "", p[4])
			return
		}
	}
	if len(p) == 6 && p[3] == "projects" && p[5] == "members" && r.Method == http.MethodGet {
		h.list(w, r, tenantID, p[4])
		return
	}
	if len(p) == 7 && p[3] == "projects" && p[5] == "members" {
		if r.Method == http.MethodPatch {
			h.change(w, r, tenantID, p[4], p[6])
			return
		}
		if r.Method == http.MethodDelete {
			h.remove(w, r, tenantID, p[4], p[6])
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
		Email       string `json:"email"`
		ProjectID   string `json:"project_id"`
		TenantRole  string `json:"tenant_role"`
		ProjectRole string `json:"project_role"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	input := CreateInvitationInput{TenantID: tenantID, ProjectID: body.ProjectID, Email: body.Email, TenantRole: body.TenantRole, ProjectRole: body.ProjectRole, ActorID: actor, RequestID: requestID(r)}
	if err := validateCreate(input); err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	if !h.allowRateLimit(w, r, platformratelimit.Input{
		Class:    platformratelimit.ClassCollaborationInviteCreate,
		KeyParts: []string{tenantID, actor, strings.ToLower(strings.TrimSpace(body.Email))}, Cost: 1,
	}) {
		return
	}
	result, err := h.service.CreateInvitation(r.Context(), input)
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"ok": true, "invitation": result})
}

func (h *Handler) resend(w http.ResponseWriter, r *http.Request, tenantID, invitationID string) {
	actor, ok := h.authorizedMutation(w, r)
	if !ok {
		return
	}
	result, err := h.service.ResendInvitation(r.Context(), InvitationActionInput{TenantID: tenantID, InvitationID: invitationID, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "invitation": result})
}

func (h *Handler) revoke(w http.ResponseWriter, r *http.Request, tenantID, invitationID string) {
	actor, ok := h.authorizedMutation(w, r)
	if !ok {
		return
	}
	result, err := h.service.RevokeInvitation(r.Context(), InvitationActionInput{TenantID: tenantID, InvitationID: invitationID, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "invitation": result})
}

func (h *Handler) accept(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method is not allowed", requestID(r))
		return
	}
	actor, ok := h.authorizedMutation(w, r)
	if !ok {
		return
	}
	var body struct {
		Token string `json:"token"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if strings.TrimSpace(body.Token) == "" {
		writeError(w, http.StatusBadRequest, CodeValidationFailed, "token and authenticated user are required", requestID(r))
		return
	}
	if h.trustedClientKeyResolver == nil {
		writeError(w, http.StatusServiceUnavailable, "RATE_LIMIT_BACKEND_UNAVAILABLE", "rate-limit backend is unavailable", requestID(r))
		return
	}
	clientKey, err := h.trustedClientKeyResolver.ResolveTrustedClientKey(r.Context(), r)
	if err != nil || strings.TrimSpace(clientKey) == "" {
		writeError(w, http.StatusServiceUnavailable, "RATE_LIMIT_BACKEND_UNAVAILABLE", "rate-limit backend is unavailable", requestID(r))
		return
	}
	tokenHash := sha256.Sum256([]byte(body.Token))
	if !h.allowRateLimit(w, r, platformratelimit.Input{
		Class:    platformratelimit.ClassCollaborationInviteAccept,
		KeyParts: []string{strings.TrimSpace(clientKey), fmt.Sprintf("%x", tokenHash[:])}, Cost: 1,
	}) {
		return
	}
	result, err := h.service.AcceptInvitation(r.Context(), AcceptInvitationInput{Token: body.Token, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "invitation": result})
}

func (h *Handler) list(w http.ResponseWriter, r *http.Request, tenantID, projectID string) {
	actor, ok := h.actor(w, r)
	if !ok {
		return
	}
	items, err := h.service.ListMembers(r.Context(), ListInput{TenantID: tenantID, ProjectID: projectID, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "members": items})
}

func (h *Handler) listInvitations(w http.ResponseWriter, r *http.Request, tenantID string) {
	actor, ok := h.actor(w, r)
	if !ok {
		return
	}
	projectID := strings.TrimSpace(r.URL.Query().Get("project_id"))
	items, err := h.service.ListInvitations(r.Context(), ListInput{TenantID: tenantID, ProjectID: projectID, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "invitations": items})
}
func (h *Handler) change(w http.ResponseWriter, r *http.Request, tenantID, projectID, userID string) {
	actor, ok := h.authorizedMutation(w, r)
	if !ok {
		return
	}
	var body struct {
		Role   string `json:"role"`
		Status string `json:"status"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	member, err := h.service.ChangeMembership(r.Context(), MembershipChangeInput{TenantID: tenantID, ProjectID: projectID, UserID: userID, ActorID: actor, Role: body.Role, Status: body.Status, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "member": member})
}
func (h *Handler) remove(w http.ResponseWriter, r *http.Request, tenantID, projectID, userID string) {
	actor, ok := h.authorizedMutation(w, r)
	if !ok {
		return
	}
	err := h.service.RemoveMembership(r.Context(), MembershipChangeInput{TenantID: tenantID, ProjectID: projectID, UserID: userID, ActorID: actor, RequestID: requestID(r)})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (h *Handler) actor(w http.ResponseWriter, r *http.Request) (string, bool) {
	if h.service == nil || h.actorResolver == nil {
		writeError(w, http.StatusServiceUnavailable, CodeBackendUnavailable, "collaboration backend is not configured", requestID(r))
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

func (h *Handler) allowRateLimit(w http.ResponseWriter, r *http.Request, input platformratelimit.Input) bool {
	if h.rateLimiter == nil {
		writeError(w, http.StatusServiceUnavailable, "RATE_LIMIT_BACKEND_UNAVAILABLE", "rate-limit backend is unavailable", requestID(r))
		return false
	}
	decision, err := h.rateLimiter.Allow(r.Context(), input)
	if err != nil {
		code := platformratelimit.ErrorCode(err)
		if code != "RATE_LIMIT_POLICY_UNCONFIGURED" {
			code = "RATE_LIMIT_BACKEND_UNAVAILABLE"
		}
		writeError(w, http.StatusServiceUnavailable, code, "rate-limit backend is unavailable", requestID(r))
		return false
	}
	if decision.Allowed {
		return true
	}
	retryAfter := int64((decision.RetryAfter + time.Second - 1) / time.Second)
	if retryAfter < 1 {
		retryAfter = 1
	}
	w.Header().Set("Retry-After", strconv.FormatInt(retryAfter, 10))
	writeError(w, http.StatusTooManyRequests, "RATE_LIMIT_EXCEEDED", "request rate limit exceeded", requestID(r))
	return false
}
func writeDomainError(w http.ResponseWriter, err error, requestID string) {
	code := ErrorCode(err)
	status := http.StatusInternalServerError
	switch code {
	case CodeValidationFailed:
		status = http.StatusBadRequest
	case CodeUnauthenticated:
		status = http.StatusUnauthorized
	case CodeAccessDenied:
		status = http.StatusForbidden
	case CodeInvitationInvalid, CodeMembershipNotFound:
		status = http.StatusNotFound
	case CodeInvitationConflict, CodeInvitationExpired, CodeInvitationConsumed, CodeLastOwner:
		status = http.StatusConflict
	case CodeDeliveryUnavailable:
		status = http.StatusBadGateway
	}
	writeError(w, status, code, err.Error(), requestID)
}
func writeError(w http.ResponseWriter, status int, code, message, requestID string) {
	writeJSON(w, status, map[string]any{"ok": false, "error": map[string]string{"code": code, "message": message, "request_id": requestID}})
}
func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
