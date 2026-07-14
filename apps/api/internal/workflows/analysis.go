package workflows

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"go.temporal.io/sdk/client"
)

const AnalysisWorkflowType = "analysis_run"
const PiAnalysisWorkflowName = "PiAnalysisRunWorkflow"
const AnalysisTaskQueue = "analysis-streaming"

type StartAnalysisRunInput struct {
	TenantID        string
	ProjectID       string
	UploadID        string
	SourceFileID    string
	SourceObjectKey string
	SourceFilename  string
	SourceMimeType  string
	SourceSizeBytes int64
	SourceSHA256    string
	ActorUserID     string
	RequestID       string
	Mode            string
	Instruction     string
	Hints           map[string]any
	Options         map[string]any
}

type GetAnalysisRunInput struct {
	TenantID string
	RunID    string
}

type ListAnalysisRunsInput struct {
	TenantID  string
	ProjectID string
}

type ListAnalysisEventsInput struct {
	TenantID     string
	RunID        string
	AfterEventID string
}

type CancelAnalysisRunInput struct {
	TenantID    string
	RunID       string
	ActorUserID string
	RequestID   string
}

type ListAnalysisWorkspaceFilesInput struct {
	TenantID string
	RunID    string
}

type GetAnalysisWorkspaceFileInput struct {
	TenantID string
	RunID    string
	Path     string
}

type ListAnalysisCandidatesInput struct {
	TenantID  string
	ProjectID string
	RunID     string
}

type AnalysisRun struct {
	RunID        string         `json:"run_id"`
	TraceID      string         `json:"trace_id,omitempty"`
	TenantID     string         `json:"-"`
	ProjectID    string         `json:"project_id"`
	WorkflowType string         `json:"workflow_type"`
	Status       string         `json:"status"`
	Mode         string         `json:"mode,omitempty"`
	Instruction  string         `json:"instruction,omitempty"`
	UploadID     string         `json:"upload_id,omitempty"`
	SourceFileID string         `json:"source_file_id,omitempty"`
	Progress     int            `json:"progress,omitempty"`
	Message      string         `json:"message,omitempty"`
	ErrorCode    string         `json:"error_code,omitempty"`
	ErrorMessage string         `json:"error_message,omitempty"`
	CreatedAt    string         `json:"created_at,omitempty"`
	UpdatedAt    string         `json:"updated_at,omitempty"`
	Result       map[string]any `json:"result,omitempty"`
}

type AnalysisEvent struct {
	EventID   string         `json:"event_id"`
	RunID     string         `json:"run_id"`
	ProjectID string         `json:"project_id"`
	Sequence  int            `json:"sequence"`
	EventType string         `json:"event_type"`
	Payload   map[string]any `json:"payload"`
	CreatedAt string         `json:"created_at"`
}

type AnalysisWorkspaceFile struct {
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

// AnalysisCandidate is a non-canon extraction from an analysis run.
// Status "candidate" means not yet accepted into assets/graph readiness.
type AnalysisCandidate struct {
	CandidateID    string         `json:"candidate_id"`
	RunID          string         `json:"run_id"`
	ProjectID      string         `json:"project_id"`
	CandidateType  string         `json:"candidate_type"`
	Name           string         `json:"name"`
	Status         string         `json:"status"`
	WorkspacePath  string         `json:"workspace_path,omitempty"`
	Payload        map[string]any `json:"payload,omitempty"`
	CreatedAt      string         `json:"created_at,omitempty"`
	UpdatedAt      string         `json:"updated_at,omitempty"`
}

type AnalysisRunCancellation struct {
	RunID  string `json:"run_id"`
	Status string `json:"status"`
}

type AnalysisRunStarter interface {
	StartAnalysisRun(context.Context, StartAnalysisRunInput) (AnalysisRun, error)
}

type AnalysisRunReader interface {
	GetAnalysisRun(context.Context, GetAnalysisRunInput) (AnalysisRun, error)
	ListAnalysisRuns(context.Context, ListAnalysisRunsInput) ([]AnalysisRun, error)
}

type AnalysisEventReader interface {
	ListAnalysisEvents(context.Context, ListAnalysisEventsInput) ([]AnalysisEvent, error)
}

type AnalysisCanceller interface {
	CancelAnalysisRun(context.Context, CancelAnalysisRunInput) (AnalysisRunCancellation, error)
}

type AnalysisWorkspaceReader interface {
	ListWorkspaceFiles(context.Context, ListAnalysisWorkspaceFilesInput) ([]AnalysisWorkspaceFile, error)
	GetWorkspaceFile(context.Context, GetAnalysisWorkspaceFileInput) (AnalysisWorkspaceFile, error)
}

type AnalysisCandidateReader interface {
	ListAnalysisCandidates(context.Context, ListAnalysisCandidatesInput) ([]AnalysisCandidate, error)
}

// ImportAnalysisAssetsInput projects completed Pi analysis candidates into the asset library.
type ImportAnalysisAssetsInput struct {
	TenantID  string
	ProjectID string
	RunID     string
}

type ImportAnalysisAssetsResult struct {
	ImportedCount int `json:"imported_count"`
	SkippedCount  int `json:"skipped_count"`
}

// AnalysisAssetImporter auto-imports analysis candidates into assets for author-friendly flow.
type AnalysisAssetImporter interface {
	EnsureAnalysisAssetsImported(context.Context, ImportAnalysisAssetsInput) (ImportAnalysisAssetsResult, error)
}

type AnalysisAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	Mode               string
	Status             string
	ModuleKey          string
	Instruction        string
	UploadID           string
	SourceFileID       string
	Hints              map[string]any
	Options            map[string]any
}

