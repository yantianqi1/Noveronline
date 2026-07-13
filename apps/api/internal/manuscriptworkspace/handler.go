package manuscriptworkspace

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"mirofish-novel/apps/api/internal/writerplanning"
)

type HandlerConfig struct {
	Store           Store
	Commands        *CommandService
	CommandReader   CommandRepository
	Exports         ExportStateStore
	ExportGenerator ExportArtifactGenerator
	Dedup           DedupStore
	Planning        writerplanning.Starter
	Resolver        TrustedContextResolver
	Authorizer      PermissionAuthorizer
}

type Handler struct {
	config HandlerConfig
}

func NewHandler(config HandlerConfig) *Handler { return &Handler{config: config} }

func (h *Handler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	projectID, parts, ok := parseWorkspacePath(request.URL.Path)
	if !ok {
		writeWorkspaceError(response, http.StatusNotFound, "NOT_FOUND", "manuscript workspace route not found")
		return
	}
	if h.config.Resolver == nil {
		writeWorkspaceError(response, http.StatusUnauthorized, "UNAUTHENTICATED", "authentication is required")
		return
	}
	scope, err := h.config.Resolver.ResolveManuscriptContext(request.Context(), request, projectID)
	if err != nil || strings.TrimSpace(scope.TenantID) == "" || strings.TrimSpace(scope.ActorUserID) == "" {
		writeWorkspaceError(response, http.StatusUnauthorized, "UNAUTHENTICATED", "authentication is required")
		return
	}
	scope = normalizeScope(scope)
	scope.ProjectID = projectID
	if scope.RequestID == "" {
		scope.RequestID = strings.TrimSpace(request.Header.Get("X-Request-Id"))
	}
	permission := PermissionRead
	if request.Method != http.MethodGet {
		permission = PermissionWrite
	}
	if h.config.Authorizer == nil {
		writeWorkspaceError(response, http.StatusServiceUnavailable, "AUTHORIZATION_BACKEND_UNCONFIGURED", "authorization backend is not configured")
		return
	}
	if err := h.config.Authorizer.AuthorizeManuscript(request.Context(), scope, permission); err != nil {
		writeWorkspaceError(response, http.StatusForbidden, "ACCESS_DENIED", "manuscript workspace access is required")
		return
	}

	if h.routeBlocks(response, request, scope, parts) ||
		h.routeCommands(response, request, scope, parts) ||
		h.routeExports(response, request, scope, parts) ||
		h.routeDedupExtraction(response, request, scope, parts) ||
		h.routeDedup(response, request, scope, parts) {
		return
	}
	writeWorkspaceError(response, http.StatusNotFound, "NOT_FOUND", "manuscript workspace route not found")
}

func (h *Handler) routeDedupExtraction(response http.ResponseWriter, request *http.Request, scope Scope, parts []string) bool {
	if len(parts) != 1 || parts[0] != "dedup-extractions" {
		return false
	}
	if request.Method != http.MethodPost {
		writeMethodNotAllowed(response)
		return true
	}
	if h.config.Planning == nil {
		writeWorkspaceError(response, http.StatusServiceUnavailable, "WRITER_PLANNING_BACKEND_UNCONFIGURED", "writer planning backend is not configured")
		return true
	}
	var body struct {
		BlockIDs  []string `json:"block_ids"`
		ChapterID string   `json:"chapter_id"`
	}
	if !decodeBody(response, request, &body) {
		return true
	}
	result, err := h.config.Planning.Start(request.Context(), writerplanning.StartInput{
		TenantID: scope.TenantID, ProjectID: scope.ProjectID, ActorUserID: scope.ActorUserID,
		RequestID: scope.RequestID, Kind: writerplanning.KindDedup,
		BlockIDs: body.BlockIDs, ChapterID: body.ChapterID,
	})
	if err != nil {
		writePlanningError(response, err)
		return true
	}
	writeResult(response, result, nil, http.StatusAccepted)
	return true
}

func writePlanningError(response http.ResponseWriter, err error) {
	code := writerplanning.ErrorCode(err)
	status, message := http.StatusInternalServerError, "writer planning request failed"
	switch code {
	case "VALIDATION_FAILED":
		status, message = http.StatusBadRequest, "invalid writer planning request"
	case "WRITER_DEDUP_SOURCE_NOT_FOUND":
		status, message = http.StatusNotFound, "selected manuscript source was not found"
	case "IDEMPOTENCY_CONFLICT", "BOOK_PLAN_CONFLICT":
		status, message = http.StatusConflict, "writer planning state changed"
	case "WRITER_PLANNING_BACKEND_UNCONFIGURED":
		status, message = http.StatusServiceUnavailable, "writer planning backend is not configured"
	case "WRITER_PLANNING_START_FAILED":
		status, message = http.StatusBadGateway, "writer planning workflow failed to start"
	}
	writeWorkspaceError(response, status, code, message)
}

