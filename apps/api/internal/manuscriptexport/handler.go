package manuscriptexport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/manuscriptworkspace"
	"mirofish-novel/apps/api/internal/workflows"
)

type ActorResolver interface {
	ResolveActor(context.Context, *http.Request) (string, error)
}

type Config struct {
	Exporter      workflows.ManuscriptArtifactExporter
	States        manuscriptworkspace.ExportStateStore
	Artifacts     ArtifactStore
	Authorizer    auth.Authorizer
	ActorResolver ActorResolver
}

type Handler struct {
	exporter      workflows.ManuscriptArtifactExporter
	states        manuscriptworkspace.ExportStateStore
	artifacts     ArtifactStore
	authorizer    auth.Authorizer
	actorResolver ActorResolver
}

func NewHandler(config Config) *Handler {
	return &Handler{
		exporter:      config.Exporter,
		states:        config.States,
		artifacts:     config.Artifacts,
		authorizer:    config.Authorizer,
		actorResolver: config.ActorResolver,
	}
}

func (h *Handler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet {
		writeError(response, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method is not allowed")
		return
	}
	projectID, exportID := exportTargetFromPath(request.URL.Path)
	if projectID == "" {
		writeError(response, http.StatusNotFound, "NOT_FOUND", "manuscript export route not found")
		return
	}
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" || h.actorResolver == nil {
		writeError(response, http.StatusUnauthorized, auth.CodeUnauthenticated, "authentication is required")
		return
	}
	actorID, err := h.actorResolver.ResolveActor(request.Context(), request)
	if err != nil || strings.TrimSpace(actorID) == "" {
		writeError(response, http.StatusUnauthorized, auth.CodeUnauthenticated, "authentication is required")
		return
	}
	if h.authorizer == nil {
		writeError(response, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, "authorization backend is not configured")
		return
	}
	requestID := strings.TrimSpace(request.Header.Get("X-Request-Id"))
	if err := h.authorizer.Authorize(request.Context(), auth.AuthorizeInput{
		UserID:     strings.TrimSpace(actorID),
		TenantID:   tenantID,
		ProjectID:  projectID,
		Permission: auth.PermissionProjectRead,
		RequestID:  requestID,
	}); err != nil {
		writeError(response, http.StatusForbidden, auth.CodeAccessDenied, "project read access is required")
		return
	}
	if exportID != "" {
		h.serveStoredArtifact(response, request, tenantID, actorID, projectID, exportID, requestID)
		return
	}
	h.serveLegacyArtifact(response, request, tenantID, projectID)
}

func (h *Handler) serveLegacyArtifact(response http.ResponseWriter, request *http.Request, tenantID, projectID string) {
	if h.exporter == nil {
		writeError(response, http.StatusServiceUnavailable, "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", "manuscript export backend is not configured")
		return
	}
	artifact, err := h.exporter.ExportManuscriptArtifact(request.Context(), workflows.ExportManuscriptArtifactInput{TenantID: tenantID, ProjectID: projectID, Format: request.URL.Query().Get("format")})
	if err != nil {
		writeWorkflowError(response, err)
		return
	}
	writeArtifact(response, artifact.ContentType, artifact.FileName, artifact.Content, artifact.SHA256)
}

func (h *Handler) serveStoredArtifact(response http.ResponseWriter, request *http.Request, tenantID, actorID, projectID, exportID, requestID string) {
	if h.states == nil || h.artifacts == nil {
		writeError(response, http.StatusServiceUnavailable, "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", "manuscript artifact backend is not configured")
		return
	}
	record, err := h.states.GetPrivateExport(request.Context(), manuscriptworkspace.Scope{TenantID: tenantID, ProjectID: projectID, ActorUserID: actorID, RequestID: requestID}, exportID)
	if err != nil {
		writeStateError(response, err)
		return
	}
	if record.Status != "completed" || record.ArtifactObjectRef == "" || record.ArtifactSHA256 == "" || record.ArtifactSizeBytes <= 0 {
		writeError(response, http.StatusConflict, "MANUSCRIPT_ARTIFACT_NOT_READY", "manuscript artifact is not ready")
		return
	}
	content, err := h.artifacts.Read(request.Context(), record.ArtifactObjectRef)
	if err != nil {
		writeError(response, http.StatusInternalServerError, "MANUSCRIPT_ARTIFACT_READ_FAILED", "manuscript artifact could not be read")
		return
	}
	digest := sha256.Sum256(content)
	actualSHA := hex.EncodeToString(digest[:])
	if int64(len(content)) != record.ArtifactSizeBytes || actualSHA != record.ArtifactSHA256 {
		writeError(response, http.StatusInternalServerError, "MANUSCRIPT_ARTIFACT_INTEGRITY_FAILED", "manuscript artifact integrity check failed")
		return
	}
	writeArtifact(response, "text/plain; charset=utf-8", safeDownloadName(projectID, record.Format), content, actualSHA)
}