type AnalysisCompensationInput struct {
	TenantID     string
	ProjectID    string
	RunID        string
	ActorUserID  string
	RequestID    string
	TraceID      string
	UploadID     string
	SourceFileID string
}

type AnalysisCancellationInput struct {
	TenantID    string
	RunID       string
	ActorUserID string
	RequestID   string
	Status      string
}

type AnalysisAdmissionStore interface {
	AdmitAnalysisRun(context.Context, AnalysisAdmissionInput) (AnalysisRun, bool, error)
	CompensateAnalysisRunStart(context.Context, AnalysisCompensationInput) error
}

type AnalysisCancellationStore interface {
	CancelAnalysisRun(context.Context, AnalysisCancellationInput) error
}

type FailClosedAnalysisStarter struct{}

func NewFailClosedAnalysisStarter() *FailClosedAnalysisStarter {
	return &FailClosedAnalysisStarter{}
}

func (s *FailClosedAnalysisStarter) StartAnalysisRun(_ context.Context, _ StartAnalysisRunInput) (AnalysisRun, error) {
	return AnalysisRun{}, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "Temporal workflow backend is not configured for analysis_run",
	}
}

type LocalAnalysisStarter struct {
	mu     sync.RWMutex
	runs   map[string]AnalysisRun
	events map[string][]AnalysisEvent
	files  map[string][]AnalysisWorkspaceFile
}

func NewLocalAnalysisStarter() *LocalAnalysisStarter {
	return &LocalAnalysisStarter{
		runs:   map[string]AnalysisRun{},
		events: map[string][]AnalysisEvent{},
		files:  map[string][]AnalysisWorkspaceFile{},
	}
}

func (s *LocalAnalysisStarter) StartAnalysisRun(_ context.Context, input StartAnalysisRunInput) (AnalysisRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.UploadID) == "" {
		return AnalysisRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and upload_id are required",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return AnalysisRun{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to allocate analysis run id"}
	}
	mode := strings.TrimSpace(input.Mode)
	if mode == "" {
		mode = "full"
	}
	instruction := strings.TrimSpace(input.Instruction)
	if instruction == "" {
		instruction = "Analyze the uploaded novel into structured story knowledge."
	}
	run := AnalysisRun{
		RunID:        runID,
		TraceID:      traceIDForRun(runID),
		TenantID:     strings.TrimSpace(input.TenantID),
		ProjectID:    strings.TrimSpace(input.ProjectID),
		WorkflowType: AnalysisWorkflowType,
		Status:       "queued",
		Mode:         mode,
		Instruction:  instruction,
		UploadID:     strings.TrimSpace(input.UploadID),
		SourceFileID: strings.TrimSpace(input.SourceFileID),
		CreatedAt:    time.Now().UTC().Format(time.RFC3339Nano),
		UpdatedAt:    time.Now().UTC().Format(time.RFC3339Nano),
	}
	eventID, err := newRunID()
	if err != nil {
		return AnalysisRun{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to allocate analysis event id"}
	}
	s.mu.Lock()
	s.runs[runID] = run
	s.events[runID] = []AnalysisEvent{{
		EventID:   eventID,
		RunID:     runID,
		ProjectID: run.ProjectID,
		Sequence:  1,
		EventType: "workflow.queued",
		Payload: map[string]any{
			"status":         "queued",
			"workflow_type":  AnalysisWorkflowType,
			"request_id":     strings.TrimSpace(input.RequestID),
			"upload_id":      run.UploadID,
			"source_file_id": run.SourceFileID,
		},
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	}}
	s.files[runID] = []AnalysisWorkspaceFile{}
	s.mu.Unlock()
	return run, nil
}

