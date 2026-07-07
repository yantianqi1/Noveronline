package workflows

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"go.temporal.io/sdk/client"
)

const WriterWorkflowType = "writer_run"
const PiWriterWorkflowName = "PiWriterRunWorkflow"
const WriterTaskQueue = "writer-streaming"

type StartWriterRunInput struct {
	TenantID     string
	ProjectID    string
	ActorUserID  string
	RequestID    string
	Mode         string
	Instruction  string
	Options      map[string]any
	WorkflowType string
}

type GetWriterRunInput struct {
	TenantID string
	RunID    string
}

type ListWriterEventsInput struct {
	TenantID     string
	RunID        string
	AfterEventID string
}

type CancelWriterRunInput struct {
	TenantID    string
	RunID       string
	ActorUserID string
	RequestID   string
}

type WriterRun struct {
	RunID     string
	TraceID   string
	TenantID  string
	ProjectID string
	Status    string
}

type WriterRunCancellation struct {
	RunID  string
	Status string
}

type WriterEvent struct {
	EventID   string         `json:"event_id"`
	RunID     string         `json:"run_id"`
	ProjectID string         `json:"project_id"`
	Sequence  int            `json:"sequence"`
	EventType string         `json:"event_type"`
	Payload   map[string]any `json:"payload"`
	CreatedAt string         `json:"created_at"`
}

type WriterStarter interface {
	StartWriterRun(context.Context, StartWriterRunInput) (WriterRun, error)
}

type WriterReader interface {
	GetWriterRun(context.Context, GetWriterRunInput) (WriterRun, error)
}

type WriterEventReader interface {
	ListWriterEvents(context.Context, ListWriterEventsInput) ([]WriterEvent, error)
}

type WriterCanceller interface {
	CancelWriterRun(context.Context, CancelWriterRunInput) (WriterRunCancellation, error)
}

type WriterAdmissionStore interface {
	AdmitWriterRun(context.Context, WriterAdmissionInput) error
}

type WriterCancellationStore interface {
	CancelWriterRun(context.Context, WriterCancellationInput) error
}

type WriterStore interface {
	WriterStarter
	WriterReader
	WriterEventReader
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "WORKFLOW_FAILED"
}

type LocalWriterStarter struct {
	mu     sync.RWMutex
	runs   map[string]WriterRun
	events map[string][]WriterEvent
}

func NewLocalWriterStarter() *LocalWriterStarter {
	return &LocalWriterStarter{
		runs:   map[string]WriterRun{},
		events: map[string][]WriterEvent{},
	}
}

func (s *LocalWriterStarter) StartWriterRun(_ context.Context, input StartWriterRunInput) (WriterRun, error) {
	if input.TenantID == "" || input.ProjectID == "" || input.Mode == "" || input.Instruction == "" {
		return WriterRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, mode, and instruction are required",
		}
	}
	if input.WorkflowType == "" {
		input.WorkflowType = WriterWorkflowType
	}
	runID, err := newRunID()
	if err != nil {
		return WriterRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate writer run id",
		}
	}
	traceID := traceIDForRun(runID)
	run := WriterRun{
		RunID:     runID,
		TraceID:   traceID,
		TenantID:  input.TenantID,
		ProjectID: input.ProjectID,
		Status:    "queued",
	}
	eventID, err := newRunID()
	if err != nil {
		return WriterRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate writer run event id",
		}
	}
	s.mu.Lock()
	s.runs[runID] = run
	s.events[runID] = []WriterEvent{{
		EventID:   eventID,
		RunID:     runID,
		ProjectID: input.ProjectID,
		Sequence:  1,
		EventType: "workflow.queued",
		Payload: map[string]any{
			"status":        "queued",
			"workflow_type": input.WorkflowType,
			"request_id":    strings.TrimSpace(input.RequestID),
		},
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	}}
	s.mu.Unlock()
	return run, nil
}

