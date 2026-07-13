package writerplanning

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.temporal.io/sdk/client"
)

const (
	KindDedup            = "dedup"
	KindBookPlan         = "book_plan"
	DedupModuleKey       = "writer_dedup_extractor"
	BookPlanModuleKey    = "writer_book_planner"
	PlanningTaskQueue    = "writer-planning"
	DedupWorkflowName    = "WriterDedupExtractionWorkflow"
	BookPlanWorkflowName = "WriterBookPlanWorkflow"
)

func WorkflowType(kind string) string {
	if kind == KindDedup {
		return "writer_dedup_extraction"
	}
	if kind == KindBookPlan {
		return "writer_book_plan_generation"
	}
	return ""
}

type StartInput struct {
	TenantID, ProjectID, ActorUserID, RequestID string
	Kind, ChapterID, BookPlanID                 string
	BlockIDs                                    []string
	ExpectedVersion                             int64
}

type Admission struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	ModuleKey    string `json:"module_key"`
	Status       string `json:"status"`
	BookPlanID   string `json:"book_plan_id,omitempty"`
	Replay       bool   `json:"replay"`
}

type AppError struct {
	Code, Message string
	cause         error
}

func (e *AppError) Error() string { return e.Message }
func (e *AppError) Unwrap() error { return e.cause }
func ErrorCode(err error) string {
	var target *AppError
	if errors.As(err, &target) {
		return target.Code
	}
	return "WRITER_PLANNING_FAILED"
}

type TemporalClient interface {
	ExecuteWorkflow(context.Context, client.StartWorkflowOptions, any, ...any) (client.WorkflowRun, error)
}

type AdmissionStore interface {
	Admit(context.Context, StartInput, Admission, string, string) (Admission, bool, error)
	Compensate(context.Context, StartInput, Admission) error
}

type Starter interface {
	Start(context.Context, StartInput) (Admission, error)
}

type TemporalConfig struct {
	Client    TemporalClient
	Store     AdmissionStore
	TaskQueue string
}
type TemporalStarter struct {
	client    TemporalClient
	store     AdmissionStore
	taskQueue string
}

func NewTemporalStarter(config TemporalConfig) *TemporalStarter {
	queue := strings.TrimSpace(config.TaskQueue)
	if queue == "" {
		queue = PlanningTaskQueue
	}
	return &TemporalStarter{client: config.Client, store: config.Store, taskQueue: queue}
}

func (s *TemporalStarter) Start(ctx context.Context, input StartInput) (Admission, error) {
	input = normalize(input)
	module, workflowName, err := validate(input)
	if err != nil {
		return Admission{}, err
	}
	if s == nil || s.client == nil || s.store == nil {
		return Admission{}, appError("WRITER_PLANNING_BACKEND_UNCONFIGURED", "writer planning backend is not configured")
	}
	payloadHash, err := fingerprint(input)
	if err != nil {
		return Admission{}, appError("VALIDATION_FAILED", "writer planning request must be JSON serializable")
	}
	proposed := Admission{RunID: uuid.NewString(), ProjectID: input.ProjectID, WorkflowType: WorkflowType(input.Kind), ModuleKey: module, Status: "queued", BookPlanID: input.BookPlanID}
	temporalID := proposed.WorkflowType + "_" + proposed.RunID
	admitted, replay, err := s.store.Admit(ctx, input, proposed, temporalID, payloadHash)
	if err != nil {
		return Admission{}, err
	}
	if replay {
		admitted.Replay = true
		return admitted, nil
	}
	payload := map[string]any{
		"context": map[string]any{
			"tenant_id": input.TenantID, "project_id": input.ProjectID, "run_id": admitted.RunID,
			"workflow_type": admitted.WorkflowType, "actor_user_id": input.ActorUserID,
			"module_key": module, "trace_id": "trace_" + admitted.RunID,
			"permissions": map[string][]string{module: {"run"}},
		},
	}
	if input.Kind == KindDedup {
		payload["block_ids"], payload["chapter_id"] = append([]string(nil), input.BlockIDs...), input.ChapterID
	}
	if input.Kind == KindBookPlan {
		payload["book_plan_id"], payload["expected_version"] = input.BookPlanID, input.ExpectedVersion
	}
	_, err = s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{ID: temporalID, TaskQueue: s.taskQueue, WorkflowExecutionTimeout: time.Hour, WorkflowRunTimeout: time.Hour}, workflowName, payload)
	if err != nil {
		compensationCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		defer cancel()
		if compensationErr := s.store.Compensate(compensationCtx, input, admitted); compensationErr != nil {
			return Admission{}, compensationErr
		}
		return Admission{}, appError("WRITER_PLANNING_START_FAILED", "writer planning workflow failed to start")
	}
	return admitted, nil
}

func validate(input StartInput) (string, string, error) {
	if input.TenantID == "" || input.ProjectID == "" || input.ActorUserID == "" || input.RequestID == "" {
		return "", "", appError("VALIDATION_FAILED", "writer planning scope and request_id are required")
	}
	switch input.Kind {
	case KindDedup:
		if len(input.BlockIDs) == 0 && input.ChapterID == "" {
			return "", "", appError("VALIDATION_FAILED", "dedup extraction requires selected block_ids or chapter_id")
		}
		seen := map[string]struct{}{}
		for _, id := range input.BlockIDs {
			if id == "" {
				return "", "", appError("VALIDATION_FAILED", "block_ids are invalid")
			}
			if _, ok := seen[id]; ok {
				return "", "", appError("VALIDATION_FAILED", "block_ids must be unique")
			}
			seen[id] = struct{}{}
		}
		return DedupModuleKey, DedupWorkflowName, nil
	case KindBookPlan:
		if input.BookPlanID == "" || input.ExpectedVersion <= 0 {
			return "", "", appError("VALIDATION_FAILED", "book_plan_id and expected_version are required")
		}
		return BookPlanModuleKey, BookPlanWorkflowName, nil
	default:
		return "", "", appError("VALIDATION_FAILED", "writer planning kind is invalid")
	}
}

func normalize(input StartInput) StartInput {
	input.TenantID, input.ProjectID = strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID)
	input.ActorUserID, input.RequestID = strings.TrimSpace(input.ActorUserID), strings.TrimSpace(input.RequestID)
	input.Kind, input.ChapterID, input.BookPlanID = strings.TrimSpace(input.Kind), strings.TrimSpace(input.ChapterID), strings.TrimSpace(input.BookPlanID)
	for index := range input.BlockIDs {
		input.BlockIDs[index] = strings.TrimSpace(input.BlockIDs[index])
	}
	return input
}

func fingerprint(input StartInput) (string, error) {
	payload, err := json.Marshal(struct {
		Kind, ProjectID, ChapterID, BookPlanID string
		BlockIDs                               []string
		ExpectedVersion                        int64
	}{input.Kind, input.ProjectID, input.ChapterID, input.BookPlanID, input.BlockIDs, input.ExpectedVersion})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func appError(code, message string) *AppError { return &AppError{Code: code, Message: message} }