func (s *LocalAnalysisStarter) GetAnalysisRun(_ context.Context, input GetAnalysisRunInput) (AnalysisRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return AnalysisRun{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	s.mu.RLock()
	run, ok := s.runs[input.RunID]
	s.mu.RUnlock()
	if !ok || run.TenantID != input.TenantID {
		return AnalysisRun{}, &AppError{Code: "NOT_FOUND", Message: "analysis run not found"}
	}
	return run, nil
}

func (s *LocalAnalysisStarter) ListAnalysisRuns(_ context.Context, input ListAnalysisRunsInput) ([]AnalysisRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]AnalysisRun, 0)
	for _, run := range s.runs {
		if run.TenantID == input.TenantID && run.ProjectID == input.ProjectID {
			items = append(items, run)
		}
	}
	return items, nil
}

func (s *LocalAnalysisStarter) ListAnalysisEvents(_ context.Context, input ListAnalysisEventsInput) ([]AnalysisEvent, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	s.mu.RLock()
	run, ok := s.runs[input.RunID]
	events := append([]AnalysisEvent(nil), s.events[input.RunID]...)
	s.mu.RUnlock()
	if !ok || run.TenantID != input.TenantID {
		return nil, &AppError{Code: "NOT_FOUND", Message: "analysis run not found"}
	}
	after := strings.TrimSpace(input.AfterEventID)
	if after == "" {
		return events, nil
	}
	for index, event := range events {
		if event.EventID == after {
			return events[index+1:], nil
		}
	}
	return nil, &AppError{Code: "EVENT_CURSOR_NOT_FOUND", Message: "analysis event cursor not found"}
}

