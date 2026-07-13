package assetdistillation

import (
	"context"
	"database/sql"
	"strings"
	"time"

	"go.temporal.io/sdk/client"

	"mirofish-novel/apps/api/internal/workflows"
)

type TemporalWorkflowClient interface {
	ExecuteWorkflow(context.Context, client.StartWorkflowOptions, any, ...any) (client.WorkflowRun, error)
}

type Starter interface {
	StartManual(context.Context, StartManualInput) (Admission, error)
	StartDispatched(context.Context, Scope, string, string, string) error
}

type Store interface {
	GetSettings(context.Context, Scope) (Settings, error)
	PatchSettings(context.Context, Scope, SettingsPatch) (Settings, error)
	AdmitManual(context.Context, StartManualInput) (Admission, bool, error)
	EnqueueFromSources(context.Context, Scope, string, []SourceBlock) (Admission, bool, error)
	MarkDispatched(context.Context, string, string) error
	MarkDispatchRetry(context.Context, string, string, string, int, time.Time) error
	ClaimPendingDispatch(context.Context, int) ([]OutboxItem, error)
	ListProposals(context.Context, Scope, string) ([]ProposalSummary, error)
	GetProposal(context.Context, Scope, string, bool) (ProposalDetail, error)
	Decide(context.Context, DecisionInput) (DecisionResult, error)
	StaleProposalsForBlock(context.Context, Scope, string) error
	LookupProposalProject(context.Context, string, string) (string, error)
}

type TemporalStarter struct {
	client    TemporalWorkflowClient
	store     Store
	taskQueue string
}

func NewTemporalStarter(c TemporalWorkflowClient, store Store, taskQueue string) *TemporalStarter {
	queue := strings.TrimSpace(taskQueue)
	if queue == "" {
		queue = TaskQueue
	}
	return &TemporalStarter{client: c, store: store, taskQueue: queue}
}

func (s *TemporalStarter) StartManual(ctx context.Context, input StartManualInput) (Admission, error) {
	if s == nil || s.store == nil {
		return Admission{}, appError(CodeBackendUnconfigured, "asset distillation backend is not configured")
	}
	admitted, replay, err := s.store.AdmitManual(ctx, input)
	if err != nil {
		return Admission{}, err
	}
	admitted.Replay = replay
	if replay || s.client == nil {
		return admitted, nil
	}
	if err := s.startWorkflow(ctx, input.Scope, admitted); err != nil {
		return Admission{}, err
	}
	_ = s.store.MarkDispatched(ctx, input.Scope.TenantID, admitted.RequestID)
	return admitted, nil
}

func (s *TemporalStarter) StartDispatched(ctx context.Context, scope Scope, requestID, runID, triggerKind string) error {
	if s == nil || s.client == nil {
		return appError(CodeBackendUnconfigured, "asset distillation temporal client is not configured")
	}
	admitted := Admission{
		RunID: runID, RequestID: requestID, ProjectID: scope.ProjectID,
		WorkflowType: WorkflowType, ModuleKey: ModuleKey, Status: "queued", TriggerKind: triggerKind,
	}
	if err := s.startWorkflow(ctx, scope, admitted); err != nil {
		return err
	}
	return s.store.MarkDispatched(ctx, scope.TenantID, requestID)
}

func (s *TemporalStarter) startWorkflow(ctx context.Context, scope Scope, admitted Admission) error {
	temporalID := WorkflowType + "_" + admitted.RunID
	payload := map[string]any{
		"context": map[string]any{
			"tenant_id": scope.TenantID, "project_id": admitted.ProjectID, "run_id": admitted.RunID,
			"workflow_type": WorkflowType, "actor_user_id": scope.ActorUserID,
			"module_key": ModuleKey, "trace_id": "trace_" + admitted.RunID,
			"permissions": map[string][]string{ModuleKey: {"run"}},
		},
		"request_id":   admitted.RequestID,
		"trigger_kind": admitted.TriggerKind,
	}
	_, err := s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: time.Hour,
		WorkflowRunTimeout:       time.Hour,
	}, WorkflowName, payload)
	if err != nil {
		if strings.Contains(err.Error(), "already started") || strings.Contains(err.Error(), "WorkflowExecutionAlreadyStarted") {
			return nil
		}
		return appError(CodeStartFailed, "manuscript asset distillation workflow failed to start")
	}
	return nil
}

type Dispatcher struct {
	store   Store
	starter Starter
}

func NewDispatcher(store Store, starter Starter) *Dispatcher {
	return &Dispatcher{store: store, starter: starter}
}