func (h *Handler) routeBlocks(response http.ResponseWriter, request *http.Request, scope Scope, parts []string) bool {
	if len(parts) > 0 && parts[0] == "blocks" && h.config.Store == nil {
		writeDomainError(response, &AppError{Code: "MANUSCRIPT_BACKEND_UNCONFIGURED", Message: "manuscript workspace backend is not configured"})
		return true
	}
	if len(parts) == 1 && parts[0] == "blocks" {
		switch request.Method {
		case http.MethodGet:
			blocks, err := h.config.Store.ListBlocks(request.Context(), scope, request.URL.Query().Get("include_deleted") == "true")
			writeResult(response, map[string]any{"blocks": blocks}, err, http.StatusOK)
			return true
		default:
			writeMethodNotAllowed(response)
			return true
		}
	}
	if len(parts) == 2 && parts[0] == "blocks" && parts[1] == "reorder" {
		if request.Method != http.MethodPost {
			writeMethodNotAllowed(response)
			return true
		}
		var body struct {
			Items []ReorderItem `json:"items"`
		}
		if !decodeBody(response, request, &body) {
			return true
		}
		blocks, err := h.config.Store.ReorderBlocks(request.Context(), ReorderBlocksInput{Scope: scope, Items: body.Items})
		writeResult(response, map[string]any{"blocks": blocks}, err, http.StatusOK)
		return true
	}
	if len(parts) == 2 && parts[0] == "blocks" {
		blockID := parts[1]
		switch request.Method {
		case http.MethodGet:
			block, err := h.config.Store.GetPrivateBlock(request.Context(), scope, blockID)
			writeResult(response, block, err, http.StatusOK)
		case http.MethodPatch:
			var body updateBlockBody
			if !decodeBody(response, request, &body) {
				return true
			}
			block, err := h.config.Store.UpdateBlock(request.Context(), UpdateBlockInput{
				Scope: scope, BlockID: blockID, ExpectedVersion: body.ExpectedVersion,
				ContentText: body.ContentText, Status: body.Status, Tags: body.Tags,
				ChapterID: body.ChapterID, SceneID: body.SceneID,
			})
			writeResult(response, block, err, http.StatusOK)
		case http.MethodDelete:
			var body struct {
				ExpectedVersion int `json:"expected_version"`
			}
			if !decodeBody(response, request, &body) {
				return true
			}
			block, err := h.config.Store.DeleteBlock(request.Context(), DeleteBlockInput{
				Scope: scope, BlockID: blockID, ExpectedVersion: body.ExpectedVersion,
			})
			writeResult(response, block, err, http.StatusOK)
		default:
			writeMethodNotAllowed(response)
		}
		return true
	}
	if len(parts) == 3 && parts[0] == "blocks" && parts[2] == "move" {
		if request.Method != http.MethodPost {
			writeMethodNotAllowed(response)
			return true
		}
		var body struct {
			ExpectedVersion int           `json:"expected_version"`
			ChapterID       string        `json:"chapter_id"`
			SceneID         string        `json:"scene_id"`
			Items           []ReorderItem `json:"items"`
		}
		if !decodeBody(response, request, &body) {
			return true
		}
		blocks, err := h.config.Store.MoveBlock(request.Context(), MoveBlockInput{
			Scope: scope, BlockID: parts[1], ExpectedVersion: body.ExpectedVersion,
			ChapterID: body.ChapterID, SceneID: body.SceneID, Items: body.Items,
		})
		writeResult(response, map[string]any{"blocks": blocks}, err, http.StatusOK)
		return true
	}
	if len(parts) == 3 && parts[0] == "blocks" && parts[2] == "tags" {
		if request.Method != http.MethodPut {
			writeMethodNotAllowed(response)
			return true
		}
		var body struct {
			ExpectedVersion int      `json:"expected_version"`
			Tags            []string `json:"tags"`
		}
		if !decodeBody(response, request, &body) {
			return true
		}
		block, err := h.config.Store.TagBlock(request.Context(), TagBlockInput{
			Scope: scope, BlockID: parts[1], ExpectedVersion: body.ExpectedVersion, Tags: body.Tags,
		})
		writeResult(response, block, err, http.StatusOK)
		return true
	}
	if len(parts) == 3 && parts[0] == "blocks" && parts[2] == "versions" {
		if request.Method != http.MethodGet {
			writeMethodNotAllowed(response)
			return true
		}
		versions, err := h.config.Store.ListVersions(request.Context(), scope, parts[1])
		writeResult(response, map[string]any{"versions": versions}, err, http.StatusOK)
		return true
	}
	if len(parts) == 4 && parts[0] == "blocks" && parts[2] == "versions" {
		if request.Method != http.MethodGet {
			writeMethodNotAllowed(response)
			return true
		}
		version, err := h.config.Store.GetPrivateVersion(request.Context(), scope, parts[1], parts[3])
		writeResult(response, version, err, http.StatusOK)
		return true
	}
	if len(parts) == 5 && parts[0] == "blocks" && parts[2] == "versions" && parts[4] == "restore" {
		if request.Method != http.MethodPost {
			writeMethodNotAllowed(response)
			return true
		}
		var body struct {
			ExpectedVersion int `json:"expected_version"`
		}
		if !decodeBody(response, request, &body) {
			return true
		}
		block, err := h.config.Store.RestoreVersion(request.Context(), RestoreBlockInput{
			Scope: scope, BlockID: parts[1], VersionID: parts[3], ExpectedVersion: body.ExpectedVersion,
		})
		writeResult(response, block, err, http.StatusOK)
		return true
	}
	return false
}

