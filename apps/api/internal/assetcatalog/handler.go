package assetcatalog

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
)

type Handler struct{ store Store }

func NewHandler(store Store) http.Handler { return &Handler{store: store} }

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "private, no-store")
	scope, ok := RequestScopeFromContext(r.Context())
	if !ok || strings.TrimSpace(scope.ActorID) == "" || strings.TrimSpace(scope.TenantID) == "" {
		writeError(w, http.StatusUnauthorized, "UNAUTHENTICATED", "trusted actor context is required")
		return
	}
	projectID, parts, ok := parsePath(r.URL.Path)
	if !ok {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "asset catalog route not found")
		return
	}
	if scope.ProjectID == "" {
		scope.ProjectID = projectID
	}
	if scope.ProjectID != projectID {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "resource not found")
		return
	}
	if h.store == nil {
		writeError(w, http.StatusServiceUnavailable, "ASSET_CATALOG_BACKEND_UNCONFIGURED", "asset catalog backend is not configured")
		return
	}
	h.route(w, r, scope, parts)
}

func parsePath(path string) (string, []string, bool) {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) < 5 || parts[0] != "v1" || parts[1] != "projects" || parts[3] != "asset-catalog" || parts[2] == "" {
		return "", nil, false
	}
	return parts[2], parts[4:], true
}

func (h *Handler) route(w http.ResponseWriter, r *http.Request, scope RequestScope, p []string) {
	if len(p) >= 1 && p[0] == "assets" {
		h.assets(w, r, scope, p[1:])
		return
	}
	if len(p) >= 1 && p[0] == "collections" {
		h.collections(w, r, scope, p[1:])
		return
	}
	writeError(w, http.StatusNotFound, "NOT_FOUND", "asset catalog route not found")
}

func (h *Handler) assets(w http.ResponseWriter, r *http.Request, scope RequestScope, p []string) {
	if len(p) < 1 || p[0] == "" {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "asset not found")
		return
	}
	assetID := p[0]
	if len(p) == 1 && r.Method == http.MethodGet {
		a, err := h.store.GetAsset(r.Context(), scope, assetID, scope.Can(PermissionReadPrivate))
		a.Capabilities = Capabilities{ReadPrivate: scope.Can(PermissionReadPrivate), Mutate: scope.Can(PermissionMutate), ManageCollections: scope.Can(PermissionCollections)}
		writeResult(w, a, err, http.StatusOK)
		return
	}
	if len(p) == 1 && r.Method == http.MethodPatch {
		if !authorize(w, scope, PermissionMutate) {
			return
		}
		var input AssetPatch
		if !decodeJSON(w, r, &input) {
			return
		}
		a, err := h.store.UpdateAsset(r.Context(), scope, assetID, input)
		writeResult(w, a, err, http.StatusOK)
		return
	}
	if len(p) == 2 && p[1] == "versions" && r.Method == http.MethodGet {
		private := r.URL.Query().Get("include_private") == "true"
		if private && !scope.Can(PermissionReadPrivate) {
			writeError(w, http.StatusForbidden, "ASSET_PRIVATE_ACCESS_DENIED", "private version snapshots require permission")
			return
		}
		versions, err := h.store.ListVersions(r.Context(), scope, assetID, private)
		writeResult(w, map[string]any{"versions": versions}, err, http.StatusOK)
		return
	}
	if len(p) == 2 && p[1] == "restore" && r.Method == http.MethodPost {
		if !authorize(w, scope, PermissionMutate) {
			return
		}
		var input RestoreInput
		if !decodeJSON(w, r, &input) {
			return
		}
		a, err := h.store.RestoreAsset(r.Context(), scope, assetID, input)
		writeResult(w, a, err, http.StatusOK)
		return
	}
	writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method is not allowed")
}