func (s *LocalAnalysisStarter) CancelAnalysisRun(_ context.Context, input CancelAnalysisRunInput) (AnalysisRunCancellation, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return AnalysisRunCancellation{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	run, ok := s.runs[input.RunID]
	if !ok || run.TenantID != input.TenantID {
		return AnalysisRunCancellation{}, &AppError{Code: "NOT_FOUND", Message: "analysis run not found"}
	}
	run.Status = "cancelled"
	run.UpdatedAt = time.Now().UTC().Format(time.RFC3339Nano)
	s.runs[input.RunID] = run
	return AnalysisRunCancellation{RunID: run.RunID, Status: "cancelled"}, nil
}

func (s *LocalAnalysisStarter) ListWorkspaceFiles(_ context.Context, input ListAnalysisWorkspaceFilesInput) ([]AnalysisWorkspaceFile, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	s.mu.RLock()
	run, ok := s.runs[input.RunID]
	files := append([]AnalysisWorkspaceFile(nil), s.files[input.RunID]...)
	s.mu.RUnlock()
	if !ok || run.TenantID != input.TenantID {
		return nil, &AppError{Code: "NOT_FOUND", Message: "analysis run not found"}
	}
	return files, nil
}

func (s *LocalAnalysisStarter) GetWorkspaceFile(_ context.Context, input GetAnalysisWorkspaceFileInput) (AnalysisWorkspaceFile, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" || strings.TrimSpace(input.Path) == "" {
		return AnalysisWorkspaceFile{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, run_id, and path are required"}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	run, ok := s.runs[input.RunID]
	if !ok || run.TenantID != input.TenantID {
		return AnalysisWorkspaceFile{}, &AppError{Code: "NOT_FOUND", Message: "analysis run not found"}
	}
	for _, file := range s.files[input.RunID] {
		if file.Path == strings.TrimSpace(input.Path) {
			return file, nil
		}
	}
	return AnalysisWorkspaceFile{}, &AppError{Code: "NOT_FOUND", Message: "analysis workspace file not found"}
}

type DisabledAnalysisEventReader struct{}

func NewDisabledAnalysisEventReader() *DisabledAnalysisEventReader {
	return &DisabledAnalysisEventReader{}
}

func (r *DisabledAnalysisEventReader) ListAnalysisEvents(context.Context, ListAnalysisEventsInput) ([]AnalysisEvent, error) {
	return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis event reader is not configured"}
}

type DisabledAnalysisCanceller struct{}

func NewDisabledAnalysisCanceller() *DisabledAnalysisCanceller {
	return &DisabledAnalysisCanceller{}
}

func (c *DisabledAnalysisCanceller) CancelAnalysisRun(context.Context, CancelAnalysisRunInput) (AnalysisRunCancellation, error) {
	return AnalysisRunCancellation{}, &AppError{
		Code:    "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED",
		Message: "analysis cancellation backend is not configured",
	}
}

type DisabledAnalysisWorkspaceReader struct{}

func NewDisabledAnalysisWorkspaceReader() *DisabledAnalysisWorkspaceReader {
	return &DisabledAnalysisWorkspaceReader{}
}

func (r *DisabledAnalysisWorkspaceReader) ListWorkspaceFiles(context.Context, ListAnalysisWorkspaceFilesInput) ([]AnalysisWorkspaceFile, error) {
	return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis workspace reader is not configured"}
}

func (r *DisabledAnalysisWorkspaceReader) GetWorkspaceFile(context.Context, GetAnalysisWorkspaceFileInput) (AnalysisWorkspaceFile, error) {
	return AnalysisWorkspaceFile{}, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis workspace reader is not configured"}
}

type DisabledAnalysisCandidateReader struct{}

func NewDisabledAnalysisCandidateReader() *DisabledAnalysisCandidateReader {
	return &DisabledAnalysisCandidateReader{}
}

func (r *DisabledAnalysisCandidateReader) ListAnalysisCandidates(context.Context, ListAnalysisCandidatesInput) ([]AnalysisCandidate, error) {
	return nil, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis candidate reader is not configured"}
}

type DisabledAnalysisAssetImporter struct{}

func NewDisabledAnalysisAssetImporter() *DisabledAnalysisAssetImporter {
	return &DisabledAnalysisAssetImporter{}
}

func (i *DisabledAnalysisAssetImporter) EnsureAnalysisAssetsImported(context.Context, ImportAnalysisAssetsInput) (ImportAnalysisAssetsResult, error) {
	return ImportAnalysisAssetsResult{}, nil
}

type TemporalAnalysisConfig struct {
	Client            TemporalWorkflowClient
	TaskQueue         string
	AdmissionStore    AnalysisAdmissionStore
	CancellationStore AnalysisCancellationStore
}

type TemporalAnalysisStarter struct {
	client            TemporalWorkflowClient
	taskQueue         string
	admissionStore    AnalysisAdmissionStore
	cancellationStore AnalysisCancellationStore
	mu                sync.RWMutex
	runs              map[string]AnalysisRun
}

func NewTemporalAnalysisStarter(config TemporalAnalysisConfig) *TemporalAnalysisStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = AnalysisTaskQueue
	}
	cancellationStore := config.CancellationStore
	if cancellationStore == nil {
		if store, ok := config.AdmissionStore.(AnalysisCancellationStore); ok {
			cancellationStore = store
		}
	}
	return &TemporalAnalysisStarter{
		client:            config.Client,
		taskQueue:         taskQueue,
		admissionStore:    config.AdmissionStore,
		cancellationStore: cancellationStore,
		runs:              map[string]AnalysisRun{},
	}
}

