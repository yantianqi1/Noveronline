package httpapi

import (
	"encoding/json"
	"net/http"
	"strings"

	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/worldline"
)

type startWorldlineGoalStartRequest struct {
	Goal         string         `json:"goal"`
	AnchorPathID string         `json:"anchor_path_id"`
	Options      map[string]any `json:"options"`
}

func (s *Server) handleStartWorldlineGoalStart(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "worldline-goal-starts")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project worldline goal-start route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return
	}
	var payload startWorldlineGoalStartRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline goal-start payload", nil)
		return
	}
	actorUserID := s.actorUserID(request)
	resolution, err := llm.EnsureWorldlineCastModuleBindings(
		request.Context(),
		s.llmResolver,
		s.llmBindingStore,
		tenantID,
		projectID,
		actorUserID,
	)
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	options := cloneOptions(sanitizeAssetPayload(payload.Options))
	if options == nil {
		options = map[string]any{}
	}
	options["module_key"] = worldline.WorldlineCastPlannerModuleKey
	options["llm_resolution"] = workflowLLMResolution(resolution)
	options["required_module_keys"] = append([]string(nil), llm.WorldlineCastRequiredModules...)
	record, err := s.worldlineGoalStartStarter.StartGoalStart(request.Context(), worldline.StartGoalStartInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ActorUserID:  actorUserID,
		RequestID:    requestID(request),
		Goal:         strings.TrimSpace(payload.Goal),
		AnchorPathID: strings.TrimSpace(payload.AnchorPathID),
		Options:      options,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineGoalStartPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, record)
}

func (s *Server) handleListWorldlineGoalStarts(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "worldline-goal-starts")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project worldline goal-start route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.worldlineGoalStartReader.ListGoalStarts(request.Context(), worldline.ListGoalStartsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[worldline.GoalStartRecord]{Items: items})
}

func (s *Server) handleGetWorldlineGoalStart(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-goal-starts/")
	runID = strings.Trim(runID, "/")
	if runID == "" || strings.Contains(runID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline goal-start route not found", nil)
		return
	}
	record, err := s.worldlineGoalStartReader.GetGoalStart(request.Context(), worldline.GetGoalStartInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, err.Error(), nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, record.ProjectID) {
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func worldlineGoalStartPublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "invalid worldline goal-start request"
	case "NOT_FOUND":
		return "worldline goal-start resource was not found"
	case "IDEMPOTENCY_CONFLICT":
		return "request_id was already used for a different worldline goal-start"
	case "WORLDLINE_GOAL_START_ACTIVE":
		return "this project already has an active worldline"
	case "WORLDLINE_GOAL_START_BACKEND_UNCONFIGURED", "WORKFLOW_BACKEND_UNCONFIGURED":
		return "worldline goal-start backend is not configured"
	case "WORKFLOW_ADMISSION_FAILED":
		return "failed to admit worldline goal-start"
	case "WORKFLOW_FAILED":
		return "failed to start worldline goal-start workflow"
	default:
		return "worldline goal-start request failed"
	}
}