func (s *LocalWriterStarter) GetWriterRun(_ context.Context, input GetWriterRunInput) (WriterRun, error) {
	if input.TenantID == "" || input.RunID == "" {
		return WriterRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	s.mu.RLock()
	run, ok := s.runs[input.RunID]
	s.mu.RUnlock()
	if !ok || run.TenantID != input.TenantID {
		return WriterRun{}, &AppError{
			Code:    "NOT_FOUND",
			Message: "writer run not found",
		}
	}
	return run, nil
}

func (s *LocalWriterStarter) ListWriterEvents(_ context.Context, input ListWriterEventsInput) ([]WriterEvent, error) {
	if input.TenantID == "" || input.RunID == "" {
		return nil, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	s.mu.RLock()
	run, ok := s.runs[input.RunID]
	events := append([]WriterEvent(nil), s.events[input.RunID]...)
	s.mu.RUnlock()
	if !ok || run.TenantID != input.TenantID {
		return nil, &AppError{
			Code:    "NOT_FOUND",
			Message: "writer run not found",
		}
	}
	afterEventID := strings.TrimSpace(input.AfterEventID)
	if afterEventID == "" {
		return events, nil
	}
	for index, event := range events {
		if event.EventID == afterEventID {
			return events[index+1:], nil
		}
	}
	return nil, &AppError{
		Code:    "EVENT_CURSOR_NOT_FOUND",
		Message: "writer event cursor not found",
	}
}

type DisabledWriterEventReader struct{}

func NewDisabledWriterEventReader() *DisabledWriterEventReader {
	return &DisabledWriterEventReader{}
}

func (r *DisabledWriterEventReader) ListWriterEvents(_ context.Context, _ ListWriterEventsInput) ([]WriterEvent, error) {
	return nil, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "writer event reader is not configured",
	}
}

type DisabledWriterCanceller struct{}

func NewDisabledWriterCanceller() *DisabledWriterCanceller {
	return &DisabledWriterCanceller{}
}

func (c *DisabledWriterCanceller) CancelWriterRun(_ context.Context, _ CancelWriterRunInput) (WriterRunCancellation, error) {
	return WriterRunCancellation{}, &AppError{
		Code:    "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED",
		Message: "writer cancellation backend is not configured",
	}
}

type TemporalWriterConfig struct {
	Client            TemporalWorkflowClient
	TaskQueue         string
	AdmissionStore    WriterAdmissionStore
	CancellationStore WriterCancellationStore
}

type TemporalWriterStarter struct {
	client            TemporalWorkflowClient
	taskQueue         string
	admissionStore    WriterAdmissionStore
	cancellationStore WriterCancellationStore
	mu                sync.RWMutex
	runs              map[string]WriterRun
}

func NewTemporalWriterStarter(config TemporalWriterConfig) *TemporalWriterStarter {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = WriterTaskQueue
	}
	cancellationStore := config.CancellationStore
	if cancellationStore == nil {
		if store, ok := config.AdmissionStore.(WriterCancellationStore); ok {
			cancellationStore = store
		}
	}
	return &TemporalWriterStarter{
		client:            config.Client,
		taskQueue:         taskQueue,
		admissionStore:    config.AdmissionStore,
		cancellationStore: cancellationStore,
		runs:              map[string]WriterRun{},
	}
}

func NewTemporalWriterStarterFromAddress(ctx context.Context, address string, namespace string, taskQueue string) (*TemporalWriterStarter, client.Client, error) {
	address = strings.TrimSpace(address)
	if address == "" {
		return nil, nil, fmt.Errorf("temporal address is required")
	}
	namespace = strings.TrimSpace(namespace)
	if namespace == "" {
		namespace = "default"
	}
	temporalClient, err := client.DialContext(ctx, client.Options{
		HostPort:  address,
		Namespace: namespace,
	})
	if err != nil {
		return nil, nil, err
	}
	return NewTemporalWriterStarter(TemporalWriterConfig{
		Client:    temporalClient,
		TaskQueue: taskQueue,
	}), temporalClient, nil
}