func (s *TemporalAnalysisStarter) StartAnalysisRun(ctx context.Context, input StartAnalysisRunInput) (AnalysisRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.UploadID) == "" {
		return AnalysisRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and upload_id are required",
		}
	}
	if s.client == nil {
		return AnalysisRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for analysis_run",
		}
	}
	if strings.TrimSpace(input.SourceFileID) == "" || strings.TrimSpace(input.SourceObjectKey) == "" {
		return AnalysisRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "analysis source metadata is incomplete",
		}
	}
	runID, err := newRunID()
	if err != nil {
		return AnalysisRun{}, &AppError{Code: "WORKFLOW_FAILED", Message: "failed to allocate analysis run id"}
	}
	traceID := traceIDForRun(runID)
	mode := strings.TrimSpace(input.Mode)
	if mode == "" {
		mode = "full"
	}
	instruction := strings.TrimSpace(input.Instruction)
	if instruction == "" {
		instruction = "Analyze the uploaded novel into structured story knowledge."
	}
	temporalWorkflowID := "analysis_run_" + runID
	run := AnalysisRun{
		RunID:        runID,
		TraceID:      traceID,
		TenantID:     strings.TrimSpace(input.TenantID),
		ProjectID:    strings.TrimSpace(input.ProjectID),
		WorkflowType: AnalysisWorkflowType,
		Status:       "queued",
		Mode:         mode,
		Instruction:  instruction,
		UploadID:     strings.TrimSpace(input.UploadID),
		SourceFileID: strings.TrimSpace(input.SourceFileID),
	}
	if s.admissionStore != nil {
		admitted, replayed, admitErr := s.admissionStore.AdmitAnalysisRun(ctx, AnalysisAdmissionInput{
			TenantID:           input.TenantID,
			ProjectID:          input.ProjectID,
			RunID:              runID,
			TraceID:            traceID,
			WorkflowType:       AnalysisWorkflowType,
			TemporalWorkflowID: temporalWorkflowID,
			ActorUserID:        strings.TrimSpace(input.ActorUserID),
			RequestID:          strings.TrimSpace(input.RequestID),
			Mode:               mode,
			Status:             "queued",
			ModuleKey:          moduleKeyFromAnalysisOptions(input.Options),
			Instruction:        instruction,
			UploadID:           strings.TrimSpace(input.UploadID),
			SourceFileID:       strings.TrimSpace(input.SourceFileID),
			Hints:              sanitizeAnalysisHints(input.Hints),
			Options:            sanitizeAnalysisOptions(input.Options),
		})
		if admitErr != nil {
			if code := ErrorCode(admitErr); code == "IDEMPOTENCY_CONFLICT" || code == "VALIDATION_FAILED" || code == "SOURCE_FILE_NOT_UPLOADED" {
				return AnalysisRun{}, admitErr
			}
			return AnalysisRun{}, &AppError{
				Code:    "WORKFLOW_ADMISSION_FAILED",
				Message: "failed to persist analysis_run admission",
			}
		}
		if replayed {
			s.mu.Lock()
			s.runs[admitted.RunID] = admitted
			s.mu.Unlock()
			return admitted, nil
		}
		run = admitted
		if strings.TrimSpace(run.RunID) == "" {
			run.RunID = runID
		}
		if strings.TrimSpace(run.TraceID) == "" {
			run.TraceID = traceIDForRun(run.RunID)
		}
		temporalWorkflowID = "analysis_run_" + run.RunID
	}
	payload := map[string]any{
		"tenant_id":          input.TenantID,
		"project_id":         input.ProjectID,
		"run_id":             run.RunID,
		"workflow_type":      AnalysisWorkflowType,
		"requested_by":       strings.TrimSpace(input.ActorUserID),
		"request_id":         strings.TrimSpace(input.RequestID),
		"trace_id":           run.TraceID,
		"mode":               mode,
		"instruction":        instruction,
		"upload_id":          strings.TrimSpace(input.UploadID),
		"source_file_id":     strings.TrimSpace(input.SourceFileID),
		"source_object_key":  strings.TrimSpace(input.SourceObjectKey),
		"source_filename":    strings.TrimSpace(input.SourceFilename),
		"source_mime_type":   strings.TrimSpace(input.SourceMimeType),
		"source_size_bytes":  input.SourceSizeBytes,
		"source_sha256":      strings.TrimSpace(input.SourceSHA256),
		"hints":              sanitizeAnalysisHints(input.Hints),
		"options":            sanitizeAnalysisOptions(input.Options),
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 12 * time.Hour,
		WorkflowRunTimeout:       12 * time.Hour,
	}, PiAnalysisWorkflowName, payload)
	if err != nil {
		if s.admissionStore != nil {
			compensationCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
			defer cancel()
			_ = s.admissionStore.CompensateAnalysisRunStart(compensationCtx, AnalysisCompensationInput{
				TenantID:     input.TenantID,
				ProjectID:    input.ProjectID,
				RunID:        run.RunID,
				ActorUserID:  strings.TrimSpace(input.ActorUserID),
				RequestID:    strings.TrimSpace(input.RequestID),
				TraceID:      run.TraceID,
				UploadID:     strings.TrimSpace(input.UploadID),
				SourceFileID: strings.TrimSpace(input.SourceFileID),
			})
		}
		return AnalysisRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to start analysis_run workflow",
		}
	}
	s.mu.Lock()
	s.runs[run.RunID] = run
	s.mu.Unlock()
	return run, nil
}