func writeArtifact(response http.ResponseWriter, contentType, fileName string, content []byte, digest string) {
	response.Header().Set("Content-Type", contentType)
	response.Header().Set("Content-Disposition", `attachment; filename="`+fileName+`"`)
	response.Header().Set("Content-Length", strconv.FormatInt(int64(len(content)), 10))
	response.Header().Set("X-Content-SHA256", digest)
	response.Header().Set("Cache-Control", "private, no-store")
	response.WriteHeader(http.StatusOK)
	_, _ = response.Write(content)
}

func exportTargetFromPath(path string) (string, string) {
	const prefix = "/v1/projects/"
	if !strings.HasPrefix(path, prefix) {
		return "", ""
	}
	parts := strings.Split(strings.Trim(strings.TrimPrefix(path, prefix), "/"), "/")
	if len(parts) == 3 && parts[1] == "manuscript" && parts[2] == "export" {
		return strings.TrimSpace(parts[0]), ""
	}
	if len(parts) == 5 && parts[1] == "manuscript" && parts[2] == "exports" && parts[4] == "download" {
		return strings.TrimSpace(parts[0]), strings.TrimSpace(parts[3])
	}
	return "", ""
}

func safeDownloadName(projectID, format string) string {
	name := strings.TrimSuffix(workflowsSafeFileName(projectID), ".txt")
	return name + "." + strings.ToLower(strings.TrimSpace(format))
}

func workflowsSafeFileName(projectID string) string {
	var builder strings.Builder
	for _, character := range strings.TrimSpace(projectID) {
		if character >= 'a' && character <= 'z' || character >= 'A' && character <= 'Z' || character >= '0' && character <= '9' || character == '-' || character == '_' {
			builder.WriteRune(character)
		} else {
			builder.WriteRune('-')
		}
	}
	base := strings.Trim(builder.String(), "-")
	if base == "" {
		base = "project"
	}
	return base + "-manuscript.txt"
}

func writeWorkflowError(response http.ResponseWriter, err error) {
	code := workflows.ErrorCode(err)
	switch code {
	case "VALIDATION_FAILED", "MANUSCRIPT_EXPORT_FORMAT_UNSUPPORTED":
		writeError(response, http.StatusBadRequest, code, "invalid manuscript export request")
	case "MANUSCRIPT_EMPTY":
		writeError(response, http.StatusConflict, code, "manuscript has no adopted content to export")
	case "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED":
		writeError(response, http.StatusServiceUnavailable, code, "manuscript export backend is not configured")
	default:
		writeError(response, http.StatusInternalServerError, code, "manuscript export failed")
	}
}

func writeStateError(response http.ResponseWriter, err error) {
	switch manuscriptworkspace.ErrorCode(err) {
	case "NOT_FOUND":
		writeError(response, http.StatusNotFound, "NOT_FOUND", "manuscript export was not found")
	case "VALIDATION_FAILED":
		writeError(response, http.StatusBadRequest, "VALIDATION_FAILED", "invalid manuscript export request")
	default:
		writeError(response, http.StatusInternalServerError, "MANUSCRIPT_EXPORT_STATE_FAILED", "manuscript export state could not be read")
	}
}

func writeError(response http.ResponseWriter, status int, code string, message string) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(map[string]any{
		"error": map[string]any{
			"code":    code,
			"message": message,
			"details": map[string]any{},
		},
	})
}