func (h *Handler) collections(w http.ResponseWriter, r *http.Request, scope RequestScope, p []string) {
	if len(p) == 0 && r.Method == http.MethodGet {
		items, err := h.store.ListCollections(r.Context(), scope)
		writeResult(w, map[string]any{"collections": items}, err, http.StatusOK)
		return
	}
	if len(p) == 0 && r.Method == http.MethodPost {
		if !authorize(w, scope, PermissionCollections) {
			return
		}
		var input CollectionInput
		if !decodeJSON(w, r, &input) {
			return
		}
		c, err := h.store.CreateCollection(r.Context(), scope, input)
		writeResult(w, c, err, http.StatusCreated)
		return
	}
	if len(p) < 1 || p[0] == "" {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "collection not found")
		return
	}
	id := p[0]
	if len(p) == 1 && r.Method == http.MethodPatch {
		if !authorize(w, scope, PermissionCollections) {
			return
		}
		var input CollectionInput
		if !decodeJSON(w, r, &input) {
			return
		}
		c, err := h.store.UpdateCollection(r.Context(), scope, id, input)
		writeResult(w, c, err, http.StatusOK)
		return
	}
	if len(p) == 1 && r.Method == http.MethodDelete {
		if !authorize(w, scope, PermissionCollections) {
			return
		}
		err := h.store.DeleteCollection(r.Context(), scope, id)
		if err != nil {
			writeResult(w, nil, err, 0)
			return
		}
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if len(p) == 2 && p[1] == "order" && r.Method == http.MethodPut {
		if !authorize(w, scope, PermissionCollections) {
			return
		}
		var input ReorderInput
		if !decodeJSON(w, r, &input) {
			return
		}
		c, err := h.store.ReorderMemberships(r.Context(), scope, id, input)
		writeResult(w, c, err, http.StatusOK)
		return
	}
	if len(p) == 3 && p[1] == "items" {
		assetID := p[2]
		if !authorize(w, scope, PermissionCollections) {
			return
		}
		if r.Method == http.MethodPut {
			var input MembershipInput
			if !decodeJSON(w, r, &input) {
				return
			}
			c, err := h.store.AddMembership(r.Context(), scope, id, assetID, input)
			writeResult(w, c, err, http.StatusOK)
			return
		}
		if r.Method == http.MethodDelete {
			if r.ContentLength > 0 {
				writeError(w, http.StatusBadRequest, "INVALID_JSON", "DELETE membership does not accept a body")
				return
			}
			c, err := h.store.RemoveMembership(r.Context(), scope, id, assetID)
			writeResult(w, c, err, http.StatusOK)
			return
		}
	}
	writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method is not allowed")
}

func authorize(w http.ResponseWriter, scope RequestScope, p Permission) bool {
	if scope.Can(p) {
		return true
	}
	writeError(w, http.StatusForbidden, "ASSET_CATALOG_ACCESS_DENIED", "operation requires "+string(p))
	return false
}

func decodeJSON(w http.ResponseWriter, r *http.Request, target any) bool {
	if !strings.HasPrefix(strings.ToLower(r.Header.Get("Content-Type")), "application/json") {
		writeError(w, http.StatusUnsupportedMediaType, "CONTENT_TYPE_REQUIRED", "application/json is required")
		return false
	}
	decoder := json.NewDecoder(io.LimitReader(r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "request body must be one strict JSON object")
		return false
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		writeError(w, http.StatusBadRequest, "INVALID_JSON", "request body must contain one JSON object")
		return false
	}
	return true
}

func writeResult(w http.ResponseWriter, value any, err error, status int) {
	if err != nil {
		switch {
		case errors.Is(err, ErrNotFound):
			writeError(w, http.StatusNotFound, "NOT_FOUND", "resource not found")
		case errors.Is(err, ErrConflict):
			writeError(w, http.StatusConflict, "ASSET_VERSION_CONFLICT", "expected_version does not match current version")
		case errors.Is(err, ErrInvalid):
			writeError(w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", err.Error())
		default:
			writeError(w, http.StatusInternalServerError, "ASSET_CATALOG_FAILED", "asset catalog operation failed")
		}
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{"error": map[string]any{"code": code, "message": message, "details": map[string]any{}}})
}
