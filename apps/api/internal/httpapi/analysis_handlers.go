package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/workflows"
)

type startAnalysisRunRequest struct {
	UploadID    string         `json:"upload_id"`
	Mode        string         `json:"mode"`
	Instruction string         `json:"instruction"`
	Hints       map[string]any `json:"hints"`
	Options     map[string]any `json:"options"`
}

type startAnalysisRunResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
	Mode         string `json:"mode,omitempty"`
}

type analysisRunResponse struct {
	RunID        string `json:"run_id"`
	TraceID      string `json:"trace_id,omitempty"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
	Mode         string `json:"mode,omitempty"`
	Instruction  string `json:"instruction,omitempty"`
	UploadID     string `json:"upload_id,omitempty"`
	SourceFileID string `json:"source_file_id,omitempty"`
	Progress     int    `json:"progress,omitempty"`
	Message      string `json:"message,omitempty"`
	ErrorCode    string `json:"error_code,omitempty"`
	ErrorMessage string `json:"error_message,omitempty"`
	CreatedAt    string `json:"created_at,omitempty"`
	UpdatedAt    string `json:"updated_at,omitempty"`
}

type analysisEventResponse struct {
	EventID   string         `json:"event_id"`
	RunID     string         `json:"run_id"`
	ProjectID string         `json:"project_id"`
	Sequence  int            `json:"sequence"`
	EventType string         `json:"event_type"`
	Payload   map[string]any `json:"payload"`
	CreatedAt string         `json:"created_at"`
}

type analysisWorkspaceFileResponse struct {
	FileID        string         `json:"file_id"`
	RunID         string         `json:"run_id"`
	ProjectID     string         `json:"project_id"`
	Path          string         `json:"path"`
	Kind          string         `json:"kind"`
	MimeType      string         `json:"mime_type"`
	SizeBytes     int64          `json:"size_bytes"`
	ContentSHA256 string         `json:"content_sha256"`
	ContentText   string         `json:"content_text,omitempty"`
	Metadata      map[string]any `json:"metadata,omitempty"`
	UpdatedAt     string         `json:"updated_at,omitempty"`
}

func analysisRunToResponse(run workflows.AnalysisRun) analysisRunResponse {
	return analysisRunResponse{
		RunID:        run.RunID,
		TraceID:      run.TraceID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
		Mode:         run.Mode,
		Instruction:  run.Instruction,
		UploadID:     run.UploadID,
		SourceFileID: run.SourceFileID,
		Progress:     run.Progress,
		Message:      run.Message,
		ErrorCode:    run.ErrorCode,
		ErrorMessage: run.ErrorMessage,
		CreatedAt:    run.CreatedAt,
		UpdatedAt:    run.UpdatedAt,
	}
}

func (s *Server) handleStartAnalysisRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "analysis-runs")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project analysis route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return
	}
	var payload startAnalysisRunRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid analysis run payload", nil)
		return
	}
	if !sourcefiles.IsConfigured(s.sourceFileStore) {
		writeSourceFileError(response, request, sourcefiles.NewAppError("SOURCE_FILE_BACKEND_UNCONFIGURED", "source file backend is not configured"))
		return
	}
	// Fail closed (and auto-ensure from an existing chat binding when possible)
	// before Temporal admit so authors never queue a run that dies at planner.
	actorUserID := s.actorUserID(request)
	primaryResolution, err := llm.EnsureAnalysisModuleBindings(
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
	validated, err := s.sourceFileStore.ValidateSourceFile(request.Context(), sourcefiles.ValidateInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		UploadID:  strings.TrimSpace(payload.UploadID),
	})
	if err != nil {
		writeSourceFileError(response, request, err)
		return
	}
	options := sanitizeWorkflowOptions(payload.Options)
	options["module_key"] = workflows.ModuleKeyFromAnalysisOptions(options)
	options["llm_resolution"] = workflowLLMResolution(primaryResolution)
	options["required_module_keys"] = append([]string(nil), llm.AnalysisRequiredModules...)
	run, err := s.analysisStarter.StartAnalysisRun(request.Context(), workflows.StartAnalysisRunInput{
		TenantID:        tenantID,
		ProjectID:       projectID,
		UploadID:        strings.TrimSpace(payload.UploadID),
		ActorUserID:     actorUserID,
		RequestID:       requestID(request),
		SourceFileID:    validated.FileID,
		SourceObjectKey: validated.ObjectKey,
		SourceFilename:  validated.Filename,
		SourceMimeType:  validated.MimeType,
		SourceSizeBytes: validated.SizeBytes,
		SourceSHA256:    validated.SHA256,
		Mode:            strings.TrimSpace(payload.Mode),
		Instruction:     strings.TrimSpace(payload.Instruction),
		Hints:           sanitizeWorkflowOptions(payload.Hints),
		Options:         options,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startAnalysisRunResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
		Mode:         run.Mode,
	})
}

func (s *Server) handleListAnalysisRuns(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "analysis-runs")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project analysis route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	runs, err := s.analysisRunReader.ListAnalysisRuns(request.Context(), workflows.ListAnalysisRunsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	items := make([]analysisRunResponse, 0, len(runs))
	for _, run := range runs {
		items = append(items, analysisRunToResponse(run))
	}
	writeJSON(response, http.StatusOK, listResponse[analysisRunResponse]{Items: items})
}

func (s *Server) handleGetAnalysisRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := analysisRunIDFromDetailPath(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "analysis run route not found", nil)
		return
	}
	run, err := s.analysisRunReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	writeJSON(response, http.StatusOK, analysisRunToResponse(run))
}

func (s *Server) handleListAnalysisRunEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := analysisRunIDFromEventsPath(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "analysis run events route not found", nil)
		return
	}
	run, err := s.analysisRunReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	cursor := afterEventIDFromRequest(request)
	events, err := s.analysisEventReader.ListAnalysisEvents(request.Context(), workflows.ListAnalysisEventsInput{
		TenantID:     tenantID,
		RunID:        runID,
		AfterEventID: cursor,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	events = sanitizeAnalysisEvents(events)
	if strings.Contains(request.Header.Get("Accept"), "text/event-stream") {
		holdOpen := request.URL.Query().Get("stream") == "1" || isActiveAnalysisRunStatus(run.Status)
		if holdOpen {
			writeAnalysisEventsSSEHeldOpen(response, request, s.analysisEventReader, s.analysisRunReader, tenantID, runID, cursor, events, run.Status)
			return
		}
		writeAnalysisEventsSSE(response, events)
		return
	}
	items := make([]analysisEventResponse, 0, len(events))
	for _, event := range events {
		items = append(items, analysisEventResponse{
			EventID:   event.EventID,
			RunID:     event.RunID,
			ProjectID: event.ProjectID,
			Sequence:  event.Sequence,
			EventType: event.EventType,
			Payload:   event.Payload,
			CreatedAt: event.CreatedAt,
		})
	}
	writeJSON(response, http.StatusOK, listResponse[analysisEventResponse]{Items: items})
}

func isActiveAnalysisRunStatus(status string) bool {
	status = strings.TrimSpace(status)
	return status == "queued" || status == "running"
}

func isTerminalAnalysisEventType(eventType string) bool {
	switch eventType {
	case "analysis.run.completed", "analysis.run.failed", "analysis.run.cancelled":
		return true
	default:
		return false
	}
}

func sanitizeAnalysisEvents(events []workflows.AnalysisEvent) []workflows.AnalysisEvent {
	sanitized := make([]workflows.AnalysisEvent, 0, len(events))
	for _, event := range events {
		event.Payload = workflows.SanitizeWorkflowEventPayload(event.Payload)
		sanitized = append(sanitized, event)
	}
	return sanitized
}

func writeAnalysisEventSSEFrame(response http.ResponseWriter, event workflows.AnalysisEvent) {
	payload, err := json.Marshal(event)
	if err != nil {
		return
	}
	_, _ = response.Write([]byte("id: " + event.EventID + "\n"))
	_, _ = response.Write([]byte("event: workflow.event\n"))
	_, _ = response.Write([]byte("data: " + string(payload) + "\n\n"))
}

func writeAnalysisEventsSSE(response http.ResponseWriter, events []workflows.AnalysisEvent) {
	response.Header().Set("Content-Type", "text/event-stream")
	response.Header().Set("Cache-Control", "no-cache")
	response.Header().Set("X-Accel-Buffering", "no")
	response.WriteHeader(http.StatusOK)
	for _, event := range events {
		writeAnalysisEventSSEFrame(response, event)
	}
	if flusher, ok := response.(http.Flusher); ok {
		flusher.Flush()
	}
}

// writeAnalysisEventsSSEHeldOpen streams known events then poll-forwards new ones until
// terminal event, client disconnect, or hold budget (25s) is exhausted.
func writeAnalysisEventsSSEHeldOpen(
	response http.ResponseWriter,
	request *http.Request,
	eventReader workflows.AnalysisEventReader,
	runReader workflows.AnalysisRunReader,
	tenantID string,
	runID string,
	initialCursor string,
	initialEvents []workflows.AnalysisEvent,
	initialStatus string,
) {
	response.Header().Set("Content-Type", "text/event-stream")
	response.Header().Set("Cache-Control", "no-cache")
	response.Header().Set("Connection", "keep-alive")
	response.Header().Set("X-Accel-Buffering", "no")
	response.WriteHeader(http.StatusOK)
	flusher, _ := response.(http.Flusher)

	cursor := strings.TrimSpace(initialCursor)
	for _, event := range initialEvents {
		writeAnalysisEventSSEFrame(response, event)
		cursor = event.EventID
		if isTerminalAnalysisEventType(event.EventType) {
			if flusher != nil {
				flusher.Flush()
			}
			return
		}
	}
	if flusher != nil {
		flusher.Flush()
	}

	status := strings.TrimSpace(initialStatus)
	if !isActiveAnalysisRunStatus(status) {
		return
	}

	deadline := time.Now().Add(25 * time.Second)
	ticker := time.NewTicker(700 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-request.Context().Done():
			return
		case <-ticker.C:
			if time.Now().After(deadline) {
				_, _ = response.Write([]byte(": hold-timeout\n\n"))
				if flusher != nil {
					flusher.Flush()
				}
				return
			}
			if eventReader == nil {
				return
			}
			next, err := eventReader.ListAnalysisEvents(request.Context(), workflows.ListAnalysisEventsInput{
				TenantID:     tenantID,
				RunID:        runID,
				AfterEventID: cursor,
			})
			if err != nil {
				_, _ = response.Write([]byte(": poll-error\n\n"))
				if flusher != nil {
					flusher.Flush()
				}
				continue
			}
			next = sanitizeAnalysisEvents(next)
			for _, event := range next {
				writeAnalysisEventSSEFrame(response, event)
				cursor = event.EventID
				if isTerminalAnalysisEventType(event.EventType) {
					if flusher != nil {
						flusher.Flush()
					}
					return
				}
			}
			if flusher != nil {
				flusher.Flush()
			}
			if runReader != nil {
				if run, err := runReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{TenantID: tenantID, RunID: runID}); err == nil {
					status = run.Status
					if !isActiveAnalysisRunStatus(status) {
						return
					}
				}
			}
			_, _ = response.Write([]byte(": keepalive\n\n"))
			if flusher != nil {
				flusher.Flush()
			}
		}
	}
}

func (s *Server) handleCancelAnalysisRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := analysisRunIDFromCancelPath(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "analysis run cancel route not found", nil)
		return
	}
	run, err := s.analysisRunReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, run.ProjectID, auth.PermissionCreativeWrite) {
		return
	}
	result, err := s.analysisCanceller.CancelAnalysisRun(request.Context(), workflows.CancelAnalysisRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, map[string]string{
		"run_id": result.RunID,
		"status": result.Status,
	})
}

func (s *Server) handleListAnalysisWorkspaceFiles(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := analysisRunIDFromWorkspacePath(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "analysis workspace route not found", nil)
		return
	}
	run, err := s.analysisRunReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	files, err := s.analysisWorkspaceReader.ListWorkspaceFiles(request.Context(), workflows.ListAnalysisWorkspaceFilesInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	items := make([]analysisWorkspaceFileResponse, 0, len(files))
	for _, file := range files {
		items = append(items, analysisWorkspaceFileToResponse(file, false))
	}
	writeJSON(response, http.StatusOK, listResponse[analysisWorkspaceFileResponse]{Items: items})
}

func (s *Server) handleGetAnalysisWorkspaceFile(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID, path := analysisRunWorkspaceFileFromPath(request.URL.Path)
	if runID == "" || path == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "analysis workspace file route not found", nil)
		return
	}
	run, err := s.analysisRunReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	file, err := s.analysisWorkspaceReader.GetWorkspaceFile(request.Context(), workflows.GetAnalysisWorkspaceFileInput{
		TenantID: tenantID,
		RunID:    runID,
		Path:     path,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, analysisWorkspaceFileToResponse(file, true))
}

func analysisWorkspaceFileToResponse(file workflows.AnalysisWorkspaceFile, includeContent bool) analysisWorkspaceFileResponse {
	item := analysisWorkspaceFileResponse{
		FileID:        file.FileID,
		RunID:         file.RunID,
		ProjectID:     file.ProjectID,
		Path:          file.Path,
		Kind:          file.Kind,
		MimeType:      file.MimeType,
		SizeBytes:     file.SizeBytes,
		ContentSHA256: file.ContentSHA256,
		Metadata:      file.Metadata,
		UpdatedAt:     file.UpdatedAt,
	}
	if includeContent {
		item.ContentText = file.ContentText
	}
	return item
}

type analysisCandidateResponse struct {
	CandidateID   string         `json:"candidate_id"`
	RunID         string         `json:"run_id"`
	ProjectID     string         `json:"project_id"`
	CandidateType string         `json:"candidate_type"`
	Name          string         `json:"name"`
	Status        string         `json:"status"`
	WorkspacePath string         `json:"workspace_path,omitempty"`
	Payload       map[string]any `json:"payload,omitempty"`
	CreatedAt     string         `json:"created_at,omitempty"`
	UpdatedAt     string         `json:"updated_at,omitempty"`
}

func (s *Server) handleListAnalysisCandidates(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := analysisRunIDFromCandidatesPath(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "analysis candidates route not found", nil)
		return
	}
	run, err := s.analysisRunReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	// Author-friendly backfill: completed runs auto-import candidates into assets.
	if strings.EqualFold(strings.TrimSpace(run.Status), "completed") {
		_, _ = s.analysisAssetImporter.EnsureAnalysisAssetsImported(request.Context(), workflows.ImportAnalysisAssetsInput{
			TenantID:  tenantID,
			ProjectID: run.ProjectID,
			RunID:     runID,
		})
	}
	items, err := s.analysisCandidateReader.ListAnalysisCandidates(request.Context(), workflows.ListAnalysisCandidatesInput{
		TenantID:  tenantID,
		ProjectID: run.ProjectID,
		RunID:     runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	responseItems := make([]analysisCandidateResponse, 0, len(items))
	for _, item := range items {
		responseItems = append(responseItems, analysisCandidateResponse{
			CandidateID:   item.CandidateID,
			RunID:         item.RunID,
			ProjectID:     item.ProjectID,
			CandidateType: item.CandidateType,
			Name:          item.Name,
			Status:        item.Status,
			WorkspacePath: item.WorkspacePath,
			Payload:       item.Payload,
			CreatedAt:     item.CreatedAt,
			UpdatedAt:     item.UpdatedAt,
		})
	}
	writeJSON(response, http.StatusOK, listResponse[analysisCandidateResponse]{Items: responseItems})
}

type importAnalysisAssetsResponse struct {
	RunID         string `json:"run_id"`
	ProjectID     string `json:"project_id"`
	ImportedCount int    `json:"imported_count"`
	SkippedCount  int    `json:"skipped_count"`
	Status        string `json:"status"`
}

func (s *Server) handleImportAnalysisAssets(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := analysisRunIDFromAssetsImportPath(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "analysis assets import route not found", nil)
		return
	}
	run, err := s.analysisRunReader.GetAnalysisRun(request.Context(), workflows.GetAnalysisRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, run.ProjectID, auth.PermissionCreativeWrite) {
		return
	}
	if !strings.EqualFold(strings.TrimSpace(run.Status), "completed") {
		writeError(response, request, http.StatusConflict, "ANALYSIS_RUN_NOT_COMPLETED", "analysis run must be completed before asset import", nil)
		return
	}
	result, err := s.analysisAssetImporter.EnsureAnalysisAssetsImported(request.Context(), workflows.ImportAnalysisAssetsInput{
		TenantID:  tenantID,
		ProjectID: run.ProjectID,
		RunID:     runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, importAnalysisAssetsResponse{
		RunID:         runID,
		ProjectID:     run.ProjectID,
		ImportedCount: result.ImportedCount,
		SkippedCount:  result.SkippedCount,
		Status:        "completed",
	})
}

func isAnalysisRunDetailPath(path string) bool {
	return analysisRunIDFromDetailPath(path) != ""
}

func isAnalysisCandidatesPath(path string) bool {
	return analysisRunIDFromCandidatesPath(path) != ""
}

func isAnalysisAssetsImportPath(path string) bool {
	return analysisRunIDFromAssetsImportPath(path) != ""
}

func analysisRunIDFromCandidatesPath(path string) string {
	const prefix = "/v1/analysis-runs/"
	const suffix = "/candidates"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	runID := strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix)
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func analysisRunIDFromAssetsImportPath(path string) string {
	const prefix = "/v1/analysis-runs/"
	const suffix = "/import-assets"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	runID := strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix)
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func isAnalysisRunEventsPath(path string) bool {
	return analysisRunIDFromEventsPath(path) != ""
}

func isAnalysisRunCancelPath(path string) bool {
	return analysisRunIDFromCancelPath(path) != ""
}

func isAnalysisWorkspaceFilesPath(path string) bool {
	return analysisRunIDFromWorkspacePath(path) != ""
}

func isAnalysisWorkspaceFilePath(path string) bool {
	runID, filePath := analysisRunWorkspaceFileFromPath(path)
	return runID != "" && filePath != ""
}

func analysisRunIDFromDetailPath(path string) string {
	const prefix = "/v1/analysis-runs/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	runID := strings.TrimPrefix(path, prefix)
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func analysisRunIDFromEventsPath(path string) string {
	const prefix = "/v1/analysis-runs/"
	const suffix = "/events"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	runID := strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix)
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func analysisRunIDFromCancelPath(path string) string {
	const prefix = "/v1/analysis-runs/"
	const suffix = "/cancel"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	runID := strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix)
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func analysisRunIDFromWorkspacePath(path string) string {
	const prefix = "/v1/analysis-runs/"
	const suffix = "/workspace/files"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	runID := strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix)
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func analysisRunWorkspaceFileFromPath(path string) (string, string) {
	const prefix = "/v1/analysis-runs/"
	const marker = "/workspace/files/"
	if !strings.HasPrefix(path, prefix) {
		return "", ""
	}
	remainder := strings.TrimPrefix(path, prefix)
	runID, rest, ok := strings.Cut(remainder, marker)
	if !ok || runID == "" || rest == "" || strings.Contains(runID, "/") {
		return "", ""
	}
	return runID, rest
}

type disabledAnalysisRunReader struct{}

func (r *disabledAnalysisRunReader) ListAnalysisRuns(context.Context, workflows.ListAnalysisRunsInput) ([]workflows.AnalysisRun, error) {
	return nil, &workflows.AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis run reader is not configured"}
}

func (r *disabledAnalysisRunReader) GetAnalysisRun(context.Context, workflows.GetAnalysisRunInput) (workflows.AnalysisRun, error) {
	return workflows.AnalysisRun{}, &workflows.AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis run reader is not configured"}
}