func (d *Dispatcher) Tick(ctx context.Context, limit int) (int, error) {
	if d == nil || d.store == nil || d.starter == nil {
		return 0, nil
	}
	items, err := d.store.ClaimPendingDispatch(ctx, limit)
	if err != nil || len(items) == 0 {
		return 0, err
	}
	started := 0
	var firstErr error
	for _, item := range items {
		scope := Scope{TenantID: item.TenantID, ProjectID: item.ProjectID}
		err := d.starter.StartDispatched(ctx, scope, item.RequestID, item.RunID, item.TriggerKind)
		if err != nil {
			next := time.Now().UTC().Add(time.Duration(min(item.Attempt+1, 6)) * 30 * time.Second)
			if markErr := d.store.MarkDispatchRetry(ctx, item.TenantID, item.RequestID, "DISPATCH_START_FAILED", item.Attempt+1, next); markErr != nil && firstErr == nil {
				firstErr = markErr
			}
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		started++
	}
	return started, firstErr
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// Enqueuer adapts SQL store + starter for post-adoption outbox admission.
type Enqueuer struct {
	store   *SQLStore
	starter Starter
}

func NewEnqueuer(store *SQLStore, starter Starter) *Enqueuer {
	return &Enqueuer{store: store, starter: starter}
}

type AfterAdoptionInput struct {
	TenantID, ProjectID, ActorUserID, RequestID string
	BlockID, ChapterID, SceneID                 string
}

// EnqueueAfterAdoptionInTx inserts the durable outbox row on the open adoption transaction.
// Temporal dispatch remains best-effort via the outbox dispatcher after commit.
func (e *Enqueuer) EnqueueAfterAdoptionInTx(ctx context.Context, rows workflows.DraftAdoptionSQLRows, input workflows.DraftAdoptionInput, result workflows.DraftAdoptionResult) error {
	if e == nil || e.store == nil || rows == nil {
		return nil
	}
	projectID := strings.TrimSpace(result.ProjectID)
	blockID := strings.TrimSpace(result.BlockID)
	if projectID == "" || blockID == "" {
		return nil
	}
	scope := Scope{
		TenantID: strings.TrimSpace(input.TenantID), ProjectID: projectID,
		ActorUserID: strings.TrimSpace(input.ActorUserID), RequestID: strings.TrimSpace(input.RequestID),
	}
	settings, err := loadSettingsOn(ctx, rows, scope)
	if err != nil {
		return err
	}
	if settings.TriggerMode != "after_adoption" {
		return nil
	}
	src, err := resolveActiveBlockSourceOn(ctx, rows, scope, blockID)
	if err != nil {
		return err
	}
	_, _, err = e.store.EnqueueFromSourcesOn(ctx, rows, scope, "draft_adoption", []SourceBlock{src})
	return err
}

// EnqueueAfterAdoption remains for compatibility tests and non-transactional callers.
func (e *Enqueuer) EnqueueAfterAdoption(ctx context.Context, input AfterAdoptionInput) error {
	if e == nil || e.store == nil {
		return appError(CodeBackendUnconfigured, "asset distillation enqueuer is not configured")
	}
	scope := Scope{
		TenantID: input.TenantID, ProjectID: input.ProjectID,
		ActorUserID: input.ActorUserID, RequestID: input.RequestID,
	}
	settings, err := e.store.GetSettings(ctx, scope)
	if err != nil {
		return err
	}
	if settings.TriggerMode != "after_adoption" {
		return nil
	}
	sources, err := e.store.resolveManualSources(ctx, StartManualInput{
		Scope: scope, BlockIDs: []string{input.BlockID},
	})
	if err != nil {
		return err
	}
	if len(sources) == 0 {
		return appError(CodeNotFound, "active manuscript sources were not found")
	}
	admission, replay, err := e.store.EnqueueFromSources(ctx, scope, "draft_adoption", sources)
	if err != nil || replay || e.starter == nil {
		return err
	}
	return e.starter.StartDispatched(ctx, scope, admission.RequestID, admission.RunID, admission.TriggerKind)
}

func resolveActiveBlockSourceOn(ctx context.Context, q sqlQuerier, scope Scope, blockID string) (SourceBlock, error) {
	var src SourceBlock
	var content string
	err := q.QueryRowContext(ctx, `SELECT block_id::text, version, content_text,
  COALESCE(chapter_id::text,''), COALESCE(scene_id::text,'')
FROM manuscript_blocks
WHERE tenant_id=$1::uuid AND project_id=$2::uuid AND block_id=$3::uuid AND status='active'`,
		scope.TenantID, scope.ProjectID, blockID).Scan(&src.BlockID, &src.BlockVersion, &content, &src.ChapterID, &src.SceneID)
	if err == sql.ErrNoRows {
		return SourceBlock{}, appError(CodeNotFound, "active manuscript sources were not found")
	}
	if err != nil {
		return SourceBlock{}, err
	}
	src.ContentSHA = contentSHA256(content)
	return src, nil
}