func (s *TemporalWriterStarter) StartWriterRun(ctx context.Context, input StartWriterRunInput) (WriterRun, error) {
	if input.TenantID == "" || input.ProjectID == "" || input.Mode == "" || input.Instruction == "" {
		return WriterRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, mode, and instruction are required",
		}
	}
	if s.client == nil {
		return WriterRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for writer_run",
		}
	}
	if input.WorkflowType == "" {
		input.WorkflowType = WriterWorkflowType
	}
	runID, err := newRunID()
	if err != nil {
		return WriterRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: "failed to allocate writer run id",
		}
	}
	traceID := traceIDForRun(runID)
	payload := map[string]any{
		"tenant_id":     input.TenantID,
		"project_id":    input.ProjectID,
		"run_id":        runID,
		"workflow_type": input.WorkflowType,
		"requested_by":  strings.TrimSpace(input.ActorUserID),
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      traceID,
		"mode":          input.Mode,
		"instruction":   input.Instruction,
		"options":       input.Options,
	}
	temporalWorkflowID := "writer_run_" + runID
	if s.admissionStore != nil {
		err = s.admissionStore.AdmitWriterRun(ctx, WriterAdmissionInput{
			TenantID:           input.TenantID,
			ProjectID:          input.ProjectID,
			RunID:              runID,
			TraceID:            traceID,
			WorkflowType:       input.WorkflowType,
			TemporalWorkflowID: temporalWorkflowID,
			ActorUserID:        strings.TrimSpace(input.ActorUserID),
			RequestID:          strings.TrimSpace(input.RequestID),
			Mode:               input.Mode,
			Status:             "queued",
			ModuleKey:          moduleKeyFromWriterOptions(input.Options),
			Instruction:        input.Instruction,
			Options:            input.Options,
		})
		if err != nil {
			return WriterRun{}, &AppError{
				Code:    "WORKFLOW_ADMISSION_FAILED",
				Message: fmt.Sprintf("failed to persist writer_run admission: %v", err),
			}
		}
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 6 * time.Hour,
		WorkflowRunTimeout:       6 * time.Hour,
	}, PiWriterWorkflowName, payload)
	if err != nil {
		return WriterRun{}, &AppError{
			Code:    "WORKFLOW_FAILED",
			Message: fmt.Sprintf("failed to start writer_run workflow: %v", err),
		}
	}
	run := WriterRun{
		RunID:     runID,
		TraceID:   traceID,
		TenantID:  input.TenantID,
		ProjectID: input.ProjectID,
		Status:    "queued",
	}
	s.mu.Lock()
	s.runs[runID] = run
	s.mu.Unlock()
	return run, nil
}

func (s *TemporalWriterStarter) GetWriterRun(_ context.Context, input GetWriterRunInput) (WriterRun, error) {
	if input.TenantID == "" || input.RunID == "" {
		return WriterRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	s.mu.RLock()
	run, ok := s.runs[input.RunID]
	s.mu.RUnlock()
	if !ok || run.TenantID != input.TenantID {
		return WriterRun{}, &AppError{
			Code:    "NOT_FOUND",
			Message: "writer run not found",
		}
	}
	return run, nil
}

func (s *TemporalWriterStarter) CancelWriterRun(ctx context.Context, input CancelWriterRunInput) (WriterRunCancellation, error) {
	if input.TenantID == "" || input.RunID == "" {
		return WriterRunCancellation{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	if s.client == nil {
		return WriterRunCancellation{}, &AppError{
			Code:    "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED",
			Message: "Temporal workflow client is not configured for writer_run cancellation",
		}
	}
	runID := strings.TrimSpace(input.RunID)
	status := "cancelled"
	if err := s.client.CancelWorkflow(ctx, "writer_run_"+runID, ""); err != nil {
		return WriterRunCancellation{}, &AppError{
			Code:    "WORKFLOW_CANCEL_FAILED",
			Message: fmt.Sprintf("failed to cancel writer_run workflow: %v", err),
		}
	}
	if s.cancellationStore != nil {
		err := s.cancellationStore.CancelWriterRun(ctx, WriterCancellationInput{
			TenantID:    strings.TrimSpace(input.TenantID),
			RunID:       runID,
			ActorUserID: strings.TrimSpace(input.ActorUserID),
			RequestID:   strings.TrimSpace(input.RequestID),
			Status:      status,
		})
		if err != nil {
			return WriterRunCancellation{}, err
		}
	}
	s.mu.Lock()
	if run, ok := s.runs[runID]; ok && run.TenantID == strings.TrimSpace(input.TenantID) {
		run.Status = status
		s.runs[runID] = run
	}
	s.mu.Unlock()
	return WriterRunCancellation{RunID: runID, Status: status}, nil
}

func newRunID() (string, error) {
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return "", err
	}
	bytes[6] = (bytes[6] & 0x0f) | 0x40
	bytes[8] = (bytes[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", bytes[0:4], bytes[4:6], bytes[6:8], bytes[8:10], bytes[10:16]), nil
}

func traceIDForRun(runID string) string {
	return "trace_" + strings.TrimPrefix(strings.TrimSpace(runID), "run_")
}