func (s *TemporalAnalysisStarter) CancelAnalysisRun(ctx context.Context, input CancelAnalysisRunInput) (AnalysisRunCancellation, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return AnalysisRunCancellation{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if s.client == nil {
		return AnalysisRunCancellation{}, &AppError{
			Code:    "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED",
			Message: "analysis cancellation backend is not configured",
		}
	}
	workflowID := "analysis_run_" + strings.TrimSpace(input.RunID)
	if err := s.client.CancelWorkflow(ctx, workflowID, ""); err != nil {
		return AnalysisRunCancellation{}, &AppError{
			Code:    "WORKFLOW_CANCEL_FAILED",
			Message: "failed to cancel analysis run",
		}
	}
	if s.cancellationStore != nil {
		if err := s.cancellationStore.CancelAnalysisRun(ctx, AnalysisCancellationInput{
			TenantID:    strings.TrimSpace(input.TenantID),
			RunID:       strings.TrimSpace(input.RunID),
			ActorUserID: strings.TrimSpace(input.ActorUserID),
			RequestID:   strings.TrimSpace(input.RequestID),
			Status:      "cancelled",
		}); err != nil {
			return AnalysisRunCancellation{}, err
		}
	}
	return AnalysisRunCancellation{RunID: strings.TrimSpace(input.RunID), Status: "cancelled"}, nil
}

func ModuleKeyFromAnalysisOptions(options map[string]any) string {
	if options == nil {
		return "analysis_planner"
	}
	if value, ok := options["module_key"].(string); ok && strings.TrimSpace(value) != "" {
		return strings.TrimSpace(value)
	}
	return "analysis_planner"
}

func moduleKeyFromAnalysisOptions(options map[string]any) string {
	return ModuleKeyFromAnalysisOptions(options)
}

func sanitizeAnalysisHints(hints map[string]any) map[string]any {
	if hints == nil {
		return map[string]any{}
	}
	return sanitizeAnalysisMap(hints)
}

func sanitizeAnalysisOptions(options map[string]any) map[string]any {
	if options == nil {
		return map[string]any{
			"module_key": "analysis_planner",
		}
	}
	cleaned := sanitizeAnalysisMap(options)
	if _, ok := cleaned["module_key"]; !ok {
		cleaned["module_key"] = "analysis_planner"
	}
	return cleaned
}

func sanitizeAnalysisMap(input map[string]any) map[string]any {
	clean := map[string]any{}
	for key, value := range input {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if isUntrustedAnalysisField(normalizedKey) {
			continue
		}
		clean[key] = sanitizeAnalysisValue(value)
	}
	return clean
}

func sanitizeAnalysisValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeAnalysisMap(typed)
	case []any:
		values := make([]any, 0, len(typed))
		for _, item := range typed {
			values = append(values, sanitizeAnalysisValue(item))
		}
		return values
	default:
		return value
	}
}

func isUntrustedAnalysisField(field string) bool {
	switch field {
	case "tenant_id", "tenantid", "project_id", "projectid",
		"api_key", "apikey", "credential", "credentials", "credential_ref", "credentialref",
		"encrypted_api_key", "encryptedapikey", "prompt", "response", "raw", "raw_body", "rawbody",
		"raw_text", "rawtext", "body", "content", "object_key", "objectkey", "source_object_key",
		"sourceobjectkey", "draft", "manuscript":
		return true
	default:
		return strings.Contains(field, "api_key") ||
			strings.Contains(field, "credential") ||
			strings.Contains(field, "object_key") ||
			strings.Contains(field, "prompt") ||
			strings.Contains(field, "raw_body")
	}
}

func analysisObjectKey(projectID, runID, path string) string {
	return fmt.Sprintf("projects/%s/analysis/%s/%s", strings.TrimSpace(projectID), strings.TrimSpace(runID), strings.TrimSpace(path))
}
