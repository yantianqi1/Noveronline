package assetdistillation

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"mirofish-novel/apps/api/internal/auth"
)

type ActorResolver interface {
	ResolveActor(context.Context, *http.Request) (string, error)
}

type Authorizer interface {
	Authorize(context.Context, auth.AuthorizeInput) error
}

// GraphRebuildStarter starts an incremental story_graph_build after accepted projection.
type GraphRebuildStarter interface {
	StartAfterAssetAccept(ctx context.Context, tenantID, projectID, actorUserID, requestID, acceptedAssetID string) error
}

type HandlerConfig struct {
	Store        Store
	Starter      Starter
	Actors       ActorResolver
	Authorizer   Authorizer
	GraphRebuild GraphRebuildStarter
}

type Handler struct {
	store        Store
	starter      Starter
	actors       ActorResolver
	authorizer   Authorizer
	graphRebuild GraphRebuildStarter
}

func NewHandler(config HandlerConfig) *Handler {
	return &Handler{
		store: config.Store, starter: config.Starter, actors: config.Actors,
		authorizer: config.Authorizer, graphRebuild: config.GraphRebuild,
	}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if h == nil || h.store == nil {
		writeErr(w, r, appError(CodeBackendUnconfigured, "asset distillation backend is not configured"))
		return
	}
	path := strings.TrimSpace(r.URL.Path)
	parts := splitPath(path)

	// GET/PATCH /v1/projects/{projectId}/asset-distillation-settings
	if len(parts) == 4 && parts[0] == "v1" && parts[1] == "projects" && parts[3] == "asset-distillation-settings" {
		projectID := parts[2]
		switch r.Method {
		case http.MethodGet:
			h.handleGetSettings(w, r, projectID)
		case http.MethodPatch:
			h.handlePatchSettings(w, r, projectID)
		default:
			writeErr(w, r, appError(CodeValidationFailed, "method not allowed"))
		}
		return
	}
	// POST /v1/projects/{projectId}/manuscript-asset-distillations
	if len(parts) == 4 && parts[0] == "v1" && parts[1] == "projects" && parts[3] == "manuscript-asset-distillations" && r.Method == http.MethodPost {
		h.handleStartManual(w, r, parts[2])
		return
	}
	// GET /v1/projects/{projectId}/asset-proposals
	if len(parts) == 4 && parts[0] == "v1" && parts[1] == "projects" && parts[3] == "asset-proposals" && r.Method == http.MethodGet {
		h.handleListProposals(w, r, parts[2])
		return
	}
	// GET /v1/asset-proposals/{candidateAssetId}
	// POST /v1/asset-proposals/{candidateAssetId}/decisions
	if len(parts) >= 3 && parts[0] == "v1" && parts[1] == "asset-proposals" {
		candidateID := parts[2]
		if len(parts) == 3 && r.Method == http.MethodGet {
			h.handleGetProposal(w, r, candidateID)
			return
		}
		if len(parts) == 4 && parts[3] == "decisions" && r.Method == http.MethodPost {
			h.handleDecision(w, r, candidateID)
			return
		}
	}
	writeErr(w, r, appError(CodeNotFound, "asset distillation route not found"))
}

func IsRoute(method, path string) bool {
	parts := splitPath(path)
	if len(parts) == 4 && parts[0] == "v1" && parts[1] == "projects" {
		switch parts[3] {
		case "asset-distillation-settings":
			return method == http.MethodGet || method == http.MethodPatch
		case "manuscript-asset-distillations":
			return method == http.MethodPost
		case "asset-proposals":
			return method == http.MethodGet
		}
	}
	if len(parts) == 3 && parts[0] == "v1" && parts[1] == "asset-proposals" {
		return method == http.MethodGet
	}
	if len(parts) == 4 && parts[0] == "v1" && parts[1] == "asset-proposals" && parts[3] == "decisions" {
		return method == http.MethodPost
	}
	return false
}

func (h *Handler) handleGetSettings(w http.ResponseWriter, r *http.Request, projectID string) {
	scope, err := h.authorize(r, projectID, auth.PermissionProjectRead)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	settings, err := h.store.GetSettings(r.Context(), scope)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, settings)
}

func (h *Handler) handlePatchSettings(w http.ResponseWriter, r *http.Request, projectID string) {
	scope, err := h.authorize(r, projectID, auth.PermissionAssetManage)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	var body SettingsPatch
	if err := decodeJSON(r, &body); err != nil {
		writeErr(w, r, err)
		return
	}
	settings, err := h.store.PatchSettings(r.Context(), scope, body)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, settings)
}