type updateBlockBody struct {
	ExpectedVersion int       `json:"expected_version"`
	ContentText     *string   `json:"content_text"`
	Status          *string   `json:"status"`
	Tags            *[]string `json:"tags"`
	ChapterID       *string   `json:"chapter_id"`
	SceneID         *string   `json:"scene_id"`
}

func (h *Handler) routeCommands(response http.ResponseWriter, request *http.Request, scope Scope, parts []string) bool {
	if len(parts) == 1 && parts[0] == "commands" {
		if request.Method != http.MethodPost {
			writeMethodNotAllowed(response)
			return true
		}
		if h.config.Commands == nil {
			writeDomainError(response, commandBackendUnconfigured())
			return true
		}
		var body struct {
			CommandType     string         `json:"command_type"`
			TargetChapterID string         `json:"target_chapter_id"`
			TargetSceneID   string         `json:"target_scene_id"`
			TargetBlockID   string         `json:"target_block_id"`
			Options         map[string]any `json:"options"`
		}
		if !decodeBody(response, request, &body) {
			return true
		}
		result, err := h.config.Commands.Admit(request.Context(), CommandInput{
			Scope: scope, CommandType: body.CommandType, TargetChapterID: body.TargetChapterID,
			TargetSceneID: body.TargetSceneID, TargetBlockID: body.TargetBlockID, Options: body.Options,
		})
		writeResult(response, result, err, http.StatusAccepted)
		return true
	}
	if len(parts) == 2 && parts[0] == "commands" {
		if request.Method != http.MethodGet {
			writeMethodNotAllowed(response)
			return true
		}
		if h.config.CommandReader == nil {
			writeDomainError(response, commandBackendUnconfigured())
			return true
		}
		run, err := h.config.CommandReader.GetCommand(request.Context(), scope, parts[1])
		writeResult(response, run, err, http.StatusOK)
		return true
	}
	return false
}

func (h *Handler) routeExports(response http.ResponseWriter, request *http.Request, scope Scope, parts []string) bool {
	if len(parts) != 1 || parts[0] != "exports" {
		return false
	}
	if h.config.Exports == nil {
		writeDomainError(response, &AppError{Code: "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", Message: "manuscript export state backend is not configured"})
		return true
	}
	switch request.Method {
	case http.MethodGet:
		records, err := h.config.Exports.ListExports(request.Context(), scope)
		writeResult(response, map[string]any{"exports": records}, err, http.StatusOK)
	case http.MethodPost:
		var body struct {
			Format string `json:"format"`
		}
		if !decodeBody(response, request, &body) {
			return true
		}
		if h.config.ExportGenerator == nil {
			writeDomainError(response, &AppError{Code: "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", Message: "manuscript artifact generator is not configured"})
			return true
		}
		record, replay, err := h.config.ExportGenerator.GenerateExport(request.Context(), CreateExportInput{Scope: scope, Format: body.Format})
		writeResult(response, map[string]any{"export": record, "replay": replay}, err, http.StatusAccepted)
	default:
		writeMethodNotAllowed(response)
	}
	return true
}

func (h *Handler) routeDedup(response http.ResponseWriter, request *http.Request, scope Scope, parts []string) bool {
	if len(parts) > 0 && parts[0] == "dedup-patterns" && h.config.Dedup == nil {
		writeDomainError(response, &AppError{Code: "DEDUP_BACKEND_UNCONFIGURED", Message: "dedup candidate backend is not configured"})
		return true
	}
	if len(parts) == 1 && parts[0] == "dedup-patterns" {
		if request.Method != http.MethodGet {
			writeMethodNotAllowed(response)
			return true
		}
		patterns, err := h.config.Dedup.ListDedupPatterns(request.Context(), scope, request.URL.Query().Get("lifecycle"))
		writeResult(response, map[string]any{"patterns": patterns}, err, http.StatusOK)
		return true
	}
	if len(parts) == 3 && parts[0] == "dedup-patterns" && (parts[2] == "accept" || parts[2] == "reject") {
		if request.Method != http.MethodPost {
			writeMethodNotAllowed(response)
			return true
		}
		decision := "accepted"
		if parts[2] == "reject" {
			decision = "rejected"
		}
		pattern, err := h.config.Dedup.ReviewDedupPattern(request.Context(), ReviewDedupPatternInput{
			Scope: scope, PatternID: parts[1], Decision: decision,
		})
		writeResult(response, pattern, err, http.StatusOK)
		return true
	}
	return false
}

func parseWorkspacePath(path string) (string, []string, bool) {
	const prefix = "/v1/projects/"
	if !strings.HasPrefix(path, prefix) {
		return "", nil, false
	}
	parts := strings.Split(strings.Trim(strings.TrimPrefix(path, prefix), "/"), "/")
	if len(parts) < 3 || strings.TrimSpace(parts[0]) == "" || parts[1] != "manuscript-workspace" {
		return "", nil, false
	}
	for _, part := range parts {
		if strings.TrimSpace(part) == "" {
			return "", nil, false
		}
	}
	return parts[0], parts[2:], true
}

func decodeBody(response http.ResponseWriter, request *http.Request, target any) bool {
	decoder := json.NewDecoder(io.LimitReader(request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeWorkspaceError(response, http.StatusBadRequest, "VALIDATION_FAILED", "request body is invalid")
		return false
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		writeWorkspaceError(response, http.StatusBadRequest, "VALIDATION_FAILED", "request body is invalid")
		return false
	}
	return true
}

func writeResult(response http.ResponseWriter, value any, err error, status int) {
	if err != nil {
		writeDomainError(response, err)
		return
	}
	response.Header().Set("Content-Type", "application/json")
	response.Header().Set("Cache-Control", "private, no-store")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(value)
}

func writeDomainError(response http.ResponseWriter, err error) {
	code := ErrorCode(err)
	status := http.StatusInternalServerError
	message := "manuscript workspace request failed"
	switch code {
	case "VALIDATION_FAILED":
		status, message = http.StatusBadRequest, "invalid manuscript workspace request"
	case "NOT_FOUND":
		status, message = http.StatusNotFound, "manuscript workspace resource not found"
	case "OPTIMISTIC_CONFLICT", "MANUSCRIPT_BLOCK_DELETED", "MANUSCRIPT_REORDER_SET_MISMATCH", "COMMAND_STATE_CONFLICT", "EXPORT_STATE_CONFLICT", "DEDUP_PATTERN_STATE_CONFLICT", "IDEMPOTENCY_CONFLICT":
		status, message = http.StatusConflict, "manuscript workspace state changed"
	case "COMMAND_BACKEND_UNCONFIGURED", "MANUSCRIPT_BACKEND_UNCONFIGURED", "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", "DEDUP_BACKEND_UNCONFIGURED":
		status, message = http.StatusServiceUnavailable, "manuscript workspace backend is not configured"
	case "COMMAND_START_FAILED":
		status, message = http.StatusBadGateway, "writer command start failed"
	case "MANUSCRIPT_ARTIFACT_GENERATION_FAILED":
		status, message = http.StatusBadGateway, "manuscript artifact generation failed"
	}
	writeWorkspaceError(response, status, code, message)
}

func writeMethodNotAllowed(response http.ResponseWriter) {
	writeWorkspaceError(response, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method is not allowed")
}

func writeWorkspaceError(response http.ResponseWriter, status int, code, message string) {
	response.Header().Set("Content-Type", "application/json")
	response.Header().Set("Cache-Control", "private, no-store")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(map[string]any{
		"error": map[string]any{"code": code, "message": message, "details": map[string]any{}},
	})
}