func (h *Handler) handleStartManual(w http.ResponseWriter, r *http.Request, projectID string) {
	scope, err := h.authorize(r, projectID, auth.PermissionCreativeWrite)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	var body struct {
		BlockIDs              []string       `json:"block_ids"`
		ExpectedVersions      map[string]int `json:"expected_versions"`
		ChapterID             string         `json:"chapter_id"`
		ExpectedBlockVersions map[string]int `json:"expected_block_versions"`
		// Reject raw text identity smuggling.
		ContentText string `json:"content_text"`
		Body        string `json:"body"`
		TenantID    string `json:"tenant_id"`
		ProjectID   string `json:"project_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeErr(w, r, err)
		return
	}
	if body.ContentText != "" || body.Body != "" || body.TenantID != "" || body.ProjectID != "" {
		writeErr(w, r, appError(CodeValidationFailed, "manual distillation does not accept body identity or manuscript text"))
		return
	}
	if h.starter == nil {
		writeErr(w, r, appError(CodeBackendUnconfigured, "asset distillation starter is not configured"))
		return
	}
	admission, err := h.starter.StartManual(r.Context(), StartManualInput{
		Scope: scope, BlockIDs: body.BlockIDs, ExpectedVersions: body.ExpectedVersions,
		ChapterID: body.ChapterID, ExpectedBlockVersions: body.ExpectedBlockVersions,
	})
	if err != nil {
		writeErr(w, r, err)
		return
	}
	writeJSON(w, http.StatusAccepted, admission)
}

func (h *Handler) handleListProposals(w http.ResponseWriter, r *http.Request, projectID string) {
	scope, err := h.authorize(r, projectID, auth.PermissionProjectRead)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	status := strings.TrimSpace(r.URL.Query().Get("status"))
	items, err := h.store.ListProposals(r.Context(), scope, status)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *Handler) handleGetProposal(w http.ResponseWriter, r *http.Request, candidateID string) {
	tenantID := strings.TrimSpace(r.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeErr(w, r, appError(CodeValidationFailed, "tenant_id is required"))
		return
	}
	projectID, err := h.store.LookupProposalProject(r.Context(), tenantID, candidateID)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	scope, err := h.authorize(r, projectID, auth.PermissionProjectRead)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	includePrivate := false
	if h.authorizer != nil {
		if authErr := h.authorizer.Authorize(r.Context(), auth.AuthorizeInput{
			UserID: scope.ActorUserID, TenantID: tenantID, ProjectID: projectID,
			Permission: auth.PermissionAssetManage, RequestID: scope.RequestID,
		}); authErr == nil {
			includePrivate = true
		}
	}
	detail, err := h.store.GetProposal(r.Context(), scope, candidateID, includePrivate)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (h *Handler) handleDecision(w http.ResponseWriter, r *http.Request, candidateID string) {
	tenantID := strings.TrimSpace(r.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeErr(w, r, appError(CodeValidationFailed, "tenant_id is required"))
		return
	}
	projectID, err := h.store.LookupProposalProject(r.Context(), tenantID, candidateID)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	scope, err := h.authorize(r, projectID, auth.PermissionAssetManage)
	if err != nil {
		writeErr(w, r, err)
		return
	}
	var body struct {
		Decision              string `json:"decision"`
		TargetLifecycle       string `json:"target_lifecycle"`
		TargetAssetID         string `json:"target_asset_id"`
		ExpectedTargetVersion int    `json:"expected_target_version"`
		Note                  string `json:"note"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeErr(w, r, err)
		return
	}
	result, err := h.store.Decide(r.Context(), DecisionInput{
		Scope: scope, CandidateAssetID: candidateID, Decision: body.Decision,
		TargetLifecycle: body.TargetLifecycle, TargetAssetID: body.TargetAssetID,
		ExpectedTargetVersion: body.ExpectedTargetVersion, Note: body.Note,
	})
	if err != nil {
		writeErr(w, r, err)
		return
	}
	// CONN-003: after accepted projection, rebuild story_graph snapshots so Graph UI sees new nodes/edges.
	if h.graphRebuild != nil && result.ReviewStatus == "accepted" && strings.TrimSpace(result.AcceptedAssetID) != "" {
		rebuildErr := h.graphRebuild.StartAfterAssetAccept(
			r.Context(), scope.TenantID, scope.ProjectID, scope.ActorUserID, scope.RequestID, result.AcceptedAssetID,
		)
		if rebuildErr != nil {
			// Keep accept success; surface rebuild failure on the decision payload for operator visibility.
			writeJSON(w, http.StatusOK, map[string]any{
				"candidate_asset_id":      result.CandidateAssetID,
				"review_status":           result.ReviewStatus,
				"accepted_asset_id":       result.AcceptedAssetID,
				"replay":                  result.Replay,
				"story_graph_rebuild_error": ErrorCode(rebuildErr),
				"story_graph_rebuild_detail": "asset accepted but story graph rebuild failed to start",
			})
			return
		}
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) authorize(r *http.Request, projectID string, permission auth.Permission) (Scope, error) {
	tenantID := strings.TrimSpace(r.Header.Get("X-Tenant-Id"))
	if tenantID == "" || strings.TrimSpace(projectID) == "" {
		return Scope{}, appError(CodeValidationFailed, "tenant and project are required")
	}
	if h.actors == nil {
		return Scope{}, appError(CodeBackendUnconfigured, "actor resolver is not configured")
	}
	actor, err := h.actors.ResolveActor(r.Context(), r)
	if err != nil || strings.TrimSpace(actor) == "" {
		return Scope{}, appError(CodeAccessDenied, "authenticated actor is required")
	}
	requestID := strings.TrimSpace(r.Header.Get("X-Request-Id"))
	if h.authorizer != nil {
		if authErr := h.authorizer.Authorize(r.Context(), auth.AuthorizeInput{
			UserID: actor, TenantID: tenantID, ProjectID: projectID,
			Permission: permission, RequestID: requestID,
		}); authErr != nil {
			return Scope{}, appError(CodeAccessDenied, "permission denied")
		}
	}
	return Scope{TenantID: tenantID, ProjectID: projectID, ActorUserID: actor, RequestID: requestID}, nil
}

func decodeJSON(r *http.Request, dest any) error {
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(dest); err != nil {
		return appError(CodeValidationFailed, "request body is invalid")
	}
	return nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeErr(w http.ResponseWriter, r *http.Request, err error) {
	code := ErrorCode(err)
	message := "asset distillation request failed"
	if ae, ok := err.(*AppError); ok && ae.Message != "" {
		message = ae.Message
	}
	writeJSON(w, HTTPStatus(err), map[string]any{
		"error": map[string]any{"code": code, "message": message, "request_id": strings.TrimSpace(r.Header.Get("X-Request-Id"))},
	})
}

func splitPath(path string) []string {
	path = strings.Trim(path, "/")
	if path == "" {
		return nil
	}
	return strings.Split(path, "/")
}
