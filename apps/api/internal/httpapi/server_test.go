package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/assets"
	"mirofish-novel/apps/api/internal/characterconsole"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/projectoverview"
	"mirofish-novel/apps/api/internal/projectreadiness"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/storygraph"
	"mirofish-novel/apps/api/internal/traces"
	"mirofish-novel/apps/api/internal/workflows"
	"mirofish-novel/apps/api/internal/worldline"
)

type recordingStarter struct {
	input workflows.StartWriterRunInput
	err   error
}

func (s *recordingStarter) StartWriterRun(ctx context.Context, input workflows.StartWriterRunInput) (workflows.WriterRun, error) {
	s.input = input
	if s.err != nil {
		return workflows.WriterRun{}, s.err
	}
	return workflows.WriterRun{
		RunID:     "run_123",
		TraceID:   "trace_123",
		ProjectID: input.ProjectID,
		Status:    "queued",
	}, nil
}

type recordingWriterReader struct {
	input workflows.GetWriterRunInput
	run   workflows.WriterRun
	err   error
}

func (r *recordingWriterReader) GetWriterRun(ctx context.Context, input workflows.GetWriterRunInput) (workflows.WriterRun, error) {
	r.input = input
	if r.err != nil {
		return workflows.WriterRun{}, r.err
	}
	return r.run, nil
}

type recordingWorkflowReader struct {
	input workflows.GetWorkflowRunInput
	run   workflows.WorkflowRun
	err   error
}

func (r *recordingWorkflowReader) GetWorkflowRun(ctx context.Context, input workflows.GetWorkflowRunInput) (workflows.WorkflowRun, error) {
	r.input = input
	if r.err != nil {
		return workflows.WorkflowRun{}, r.err
	}
	return r.run, nil
}

type recordingSeedRunReader struct {
	listInput workflows.ListSeedRunsInput
	getInput  workflows.GetSeedRunInput
	runs      []workflows.WorkflowRun
	run       workflows.WorkflowRun
	listErr   error
	getErr    error
}

func (r *recordingSeedRunReader) ListSeedRuns(ctx context.Context, input workflows.ListSeedRunsInput) ([]workflows.WorkflowRun, error) {
	r.listInput = input
	if r.listErr != nil {
		return nil, r.listErr
	}
	return r.runs, nil
}

func (r *recordingSeedRunReader) GetSeedRun(ctx context.Context, input workflows.GetSeedRunInput) (workflows.WorkflowRun, error) {
	r.getInput = input
	if r.getErr != nil {
		return workflows.WorkflowRun{}, r.getErr
	}
	return r.run, nil
}

type recordingProjectReadinessReader struct {
	input    projectreadiness.GetLatestSnapshotInput
	snapshot projectreadiness.Snapshot
	err      error
}

func (r *recordingProjectReadinessReader) GetLatestSnapshot(ctx context.Context, input projectreadiness.GetLatestSnapshotInput) (projectreadiness.Snapshot, error) {
	r.input = input
	if r.err != nil {
		return projectreadiness.Snapshot{}, r.err
	}
	return r.snapshot, nil
}

type recordingProjectOverviewReader struct {
	input    projectoverview.GetProjectOverviewInput
	overview projectoverview.Overview
	err      error
}

func (r *recordingProjectOverviewReader) GetProjectOverview(ctx context.Context, input projectoverview.GetProjectOverviewInput) (projectoverview.Overview, error) {
	r.input = input
	if r.err != nil {
		return projectoverview.Overview{}, r.err
	}
	return r.overview, nil
}

type recordingWriterEventReader struct {
	input  workflows.ListWriterEventsInput
	events []workflows.WriterEvent
	err    error
}

func (r *recordingWriterEventReader) ListWriterEvents(ctx context.Context, input workflows.ListWriterEventsInput) ([]workflows.WriterEvent, error) {
	r.input = input
	if r.err != nil {
		return nil, r.err
	}
	return r.events, nil
}

type recordingWorkflowEventReader struct {
	input  workflows.ListWorkflowEventsInput
	events []workflows.WorkflowEvent
	err    error
}

func (r *recordingWorkflowEventReader) ListWorkflowEvents(ctx context.Context, input workflows.ListWorkflowEventsInput) ([]workflows.WorkflowEvent, error) {
	r.input = input
	if r.err != nil {
		return nil, r.err
	}
	return r.events, nil
}

type recordingWriterCanceller struct {
	input workflows.CancelWriterRunInput
	err   error
}

func (c *recordingWriterCanceller) CancelWriterRun(ctx context.Context, input workflows.CancelWriterRunInput) (workflows.WriterRunCancellation, error) {
	c.input = input
	if c.err != nil {
		return workflows.WriterRunCancellation{}, c.err
	}
	return workflows.WriterRunCancellation{
		RunID:  input.RunID,
		Status: "cancel_requested",
	}, nil
}

type recordingWorkflowCanceller struct {
	input  workflows.CancelWorkflowRunInput
	err    error
	called bool
}

func (c *recordingWorkflowCanceller) CancelWorkflowRun(ctx context.Context, input workflows.CancelWorkflowRunInput) (workflows.WorkflowRunCancellation, error) {
	c.input = input
	c.called = true
	if c.err != nil {
		return workflows.WorkflowRunCancellation{}, c.err
	}
	return workflows.WorkflowRunCancellation{
		RunID:  input.RunID,
		Status: "cancel_requested",
	}, nil
}

type recordingWorkflowRetrier struct {
	input  workflows.RetryWorkflowRunInput
	err    error
	called bool
}

func (r *recordingWorkflowRetrier) RetryWorkflowRun(ctx context.Context, input workflows.RetryWorkflowRunInput) (workflows.WorkflowRunRetry, error) {
	r.input = input
	r.called = true
	if r.err != nil {
		return workflows.WorkflowRunRetry{}, r.err
	}
	return workflows.WorkflowRunRetry{
		RunID:  input.RunID,
		Status: "retry_requested",
	}, nil
}

type recordingSeedStarter struct {
	input workflows.StartSeedRunInput
	err   error
}

func (s *recordingSeedStarter) StartSeedRun(ctx context.Context, input workflows.StartSeedRunInput) (workflows.SeedRun, error) {
	s.input = input
	if s.err != nil {
		return workflows.SeedRun{}, s.err
	}
	return workflows.SeedRun{
		RunID:        "seed-run-123",
		ProjectID:    input.ProjectID,
		WorkflowType: workflows.SeedWorkflowType,
		Status:       "queued",
	}, nil
}

type recordingStoryGraphBuildStarter struct {
	input workflows.StartStoryGraphBuildInput
	err   error
}

func (s *recordingStoryGraphBuildStarter) StartStoryGraphBuild(ctx context.Context, input workflows.StartStoryGraphBuildInput) (workflows.StoryGraphBuildRun, error) {
	s.input = input
	if s.err != nil {
		return workflows.StoryGraphBuildRun{}, s.err
	}
	return workflows.StoryGraphBuildRun{
		RunID:        "story-graph-run-123",
		ProjectID:    input.ProjectID,
		WorkflowType: workflows.StoryGraphBuildWorkflowType,
		Status:       "queued",
	}, nil
}

type recordingStoryGraphBondGenerationStarter struct {
	input workflows.StartStoryGraphBondGenerationInput
	err   error
}

func (s *recordingStoryGraphBondGenerationStarter) StartStoryGraphBondGeneration(ctx context.Context, input workflows.StartStoryGraphBondGenerationInput) (workflows.StoryGraphBondGenerationRun, error) {
	s.input = input
	if s.err != nil {
		return workflows.StoryGraphBondGenerationRun{}, s.err
	}
	return workflows.StoryGraphBondGenerationRun{
		RunID:        "story-graph-bond-run-123",
		ProjectID:    input.ProjectID,
		WorkflowType: workflows.StoryGraphBondGenerationWorkflowType,
		Status:       "queued",
	}, nil
}

type recordingStoryGraphReader struct {
	input         storygraph.GetCurrentInput
	viewInput     storygraph.GetViewInput
	nodeInput     storygraph.GetNodeInput
	edgeInput     storygraph.GetEdgeInput
	evidenceInput storygraph.GetEvidenceInput
	layoutInput   storygraph.GetLayoutInput
	clustersInput storygraph.ListClustersInput
	current       storygraph.CurrentSnapshot
	view          storygraph.GraphView
	node          storygraph.GraphNodeDetail
	edge          storygraph.GraphEdgeDetail
	evidence      storygraph.GraphEvidence
	layout        storygraph.GraphLayout
	clusters      storygraph.GraphClusters
	err           error
}

func (r *recordingStoryGraphReader) GetCurrentSnapshot(ctx context.Context, input storygraph.GetCurrentInput) (storygraph.CurrentSnapshot, error) {
	r.input = input
	if r.err != nil {
		return storygraph.CurrentSnapshot{}, r.err
	}
	return r.current, nil
}

func (r *recordingStoryGraphReader) GetView(ctx context.Context, input storygraph.GetViewInput) (storygraph.GraphView, error) {
	r.viewInput = input
	if r.err != nil {
		return storygraph.GraphView{}, r.err
	}
	return r.view, nil
}

func (r *recordingStoryGraphReader) GetNode(ctx context.Context, input storygraph.GetNodeInput) (storygraph.GraphNodeDetail, error) {
	r.nodeInput = input
	if r.err != nil {
		return storygraph.GraphNodeDetail{}, r.err
	}
	return r.node, nil
}

func (r *recordingStoryGraphReader) GetEdge(ctx context.Context, input storygraph.GetEdgeInput) (storygraph.GraphEdgeDetail, error) {
	r.edgeInput = input
	if r.err != nil {
		return storygraph.GraphEdgeDetail{}, r.err
	}
	return r.edge, nil
}

func (r *recordingStoryGraphReader) GetEvidence(ctx context.Context, input storygraph.GetEvidenceInput) (storygraph.GraphEvidence, error) {
	r.evidenceInput = input
	if r.err != nil {
		return storygraph.GraphEvidence{}, r.err
	}
	return r.evidence, nil
}

func (r *recordingStoryGraphReader) GetLayout(ctx context.Context, input storygraph.GetLayoutInput) (storygraph.GraphLayout, error) {
	r.layoutInput = input
	if r.err != nil {
		return storygraph.GraphLayout{}, r.err
	}
	return r.layout, nil
}

func (r *recordingStoryGraphReader) ListClusters(ctx context.Context, input storygraph.ListClustersInput) (storygraph.GraphClusters, error) {
	r.clustersInput = input
	if r.err != nil {
		return storygraph.GraphClusters{}, r.err
	}
	return r.clusters, nil
}

type recordingWorldlineSavedPathReader struct {
	input worldline.ListSavedPathsInput
	paths []worldline.SavedPathRecord
	err   error
}

func (r *recordingWorldlineSavedPathReader) ListSavedPaths(ctx context.Context, input worldline.ListSavedPathsInput) ([]worldline.SavedPathRecord, error) {
	r.input = input
	if r.err != nil {
		return nil, r.err
	}
	return r.paths, nil
}

type recordingWorldlineSavedPathStore struct {
	input worldline.CreateSavedPathInput
	path  worldline.SavedPathRecord
	err   error
}

func (s *recordingWorldlineSavedPathStore) CreateSavedPath(ctx context.Context, input worldline.CreateSavedPathInput) (worldline.SavedPathRecord, error) {
	s.input = input
	if s.err != nil {
		return worldline.SavedPathRecord{}, s.err
	}
	return s.path, nil
}

type recordingWorldlineSessionStarter struct {
	input worldline.StartSessionInput
	run   worldline.SessionRun
	err   error
}

func (s *recordingWorldlineSessionStarter) StartSession(ctx context.Context, input worldline.StartSessionInput) (worldline.SessionRun, error) {
	s.input = input
	if s.err != nil {
		return worldline.SessionRun{}, s.err
	}
	return s.run, nil
}

type recordingWorldlineStepStarter struct {
	input worldline.StartStepInput
	run   worldline.StepRun
	err   error
}

func (s *recordingWorldlineStepStarter) StartStep(ctx context.Context, input worldline.StartStepInput) (worldline.StepRun, error) {
	s.input = input
	if s.err != nil {
		return worldline.StepRun{}, s.err
	}
	return s.run, nil
}

type recordingWorldlineSessionReader struct {
	listInput worldline.ListSessionsInput
	getInput  worldline.GetSessionInput
	sessions  []worldline.SessionRecord
	session   worldline.SessionRecord
	err       error
}

func (r *recordingWorldlineSessionReader) ListSessions(ctx context.Context, input worldline.ListSessionsInput) ([]worldline.SessionRecord, error) {
	r.listInput = input
	if r.err != nil {
		return nil, r.err
	}
	return r.sessions, nil
}

func (r *recordingWorldlineSessionReader) GetSession(ctx context.Context, input worldline.GetSessionInput) (worldline.SessionRecord, error) {
	r.getInput = input
	if r.err != nil {
		return worldline.SessionRecord{}, r.err
	}
	return r.session, nil
}

type recordingWorldlineTimelineReader struct {
	input  worldline.ListTimelineInput
	events []worldline.TimelineEventRecord
	err    error
}

func (r *recordingWorldlineTimelineReader) ListTimeline(ctx context.Context, input worldline.ListTimelineInput) ([]worldline.TimelineEventRecord, error) {
	r.input = input
	if r.err != nil {
		return nil, r.err
	}
	return r.events, nil
}

type recordingWorldlineEventReader struct {
	input  worldline.ListEventsInput
	events []worldline.EventRecord
	err    error
}

func (r *recordingWorldlineEventReader) ListEvents(ctx context.Context, input worldline.ListEventsInput) ([]worldline.EventRecord, error) {
	r.input = input
	if r.err != nil {
		return nil, r.err
	}
	return r.events, nil
}

type recordingWorldlineEventAdoptionStore struct {
	input worldline.AdoptEventInput
	event worldline.EventRecord
	err   error
}

func (s *recordingWorldlineEventAdoptionStore) AdoptEvent(ctx context.Context, input worldline.AdoptEventInput) (worldline.EventRecord, error) {
	s.input = input
	if s.err != nil {
		return worldline.EventRecord{}, s.err
	}
	return s.event, nil
}

type recordingWorldlineEventMutationStore struct {
	input worldline.UpdateEventInput
	event worldline.EventRecord
	err   error
}

func (s *recordingWorldlineEventMutationStore) UpdateEvent(ctx context.Context, input worldline.UpdateEventInput) (worldline.EventRecord, error) {
	s.input = input
	if s.err != nil {
		return worldline.EventRecord{}, s.err
	}
	return s.event, nil
}

type recordingWorldlineVariableStore struct {
	input    worldline.InjectVariableInput
	variable worldline.VariableRecord
	err      error
}

func (s *recordingWorldlineVariableStore) InjectVariable(ctx context.Context, input worldline.InjectVariableInput) (worldline.VariableRecord, error) {
	s.input = input
	if s.err != nil {
		return worldline.VariableRecord{}, s.err
	}
	return s.variable, nil
}

type recordingWorldlinePreparationStore struct {
	createInput     worldline.CreatePreparationInput
	getInput        worldline.GetPreparationInput
	agentsInput     worldline.ListPreparedAgentsInput
	preparation     worldline.PreparationRecord
	agents          []worldline.PreparedAgentRecord
	createErr       error
	getErr          error
	agentsErr       error
	createWasCalled bool
}

func (s *recordingWorldlinePreparationStore) CreatePreparation(ctx context.Context, input worldline.CreatePreparationInput) (worldline.PreparationRecord, error) {
	s.createInput = input
	s.createWasCalled = true
	if s.createErr != nil {
		return worldline.PreparationRecord{}, s.createErr
	}
	return s.preparation, nil
}

func (s *recordingWorldlinePreparationStore) GetPreparation(ctx context.Context, input worldline.GetPreparationInput) (worldline.PreparationRecord, error) {
	s.getInput = input
	if s.getErr != nil {
		return worldline.PreparationRecord{}, s.getErr
	}
	return s.preparation, nil
}

func (s *recordingWorldlinePreparationStore) ListPreparedAgents(ctx context.Context, input worldline.ListPreparedAgentsInput) ([]worldline.PreparedAgentRecord, error) {
	s.agentsInput = input
	if s.agentsErr != nil {
		return nil, s.agentsErr
	}
	return s.agents, nil
}

type recordingCharacterConsoleStore struct {
	createInput characterconsole.CreateInteractionInput
	listInput   characterconsole.ListInteractionsInput
	getInput    characterconsole.GetInteractionInput
	updateInput characterconsole.UpdateInteractionStatusInput
	appendInput characterconsole.AppendTurnInput
	turnsInput  characterconsole.ListTurnsInput

	interaction  characterconsole.InteractionRecord
	interactions []characterconsole.InteractionRecord
	turn         characterconsole.TurnRecord
	turns        []characterconsole.TurnRecord
	err          error
	getErr       error
	turnsErr     error
}

func (s *recordingCharacterConsoleStore) CreateInteraction(ctx context.Context, input characterconsole.CreateInteractionInput) (characterconsole.InteractionRecord, error) {
	s.createInput = input
	if s.err != nil {
		return characterconsole.InteractionRecord{}, s.err
	}
	return s.interaction, nil
}

func (s *recordingCharacterConsoleStore) ListInteractions(ctx context.Context, input characterconsole.ListInteractionsInput) ([]characterconsole.InteractionRecord, error) {
	s.listInput = input
	if s.err != nil {
		return nil, s.err
	}
	return s.interactions, nil
}

func (s *recordingCharacterConsoleStore) GetInteraction(ctx context.Context, input characterconsole.GetInteractionInput) (characterconsole.InteractionRecord, error) {
	s.getInput = input
	if s.getErr != nil {
		return characterconsole.InteractionRecord{}, s.getErr
	}
	if s.err != nil {
		return characterconsole.InteractionRecord{}, s.err
	}
	return s.interaction, nil
}

func (s *recordingCharacterConsoleStore) UpdateInteractionStatus(ctx context.Context, input characterconsole.UpdateInteractionStatusInput) (characterconsole.InteractionRecord, error) {
	s.updateInput = input
	if s.err != nil {
		return characterconsole.InteractionRecord{}, s.err
	}
	return s.interaction, nil
}

func (s *recordingCharacterConsoleStore) AppendTurn(ctx context.Context, input characterconsole.AppendTurnInput) (characterconsole.TurnRecord, error) {
	s.appendInput = input
	if s.err != nil {
		return characterconsole.TurnRecord{}, s.err
	}
	return s.turn, nil
}

func (s *recordingCharacterConsoleStore) ListTurns(ctx context.Context, input characterconsole.ListTurnsInput) ([]characterconsole.TurnRecord, error) {
	s.turnsInput = input
	if s.turnsErr != nil {
		return nil, s.turnsErr
	}
	if s.err != nil {
		return nil, s.err
	}
	return s.turns, nil
}

type recordingSourceFileStore struct {
	createInput   sourcefiles.CreateInput
	completeInput sourcefiles.CompleteInput
	listInput     sourcefiles.ListInput
	validateInput sourcefiles.ValidateInput
	objectInput   sourcefiles.GetUploadObjectInput
	created       sourcefiles.Record
	completed     sourcefiles.Record
	validated     sourcefiles.ValidatedSourceFile
	object        sourcefiles.ObjectWriteInput
	items         []sourcefiles.Record
	validateErr   error
	err           error
}

func (s *recordingSourceFileStore) CreateSourceFile(ctx context.Context, input sourcefiles.CreateInput) (sourcefiles.Record, error) {
	s.createInput = input
	if s.err != nil {
		return sourcefiles.Record{}, s.err
	}
	if s.created.FileID != "" {
		return s.created, nil
	}
	return sourcefiles.Record{
		FileID:      "file-123",
		UploadID:    "upload-123",
		ProjectID:   input.ProjectID,
		Filename:    input.Filename,
		MimeType:    input.MimeType,
		SizeBytes:   input.SizeBytes,
		SHA256:      input.SHA256,
		Purpose:     input.Purpose,
		ParseStatus: "pending",
		CreatedAt:   "2026-07-04T10:00:00Z",
	}, nil
}

func (s *recordingSourceFileStore) CompleteUpload(ctx context.Context, input sourcefiles.CompleteInput) (sourcefiles.Record, error) {
	s.completeInput = input
	if s.err != nil {
		return sourcefiles.Record{}, s.err
	}
	if s.completed.FileID != "" {
		return s.completed, nil
	}
	return sourcefiles.Record{
		FileID:      "file-123",
		UploadID:    input.UploadID,
		ProjectID:   "project-123",
		Filename:    "novel.md",
		MimeType:    "text/markdown",
		SizeBytes:   2048,
		SHA256:      "abc123",
		Purpose:     "seed",
		ParseStatus: "uploaded",
		CreatedAt:   "2026-07-04T10:00:00Z",
	}, nil
}

func (s *recordingSourceFileStore) ListSourceFiles(ctx context.Context, input sourcefiles.ListInput) ([]sourcefiles.Record, error) {
	s.listInput = input
	if s.err != nil {
		return nil, s.err
	}
	return s.items, nil
}

func (s *recordingSourceFileStore) ValidateSourceFile(ctx context.Context, input sourcefiles.ValidateInput) (sourcefiles.ValidatedSourceFile, error) {
	s.validateInput = input
	if s.validateErr != nil {
		return sourcefiles.ValidatedSourceFile{}, s.validateErr
	}
	if s.validated.FileID != "" {
		return s.validated, nil
	}
	return sourcefiles.ValidatedSourceFile{
		FileID:      "file-123",
		UploadID:    input.UploadID,
		ProjectID:   input.ProjectID,
		ObjectKey:   "projects/project-123/source-files/upload-123/book.txt",
		Filename:    "book.txt",
		MimeType:    "text/plain",
		SizeBytes:   2048,
		SHA256:      "abc123",
		ParseStatus: "uploaded",
	}, nil
}

type recordingAssetReader struct {
	listInput     assets.ListAssetsInput
	getInput      assets.GetAssetInput
	facetsInput   assets.ListFacetsInput
	searchInput   assets.SearchAssetsInput
	assets        []assets.Record
	asset         assets.Record
	facets        assets.Facets
	searchResults []assets.SearchRecord
	err           error
}

type recordingArchiveMemoryReader struct {
	memoriesInput assets.ListArchiveMemoriesInput
	eventsInput   assets.ListArchiveMemoryEventsInput
	memories      []assets.ArchiveMemoryRecord
	events        []assets.ArchiveMemoryEventRecord
	err           error
}

type recordingAssetAdoptionStore struct {
	input  assets.AdoptAssetInput
	record assets.Record
	err    error
}

type recordingArchiveMemoryReviewStore struct {
	adoptInput  assets.ArchiveMemoryReviewInput
	rejectInput assets.ArchiveMemoryReviewInput
	record      assets.ArchiveMemoryRecord
	err         error
}

type recordingAssetMutationStore struct {
	createInput assets.CreateAssetInput
	patchInput  assets.PatchAssetInput
	deleteInput assets.DeleteAssetInput
	record      assets.Record
	deleted     assets.DeleteResult
	err         error
}

type recordingAssetBulkActionStore struct {
	input  assets.BulkActionInput
	result assets.BulkActionResult
	err    error
}

func (r *recordingAssetReader) ListAssets(ctx context.Context, input assets.ListAssetsInput) ([]assets.Record, error) {
	r.listInput = input
	if r.err != nil {
		return nil, r.err
	}
	return r.assets, nil
}

func (r *recordingAssetReader) GetAsset(ctx context.Context, input assets.GetAssetInput) (assets.Record, error) {
	r.getInput = input
	if r.err != nil {
		return assets.Record{}, r.err
	}
	return r.asset, nil
}

func (r *recordingAssetReader) ListFacets(ctx context.Context, input assets.ListFacetsInput) (assets.Facets, error) {
	r.facetsInput = input
	if r.err != nil {
		return assets.Facets{}, r.err
	}
	return r.facets, nil
}

func (r *recordingAssetReader) SearchAssets(ctx context.Context, input assets.SearchAssetsInput) ([]assets.SearchRecord, error) {
	r.searchInput = input
	if r.err != nil {
		return nil, r.err
	}
	return r.searchResults, nil
}

func (r *recordingArchiveMemoryReader) ListMemories(ctx context.Context, input assets.ListArchiveMemoriesInput) ([]assets.ArchiveMemoryRecord, error) {
	r.memoriesInput = input
	if r.err != nil {
		return nil, r.err
	}
	return r.memories, nil
}

func (r *recordingArchiveMemoryReader) ListMemoryEvents(ctx context.Context, input assets.ListArchiveMemoryEventsInput) ([]assets.ArchiveMemoryEventRecord, error) {
	r.eventsInput = input
	if r.err != nil {
		return nil, r.err
	}
	return r.events, nil
}

func (s *recordingAssetAdoptionStore) AdoptAsset(ctx context.Context, input assets.AdoptAssetInput) (assets.Record, error) {
	s.input = input
	if s.err != nil {
		return assets.Record{}, s.err
	}
	if s.record.AssetID != "" {
		return s.record, nil
	}
	return assets.Record{
		AssetID:    input.AssetID,
		ProjectID:  "project-123",
		Scope:      "project",
		AssetType:  "world_rule",
		Category:   "world",
		Lifecycle:  input.TargetLifecycle,
		Title:      "灵气守恒",
		Summary:    "公开摘要",
		SourceKind: "asset_ingestion",
		SourceRef:  "asset-ingestion:run-1:1",
		Enabled:    true,
		Pinned:     false,
		Tags:       []string{"world"},
		Payload:    map[string]any{"statement": "公开规则"},
		CreatedAt:  "2026-07-04T00:00:00Z",
		UpdatedAt:  "2026-07-04T00:01:00Z",
	}, nil
}

func (s *recordingArchiveMemoryReviewStore) AdoptMemory(ctx context.Context, input assets.ArchiveMemoryReviewInput) (assets.ArchiveMemoryRecord, error) {
	s.adoptInput = input
	if s.err != nil {
		return assets.ArchiveMemoryRecord{}, s.err
	}
	if s.record.MemoryID != "" {
		return s.record, nil
	}
	return assets.ArchiveMemoryRecord{
		MemoryID:   input.MemoryID,
		AssetID:    "asset-1",
		ProjectID:  input.ProjectID,
		MemoryType: "relationship",
		Status:     "canon",
		Summary:    "公开记忆摘要",
		Payload:    map[string]any{"relationship_id": "rel-1"},
		SourceKind: "asset_ingestion",
		SourceRef:  "run-1:1",
		Enabled:    true,
		CreatedAt:  "2026-07-05T00:00:00Z",
		UpdatedAt:  "2026-07-05T00:01:00Z",
	}, nil
}

func (s *recordingArchiveMemoryReviewStore) RejectMemory(ctx context.Context, input assets.ArchiveMemoryReviewInput) (assets.ArchiveMemoryRecord, error) {
	s.rejectInput = input
	if s.err != nil {
		return assets.ArchiveMemoryRecord{}, s.err
	}
	if s.record.MemoryID != "" {
		return s.record, nil
	}
	return assets.ArchiveMemoryRecord{
		MemoryID:   input.MemoryID,
		AssetID:    "asset-1",
		ProjectID:  input.ProjectID,
		MemoryType: "relationship",
		Status:     "rejected",
		Summary:    "公开记忆摘要",
		Payload:    map[string]any{"relationship_id": "rel-1"},
		SourceKind: "asset_ingestion",
		SourceRef:  "run-1:1",
		Enabled:    false,
		CreatedAt:  "2026-07-05T00:00:00Z",
		UpdatedAt:  "2026-07-05T00:01:00Z",
	}, nil
}

func (s *recordingAssetMutationStore) CreateAsset(ctx context.Context, input assets.CreateAssetInput) (assets.Record, error) {
	s.createInput = input
	if s.err != nil {
		return assets.Record{}, s.err
	}
	if s.record.AssetID != "" {
		return s.record, nil
	}
	return assets.Record{
		AssetID:    "asset-created",
		ProjectID:  input.ProjectID,
		Scope:      input.Scope,
		AssetType:  input.AssetType,
		Category:   input.Category,
		Lifecycle:  input.Lifecycle,
		Title:      input.Title,
		Summary:    input.Summary,
		SourceKind: input.SourceKind,
		SourceRef:  input.SourceRef,
		Enabled:    true,
		Pinned:     false,
		Tags:       input.Tags,
		Payload:    input.Payload,
		CreatedAt:  "2026-07-04T00:00:00Z",
		UpdatedAt:  "2026-07-04T00:00:00Z",
	}, nil
}

func (s *recordingAssetMutationStore) PatchAsset(ctx context.Context, input assets.PatchAssetInput) (assets.Record, error) {
	s.patchInput = input
	if s.err != nil {
		return assets.Record{}, s.err
	}
	if s.record.AssetID != "" {
		return s.record, nil
	}
	return assets.Record{
		AssetID:    input.AssetID,
		ProjectID:  "project-123",
		Scope:      "project",
		AssetType:  "note",
		Category:   "material",
		Lifecycle:  "archived",
		Title:      derefString(input.Title),
		Summary:    derefString(input.Summary),
		SourceKind: "manual",
		SourceRef:  "req-create",
		Enabled:    false,
		Pinned:     true,
		Tags:       derefStringSlice(input.Tags),
		Payload:    derefMap(input.Payload),
		CreatedAt:  "2026-07-04T00:00:00Z",
		UpdatedAt:  "2026-07-04T00:01:00Z",
	}, nil
}

func (s *recordingAssetMutationStore) DeleteAsset(ctx context.Context, input assets.DeleteAssetInput) (assets.DeleteResult, error) {
	s.deleteInput = input
	if s.err != nil {
		return assets.DeleteResult{}, s.err
	}
	if s.deleted.AssetID != "" {
		return s.deleted, nil
	}
	return assets.DeleteResult{AssetID: input.AssetID, ProjectID: "project-123", Deleted: true}, nil
}

func (s *recordingAssetBulkActionStore) ApplyBulkAction(ctx context.Context, input assets.BulkActionInput) (assets.BulkActionResult, error) {
	s.input = input
	if s.err != nil {
		return assets.BulkActionResult{}, s.err
	}
	if s.result.Status != "" {
		return s.result, nil
	}
	return assets.BulkActionResult{
		ProjectID:    input.ProjectID,
		Action:       input.Action,
		Status:       "accepted",
		MatchedCount: len(input.AssetIDs),
		UpdatedCount: len(input.AssetIDs),
	}, nil
}

type recordingAssetIngestionStarter struct {
	input workflows.StartAssetIngestionInput
	run   workflows.AssetIngestionRun
	err   error
}

func (s *recordingAssetIngestionStarter) StartAssetIngestion(ctx context.Context, input workflows.StartAssetIngestionInput) (workflows.AssetIngestionRun, error) {
	s.input = input
	if s.err != nil {
		return workflows.AssetIngestionRun{}, s.err
	}
	if s.run.RunID != "" {
		return s.run, nil
	}
	return workflows.AssetIngestionRun{
		RunID:        "asset-ingestion-run-123",
		ProjectID:    input.ProjectID,
		WorkflowType: workflows.AssetIngestionWorkflowType,
		Status:       "queued",
	}, nil
}

type recordingAssetIngestionReader struct {
	input workflows.GetAssetIngestionInput
	run   workflows.WorkflowRun
	err   error
}

func (r *recordingAssetIngestionReader) GetAssetIngestion(ctx context.Context, input workflows.GetAssetIngestionInput) (workflows.WorkflowRun, error) {
	r.input = input
	if r.err != nil {
		return workflows.WorkflowRun{}, r.err
	}
	return r.run, nil
}

type recordingStyleExtractionStarter struct {
	input workflows.StartStyleExtractionInput
	run   workflows.StyleExtractionRun
	err   error
}

func (s *recordingStyleExtractionStarter) StartStyleExtraction(ctx context.Context, input workflows.StartStyleExtractionInput) (workflows.StyleExtractionRun, error) {
	s.input = input
	if s.err != nil {
		return workflows.StyleExtractionRun{}, s.err
	}
	if s.run.RunID != "" {
		return s.run, nil
	}
	return workflows.StyleExtractionRun{
		RunID:        "style-extraction-run-123",
		ProjectID:    input.ProjectID,
		WorkflowType: workflows.StyleExtractionWorkflowType,
		Status:       "queued",
	}, nil
}

type recordingStyleExtractionReader struct {
	input workflows.GetStyleExtractionInput
	run   workflows.WorkflowRun
	err   error
}

func (r *recordingStyleExtractionReader) GetStyleExtraction(ctx context.Context, input workflows.GetStyleExtractionInput) (workflows.WorkflowRun, error) {
	r.input = input
	if r.err != nil {
		return workflows.WorkflowRun{}, r.err
	}
	return r.run, nil
}

type recordingAssetReindexStarter struct {
	input workflows.StartAssetReindexInput
	run   workflows.AssetReindexRun
	err   error
}

func (s *recordingAssetReindexStarter) StartAssetReindex(ctx context.Context, input workflows.StartAssetReindexInput) (workflows.AssetReindexRun, error) {
	s.input = input
	if s.err != nil {
		return workflows.AssetReindexRun{}, s.err
	}
	if s.run.RunID != "" {
		return s.run, nil
	}
	return workflows.AssetReindexRun{
		RunID:        "asset-reindex-run-123",
		ProjectID:    input.ProjectID,
		WorkflowType: workflows.AssetReindexWorkflowType,
		Status:       "queued",
	}, nil
}

func TestHealthzReturnsServiceStatus(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, response.Code)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["status"] != "ok" || body["service"] != "mirofish-api" {
		t.Fatalf("unexpected health body: %#v", body)
	}
}

func (s *recordingSourceFileStore) GetUploadObject(ctx context.Context, input sourcefiles.GetUploadObjectInput) (sourcefiles.ObjectWriteInput, error) {
	s.objectInput = input
	if s.err != nil {
		return sourcefiles.ObjectWriteInput{}, s.err
	}
	if s.object.ObjectKey != "" {
		return s.object, nil
	}
	return sourcefiles.ObjectWriteInput{
		TenantID:  input.TenantID,
		UploadID:  input.UploadID,
		FileID:    "file-123",
		ProjectID: "project-123",
		ObjectKey: "projects/project-123/source-files/upload-123/book.txt",
		Filename:  "book.txt",
		MimeType:  "text/plain",
		SizeBytes: int64(len("hello")),
		SHA256:    "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
	}, nil
}

type recordingSourceFileObjectWriter struct {
	input sourcefiles.ObjectWriteInput
	body  string
	err   error
}

func (w *recordingSourceFileObjectWriter) WriteObject(ctx context.Context, input sourcefiles.ObjectWriteInput, reader io.Reader) error {
	w.input = input
	body, err := io.ReadAll(reader)
	if err != nil {
		return err
	}
	w.body = string(body)
	return w.err
}

func TestUnknownRouteReturnsStableErrorEnvelope(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/missing", nil)
	request.Header.Set("X-Request-Id", "req_test")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected status %d, got %d", http.StatusNotFound, response.Code)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "NOT_FOUND" {
		t.Fatalf("unexpected error code: %#v", body)
	}
	if body.Error.RequestID != "req_test" {
		t.Fatalf("expected request id to round-trip, got %#v", body.Error.RequestID)
	}
}

func TestStartWriterRunCarriesTenantProjectAndRunContext(t *testing.T) {
	starter := &recordingStarter{}
	server := NewServer(Config{WriterStarter: starter, LLMResolver: boundWriterComposerResolver()})
	requestBody := bytes.NewBufferString(`{"mode":"draft","instruction":"写下一场谈判","options":{"asset_ids":["asset-1"]}}`)
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/writer-runs", requestBody)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req_writer")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter lost tenant/project context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req_writer" {
		t.Fatalf("starter lost actor/request context: %#v", starter.input)
	}
	if starter.input.Mode != "draft" || starter.input.Instruction != "写下一场谈判" {
		t.Fatalf("starter lost writer payload: %#v", starter.input)
	}
	if got := starter.input.Options["asset_ids"].([]any)[0]; got != "asset-1" {
		t.Fatalf("starter lost options: %#v", starter.input.Options)
	}
	resolution, ok := starter.input.Options["llm_resolution"].(map[string]any)
	if !ok {
		t.Fatalf("expected writer workflow llm resolution payload, got %#v", starter.input.Options)
	}
	if resolution["credential_ref"] != "credref-1" {
		t.Fatalf("expected internal credential ref in workflow payload, got %#v", resolution)
	}
	if _, ok := resolution["api_key"]; ok {
		t.Fatalf("workflow payload leaked api_key: %#v", resolution)
	}
	if _, ok := resolution["encrypted_api_key"]; ok {
		t.Fatalf("workflow payload leaked encrypted_api_key: %#v", resolution)
	}

	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "run_123" || body["trace_id"] != "trace_123" || body["status"] != "queued" || body["project_id"] != "project-123" {
		t.Fatalf("unexpected response body: %#v", body)
	}
}

func TestStartWriterRunSanitizesUntrustedOptionsBeforeStarter(t *testing.T) {
	starter := &recordingStarter{}
	server := NewServer(Config{WriterStarter: starter, LLMResolver: boundWriterComposerResolver()})
	requestBody := bytes.NewBufferString(`{
		"mode":"draft",
		"instruction":"写下一场谈判",
		"options":{
			"tenant_id":"evil-tenant",
			"project_id":"evil-project",
			"asset_ids":["asset-1"],
			"prompt":"private prompt",
			"body_text":"private body",
			"draft":"private draft",
			"source_material":"private source",
			"metadata":{"safe":"keep","api_key":"sk-private","tenant_id":"evil-nested"},
			"turns":[{"summary":"public summary","candidate_body":"private candidate","project_id":"evil-nested"}]
		}
	}`)
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/writer-runs", requestBody)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter trusted body tenant/project context: %#v", starter.input)
	}
	if got := starter.input.Options["asset_ids"].([]any)[0]; got != "asset-1" {
		t.Fatalf("starter lost safe options: %#v", starter.input.Options)
	}
	for _, forbidden := range []string{"tenant_id", "project_id", "prompt", "body_text", "draft", "source_material"} {
		if _, exists := starter.input.Options[forbidden]; exists {
			t.Fatalf("writer options retained forbidden field %q: %#v", forbidden, starter.input.Options)
		}
	}
	metadata, ok := starter.input.Options["metadata"].(map[string]any)
	if !ok || metadata["safe"] != "keep" {
		t.Fatalf("starter lost safe nested metadata: %#v", starter.input.Options)
	}
	for _, forbidden := range []string{"api_key", "tenant_id"} {
		if _, exists := metadata[forbidden]; exists {
			t.Fatalf("writer options retained forbidden nested field %q: %#v", forbidden, starter.input.Options)
		}
	}
	turns, ok := starter.input.Options["turns"].([]any)
	if !ok || len(turns) != 1 {
		t.Fatalf("starter lost public turn metadata: %#v", starter.input.Options)
	}
	turn, ok := turns[0].(map[string]any)
	if !ok || turn["summary"] != "public summary" {
		t.Fatalf("starter lost public turn summary: %#v", starter.input.Options)
	}
	for _, forbidden := range []string{"candidate_body", "project_id"} {
		if _, exists := turn[forbidden]; exists {
			t.Fatalf("writer options retained forbidden turn field %q: %#v", forbidden, starter.input.Options)
		}
	}
	resolution, ok := starter.input.Options["llm_resolution"].(map[string]any)
	if !ok || resolution["credential_ref"] != "credref-1" {
		t.Fatalf("expected trusted server-side llm resolution, got %#v", starter.input.Options)
	}
}

func TestStartWriterRunValidationErrorDoesNotEchoSensitiveUnknownField(t *testing.T) {
	starter := &recordingStarter{}
	server := NewServer(Config{WriterStarter: starter, LLMResolver: boundWriterComposerResolver()})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/writer-runs", strings.NewReader(`{
		"mode":"draft",
		"instruction":"写下一场谈判",
		"api_key":"sk-hidden"
	}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-writer-validation")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) ||
		!strings.Contains(body, `"message":"invalid writer run payload"`) ||
		!strings.Contains(body, `"request_id":"req-writer-validation"`) {
		t.Fatalf("expected stable writer validation failure, got %s", body)
	}
	for _, forbidden := range []string{"api_key", "sk-hidden", "prompt", "credential_ref", "draft", "manuscript"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("writer validation response leaked forbidden field/value %q: %s", forbidden, body)
		}
	}
	if starter.input.TenantID != "" {
		t.Fatalf("validation failure should stop before writer starter: %#v", starter.input)
	}
}

func TestCreateUploadCarriesTenantProjectActorAndReturnsSanitizedSourceFile(t *testing.T) {
	store := &recordingSourceFileStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	requestBody := bytes.NewBufferString(`{"tenant_id":"evil-tenant","filename":"novel.md","mime_type":"text/markdown","size_bytes":2048,"sha256":"abc123","purpose":"seed"}`)
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/uploads", requestBody)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("expected status %d, got %d: %s", http.StatusCreated, response.Code, response.Body.String())
	}
	if store.createInput.TenantID != "tenant-123" || store.createInput.ProjectID != "project-123" {
		t.Fatalf("store lost trusted tenant/project context: %#v", store.createInput)
	}
	if store.createInput.ActorUserID != "user-123" || store.createInput.Filename != "novel.md" || store.createInput.Purpose != "seed" {
		t.Fatalf("store lost upload metadata: %#v", store.createInput)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["file_id"] != "file-123" || body["upload_id"] != "upload-123" || body["project_id"] != "project-123" || body["parse_status"] != "pending" {
		t.Fatalf("unexpected upload response: %#v", body)
	}
	if _, ok := body["object_key"]; ok {
		t.Fatalf("upload response leaked object key: %#v", body)
	}
	if _, ok := body["api_key"]; ok {
		t.Fatalf("upload response leaked credential-like field: %#v", body)
	}
}

func TestCreateUploadValidationErrorDoesNotEchoSensitiveUnknownField(t *testing.T) {
	store := &recordingSourceFileStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/uploads", strings.NewReader(`{
		"filename":"novel.md",
		"mime_type":"text/markdown",
		"api_key":"sk-hidden"
	}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-upload-validation")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) ||
		!strings.Contains(body, `"message":"invalid upload payload"`) ||
		!strings.Contains(body, `"request_id":"req-upload-validation"`) {
		t.Fatalf("expected stable upload validation failure, got %s", body)
	}
	for _, forbidden := range []string{"api_key", "sk-hidden", "prompt", "credential_ref", "draft", "manuscript"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("upload validation response leaked forbidden field/value %q: %s", forbidden, body)
		}
	}
	if store.createInput.TenantID != "" {
		t.Fatalf("validation failure should stop before source file store: %#v", store.createInput)
	}
}

func TestCreateUploadRejectsUnsupportedSourceMimeBeforeStore(t *testing.T) {
	store := &recordingSourceFileStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/uploads", strings.NewReader(`{
		"filename":"notes.json",
		"mime_type":"application/json",
		"size_bytes":99,
		"sha256":"abc123",
		"purpose":"seed"
	}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-upload-mime")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("expected unsupported MIME 400, got %d: %s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) ||
		!strings.Contains(body, `"message":"invalid source MIME type"`) ||
		!strings.Contains(body, `"request_id":"req-upload-mime"`) {
		t.Fatalf("expected stable unsupported MIME validation failure, got %s", body)
	}
	if store.createInput.Filename != "" {
		t.Fatalf("unsupported source MIME should be rejected before store call: %#v", store.createInput)
	}
	for _, forbidden := range []string{"notes.json", "application/json", "api_key", "prompt", "credential_ref", "draft", "manuscript"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("unsupported MIME response leaked forbidden value %q: %s", forbidden, body)
		}
	}
}

func TestUploadSourceObjectUsesTenantUploadScopeAndDoesNotExposeObjectMetadata(t *testing.T) {
	store := &recordingSourceFileStore{}
	writer := &recordingSourceFileObjectWriter{}
	server := NewServer(Config{
		WriterStarter:          &recordingStarter{},
		SourceFileStore:        store,
		SourceFileObjectWriter: writer,
	})
	request := httptest.NewRequest(http.MethodPut, "/v1/uploads/upload-123/object", strings.NewReader("hello"))
	request.Header.Set("Content-Type", "text/plain")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.objectInput.TenantID != "tenant-123" || store.objectInput.UploadID != "upload-123" {
		t.Fatalf("store lost trusted tenant/upload context: %#v", store.objectInput)
	}
	if writer.input.ObjectKey != "projects/project-123/source-files/upload-123/book.txt" ||
		writer.input.TenantID != "tenant-123" ||
		writer.input.UploadID != "upload-123" ||
		writer.body != "hello" {
		t.Fatalf("writer did not receive expected internal object metadata/body: input=%#v body=%q", writer.input, writer.body)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["upload_id"] != "upload-123" || body["status"] != "stored" {
		t.Fatalf("unexpected object upload response: %#v", body)
	}
	for _, forbidden := range []string{"object_key", "presigned_url", "api_key", "raw_content"} {
		if _, ok := body[forbidden]; ok {
			t.Fatalf("object upload response leaked %s: %#v", forbidden, body)
		}
	}
}

func TestUploadSourceObjectFailsClosedWithoutObjectWriter(t *testing.T) {
	store := &recordingSourceFileStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	request := httptest.NewRequest(http.MethodPut, "/v1/uploads/upload-123/object", strings.NewReader("hello"))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED" ||
		body.Error.Message != "object storage backend is not configured" {
		t.Fatalf("unexpected error body: %#v", body)
	}
	if store.objectInput.TenantID != "" {
		t.Fatalf("unconfigured object writer should stop before source metadata lookup: %#v", store.objectInput)
	}
}

func TestUploadSourceObjectSanitizesWriterErrorsAtHTTPBoundary(t *testing.T) {
	store := &recordingSourceFileStore{}
	writer := &recordingSourceFileObjectWriter{
		err: sourcefiles.NewAppError("SOURCE_FILE_STORAGE_WRITE_FAILED", "put failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-123/source-files/upload-123/book.txt"),
	}
	server := NewServer(Config{
		WriterStarter:          &recordingStarter{},
		SourceFileStore:        store,
		SourceFileObjectWriter: writer,
	})
	request := httptest.NewRequest(http.MethodPut, "/v1/uploads/upload-123/object", strings.NewReader("hello"))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-source-object")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"code":"SOURCE_FILE_STORAGE_WRITE_FAILED"`) ||
		!strings.Contains(body, `"message":"source file object upload failed"`) ||
		!strings.Contains(body, `"request_id":"req-source-object"`) {
		t.Fatalf("expected stable source object write failure, got %s", body)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-123/source-files"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("source object write error leaked forbidden text %q: %s", forbidden, body)
		}
	}
}

func TestUploadSourceObjectRejectsNonWritableUploadStatusAtHTTPBoundary(t *testing.T) {
	store := &recordingSourceFileStore{
		err: sourcefiles.NewAppError("SOURCE_FILE_UPLOAD_NOT_WRITABLE", "cannot write object after completion prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-123/source-files/upload-123/book.txt"),
	}
	writer := &recordingSourceFileObjectWriter{}
	server := NewServer(Config{
		WriterStarter:          &recordingStarter{},
		SourceFileStore:        store,
		SourceFileObjectWriter: writer,
	})
	request := httptest.NewRequest(http.MethodPut, "/v1/uploads/upload-123/object", strings.NewReader("hello"))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-source-object-status")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusConflict {
		t.Fatalf("expected status %d, got %d: %s", http.StatusConflict, response.Code, response.Body.String())
	}
	if writer.body != "" {
		t.Fatalf("non-writable upload status must stop before object writer, got body %q", writer.body)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_UPLOAD_NOT_WRITABLE" ||
		body.Error.Message != "source file object upload cannot be written from its current status" ||
		body.Error.RequestID != "req-source-object-status" {
		t.Fatalf("unexpected error body: %#v", body)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-123/source-files", "draft", "manuscript"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("object upload status error leaked forbidden text %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestCompleteUploadUsesTenantUploadScopeAndReturnsSanitizedSourceFile(t *testing.T) {
	store := &recordingSourceFileStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/uploads/upload-123/complete", bytes.NewBufferString(`{"tenant_id":"evil-tenant","object_key":"must-not-be-used"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.completeInput.TenantID != "tenant-123" || store.completeInput.UploadID != "upload-123" {
		t.Fatalf("store lost trusted tenant/upload context: %#v", store.completeInput)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["upload_id"] != "upload-123" || body["parse_status"] != "uploaded" {
		t.Fatalf("unexpected complete response: %#v", body)
	}
	if _, ok := body["object_key"]; ok {
		t.Fatalf("complete response leaked object key: %#v", body)
	}
	if _, ok := body["presigned_url"]; ok {
		t.Fatalf("complete response leaked presigned URL: %#v", body)
	}
}

func TestCompleteUploadFailsClosedWithoutSourceFileBackend(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/uploads/upload-123/complete", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestCompleteUploadReturnsConflictWhenObjectIsMissing(t *testing.T) {
	store := &recordingSourceFileStore{err: sourcefiles.NewAppError("SOURCE_FILE_OBJECT_NOT_FOUND", "source file object was not found in object storage")}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/uploads/upload-123/complete", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusConflict {
		t.Fatalf("expected status %d, got %d: %s", http.StatusConflict, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_OBJECT_NOT_FOUND" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestCompleteUploadReturnsConflictForNonCompletableUploadStatus(t *testing.T) {
	store := &recordingSourceFileStore{err: sourcefiles.NewAppError("SOURCE_FILE_UPLOAD_NOT_COMPLETABLE", "cannot complete parsed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-123/source-files/upload-123/book.txt")}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/uploads/upload-123/complete", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-upload-complete-status")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusConflict {
		t.Fatalf("expected status %d, got %d: %s", http.StatusConflict, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_UPLOAD_NOT_COMPLETABLE" ||
		body.Error.Message != "source file upload cannot be completed from its current status" ||
		body.Error.RequestID != "req-upload-complete-status" {
		t.Fatalf("unexpected error body: %#v", body)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-123/source-files", "draft", "manuscript"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("complete upload status error leaked forbidden text %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestSourceFileRoutesSanitizeStoreErrorMessagesAtHTTPBoundary(t *testing.T) {
	sensitiveErr := sourcefiles.NewAppError("SOURCE_FILE_QUERY_FAILED", "driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-123/source-files/upload-123/book.txt")
	tests := []struct {
		name          string
		method        string
		path          string
		body          string
		expectedInput func(*recordingSourceFileStore) bool
	}{
		{
			name:   "create upload",
			method: http.MethodPost,
			path:   "/v1/projects/project-123/uploads",
			body:   `{"filename":"novel.md","mime_type":"text/markdown","size_bytes":2048,"sha256":"abc123","purpose":"seed"}`,
			expectedInput: func(store *recordingSourceFileStore) bool {
				return store.createInput.TenantID == "tenant-123" && store.createInput.ProjectID == "project-123"
			},
		},
		{
			name:   "complete upload",
			method: http.MethodPost,
			path:   "/v1/uploads/upload-123/complete",
			body:   `{}`,
			expectedInput: func(store *recordingSourceFileStore) bool {
				return store.completeInput.TenantID == "tenant-123" && store.completeInput.UploadID == "upload-123"
			},
		},
		{
			name:   "list source files",
			method: http.MethodGet,
			path:   "/v1/projects/project-123/source-files",
			expectedInput: func(store *recordingSourceFileStore) bool {
				return store.listInput.TenantID == "tenant-123" && store.listInput.ProjectID == "project-123"
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store := &recordingSourceFileStore{err: sensitiveErr}
			server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
			request := httptest.NewRequest(test.method, test.path, strings.NewReader(test.body))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Tenant-Id", "tenant-123")
			request.Header.Set("X-Request-Id", "req-source-error")
			response := httptest.NewRecorder()

			server.ServeHTTP(response, request)

			if response.Code != http.StatusServiceUnavailable {
				t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
			}
			if !test.expectedInput(store) {
				t.Fatalf("route did not call store with trusted context: %#v", store)
			}
			body := response.Body.String()
			if !strings.Contains(body, `"code":"SOURCE_FILE_QUERY_FAILED"`) ||
				!strings.Contains(body, `"message":"source file query failed"`) ||
				!strings.Contains(body, `"request_id":"req-source-error"`) {
				t.Fatalf("expected stable source file error response, got %s", body)
			}
			for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-123/source-files", "draft", "manuscript"} {
				if strings.Contains(body, forbidden) {
					t.Fatalf("source file error response leaked forbidden text %q: %s", forbidden, body)
				}
			}
		})
	}
}

func TestCreateUploadFailsClosedWithoutSourceFileBackend(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/uploads", bytes.NewBufferString(`{"filename":"novel.md","mime_type":"text/markdown","size_bytes":2048,"sha256":"abc123","purpose":"seed"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestListSourceFilesUsesTenantProjectScopeAndSanitizedRows(t *testing.T) {
	store := &recordingSourceFileStore{
		items: []sourcefiles.Record{{
			FileID:      "file-1",
			UploadID:    "upload-1",
			ProjectID:   "project-123",
			Filename:    "book.txt",
			MimeType:    "text/plain",
			SizeBytes:   99,
			SHA256:      "hash",
			Purpose:     "seed",
			ParseStatus: "pending",
			CreatedAt:   "2026-07-04T10:00:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: store})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/source-files", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.listInput.TenantID != "tenant-123" || store.listInput.ProjectID != "project-123" {
		t.Fatalf("store lost list scope: %#v", store.listInput)
	}
	var body map[string][]map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body["items"]) != 1 || body["items"][0]["upload_id"] != "upload-1" {
		t.Fatalf("unexpected source file list: %#v", body)
	}
	if _, ok := body["items"][0]["object_key"]; ok {
		t.Fatalf("source file list leaked object key: %#v", body)
	}
}

func TestListAssetsUsesTenantProjectScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingAssetReader{
		assets: []assets.Record{{
			AssetID:    "asset-1",
			ProjectID:  "project-123",
			Scope:      "project",
			AssetType:  "character",
			Category:   "entity",
			Lifecycle:  "seed",
			Title:      "主角",
			Summary:    "公开摘要",
			SourceKind: "seed_pipeline",
			SourceRef:  "entity-1",
			Enabled:    true,
			Pinned:     false,
			Tags:       []string{"主角"},
			Payload:    map[string]any{"entity_id": "entity-1"},
			CreatedAt:  "2026-07-04T00:00:00Z",
			UpdatedAt:  "2026-07-04T00:00:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/assets", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.listInput.TenantID != "tenant-123" || reader.listInput.ProjectID != "project-123" {
		t.Fatalf("reader lost list scope: %#v", reader.listInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"asset_id":"asset-1"`) || !strings.Contains(body, `"title":"主角"`) {
		t.Fatalf("unexpected asset list: %s", body)
	}
	for _, forbidden := range []string{"content_text", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("asset list leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListWorldlineSavedPathsUsesTenantProjectScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingWorldlineSavedPathReader{
		paths: []worldline.SavedPathRecord{{
			PathID:            "path-1",
			SessionID:         "session-1",
			ProjectID:         "project-123",
			Title:             "雨夜谈判路线",
			Summary:           "公开路径摘要",
			Lifecycle:         "saved",
			SelectedEventIDs:  []string{"event-1", "event-2"},
			WriterInstruction: "保持压迫感",
			CreatedAt:         "2026-07-05T00:00:00Z",
			UpdatedAt:         "2026-07-05T00:01:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineSavedPathReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/worldline/saved-paths", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.ProjectID != "project-123" {
		t.Fatalf("reader lost saved path scope: %#v", reader.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"path_id":"path-1"`) || !strings.Contains(body, `"selected_event_ids":["event-1","event-2"]`) {
		t.Fatalf("unexpected saved path list: %s", body)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("saved path list leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestCreateWorldlineSavedPathCarriesTenantSessionActorContextAndSanitizesPayload(t *testing.T) {
	store := &recordingWorldlineSavedPathStore{
		path: worldline.SavedPathRecord{
			PathID:            "path-1",
			SessionID:         "session-1",
			ProjectID:         "project-123",
			Title:             "雨夜谈判路线",
			Summary:           "公开路径摘要",
			Lifecycle:         "saved",
			SelectedEventIDs:  []string{"event-1", "event-2"},
			WriterInstruction: "保持压迫感",
			CreatedAt:         "2026-07-05T00:00:00Z",
			UpdatedAt:         "2026-07-05T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineSavedPathStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-sessions/session-1/saved-paths", strings.NewReader(`{
		"tenant_id":"tenant-from-body",
		"title":"雨夜谈判路线",
		"summary":"公开路径摘要",
		"selected_event_ids":["event-1","event-2"],
		"writer_instruction":"保持压迫感",
		"prompt":"must be stripped",
		"api_key":"must be stripped"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-456")
	request.Header.Set("X-Request-Id", "req-789")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if store.input.TenantID != "tenant-123" ||
		store.input.SessionID != "session-1" ||
		store.input.ActorUserID != "user-456" ||
		store.input.RequestID != "req-789" ||
		store.input.Title != "雨夜谈判路线" ||
		store.input.Summary != "公开路径摘要" ||
		store.input.WriterInstruction != "保持压迫感" ||
		!reflect.DeepEqual(store.input.SelectedEventIDs, []string{"event-1", "event-2"}) {
		t.Fatalf("saved path store lost context: %#v", store.input)
	}
	if store.input.TenantID == "tenant-from-body" {
		t.Fatalf("saved path store trusted body tenant: %#v", store.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"path_id":"path-1"`) ||
		!strings.Contains(body, `"selected_event_ids":["event-1","event-2"]`) ||
		!strings.Contains(body, `"writer_instruction":"保持压迫感"`) {
		t.Fatalf("unexpected saved path response: %s", body)
	}
	for _, forbidden := range []string{"tenant-from-body", "prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("saved path response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestCreateWorldlineSavedPathFailsClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-sessions/session-1/saved-paths", strings.NewReader(`{
		"title":"雨夜谈判路线",
		"selected_event_ids":["event-1"]
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_SAVED_PATH_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline saved path error, got %s", response.Body.String())
	}
}

func TestWorldlineValidationErrorsDoNotEchoDecoderDetails(t *testing.T) {
	tests := []struct {
		name      string
		method    string
		path      string
		body      string
		message   string
		requestID string
	}{
		{
			name:      "session unknown field",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/worldline-sessions",
			body:      `{"goal":"test a path","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid worldline session payload",
			requestID: "req-worldline-session-validation",
		},
		{
			name:      "step unknown field",
			method:    http.MethodPost,
			path:      "/v1/worldline-sessions/session-1/steps",
			body:      `{"mode":"director","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid worldline step payload",
			requestID: "req-worldline-step-validation",
		},
		{
			name:      "preparation unknown field",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/worldlines/preparations",
			body:      `{"goal":"prepare agents","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid worldline preparation payload",
			requestID: "req-worldline-preparation-validation",
		},
		{
			name:      "event adoption type error",
			method:    http.MethodPost,
			path:      "/v1/worldline-events/event-1/adoptions",
			body:      `{"note":42,"api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid worldline event adoption payload",
			requestID: "req-worldline-adoption-validation",
		},
		{
			name:      "event mutation type error",
			method:    http.MethodPatch,
			path:      "/v1/worldline-events/event-1",
			body:      `{"title":42,"api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid worldline event mutation payload",
			requestID: "req-worldline-mutation-validation",
		},
		{
			name:      "variable type error",
			method:    http.MethodPost,
			path:      "/v1/worldline-sessions/session-1/variables",
			body:      `{"name":"变量","locked":"yes","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid worldline variable payload",
			requestID: "req-worldline-variable-validation",
		},
		{
			name:      "saved path type error",
			method:    http.MethodPost,
			path:      "/v1/worldline-sessions/session-1/saved-paths",
			body:      `{"title":"路线","selected_event_ids":"event-1","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid worldline saved path payload",
			requestID: "req-worldline-saved-path-validation",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := NewServer(Config{WriterStarter: &recordingStarter{}})
			request := httptest.NewRequest(tt.method, tt.path, strings.NewReader(tt.body))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Tenant-Id", "tenant-123")
			request.Header.Set("X-Request-Id", tt.requestID)
			response := httptest.NewRecorder()

			server.ServeHTTP(response, request)

			if response.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d: %s", response.Code, response.Body.String())
			}
			body := response.Body.String()
			if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) ||
				!strings.Contains(body, `"message":"`+tt.message+`"`) ||
				!strings.Contains(body, `"request_id":"`+tt.requestID+`"`) ||
				!strings.Contains(body, `"details":{}`) {
				t.Fatalf("expected stable worldline validation failure, got %s", body)
			}
			for _, forbidden := range []string{
				`"details":{"error"`,
				"json:",
				"api_key",
				"sk-hidden",
				"prompt",
				"credential_ref",
				"draft",
				"manuscript",
				"adoptWorldlineEventRequest",
				"updateWorldlineEventRequest",
				"injectWorldlineVariableRequest",
				"createWorldlineSavedPathRequest",
				"selected_event_ids",
				"locked",
			} {
				if strings.Contains(body, forbidden) {
					t.Fatalf("worldline validation response leaked forbidden detail %q: %s", forbidden, body)
				}
			}
		})
	}
}

func TestStartWorldlineSessionCarriesTenantProjectActorContext(t *testing.T) {
	starter := &recordingWorldlineSessionStarter{
		run: worldline.SessionRun{
			RunID:        "run-worldline-1",
			ProjectID:    "project-123",
			WorkflowType: "worldline_session",
			Status:       "queued",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineSessionStarter: starter})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/worldline-sessions", strings.NewReader(`{
		"goal":"test a council betrayal",
		"anchor_path_id":"path-1",
		"options":{"temperature":0.7,"prompt":"must be stripped"}
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-456")
	request.Header.Set("X-Request-Id", "req-789")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" ||
		starter.input.ProjectID != "project-123" ||
		starter.input.ActorUserID != "user-456" ||
		starter.input.RequestID != "req-789" ||
		starter.input.Goal != "test a council betrayal" ||
		starter.input.AnchorPathID != "path-1" {
		t.Fatalf("starter lost worldline context: %#v", starter.input)
	}
	if _, exists := starter.input.Options["prompt"]; exists {
		t.Fatalf("worldline options retained forbidden prompt field: %#v", starter.input.Options)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"workflow_type":"worldline_session"`) || !strings.Contains(body, `"run_id":"run-worldline-1"`) {
		t.Fatalf("unexpected worldline session response: %s", body)
	}
	for _, forbidden := range []string{"prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("worldline session response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestStartWorldlineSessionFailsClosedWithoutStarter(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/worldline-sessions", strings.NewReader(`{"goal":"test a path"}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORLDLINE_SESSION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed worldline session error, got %#v", body.Error)
	}
}

func TestStartWorldlineStepCarriesTenantSessionActorContextAndSanitizesOptions(t *testing.T) {
	starter := &recordingWorldlineStepStarter{
		run: worldline.StepRun{
			RunID:        "run-step-1",
			ProjectID:    "project-123",
			SessionID:    "session-1",
			WorkflowType: "worldline_step",
			Status:       "queued",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineStepStarter: starter})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-sessions/session-1/steps", strings.NewReader(`{
		"tenant_id":"tenant-from-body",
		"mode":"director",
		"options":{"max_turns":2,"prompt":"must be stripped","credential_ref":"must be stripped","draft":"must be stripped"}
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-456")
	request.Header.Set("X-Request-Id", "req-789")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" ||
		starter.input.SessionID != "session-1" ||
		starter.input.ActorUserID != "user-456" ||
		starter.input.RequestID != "req-789" ||
		starter.input.Mode != "director" {
		t.Fatalf("step starter lost context: %#v", starter.input)
	}
	if starter.input.TenantID == "tenant-from-body" {
		t.Fatalf("step starter trusted body tenant: %#v", starter.input)
	}
	for _, forbidden := range []string{"prompt", "credential_ref", "draft"} {
		if _, exists := starter.input.Options[forbidden]; exists {
			t.Fatalf("step options retained forbidden field %q: %#v", forbidden, starter.input.Options)
		}
	}
	body := response.Body.String()
	if !strings.Contains(body, `"workflow_type":"worldline_step"`) ||
		!strings.Contains(body, `"run_id":"run-step-1"`) ||
		!strings.Contains(body, `"session_id":"session-1"`) {
		t.Fatalf("unexpected worldline step response: %s", body)
	}
	for _, forbidden := range []string{"tenant-from-body", "prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("worldline step response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestStartWorldlineStepFailsClosedWithoutStarter(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-sessions/session-1/steps", strings.NewReader(`{"mode":"director"}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_STEP_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline step error, got %s", response.Body.String())
	}
}

func TestCreateWorldlinePreparationCarriesContextAndSanitizesOptions(t *testing.T) {
	store := &recordingWorldlinePreparationStore{
		preparation: worldline.PreparationRecord{
			PrepareID:    "prepare-1",
			RunID:        "run-prepare-1",
			ProjectID:    "project-123",
			WorkflowType: "worldline_preparation",
			Status:       "queued",
			Lifecycle:    "preparing",
			GoalSummary:  "Prepare council agents",
			AnchorPathID: "path-1",
			CreatedBy:    "user-456",
			CreatedAt:    "2026-07-05T00:00:00Z",
			UpdatedAt:    "2026-07-05T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlinePreparationStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/worldlines/preparations", strings.NewReader(`{
		"goal":"Prepare council agents",
		"anchor_path_id":"path-1",
		"options":{"agent_count":3,"prompt":"must be stripped","credential_ref":"must be stripped"}
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-456")
	request.Header.Set("X-Request-Id", "req-789")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if store.createInput.TenantID != "tenant-123" ||
		store.createInput.ProjectID != "project-123" ||
		store.createInput.ActorUserID != "user-456" ||
		store.createInput.RequestID != "req-789" ||
		store.createInput.Goal != "Prepare council agents" ||
		store.createInput.AnchorPathID != "path-1" {
		t.Fatalf("preparation store lost context: %#v", store.createInput)
	}
	if _, exists := store.createInput.Options["prompt"]; exists {
		t.Fatalf("preparation options retained forbidden prompt field: %#v", store.createInput.Options)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"prepare_id":"prepare-1"`) ||
		!strings.Contains(body, `"workflow_type":"worldline_preparation"`) ||
		!strings.Contains(body, `"status":"queued"`) {
		t.Fatalf("unexpected preparation response: %s", body)
	}
	for _, forbidden := range []string{"prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("preparation response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestCreateWorldlinePreparationFailsClosedWithoutStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/worldlines/preparations", strings.NewReader(`{"goal":"prepare agents"}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed worldline preparation error, got %#v", body.Error)
	}
}

func TestGetWorldlinePreparationAndPreparedAgentsUseTenantPrepareScope(t *testing.T) {
	store := &recordingWorldlinePreparationStore{
		preparation: worldline.PreparationRecord{
			PrepareID:    "prepare-1",
			RunID:        "run-prepare-1",
			ProjectID:    "project-123",
			WorkflowType: "worldline_preparation",
			Status:       "queued",
			Lifecycle:    "preparing",
			GoalSummary:  "Prepare council agents",
			AnchorPathID: "path-1",
			CreatedBy:    "user-456",
			CreatedAt:    "2026-07-05T00:00:00Z",
			UpdatedAt:    "2026-07-05T00:01:00Z",
		},
		agents: []worldline.PreparedAgentRecord{{
			AgentID:       "agent-1",
			PrepareID:     "prepare-1",
			ProjectID:     "project-123",
			DisplayName:   "林砚",
			Role:          "protagonist",
			Status:        "queued",
			SourceAssetID: "asset-1",
			Summary:       "public agent summary",
			CreatedAt:     "2026-07-05T00:00:00Z",
			UpdatedAt:     "2026-07-05T00:01:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlinePreparationStore: store})

	detailRequest := httptest.NewRequest(http.MethodGet, "/v1/worldline-preparations/prepare-1", nil)
	detailRequest.Header.Set("X-Tenant-Id", "tenant-123")
	detailResponse := httptest.NewRecorder()
	server.ServeHTTP(detailResponse, detailRequest)

	if detailResponse.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, detailResponse.Code, detailResponse.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.PrepareID != "prepare-1" {
		t.Fatalf("reader lost preparation scope: %#v", store.getInput)
	}
	detailBody := detailResponse.Body.String()
	if !strings.Contains(detailBody, `"prepare_id":"prepare-1"`) || !strings.Contains(detailBody, `"goal_summary":"Prepare council agents"`) {
		t.Fatalf("unexpected preparation detail: %s", detailBody)
	}

	agentsRequest := httptest.NewRequest(http.MethodGet, "/v1/worldline-preparations/prepare-1/agents", nil)
	agentsRequest.Header.Set("X-Tenant-Id", "tenant-123")
	agentsResponse := httptest.NewRecorder()
	server.ServeHTTP(agentsResponse, agentsRequest)

	if agentsResponse.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, agentsResponse.Code, agentsResponse.Body.String())
	}
	if store.agentsInput.TenantID != "tenant-123" || store.agentsInput.PrepareID != "prepare-1" {
		t.Fatalf("reader lost prepared agents scope: %#v", store.agentsInput)
	}
	agentsBody := agentsResponse.Body.String()
	if !strings.Contains(agentsBody, `"agent_id":"agent-1"`) || !strings.Contains(agentsBody, `"display_name":"林砚"`) {
		t.Fatalf("unexpected prepared agents: %s", agentsBody)
	}
	for _, body := range []string{detailBody, agentsBody} {
		for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
			if strings.Contains(body, forbidden) {
				t.Fatalf("worldline preparation response leaked forbidden field %q: %s", forbidden, body)
			}
		}
	}
}

func TestListWorldlineSessionsUsesTenantProjectScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingWorldlineSessionReader{
		sessions: []worldline.SessionRecord{{
			SessionID:    "session-1",
			RunID:        "run-1",
			ProjectID:    "project-123",
			Status:       "queued",
			Lifecycle:    "active",
			GoalSummary:  "Explore public consequence",
			AnchorPathID: "path-1",
			CreatedBy:    "user-456",
			CreatedAt:    "2026-07-05T00:00:00Z",
			UpdatedAt:    "2026-07-05T00:01:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineSessionReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/worldline-sessions", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.listInput.TenantID != "tenant-123" || reader.listInput.ProjectID != "project-123" {
		t.Fatalf("reader lost session list scope: %#v", reader.listInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"session_id":"session-1"`) || !strings.Contains(body, `"goal_summary":"Explore public consequence"`) {
		t.Fatalf("unexpected session list: %s", body)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("session list leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestGetWorldlineSessionUsesTenantSessionScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingWorldlineSessionReader{
		session: worldline.SessionRecord{
			SessionID:    "session-1",
			RunID:        "run-1",
			ProjectID:    "project-123",
			Status:       "queued",
			Lifecycle:    "active",
			GoalSummary:  "Explore public consequence",
			AnchorPathID: "path-1",
			CreatedBy:    "user-456",
			CreatedAt:    "2026-07-05T00:00:00Z",
			UpdatedAt:    "2026-07-05T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineSessionReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/worldline-sessions/session-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.getInput.TenantID != "tenant-123" || reader.getInput.SessionID != "session-1" {
		t.Fatalf("reader lost session detail scope: %#v", reader.getInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"session_id":"session-1"`) || !strings.Contains(body, `"project_id":"project-123"`) {
		t.Fatalf("unexpected session detail: %s", body)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("session detail leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListWorldlineTimelineUsesTenantSessionScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingWorldlineTimelineReader{
		events: []worldline.TimelineEventRecord{{
			EventID:   "event-1",
			SessionID: "session-1",
			RunID:     "run-1",
			ProjectID: "project-123",
			EventType: "worldline.session.started",
			Sequence:  1,
			Status:    "running",
			Lifecycle: "active",
			Title:     "Director opened the current-world experiment",
			Summary:   "Public event summary",
			Kind:      "director",
			CreatedAt: "2026-07-05T00:00:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineTimelineReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/worldline-sessions/session-1/timeline", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.SessionID != "session-1" {
		t.Fatalf("reader lost timeline scope: %#v", reader.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"event_id":"event-1"`) || !strings.Contains(body, `"summary":"Public event summary"`) {
		t.Fatalf("unexpected timeline response: %s", body)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("timeline response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListWorldlineTimelineFailsClosedWithoutConfiguredReader(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/worldline-sessions/session-1/timeline", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_TIMELINE_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline timeline error, got %s", response.Body.String())
	}
}

func TestListWorldlineEventsUsesTenantSessionScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingWorldlineEventReader{
		events: []worldline.EventRecord{{
			EventID:          "event-1",
			SessionID:        "session-1",
			ProjectID:        "project-123",
			Step:             3,
			Title:            "密谈破裂",
			Summary:          "公开候选事件摘要",
			Kind:             "director",
			Status:           "candidate",
			Lifecycle:        "simulation",
			Confidence:       "0.86",
			InvolvedAgentIDs: []string{"agent-1", "agent-2"},
			StateChanges:     map[string]any{"tension": "raised"},
			SourceRunID:      "run-1",
			CreatedBy:        "user-456",
			CreatedAt:        "2026-07-05T00:00:00Z",
			UpdatedAt:        "2026-07-05T00:01:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineEventReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/worldline-sessions/session-1/events?status=candidate", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.SessionID != "session-1" || reader.input.Status != "candidate" {
		t.Fatalf("reader lost event scope: %#v", reader.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"event_id":"event-1"`) ||
		!strings.Contains(body, `"status":"candidate"`) ||
		!strings.Contains(body, `"summary":"公开候选事件摘要"`) ||
		!strings.Contains(body, `"involved_agent_ids":["agent-1","agent-2"]`) {
		t.Fatalf("unexpected worldline events response: %s", body)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("worldline events response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListWorldlineEventsFailsClosedWithoutConfiguredReader(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/worldline-sessions/session-1/events", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_EVENT_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline event error, got %s", response.Body.String())
	}
}

func TestAdoptWorldlineEventCarriesTenantEventActorContextAndSanitizesResponse(t *testing.T) {
	store := &recordingWorldlineEventAdoptionStore{
		event: worldline.EventRecord{
			EventID:          "event-1",
			SessionID:        "session-1",
			ProjectID:        "project-123",
			Step:             3,
			Title:            "密谈破裂",
			Summary:          "公开候选事件摘要",
			Kind:             "director",
			Status:           "canon",
			Lifecycle:        "canon_reference",
			Confidence:       "0.86",
			InvolvedAgentIDs: []string{"agent-1", "agent-2"},
			StateChanges:     map[string]any{"tension": "raised"},
			SourceRunID:      "run-1",
			CreatedBy:        "user-456",
			CreatedAt:        "2026-07-05T00:00:00Z",
			UpdatedAt:        "2026-07-05T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineEventAdoptionStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-events/event-1/adoptions", strings.NewReader(`{
		"tenant_id":"tenant-from-body",
		"note":"Adopt as current-world canon",
		"prompt":"must be stripped",
		"api_key":"must be stripped"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-456")
	request.Header.Set("X-Request-Id", "req-789")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if store.input.TenantID != "tenant-123" ||
		store.input.EventID != "event-1" ||
		store.input.ActorUserID != "user-456" ||
		store.input.RequestID != "req-789" ||
		store.input.Note != "Adopt as current-world canon" {
		t.Fatalf("event adoption store lost context: %#v", store.input)
	}
	if store.input.TenantID == "tenant-from-body" {
		t.Fatalf("event adoption store trusted body tenant: %#v", store.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"event_id":"event-1"`) ||
		!strings.Contains(body, `"status":"canon"`) ||
		!strings.Contains(body, `"lifecycle":"canon_reference"`) {
		t.Fatalf("unexpected event adoption response: %s", body)
	}
	for _, forbidden := range []string{"tenant-from-body", "prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("event adoption response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestAdoptWorldlineEventFailsClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-events/event-1/adoptions", strings.NewReader(`{"note":"canon"}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline event adoption error, got %s", response.Body.String())
	}
}

func TestUpdateWorldlineEventCarriesTenantEventActorContextAndSanitizesResponse(t *testing.T) {
	store := &recordingWorldlineEventMutationStore{
		event: worldline.EventRecord{
			EventID:          "event-1",
			SessionID:        "session-1",
			ProjectID:        "project-123",
			Step:             3,
			Title:            "密谈缓和",
			Summary:          "公开编辑后的候选事件摘要",
			Kind:             "director_revision",
			Status:           "candidate",
			Lifecycle:        "simulation",
			Confidence:       "0.86",
			InvolvedAgentIDs: []string{"agent-1", "agent-2"},
			StateChanges:     map[string]any{"tension": "lowered"},
			SourceRunID:      "run-1",
			CreatedBy:        "user-456",
			CreatedAt:        "2026-07-05T00:00:00Z",
			UpdatedAt:        "2026-07-05T00:02:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineEventMutationStore: store})
	request := httptest.NewRequest(http.MethodPatch, "/v1/worldline-events/event-1", strings.NewReader(`{
		"tenant_id":"tenant-from-body",
		"title":"密谈缓和",
		"summary":"公开编辑后的候选事件摘要",
		"kind":"director_revision",
		"prompt":"must be stripped",
		"api_key":"must be stripped"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-456")
	request.Header.Set("X-Request-Id", "req-789")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if store.input.TenantID != "tenant-123" ||
		store.input.EventID != "event-1" ||
		store.input.ActorUserID != "user-456" ||
		store.input.RequestID != "req-789" ||
		store.input.Title != "密谈缓和" ||
		store.input.Summary != "公开编辑后的候选事件摘要" ||
		store.input.Kind != "director_revision" {
		t.Fatalf("event mutation store lost context: %#v", store.input)
	}
	if store.input.TenantID == "tenant-from-body" {
		t.Fatalf("event mutation store trusted body tenant: %#v", store.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"event_id":"event-1"`) ||
		!strings.Contains(body, `"title":"密谈缓和"`) ||
		!strings.Contains(body, `"status":"candidate"`) {
		t.Fatalf("unexpected event mutation response: %s", body)
	}
	for _, forbidden := range []string{"tenant-from-body", "prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("event mutation response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestUpdateWorldlineEventFailsClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPatch, "/v1/worldline-events/event-1", strings.NewReader(`{"title":"edit"}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline event mutation error, got %s", response.Body.String())
	}
}

func TestInjectWorldlineVariableCarriesTenantSessionActorContextAndSanitizesPayload(t *testing.T) {
	store := &recordingWorldlineVariableStore{
		variable: worldline.VariableRecord{
			VariableID:  "variable-1",
			SessionID:   "session-1",
			ProjectID:   "project-123",
			Name:        "主角亲族提前失踪",
			Description: "公开变量摘要",
			ImpactAxis:  "kinship_pressure",
			Locked:      true,
			Source:      "author",
			CreatedBy:   "user-456",
			CreatedAt:   "2026-07-05T00:00:00Z",
			UpdatedAt:   "2026-07-05T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorldlineVariableStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-sessions/session-1/variables", strings.NewReader(`{
		"tenant_id":"tenant-from-body",
		"name":"主角亲族提前失踪",
		"description":"公开变量摘要",
		"impact_axis":"kinship_pressure",
		"locked":true,
		"source":"author",
		"prompt":"must be stripped",
		"api_key":"must be stripped"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-456")
	request.Header.Set("X-Request-Id", "req-789")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if store.input.TenantID != "tenant-123" ||
		store.input.SessionID != "session-1" ||
		store.input.ActorUserID != "user-456" ||
		store.input.RequestID != "req-789" ||
		store.input.Name != "主角亲族提前失踪" ||
		store.input.Description != "公开变量摘要" ||
		store.input.ImpactAxis != "kinship_pressure" ||
		!store.input.Locked ||
		store.input.Source != "author" {
		t.Fatalf("variable store lost context: %#v", store.input)
	}
	if store.input.TenantID == "tenant-from-body" {
		t.Fatalf("variable store trusted body tenant: %#v", store.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"variable_id":"variable-1"`) ||
		!strings.Contains(body, `"impact_axis":"kinship_pressure"`) ||
		!strings.Contains(body, `"locked":true`) {
		t.Fatalf("unexpected variable response: %s", body)
	}
	for _, forbidden := range []string{"tenant-from-body", "prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("variable response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestInjectWorldlineVariableFailsClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/worldline-sessions/session-1/variables", strings.NewReader(`{"name":"变量"}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline variable error, got %s", response.Body.String())
	}
}

func TestListWorldlineSessionsFailsClosedWithoutConfiguredReader(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/worldline-sessions", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "WORLDLINE_SESSION_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline session error, got %s", response.Body.String())
	}
}

func TestListWorldlineSavedPathsFailsClosedWithoutConfiguredReader(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/worldline/saved-paths", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, "WORLDLINE_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected fail-closed worldline error, got %s", body)
	}
}

func TestCreateCharacterInteractionCarriesTenantProjectActorContextAndSanitizesPayload(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID:      "interaction-1",
			ProjectID:          "project-123",
			WorldlineSessionID: "session-1",
			AnchorType:         "worldline_event",
			AnchorID:           "event-1",
			POVAgentID:         "agent-1",
			Mode:               "first_person",
			Status:             "active",
			Title:              "雨夜谈判前",
			Summary:            "公开摘要",
			Metadata:           map[string]any{"source": "worldline"},
			CreatedBy:          "user-123",
			CreatedAt:          "2026-07-06T00:00:00Z",
			UpdatedAt:          "2026-07-06T00:00:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/character-interactions", strings.NewReader(`{
		"tenant_id":"body-tenant",
		"project_id":"body-project",
		"worldline_session_id":"session-1",
		"anchor_type":"worldline_event",
		"anchor_id":"event-1",
		"pov_agent_id":"agent-1",
		"mode":"first_person",
		"title":"雨夜谈判前",
		"summary":"公开摘要",
		"metadata":{"source":"worldline","prompt":"must be stripped","credential_ref":"must be stripped"}
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", response.Code, response.Body.String())
	}
	if store.createInput.TenantID != "tenant-123" ||
		store.createInput.ProjectID != "project-123" ||
		store.createInput.ActorUserID != "user-123" ||
		store.createInput.RequestID != "req-123" ||
		store.createInput.WorldlineSessionID != "session-1" ||
		store.createInput.Mode != "first_person" {
		t.Fatalf("lost character interaction context: %#v", store.createInput)
	}
	if _, ok := store.createInput.Metadata["prompt"]; ok {
		t.Fatalf("metadata retained forbidden prompt field: %#v", store.createInput.Metadata)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"interaction_id":"interaction-1"`) || !strings.Contains(body, `"status":"active"`) {
		t.Fatalf("unexpected character interaction response: %s", body)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
}

func TestUpdateCharacterInteractionStatusUsesTenantScopeAndSanitizesResponse(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Mode:          "dialogue",
			Status:        "saved",
			Title:         "对话",
			Summary:       "公开摘要",
			Metadata: map[string]any{
				"safe":           "visible",
				"prompt":         "must not leak",
				"credential_ref": "secret",
			},
			CreatedAt: "2026-07-06T00:00:00Z",
			UpdatedAt: "2026-07-06T00:03:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodPatch, "/v1/character-interactions/interaction-1", strings.NewReader(`{
		"tenant_id":"body-tenant",
		"status":"saved"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-save-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", response.Code, response.Body.String())
	}
	if store.updateInput.TenantID != "tenant-123" ||
		store.updateInput.InteractionID != "interaction-1" ||
		store.updateInput.ActorUserID != "user-123" ||
		store.updateInput.RequestID != "req-save-123" ||
		store.updateInput.Status != "saved" {
		t.Fatalf("lost status update context: %#v", store.updateInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"interaction_id":"interaction-1"`) || !strings.Contains(body, `"status":"saved"`) {
		t.Fatalf("unexpected status update response: %s", body)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
}

func TestListAndGetCharacterInteractionsUseTenantScopeAndIncludeTurnsInDetail(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		interactions: []characterconsole.InteractionRecord{{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Mode:          "dialogue",
			Status:        "active",
			Title:         "对话",
			Summary:       "公开摘要",
			Metadata:      map[string]any{"source": "scene"},
			CreatedAt:     "2026-07-06T00:00:00Z",
			UpdatedAt:     "2026-07-06T00:00:00Z",
		}},
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Mode:          "dialogue",
			Status:        "active",
			Title:         "对话",
			Summary:       "公开摘要",
			Metadata:      map[string]any{"source": "scene"},
			CreatedAt:     "2026-07-06T00:00:00Z",
			UpdatedAt:     "2026-07-06T00:00:00Z",
		},
		turns: []characterconsole.TurnRecord{{
			TurnID:        "turn-1",
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			TurnOrder:     1,
			ActorType:     "user",
			ActorID:       "user-123",
			TurnKind:      "dialogue",
			Summary:       "我说出条件",
			CreatedAt:     "2026-07-06T00:01:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})

	listRequest := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/character-interactions?status=active", nil)
	listRequest.Header.Set("X-Tenant-Id", "tenant-123")
	listResponse := httptest.NewRecorder()
	server.ServeHTTP(listResponse, listRequest)
	if listResponse.Code != http.StatusOK {
		t.Fatalf("expected 200 list, got %d: %s", listResponse.Code, listResponse.Body.String())
	}
	if store.listInput.TenantID != "tenant-123" || store.listInput.ProjectID != "project-123" || store.listInput.Status != "active" {
		t.Fatalf("lost list scope: %#v", store.listInput)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, listResponse.Body.String())

	detailRequest := httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1", nil)
	detailRequest.Header.Set("X-Tenant-Id", "tenant-123")
	detailResponse := httptest.NewRecorder()
	server.ServeHTTP(detailResponse, detailRequest)
	if detailResponse.Code != http.StatusOK {
		t.Fatalf("expected 200 detail, got %d: %s", detailResponse.Code, detailResponse.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "interaction-1" {
		t.Fatalf("lost detail scope: %#v", store.getInput)
	}
	if store.turnsInput.TenantID != "tenant-123" || store.turnsInput.InteractionID != "interaction-1" {
		t.Fatalf("detail did not list turns under same scope: %#v", store.turnsInput)
	}
	body := detailResponse.Body.String()
	if !strings.Contains(body, `"turns":[`) || !strings.Contains(body, `"turn_id":"turn-1"`) {
		t.Fatalf("detail did not include turn metadata: %s", body)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
}

func TestCharacterInteractionResponsesSanitizeInjectedStorePayloadsAtHTTPBoundary(t *testing.T) {
	unsafeMetadata := map[string]any{
		"source":         "scene",
		"prompt":         "must not leak",
		"source_text":    "hidden source body",
		"api_key":        "sk-hidden",
		"credential_ref": "secret-ref",
		"nested": map[string]any{
			"content":        "hidden content",
			"candidate_body": "hidden candidate body",
			"safe":           "visible metadata",
		},
	}
	unsafeAction := map[string]any{
		"intent": "threaten",
		"body":   "hidden body",
		"nested": map[string]any{
			"draft":           "hidden draft",
			"source_material": "hidden source material",
			"safe":            "visible action",
		},
	}
	unsafeWorldState := map[string]any{
		"public":               true,
		"manuscript":           "hidden manuscript",
		"candidate_event_body": "hidden candidate event body",
		"events": []any{
			map[string]any{"response": "hidden response", "event_body": "hidden event body", "summary": "visible summary"},
		},
	}
	store := &recordingCharacterConsoleStore{
		interactions: []characterconsole.InteractionRecord{{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Mode:          "dialogue",
			Status:        "active",
			Title:         "对话",
			Summary:       "公开摘要",
			Metadata:      unsafeMetadata,
			CreatedAt:     "2026-07-06T00:00:00Z",
			UpdatedAt:     "2026-07-06T00:00:00Z",
		}},
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Mode:          "dialogue",
			Status:        "active",
			Title:         "对话",
			Summary:       "公开摘要",
			Metadata:      unsafeMetadata,
			CreatedAt:     "2026-07-06T00:00:00Z",
			UpdatedAt:     "2026-07-06T00:00:00Z",
		},
		turns: []characterconsole.TurnRecord{{
			TurnID:          "turn-1",
			InteractionID:   "interaction-1",
			ProjectID:       "project-123",
			TurnOrder:       1,
			ActorType:       "user",
			ActorID:         "user-123",
			TurnKind:        "dialogue",
			Summary:         "我说出条件",
			Action:          unsafeAction,
			WorldStateDelta: unsafeWorldState,
			CreatedAt:       "2026-07-06T00:01:00Z",
		}},
		turn: characterconsole.TurnRecord{
			TurnID:          "turn-2",
			InteractionID:   "interaction-1",
			ProjectID:       "project-123",
			TurnOrder:       2,
			ActorType:       "director",
			TurnKind:        "director_note",
			Summary:         "公开导演注记",
			Action:          unsafeAction,
			WorldStateDelta: unsafeWorldState,
			CreatedAt:       "2026-07-06T00:02:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})

	for _, scenario := range []struct {
		request  *http.Request
		expected []string
	}{
		{
			request:  httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/character-interactions", nil),
			expected: []string{"visible metadata"},
		},
		{
			request:  httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1", nil),
			expected: []string{"visible metadata", "visible action", "visible summary"},
		},
		{
			request:  httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1/turns", nil),
			expected: []string{"visible action", "visible summary"},
		},
		{
			request: httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/turns", strings.NewReader(`{
			"actor_type":"director",
			"turn_kind":"director_note",
			"summary":"公开导演注记"
		}`)),
			expected: []string{"visible action", "visible summary"},
		},
	} {
		request := scenario.request
		request.Header.Set("X-Tenant-Id", "tenant-123")
		response := httptest.NewRecorder()
		server.ServeHTTP(response, request)
		if response.Code != http.StatusOK && response.Code != http.StatusCreated {
			t.Fatalf("expected success for %s %s, got %d: %s", request.Method, request.URL.Path, response.Code, response.Body.String())
		}
		body := response.Body.String()
		assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
		for _, expected := range scenario.expected {
			if !strings.Contains(body, expected) {
				t.Fatalf("response removed safe public value %q: %s", expected, body)
			}
		}
	}
}

func TestCharacterInteractionRoutesSanitizeUnexpectedStoreErrorsAtHTTPBoundary(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		err: errors.New("driver exploded prompt=hidden api_key=sk-hidden credential_ref=secret body=private manuscript=private"),
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})

	for _, request := range []*http.Request{
		httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/character-interactions", strings.NewReader(`{
			"mode":"dialogue",
			"title":"公开标题"
		}`)),
		httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/character-interactions", nil),
		httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1", nil),
		httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/turns", strings.NewReader(`{
			"actor_type":"user",
			"turn_kind":"dialogue",
			"summary":"公开回合"
		}`)),
		httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1/turns", nil),
	} {
		request.Header.Set("X-Tenant-Id", "tenant-123")
		response := httptest.NewRecorder()

		server.ServeHTTP(response, request)

		if response.Code != http.StatusServiceUnavailable {
			t.Fatalf("expected fail-closed status for %s %s, got %d: %s", request.Method, request.URL.Path, response.Code, response.Body.String())
		}
		body := response.Body.String()
		if !strings.Contains(body, "CHARACTER_INTERACTION_QUERY_FAILED") || !strings.Contains(body, "character interaction query failed") {
			t.Fatalf("expected stable character interaction query failure, got %s", body)
		}
		assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
	}
}

func TestCharacterInteractionRoutesStabilizeCodedStoreErrorMessagesAtHTTPBoundary(t *testing.T) {
	for _, testCase := range []struct {
		name            string
		err             error
		expectedStatus  int
		expectedCode    string
		expectedMessage string
	}{
		{
			name: "not found",
			err: &characterconsole.AppError{
				Code:    "NOT_FOUND",
				Message: "character interaction missing prompt=hidden api_key=sk-hidden credential_ref=secret manuscript=private",
			},
			expectedStatus:  http.StatusNotFound,
			expectedCode:    "NOT_FOUND",
			expectedMessage: "character interaction was not found",
		},
		{
			name: "backend unconfigured",
			err: &characterconsole.AppError{
				Code:    "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED",
				Message: "backend missing prompt=hidden api_key=sk-hidden credential_ref=secret draft=private",
			},
			expectedStatus:  http.StatusServiceUnavailable,
			expectedCode:    "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED",
			expectedMessage: "character interaction backend is not configured",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := &recordingCharacterConsoleStore{getErr: testCase.err}
			server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
			request := httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1", nil)
			request.Header.Set("X-Tenant-Id", "tenant-123")
			request.Header.Set("X-Request-Id", "req-character-coded-error")

			response := httptest.NewRecorder()
			server.ServeHTTP(response, request)

			if response.Code != testCase.expectedStatus {
				t.Fatalf("expected %d, got %d: %s", testCase.expectedStatus, response.Code, response.Body.String())
			}
			body := response.Body.String()
			if !strings.Contains(body, `"code":"`+testCase.expectedCode+`"`) || !strings.Contains(body, `"message":"`+testCase.expectedMessage+`"`) {
				t.Fatalf("expected stable %s character interaction error, got %s", testCase.expectedCode, body)
			}
			assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
		})
	}
}

func TestCharacterInteractionValidationErrorsDoNotEchoSensitiveUnknownFields(t *testing.T) {
	for _, testCase := range []struct {
		name    string
		request *http.Request
	}{
		{
			name: "create interaction",
			request: httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/character-interactions", strings.NewReader(`{
				"mode":"dialogue",
				"api_key":"sk-hidden"
			}`)),
		},
		{
			name: "append turn",
			request: httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/turns", strings.NewReader(`{
				"actor_type":"user",
				"turn_kind":"dialogue",
				"prompt":"hidden prompt"
			}`)),
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := &recordingCharacterConsoleStore{}
			server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
			testCase.request.Header.Set("X-Tenant-Id", "tenant-123")
			testCase.request.Header.Set("X-Request-Id", "req-character-validation")

			response := httptest.NewRecorder()
			server.ServeHTTP(response, testCase.request)

			if response.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d: %s", response.Code, response.Body.String())
			}
			body := response.Body.String()
			if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) {
				t.Fatalf("expected validation failure, got %s", body)
			}
			assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
			if store.createInput.TenantID != "" || store.appendInput.TenantID != "" || store.getInput.TenantID != "" {
				t.Fatalf("validation failure should stop before store calls: %#v %#v %#v", store.createInput, store.appendInput, store.getInput)
			}
		})
	}
}

func TestAppendCharacterInteractionTurnDoesNotGenerateAgentReply(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		turn: characterconsole.TurnRecord{
			TurnID:        "turn-1",
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			TurnOrder:     1,
			ActorType:     "user",
			ActorID:       "user-123",
			TurnKind:      "action",
			Summary:       "我把剑放在桌上",
			Action:        map[string]any{"intent": "threaten"},
			CreatedBy:     "user-123",
			CreatedAt:     "2026-07-06T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/turns", strings.NewReader(`{
		"tenant_id":"body-tenant",
		"actor_type":"user",
		"actor_id":"user-123",
		"turn_kind":"action",
		"summary":"我把剑放在桌上",
		"action":{"intent":"threaten","prompt":"must be stripped"},
		"world_state_delta":{"public":true,"api_key":"must be stripped"},
		"trace_id":"trace-1"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-turn-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", response.Code, response.Body.String())
	}
	if store.appendInput.TenantID != "tenant-123" ||
		store.appendInput.InteractionID != "interaction-1" ||
		store.appendInput.ActorType != "user" ||
		store.appendInput.TurnKind != "action" ||
		store.appendInput.ActorUserID != "user-123" {
		t.Fatalf("lost append context: %#v", store.appendInput)
	}
	if _, ok := store.appendInput.Action["prompt"]; ok {
		t.Fatalf("turn action retained forbidden prompt field: %#v", store.appendInput.Action)
	}
	body := response.Body.String()
	if strings.Contains(body, "agent_reply") || strings.Contains(body, "chapter_draft") {
		t.Fatalf("turn append fabricated reply/draft: %s", body)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
}

func TestAppendCharacterInteractionTurnVerifiesParentInteractionScope(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Mode:          "dialogue",
			Status:        "active",
		},
		turn: characterconsole.TurnRecord{
			TurnID:        "turn-1",
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			TurnOrder:     1,
			ActorType:     "user",
			TurnKind:      "dialogue",
			Summary:       "公开回合",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/turns", strings.NewReader(`{
		"actor_type":"user",
		"turn_kind":"dialogue",
		"summary":"公开回合"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "interaction-1" {
		t.Fatalf("turn append did not verify parent interaction scope first: %#v", store.getInput)
	}
	if store.appendInput.TenantID != "tenant-123" || store.appendInput.InteractionID != "interaction-1" {
		t.Fatalf("turn append lost append scope: %#v", store.appendInput)
	}
}

func TestAppendCharacterInteractionTurnReturnsNotFoundForMissingInteraction(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		getErr: &characterconsole.AppError{Code: "NOT_FOUND", Message: "character interaction was not found"},
		turn: characterconsole.TurnRecord{
			TurnID:        "turn-1",
			InteractionID: "missing-interaction",
			ProjectID:     "project-123",
			TurnOrder:     1,
			ActorType:     "user",
			TurnKind:      "dialogue",
			Summary:       "must not be written",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/character-interactions/missing-interaction/turns", strings.NewReader(`{
		"actor_type":"user",
		"turn_kind":"dialogue",
		"summary":"公开回合"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected missing interaction to return 404, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "missing-interaction" {
		t.Fatalf("turn append did not lookup missing interaction in tenant scope: %#v", store.getInput)
	}
	if store.appendInput.InteractionID != "" {
		t.Fatalf("turn append should stop before writing a turn for a missing interaction: %#v", store.appendInput)
	}
	if strings.Contains(response.Body.String(), "turn-1") {
		t.Fatalf("missing interaction must not return appended turn metadata: %s", response.Body.String())
	}
}

func TestListCharacterInteractionTurnsVerifiesParentInteractionScope(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Mode:          "dialogue",
			Status:        "active",
		},
		turns: []characterconsole.TurnRecord{{
			TurnID:        "turn-1",
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			TurnOrder:     1,
			ActorType:     "user",
			TurnKind:      "dialogue",
			Summary:       "公开回合",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1/turns", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "interaction-1" {
		t.Fatalf("turn replay did not verify parent interaction scope first: %#v", store.getInput)
	}
	if store.turnsInput.TenantID != "tenant-123" || store.turnsInput.InteractionID != "interaction-1" {
		t.Fatalf("turn replay lost turn list scope: %#v", store.turnsInput)
	}
}

func TestListCharacterInteractionTurnsReturnsNotFoundForMissingInteraction(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		getErr: &characterconsole.AppError{Code: "NOT_FOUND", Message: "character interaction was not found"},
		turns:  []characterconsole.TurnRecord{},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodGet, "/v1/character-interactions/missing-interaction/turns", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected missing interaction to return 404, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "missing-interaction" {
		t.Fatalf("turn replay did not lookup missing interaction in tenant scope: %#v", store.getInput)
	}
	if store.turnsInput.InteractionID != "" {
		t.Fatalf("turn replay should stop before listing turns for a missing interaction: %#v", store.turnsInput)
	}
	if strings.Contains(response.Body.String(), `"items"`) {
		t.Fatalf("missing interaction must not be returned as an empty replay list: %s", response.Body.String())
	}
}

func TestCharacterInteractionRoutesFailClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/character-interactions", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d: %s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected character console fail-closed error, got %s", response.Body.String())
	}
}

func TestCharacterInteractionEventsRemainExplicitlyPending(t *testing.T) {
	store := &recordingCharacterConsoleStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodGet, "/v1/character-interactions/interaction-1/events", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected pending/fail-closed status, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "interaction-1" {
		t.Fatalf("runtime pending route did not verify tenant-scoped interaction first: %#v", store.getInput)
	}
	if !strings.Contains(response.Body.String(), "CHARACTER_CONSOLE_RUNTIME_PENDING") {
		t.Fatalf("expected explicit pending runtime, got %s", response.Body.String())
	}
}

func TestConvertCharacterInteractionToChapterDraftStartsWriterRunFromPublicMetadata(t *testing.T) {
	starter := &recordingStarter{}
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID:      "interaction-1",
			ProjectID:          "project-123",
			WorldlineSessionID: "session-1",
			AnchorType:         "worldline_event",
			AnchorID:           "event-1",
			POVAgentID:         "agent-1",
			Mode:               "dialogue",
			Status:             "saved",
			Title:              "公开互动标题",
			Summary:            "公开互动摘要",
			Metadata: map[string]any{
				"tone":           "tense",
				"prompt":         "hidden prompt",
				"api_key":        "sk-hidden",
				"credential_ref": "hidden-ref",
			},
		},
		turns: []characterconsole.TurnRecord{
			{
				TurnID:        "turn-1",
				InteractionID: "interaction-1",
				ProjectID:     "project-123",
				TurnOrder:     1,
				ActorType:     "user",
				ActorID:       "user-123",
				TurnKind:      "dialogue",
				Summary:       "第一回合公开摘要",
				Action: map[string]any{
					"intent": "question",
					"prompt": "hidden turn prompt",
				},
			},
			{
				TurnID:        "turn-2",
				InteractionID: "interaction-1",
				ProjectID:     "project-123",
				TurnOrder:     2,
				ActorType:     "agent",
				ActorID:       "agent-1",
				TurnKind:      "action",
				Summary:       "第二回合公开摘要",
				WorldStateDelta: map[string]any{
					"visible":        true,
					"candidate_body": "hidden candidate body",
				},
			},
		},
	}
	server := NewServer(Config{
		WriterStarter:         starter,
		LLMResolver:           boundWriterComposerResolver(),
		CharacterConsoleStore: store,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/chapter-drafts", strings.NewReader(`{
		"target_chapter_id":"chapter-9",
		"pov_mode":"first_person",
		"style_asset_ids":["style-1","style-2"],
		"author_instruction":"保持紧张感"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-convert-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "interaction-1" {
		t.Fatalf("chapter draft admission did not verify interaction scope: %#v", store.getInput)
	}
	if store.turnsInput.TenantID != "tenant-123" || store.turnsInput.InteractionID != "interaction-1" {
		t.Fatalf("chapter draft admission did not read turns in interaction scope: %#v", store.turnsInput)
	}
	if starter.input.TenantID != "tenant-123" ||
		starter.input.ProjectID != "project-123" ||
		starter.input.ActorUserID != "user-123" ||
		starter.input.RequestID != "req-convert-123" ||
		starter.input.Mode != "draft" ||
		starter.input.WorkflowType != workflows.WriterWorkflowType {
		t.Fatalf("writer run admission lost context: %#v", starter.input)
	}
	if !strings.Contains(starter.input.Instruction, "公开互动标题") ||
		!strings.Contains(starter.input.Instruction, "第一回合公开摘要") ||
		!strings.Contains(starter.input.Instruction, "第二回合公开摘要") ||
		!strings.Contains(starter.input.Instruction, "保持紧张感") {
		t.Fatalf("writer instruction did not include public interaction context: %q", starter.input.Instruction)
	}
	for _, forbidden := range []string{"hidden prompt", "sk-hidden", "credential_ref", "hidden-ref", "candidate body"} {
		if strings.Contains(starter.input.Instruction, forbidden) {
			t.Fatalf("writer instruction leaked forbidden value %q: %q", forbidden, starter.input.Instruction)
		}
	}
	if starter.input.Options["source"] != "character_console" ||
		starter.input.Options["character_interaction_id"] != "interaction-1" ||
		starter.input.Options["worldline_session_id"] != "session-1" ||
		starter.input.Options["target_chapter_id"] != "chapter-9" ||
		starter.input.Options["pov_mode"] != "first_person" ||
		starter.input.Options["module_key"] != "writer_composer" {
		t.Fatalf("writer options lost public conversion metadata: %#v", starter.input.Options)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"interaction_id":"interaction-1"`) ||
		!strings.Contains(body, `"run_id":"run_123"`) ||
		!strings.Contains(body, `"trace_id":"trace_123"`) ||
		!strings.Contains(body, `"workflow_type":"writer_run"`) ||
		!strings.Contains(body, `"status":"queued"`) {
		t.Fatalf("unexpected chapter draft admission response: %s", body)
	}
	if strings.Contains(body, "draft_id") || strings.Contains(body, "chapter_draft") {
		t.Fatalf("chapter draft admission response must not fabricate draft ids: %s", body)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, body)
}

func TestConvertCharacterInteractionToChapterDraftRequiresWriterBindingBeforeAdmission(t *testing.T) {
	starter := &recordingStarter{}
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Title:         "公开互动标题",
			Summary:       "公开互动摘要",
		},
		turns: []characterconsole.TurnRecord{{
			TurnID:        "turn-1",
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			TurnOrder:     1,
			ActorType:     "user",
			TurnKind:      "dialogue",
			Summary:       "公开回合",
		}},
	}
	server := NewServer(Config{
		WriterStarter:         starter,
		LLMResolver:           llm.NewStaticResolver(nil),
		CharacterConsoleStore: store,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/chapter-drafts", strings.NewReader(`{}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected missing writer binding to fail closed, got %d: %s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "LLM_MODULE_UNBOUND") {
		t.Fatalf("expected LLM binding failure, got %s", response.Body.String())
	}
	if starter.input.TenantID != "" {
		t.Fatalf("writer run admission must not start without a writer binding: %#v", starter.input)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, response.Body.String())
}

func TestConvertCharacterInteractionToChapterDraftRequiresPublicTurns(t *testing.T) {
	starter := &recordingStarter{}
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Title:         "公开互动标题",
			Summary:       "公开互动摘要",
		},
		turns: []characterconsole.TurnRecord{},
	}
	server := NewServer(Config{
		WriterStarter:         starter,
		LLMResolver:           boundWriterComposerResolver(),
		CharacterConsoleStore: store,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/chapter-drafts", strings.NewReader(`{
		"author_instruction":"不要凭空生成"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusConflict {
		t.Fatalf("expected missing public turns to fail as conflict, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "interaction-1" {
		t.Fatalf("chapter draft admission did not verify interaction scope: %#v", store.getInput)
	}
	if store.turnsInput.TenantID != "tenant-123" || store.turnsInput.InteractionID != "interaction-1" {
		t.Fatalf("chapter draft admission did not read public turns before failing: %#v", store.turnsInput)
	}
	if !strings.Contains(response.Body.String(), "CHARACTER_INTERACTION_TURNS_REQUIRED") {
		t.Fatalf("expected public turns required failure, got %s", response.Body.String())
	}
	if starter.input.TenantID != "" {
		t.Fatalf("writer run admission must not start without public turn material: %#v", starter.input)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, response.Body.String())
}

func TestConvertCharacterInteractionToChapterDraftRequiresPublicTurnSummaryMaterial(t *testing.T) {
	starter := &recordingStarter{}
	store := &recordingCharacterConsoleStore{
		interaction: characterconsole.InteractionRecord{
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			Title:         "公开互动标题",
			Summary:       "公开互动摘要",
		},
		turns: []characterconsole.TurnRecord{{
			TurnID:        "turn-1",
			InteractionID: "interaction-1",
			ProjectID:     "project-123",
			TurnOrder:     1,
			ActorType:     "user",
			TurnKind:      "dialogue",
			Summary:       "   ",
		}},
	}
	server := NewServer(Config{
		WriterStarter:         starter,
		LLMResolver:           boundWriterComposerResolver(),
		CharacterConsoleStore: store,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/character-interactions/interaction-1/chapter-drafts", strings.NewReader(`{
		"author_instruction":"不要用空白回合扩写"
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusConflict {
		t.Fatalf("expected blank public turn summaries to fail as conflict, got %d: %s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "CHARACTER_INTERACTION_TURNS_REQUIRED") {
		t.Fatalf("expected public turn summary material failure, got %s", response.Body.String())
	}
	if starter.input.TenantID != "" {
		t.Fatalf("writer run admission must not start without public turn summary material: %#v", starter.input)
	}
	assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t, response.Body.String())
}

func TestCharacterInteractionPendingRoutesReturnNotFoundForMissingInteraction(t *testing.T) {
	store := &recordingCharacterConsoleStore{
		err: &characterconsole.AppError{Code: "NOT_FOUND", Message: "character interaction was not found"},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, CharacterConsoleStore: store})
	request := httptest.NewRequest(http.MethodGet, "/v1/character-interactions/missing-interaction/events", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")

	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected missing interaction to return 404, got %d: %s", response.Code, response.Body.String())
	}
	if store.getInput.TenantID != "tenant-123" || store.getInput.InteractionID != "missing-interaction" {
		t.Fatalf("runtime pending route did not lookup missing interaction in tenant scope: %#v", store.getInput)
	}
	if !strings.Contains(response.Body.String(), "NOT_FOUND") {
		t.Fatalf("expected NOT_FOUND response, got %s", response.Body.String())
	}
	if strings.Contains(response.Body.String(), "CHARACTER_CONSOLE_RUNTIME_PENDING") {
		t.Fatalf("missing interaction must not be reported as runtime pending: %s", response.Body.String())
	}
}

func assertHTTPBodyHasNoSensitiveCharacterConsoleFields(t *testing.T, body string) {
	t.Helper()
	lower := strings.ToLower(body)
	for _, forbidden := range []string{
		"input_text",
		"output_text",
		"body_text",
		"content_text",
		"source_text",
		"source_material",
		"prompt",
		"response",
		"api_key",
		"encrypted_api_key",
		"credential_ref",
		"must be stripped",
		"candidate_body",
		"candidate_event_body",
		"event_body",
		"draft",
		"manuscript",
	} {
		if strings.Contains(lower, forbidden) {
			t.Fatalf("response leaked forbidden field/value %q: %s", forbidden, body)
		}
	}
}

func TestGetAssetUsesTenantAssetScopeAndSanitizedRow(t *testing.T) {
	reader := &recordingAssetReader{
		asset: assets.Record{
			AssetID:    "asset-1",
			ProjectID:  "project-123",
			Scope:      "project",
			AssetType:  "world_rule",
			Category:   "rule",
			Lifecycle:  "seed",
			Title:      "灵气规则",
			Summary:    "公开摘要",
			SourceKind: "seed_pipeline",
			SourceRef:  "world-rule-1",
			Enabled:    true,
			Pinned:     true,
			Tags:       []string{"世界"},
			Payload:    map[string]any{"world_rule_id": "world-rule-1"},
			CreatedAt:  "2026-07-04T00:00:00Z",
			UpdatedAt:  "2026-07-04T00:00:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/assets/asset-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.getInput.TenantID != "tenant-123" || reader.getInput.AssetID != "asset-1" {
		t.Fatalf("reader lost get scope: %#v", reader.getInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"asset_id":"asset-1"`) || !strings.Contains(body, `"title":"灵气规则"`) {
		t.Fatalf("unexpected asset detail: %s", body)
	}
	for _, forbidden := range []string{"content_text", "raw_payload_jsonb", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("asset detail leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListAssetFacetsUsesTenantProjectScopeAndSanitizedCounts(t *testing.T) {
	reader := &recordingAssetReader{
		facets: assets.Facets{
			AssetTypes: []assets.FacetBucket{{Value: "character", Count: 3}},
			Categories: []assets.FacetBucket{{Value: "entity", Count: 3}},
			Lifecycles: []assets.FacetBucket{{Value: "seed", Count: 5}},
			Sources:    []assets.FacetBucket{{Value: "seed_pipeline", Count: 5}},
			Tags:       []assets.FacetBucket{{Value: "主角", Count: 2}},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/assets/facets", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.facetsInput.TenantID != "tenant-123" || reader.facetsInput.ProjectID != "project-123" {
		t.Fatalf("reader lost facets scope: %#v", reader.facetsInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"asset_types":[{"value":"character","count":3}]`) || !strings.Contains(body, `"sources":[{"value":"seed_pipeline","count":5}]`) || !strings.Contains(body, `"tags":[{"value":"主角","count":2}]`) {
		t.Fatalf("unexpected asset facets: %s", body)
	}
	for _, forbidden := range []string{"content_text", "payload_jsonb", "raw_payload_jsonb", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("asset facets leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestSearchAssetsUsesTenantProjectQueryScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingAssetReader{
		searchResults: []assets.SearchRecord{{
			SearchDocumentID: "doc-1",
			Source:           "asset",
			SourceRef:        "asset-1",
			ProjectID:        "project-123",
			EntityType:       "world_rule",
			Title:            "灵气规则",
			Tags:             []string{"世界"},
			Payload:          map[string]any{"asset_id": "asset-1"},
			Version: assets.VersionSummary{
				Count:           2,
				LatestVersion:   3,
				LatestVersionID: "version-3",
			},
			Collections: []assets.CollectionRef{{
				CollectionID: "collection-1",
				Title:        "世界规则集",
				Lifecycle:    "canon",
			}},
			CreatedAt: "2026-07-04T00:00:00Z",
			UpdatedAt: "2026-07-04T00:00:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetReader: reader})
	request := httptest.NewRequest(http.MethodPost, "/v1/assets/search", strings.NewReader(`{"project_id":"project-123","query":"灵气"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.searchInput.TenantID != "tenant-123" || reader.searchInput.ProjectID != "project-123" || reader.searchInput.Query != "灵气" {
		t.Fatalf("reader lost search scope: %#v", reader.searchInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"search_document_id":"doc-1"`) || !strings.Contains(body, `"title":"灵气规则"`) {
		t.Fatalf("unexpected asset search: %s", body)
	}
	if strings.Contains(body, `"body"`) {
		t.Fatalf("asset search exposed body field: %s", body)
	}
	if !strings.Contains(body, `"version":{"count":2,"latest_version":3,"latest_version_id":"version-3"}`) ||
		!strings.Contains(body, `"collections":[{"collection_id":"collection-1","title":"世界规则集","lifecycle":"canon"}]`) {
		t.Fatalf("asset search omitted version/collection metadata: %s", body)
	}
	for _, forbidden := range []string{"raw_payload_jsonb", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("asset search leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListArchiveMemoriesUsesTenantProjectAssetScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingArchiveMemoryReader{
		memories: []assets.ArchiveMemoryRecord{{
			MemoryID:   "memory-1",
			AssetID:    "asset-1",
			ProjectID:  "project-123",
			MemoryType: "relationship",
			Status:     "candidate",
			Summary:    "公开记忆摘要",
			Payload:    map[string]any{"relationship_id": "rel-1"},
			SourceKind: "asset_ingestion",
			SourceRef:  "run-1:1",
			Enabled:    true,
			CreatedAt:  "2026-07-05T00:00:00Z",
			UpdatedAt:  "2026-07-05T00:00:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ArchiveMemoryReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/archive-assets/asset-1/memories?project_id=project-123", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.memoriesInput.TenantID != "tenant-123" || reader.memoriesInput.ProjectID != "project-123" || reader.memoriesInput.AssetID != "asset-1" {
		t.Fatalf("reader lost archive memory context: %#v", reader.memoriesInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"memory_id":"memory-1"`) || !strings.Contains(body, `"summary":"公开记忆摘要"`) {
		t.Fatalf("unexpected archive memory body: %s", body)
	}
	for _, forbidden := range []string{"content_text", "body_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("archive memory response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListArchiveMemoryEventsUsesTenantProjectAssetScopeAndSanitizedRows(t *testing.T) {
	reader := &recordingArchiveMemoryReader{
		events: []assets.ArchiveMemoryEventRecord{{
			EventID:   "event-1",
			MemoryID:  "memory-1",
			AssetID:   "asset-1",
			ProjectID: "project-123",
			EventType: "adoption_requested",
			Status:    "candidate",
			Payload:   map[string]any{"memory_id": "memory-1"},
			ActorID:   "user-123",
			CreatedAt: "2026-07-05T00:00:00Z",
		}},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ArchiveMemoryReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/archive-assets/asset-1/memory-events?project_id=project-123", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.eventsInput.TenantID != "tenant-123" || reader.eventsInput.ProjectID != "project-123" || reader.eventsInput.AssetID != "asset-1" {
		t.Fatalf("reader lost archive memory event context: %#v", reader.eventsInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"event_id":"event-1"`) || !strings.Contains(body, `"event_type":"adoption_requested"`) {
		t.Fatalf("unexpected archive memory event body: %s", body)
	}
	for _, forbidden := range []string{"content_text", "body_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("archive memory event response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestListArchiveMemoriesWithoutReaderFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/archive-assets/asset-1/memories?project_id=project-123", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestAdoptArchiveMemoryUsesTenantProjectActorRequestAndReturnsSanitizedMemory(t *testing.T) {
	store := &recordingArchiveMemoryReviewStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ArchiveMemoryReviewStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/archive-memories/memory-1/adoptions", strings.NewReader(`{"project_id":"project-123"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-memory-adopt")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.adoptInput.TenantID != "tenant-123" || store.adoptInput.ProjectID != "project-123" || store.adoptInput.MemoryID != "memory-1" {
		t.Fatalf("store lost archive memory adoption context: %#v", store.adoptInput)
	}
	if store.adoptInput.ActorID != "user-123" || store.adoptInput.RequestID != "req-memory-adopt" {
		t.Fatalf("store lost actor/request context: %#v", store.adoptInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"memory_id":"memory-1"`) || !strings.Contains(body, `"status":"canon"`) {
		t.Fatalf("unexpected archive memory adoption response: %s", body)
	}
	for _, forbidden := range []string{"content_text", "body_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("archive memory adoption response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestRejectArchiveMemoryUsesTenantProjectActorRequestAndReturnsSanitizedMemory(t *testing.T) {
	store := &recordingArchiveMemoryReviewStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ArchiveMemoryReviewStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/archive-memories/memory-1/rejections", strings.NewReader(`{"project_id":"project-123"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-memory-reject")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.rejectInput.TenantID != "tenant-123" || store.rejectInput.ProjectID != "project-123" || store.rejectInput.MemoryID != "memory-1" {
		t.Fatalf("store lost archive memory rejection context: %#v", store.rejectInput)
	}
	if store.rejectInput.ActorID != "user-123" || store.rejectInput.RequestID != "req-memory-reject" {
		t.Fatalf("store lost actor/request context: %#v", store.rejectInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"memory_id":"memory-1"`) || !strings.Contains(body, `"status":"rejected"`) {
		t.Fatalf("unexpected archive memory rejection response: %s", body)
	}
	for _, forbidden := range []string{"content_text", "body_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("archive memory rejection response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestAdoptArchiveMemoryFailsClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/archive-memories/memory-1/adoptions", strings.NewReader(`{"project_id":"project-123"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "ARCHIVE_MEMORY_REVIEW_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestPhase5ValidationErrorsDoNotEchoDecoderDetails(t *testing.T) {
	tests := []struct {
		name      string
		method    string
		path      string
		message   string
		requestID string
	}{
		{
			name:      "asset create",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/assets",
			message:   "invalid asset create payload",
			requestID: "req-asset-create-validation",
		},
		{
			name:      "asset search",
			method:    http.MethodPost,
			path:      "/v1/assets/search",
			message:   "invalid asset search payload",
			requestID: "req-asset-search-validation",
		},
		{
			name:      "archive memory review",
			method:    http.MethodPost,
			path:      "/v1/archive-memories/memory-1/adoptions",
			message:   "invalid archive memory review payload",
			requestID: "req-archive-memory-validation",
		},
		{
			name:      "asset bulk action",
			method:    http.MethodPost,
			path:      "/v1/assets/bulk-actions",
			message:   "invalid asset bulk action payload",
			requestID: "req-asset-bulk-validation",
		},
		{
			name:      "asset ingestion",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/asset-ingestions",
			message:   "invalid asset ingestion payload",
			requestID: "req-asset-ingestion-validation",
		},
		{
			name:      "style extraction",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/style-extractions",
			message:   "invalid style extraction payload",
			requestID: "req-style-extraction-validation",
		},
		{
			name:      "asset reindex",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/assets/reindex",
			message:   "invalid asset reindex payload",
			requestID: "req-asset-reindex-validation",
		},
		{
			name:      "story graph build",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/story-graph/builds",
			message:   "invalid story graph build payload",
			requestID: "req-story-graph-build-validation",
		},
		{
			name:      "story graph bond generation",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/story-graph/bond-generations",
			message:   "invalid story graph bond generation payload",
			requestID: "req-story-graph-bond-validation",
		},
		{
			name:      "asset adoption",
			method:    http.MethodPost,
			path:      "/v1/assets/asset-1/adoptions",
			message:   "invalid asset adoption payload",
			requestID: "req-asset-adoption-validation",
		},
		{
			name:      "asset patch",
			method:    http.MethodPatch,
			path:      "/v1/assets/asset-1",
			message:   "invalid asset patch payload",
			requestID: "req-asset-patch-validation",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := NewServer(Config{WriterStarter: &recordingStarter{}})
			request := httptest.NewRequest(tt.method, tt.path, strings.NewReader(`{
				"api_key":"sk-hidden",
				"prompt":"private",
				"credential_ref":"cred-hidden",
				"draft":"private",
				"manuscript":"private"
			}`))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Tenant-Id", "tenant-123")
			request.Header.Set("X-Request-Id", tt.requestID)
			response := httptest.NewRecorder()

			server.ServeHTTP(response, request)

			if response.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d: %s", response.Code, response.Body.String())
			}
			body := response.Body.String()
			if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) ||
				!strings.Contains(body, `"message":"`+tt.message+`"`) ||
				!strings.Contains(body, `"request_id":"`+tt.requestID+`"`) ||
				!strings.Contains(body, `"details":{}`) {
				t.Fatalf("expected stable phase 5 validation failure, got %s", body)
			}
			for _, forbidden := range []string{
				`"details":{"error"`,
				"json:",
				"api_key",
				"sk-hidden",
				"prompt",
				"credential_ref",
				"draft",
				"manuscript",
			} {
				if strings.Contains(body, forbidden) {
					t.Fatalf("phase 5 validation response leaked forbidden detail %q: %s", forbidden, body)
				}
			}
		})
	}
}

func TestAdoptAssetUsesTenantActorRequestAndReturnsSanitizedAsset(t *testing.T) {
	store := &recordingAssetAdoptionStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetAdoptionStore: store})
	request := httptest.NewRequest(http.MethodPost, "/v1/assets/asset-1/adoptions", strings.NewReader(`{"target_lifecycle":"canon"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-adopt")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.input.TenantID != "tenant-123" || store.input.AssetID != "asset-1" || store.input.TargetLifecycle != "canon" {
		t.Fatalf("store lost adoption scope: %#v", store.input)
	}
	if store.input.ActorID != "user-123" || store.input.RequestID != "req-adopt" {
		t.Fatalf("store lost actor/request context: %#v", store.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"asset_id":"asset-1"`) || !strings.Contains(body, `"lifecycle":"canon"`) {
		t.Fatalf("unexpected adoption response: %s", body)
	}
	for _, forbidden := range []string{"content_text", "material_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("asset adoption response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestAdoptAssetFailsClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/assets/asset-1/adoptions", strings.NewReader(`{"target_lifecycle":"canon"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "ASSET_ADOPTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestCreateAssetUsesTenantProjectActorRequestAndReturnsSanitizedAsset(t *testing.T) {
	store := &recordingAssetMutationStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetMutationStore: store})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/assets",
		strings.NewReader(`{"tenant_id":"tenant-body","scope":"project","asset_type":"note","category":"material","lifecycle":"material","title":"雨夜谈判素材","summary":"公开摘要","content_text":"私有正文","payload":{"tone":"压迫","api_key":"secret"},"tags":["谈判"],"source_kind":"manual","source_ref":"req-create","enabled":true,"pinned":false}`),
	)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-create")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("expected status %d, got %d: %s", http.StatusCreated, response.Code, response.Body.String())
	}
	if store.createInput.TenantID != "tenant-123" || store.createInput.ProjectID != "project-123" || store.createInput.ActorID != "user-123" || store.createInput.RequestID != "req-create" {
		t.Fatalf("unexpected create context: %#v", store.createInput)
	}
	if store.createInput.BodyTenantID == "tenant-123" || store.createInput.BodyTenantID != "tenant-body" {
		t.Fatalf("expected body tenant to be captured but not trusted, got %#v", store.createInput)
	}
	if store.createInput.ContentText != "私有正文" || store.createInput.Payload["api_key"] != nil {
		t.Fatalf("expected private content accepted and payload sanitized before store call, got %#v", store.createInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"asset_id":"asset-created"`) || !strings.Contains(body, `"title":"雨夜谈判素材"`) {
		t.Fatalf("unexpected create response: %s", body)
	}
	forbidden := []string{"content_text", "私有正文", "api_key", "encrypted_api_key", "credential_ref", "prompt", "response"}
	for _, field := range forbidden {
		if strings.Contains(body, field) {
			t.Fatalf("asset create response leaked forbidden field %q: %s", field, body)
		}
	}
}

func TestPatchAssetUsesTenantActorRequestAndReturnsSanitizedAsset(t *testing.T) {
	store := &recordingAssetMutationStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetMutationStore: store})
	request := httptest.NewRequest(
		http.MethodPatch,
		"/v1/assets/asset-1",
		strings.NewReader(`{"tenant_id":"tenant-body","title":"新标题","summary":"新摘要","lifecycle":"archived","content_text":"替换正文","payload":{"tone":"冷峻","prompt":"secret"},"tags":["更新"],"enabled":false,"pinned":true}`),
	)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-patch")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.patchInput.TenantID != "tenant-123" || store.patchInput.AssetID != "asset-1" || store.patchInput.ActorID != "user-123" || store.patchInput.RequestID != "req-patch" {
		t.Fatalf("unexpected patch context: %#v", store.patchInput)
	}
	if store.patchInput.BodyTenantID != "tenant-body" || store.patchInput.ContentText == nil || *store.patchInput.ContentText != "替换正文" {
		t.Fatalf("expected body tenant captured and private content accepted, got %#v", store.patchInput)
	}
	if _, ok := (*store.patchInput.Payload)["prompt"]; ok {
		t.Fatalf("expected payload sanitized before patch store call, got %#v", store.patchInput.Payload)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"asset_id":"asset-1"`) || !strings.Contains(body, `"lifecycle":"archived"`) {
		t.Fatalf("unexpected patch response: %s", body)
	}
	forbidden := []string{"content_text", "替换正文", "api_key", "encrypted_api_key", "credential_ref", "prompt", "response"}
	for _, field := range forbidden {
		if strings.Contains(body, field) {
			t.Fatalf("asset patch response leaked forbidden field %q: %s", field, body)
		}
	}
}

func TestDeleteAssetUsesTenantActorRequestAndReturnsSanitizedResult(t *testing.T) {
	store := &recordingAssetMutationStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetMutationStore: store})
	request := httptest.NewRequest(http.MethodDelete, "/v1/assets/asset-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-delete")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.deleteInput.TenantID != "tenant-123" || store.deleteInput.AssetID != "asset-1" || store.deleteInput.ActorID != "user-123" || store.deleteInput.RequestID != "req-delete" {
		t.Fatalf("unexpected delete context: %#v", store.deleteInput)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"asset_id":"asset-1"`) || !strings.Contains(body, `"deleted":true`) {
		t.Fatalf("unexpected delete response: %s", body)
	}
	forbidden := []string{"content_text", "payload", "api_key", "encrypted_api_key", "credential_ref", "prompt", "response"}
	for _, field := range forbidden {
		if strings.Contains(body, field) {
			t.Fatalf("asset delete response leaked forbidden field %q: %s", field, body)
		}
	}
}

func TestAssetMutationsFailClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	cases := []struct {
		method string
		path   string
		body   string
	}{
		{method: http.MethodPost, path: "/v1/projects/project-123/assets", body: `{"asset_type":"note","title":"素材"}`},
		{method: http.MethodPatch, path: "/v1/assets/asset-1", body: `{"title":"新标题"}`},
		{method: http.MethodDelete, path: "/v1/assets/asset-1"},
	}
	for _, testCase := range cases {
		request := httptest.NewRequest(testCase.method, testCase.path, strings.NewReader(testCase.body))
		request.Header.Set("X-Tenant-Id", "tenant-123")
		response := httptest.NewRecorder()

		server.ServeHTTP(response, request)

		if response.Code != http.StatusServiceUnavailable {
			t.Fatalf("%s %s: expected fail-closed status, got %d: %s", testCase.method, testCase.path, response.Code, response.Body.String())
		}
		if !strings.Contains(response.Body.String(), "ASSET_MUTATION_BACKEND_UNCONFIGURED") {
			t.Fatalf("%s %s: expected explicit mutation backend error, got %s", testCase.method, testCase.path, response.Body.String())
		}
	}
}

func TestBulkAssetActionUsesTenantProjectActorRequestAndReturnsSanitizedResult(t *testing.T) {
	store := &recordingAssetBulkActionStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetBulkActionStore: store})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/assets/bulk-actions",
		strings.NewReader(`{"tenant_id":"body-tenant","project_id":"project-123","action":"set_lifecycle","asset_ids":["asset-1","asset-2"],"target_lifecycle":"archived","category":"secret-category","payload":{"prompt":"secret","api_key":"secret-key"}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-bulk")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if store.input.TenantID != "tenant-123" || store.input.ProjectID != "project-123" {
		t.Fatalf("store lost tenant/project context: %#v", store.input)
	}
	if store.input.BodyTenantID != "body-tenant" || store.input.ActorID != "user-123" || store.input.RequestID != "req-bulk" {
		t.Fatalf("store lost body tenant or actor/request context: %#v", store.input)
	}
	if store.input.Action != "set_lifecycle" || store.input.TargetLifecycle != "archived" || len(store.input.AssetIDs) != 2 {
		t.Fatalf("store lost bulk action payload: %#v", store.input)
	}
	if _, ok := store.input.Payload["prompt"]; ok {
		t.Fatalf("expected bulk action payload to be sanitized before store call, got %#v", store.input.Payload)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"project_id":"project-123"`) || !strings.Contains(body, `"action":"set_lifecycle"`) || !strings.Contains(body, `"status":"accepted"`) {
		t.Fatalf("unexpected bulk action response: %s", body)
	}
	for _, forbidden := range []string{"asset-1", "asset-2", "secret-category", "target_lifecycle", "prompt", "api_key", "encrypted_api_key", "credential_ref", "content_text", "material_text"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("bulk action response leaked forbidden value %q: %s", forbidden, body)
		}
	}
}

func TestBulkAssetActionFailsClosedWithoutConfiguredStore(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/assets/bulk-actions",
		strings.NewReader(`{"project_id":"project-123","action":"disable","asset_ids":["asset-1"],"payload":{"content_text":"private","credential_ref":"cred-1"}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "ASSET_BULK_ACTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
	for _, forbidden := range []string{"asset-1", "private", "credential_ref", "cred-1", "content_text"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("bulk action failure leaked forbidden value %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartAssetIngestionCarriesTenantProjectActorRequestAndMaterialContext(t *testing.T) {
	starter := &recordingAssetIngestionStarter{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetIngestionStarter: starter})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/asset-ingestions",
		strings.NewReader(`{"tenant_id":"evil-tenant","material_text":"灵气不可凭空生成。","hint_type":"world_rule","scope":"project","options":{"language":"zh-CN"}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-ingest")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter lost tenant/project context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req-ingest" {
		t.Fatalf("starter lost actor/request context: %#v", starter.input)
	}
	if starter.input.MaterialText != "灵气不可凭空生成。" || starter.input.HintType != "world_rule" || starter.input.Scope != "project" {
		t.Fatalf("starter lost ingestion payload: %#v", starter.input)
	}
	if starter.input.Options["language"] != "zh-CN" {
		t.Fatalf("starter lost options: %#v", starter.input.Options)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "asset-ingestion-run-123" || body["project_id"] != "project-123" || body["workflow_type"] != workflows.AssetIngestionWorkflowType || body["status"] != "queued" {
		t.Fatalf("unexpected ingestion response: %#v", body)
	}
	for _, forbidden := range []string{"material_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("asset ingestion response leaked forbidden field %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartAssetIngestionFailsClosedWithoutConfiguredStarter(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/asset-ingestions", strings.NewReader(`{"material_text":"素材","hint_type":"note"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "ASSET_INGESTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestGetAssetIngestionUsesTenantRunScopeAndPublicWorkflowMetadata(t *testing.T) {
	reader := &recordingAssetIngestionReader{
		run: workflows.WorkflowRun{
			RunID:        "ingestion-run-123",
			WorkflowType: workflows.AssetIngestionWorkflowType,
			ProjectID:    "project-123",
			Status:       "failed",
			Progress:     20,
			Message:      "waiting for asset ingestion backend",
			ErrorCode:    "ASSET_INGESTION_BACKEND_UNCONFIGURED",
			ErrorMessage: "asset ingestion backend is not configured",
			CreatedAt:    "2026-07-04T00:00:00Z",
			UpdatedAt:    "2026-07-04T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetIngestionReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/asset-ingestions/ingestion-run-123", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.RunID != "ingestion-run-123" {
		t.Fatalf("reader lost tenant/run scope: %#v", reader.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"workflow_type":"asset_ingestion"`) || !strings.Contains(body, `"status":"failed"`) {
		t.Fatalf("unexpected asset ingestion detail: %s", body)
	}
	for _, forbidden := range []string{"material_text", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("asset ingestion detail leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestStartStyleExtractionCarriesTenantProjectActorRequestAndSourceContext(t *testing.T) {
	starter := &recordingStyleExtractionStarter{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StyleExtractionStarter: starter})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/style-extractions",
		strings.NewReader(`{"tenant_id":"evil-tenant","material_text":"这是作者风格样本文本。","source_asset_id":"asset-source-1","scope":"project","options":{"language":"zh-CN","prompt":"secret"}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-style")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter lost tenant/project context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req-style" {
		t.Fatalf("starter lost actor/request context: %#v", starter.input)
	}
	if starter.input.MaterialText != "这是作者风格样本文本。" || starter.input.SourceAssetID != "asset-source-1" || starter.input.Scope != "project" {
		t.Fatalf("starter lost style extraction payload: %#v", starter.input)
	}
	if starter.input.Options["language"] != "zh-CN" {
		t.Fatalf("starter lost options: %#v", starter.input.Options)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "style-extraction-run-123" || body["project_id"] != "project-123" || body["workflow_type"] != workflows.StyleExtractionWorkflowType || body["status"] != "queued" {
		t.Fatalf("unexpected style extraction response: %#v", body)
	}
	for _, forbidden := range []string{"material_text", "作者风格", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "source_asset_id"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("style extraction response leaked forbidden field %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartStyleExtractionFailsClosedWithoutConfiguredStarter(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/style-extractions", strings.NewReader(`{"material_text":"风格样本"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "STYLE_EXTRACTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestGetStyleExtractionUsesTenantRunScopeAndPublicWorkflowMetadata(t *testing.T) {
	reader := &recordingStyleExtractionReader{
		run: workflows.WorkflowRun{
			RunID:        "style-run-123",
			WorkflowType: workflows.StyleExtractionWorkflowType,
			ProjectID:    "project-123",
			Status:       "failed",
			Progress:     20,
			Message:      "waiting for style extraction backend",
			ErrorCode:    "STYLE_EXTRACTION_BACKEND_UNCONFIGURED",
			ErrorMessage: "style extraction backend is not configured",
			CreatedAt:    "2026-07-05T00:00:00Z",
			UpdatedAt:    "2026-07-05T00:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StyleExtractionReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/style-extractions/style-run-123", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.RunID != "style-run-123" {
		t.Fatalf("reader lost tenant/run scope: %#v", reader.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"workflow_type":"style_extraction"`) || !strings.Contains(body, `"status":"failed"`) {
		t.Fatalf("unexpected style extraction detail: %s", body)
	}
	for _, forbidden := range []string{"material_text", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("style extraction detail leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestStartAssetReindexCarriesTenantProjectActorRequestAndOptionsContext(t *testing.T) {
	starter := &recordingAssetReindexStarter{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, AssetReindexStarter: starter})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/assets/reindex",
		strings.NewReader(`{"tenant_id":"evil-tenant","scope":"project","mode":"keyword","options":{"reason":"manual","prompt":"secret"}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-reindex")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter lost tenant/project context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req-reindex" {
		t.Fatalf("starter lost actor/request context: %#v", starter.input)
	}
	if starter.input.Scope != "project" || starter.input.Mode != "keyword" {
		t.Fatalf("starter lost reindex payload: %#v", starter.input)
	}
	if starter.input.Options["reason"] != "manual" {
		t.Fatalf("starter lost sanitized options: %#v", starter.input.Options)
	}
	if _, ok := starter.input.Options["prompt"]; ok {
		t.Fatalf("starter retained forbidden option: %#v", starter.input.Options)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "asset-reindex-run-123" || body["project_id"] != "project-123" || body["workflow_type"] != workflows.AssetReindexWorkflowType || body["status"] != "queued" {
		t.Fatalf("unexpected reindex response: %#v", body)
	}
	for _, forbidden := range []string{"tenant_id", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("asset reindex response leaked forbidden field %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartAssetReindexFailsClosedWithoutConfiguredStarter(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/assets/reindex", strings.NewReader(`{"scope":"project","mode":"keyword"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "ASSET_REINDEX_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestStartStoryGraphBuildCarriesTenantProjectActorRequestAndOptionsContext(t *testing.T) {
	starter := &recordingStoryGraphBuildStarter{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphBuildStarter: starter})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/story-graph/builds",
		strings.NewReader(`{"tenant_id":"evil-tenant","mode":"full","options":{"source":"seed_canon","prompt":"secret","nested":{"content":"hidden"}}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-story-graph")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter lost tenant/project context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req-story-graph" || starter.input.Mode != "full" {
		t.Fatalf("starter lost actor/request/build context: %#v", starter.input)
	}
	if starter.input.Options["source"] != "seed_canon" {
		t.Fatalf("starter lost sanitized options: %#v", starter.input.Options)
	}
	if _, ok := starter.input.Options["prompt"]; ok {
		t.Fatalf("starter retained forbidden option: %#v", starter.input.Options)
	}
	if nested, ok := starter.input.Options["nested"].(map[string]any); !ok || len(nested) != 0 {
		t.Fatalf("starter did not sanitize nested options: %#v", starter.input.Options)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "story-graph-run-123" || body["project_id"] != "project-123" || body["workflow_type"] != workflows.StoryGraphBuildWorkflowType || body["status"] != "queued" {
		t.Fatalf("unexpected story graph build response: %#v", body)
	}
	for _, forbidden := range []string{"tenant_id", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("story graph build response leaked forbidden field %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartStoryGraphBuildFailsClosedWithoutConfiguredStarter(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/story-graph/builds", strings.NewReader(`{"mode":"full"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "STORY_GRAPH_BUILD_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestStartStoryGraphBondGenerationCarriesTenantProjectActorRequestSelectionAndOptionsContext(t *testing.T) {
	starter := &recordingStoryGraphBondGenerationStarter{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphBondGenerationStarter: starter})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/story-graph/bond-generations",
		strings.NewReader(`{"tenant_id":"evil-tenant","graph_id":"graph-123","node_ids":["node-1"," node-2 ",""],"focus":"rain treaty","options":{"generate_bonds":true,"generate_threads":true,"prompt":"secret","nested":{"content":"hidden"}}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-story-graph-bond")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter lost tenant/project context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req-story-graph-bond" {
		t.Fatalf("starter lost actor/request context: %#v", starter.input)
	}
	if starter.input.GraphID != "graph-123" || strings.Join(starter.input.NodeIDs, ",") != "node-1,node-2" || starter.input.Focus != "rain treaty" {
		t.Fatalf("starter lost graph selection context: %#v", starter.input)
	}
	if starter.input.Options["generate_bonds"] != true || starter.input.Options["generate_threads"] != true {
		t.Fatalf("starter lost sanitized generation options: %#v", starter.input.Options)
	}
	if _, ok := starter.input.Options["prompt"]; ok {
		t.Fatalf("starter retained forbidden option: %#v", starter.input.Options)
	}
	if nested, ok := starter.input.Options["nested"].(map[string]any); !ok || len(nested) != 0 {
		t.Fatalf("starter did not sanitize nested options: %#v", starter.input.Options)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "story-graph-bond-run-123" || body["project_id"] != "project-123" || body["workflow_type"] != workflows.StoryGraphBondGenerationWorkflowType || body["status"] != "queued" {
		t.Fatalf("unexpected story graph bond response: %#v", body)
	}
	for _, forbidden := range []string{"tenant_id", "node_ids", "graph_id", "focus", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("story graph bond response leaked forbidden field %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartStoryGraphBondGenerationFailsClosedWithoutConfiguredStarter(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/story-graph/bond-generations", strings.NewReader(`{"node_ids":["node-1","node-2"],"options":{"generate_bonds":true}}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "STORY_GRAPH_BOND_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestGetStoryGraphCurrentUsesTenantProjectScopeAndPublicSnapshotMetadata(t *testing.T) {
	reader := &recordingStoryGraphReader{
		current: storygraph.CurrentSnapshot{
			GraphID:           "graph-123",
			ProjectID:         "project-123",
			Version:           7,
			Status:            "ready",
			BuildRunID:        "run-graph-build",
			SourceVersionHash: "hash-public",
			NodeCount:         12,
			EdgeCount:         34,
			CreatedAt:         "2026-07-05T10:00:00Z",
			UpdatedAt:         "2026-07-05T10:01:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/story-graph/current", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.ProjectID != "project-123" {
		t.Fatalf("reader lost tenant/project scope: %#v", reader.input)
	}
	body := response.Body.String()
	for _, expected := range []string{`"graph_id":"graph-123"`, `"version":7`, `"node_count":12`, `"edge_count":34`} {
		if !strings.Contains(body, expected) {
			t.Fatalf("current graph response missing %s: %s", expected, body)
		}
	}
	for _, forbidden := range []string{"snippet", "raw_text", "seed analysis body", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("current graph response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestGetStoryGraphCurrentFailsClosedWithoutConfiguredReader(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/story-graph/current", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "STORY_GRAPH_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestGetStoryGraphViewUsesTenantProjectScopeAndSanitizesPayload(t *testing.T) {
	reader := &recordingStoryGraphReader{
		view: storygraph.GraphView{
			ViewID:    "world",
			GraphID:   "graph-123",
			ProjectID: "project-123",
			Limit:     50,
			Nodes: []storygraph.GraphNodeSummary{{
				NodeID:        "node-1",
				GraphID:       "graph-123",
				ProjectID:     "project-123",
				NodeType:      "character",
				Title:         "Ari",
				Summary:       "public summary",
				Lifecycle:     "canon",
				Importance:    0.9,
				Attributes:    map[string]any{"color": "blue"},
				EvidenceCount: 2,
				CreatedAt:     "2026-07-05T10:00:00Z",
				UpdatedAt:     "2026-07-05T10:01:00Z",
			}},
			Edges: []storygraph.GraphEdgeSummary{{
				EdgeID:        "edge-1",
				GraphID:       "graph-123",
				ProjectID:     "project-123",
				SourceNodeID:  "node-1",
				TargetNodeID:  "node-2",
				EdgeType:      "relationship",
				Label:         "ally",
				Summary:       "public relation",
				Weight:        1.5,
				Lifecycle:     "canon",
				Attributes:    map[string]any{"tone": "warm"},
				EvidenceCount: 3,
				CreatedAt:     "2026-07-05T10:00:00Z",
				UpdatedAt:     "2026-07-05T10:01:00Z",
			}},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/story-graph/views/world?limit=50&types=character,organization&include_edges=true", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.viewInput.TenantID != "tenant-123" || reader.viewInput.ProjectID != "project-123" || reader.viewInput.ViewID != "world" {
		t.Fatalf("reader lost view context: %#v", reader.viewInput)
	}
	if reader.viewInput.Limit != 50 || !reader.viewInput.IncludeEdges || strings.Join(reader.viewInput.Types, ",") != "character,organization" {
		t.Fatalf("reader lost query options: %#v", reader.viewInput)
	}
	body := response.Body.String()
	for _, expected := range []string{`"view_id":"world"`, `"node_id":"node-1"`, `"edge_id":"edge-1"`, `"color":"blue"`} {
		if !strings.Contains(body, expected) {
			t.Fatalf("view response missing %s: %s", expected, body)
		}
	}
	for _, forbidden := range []string{"snippet", "raw_text", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("view response leaked forbidden field %q: %s", forbidden, body)
		}
	}
}

func TestGetStoryGraphNodeAndEdgeUseTenantProjectScope(t *testing.T) {
	reader := &recordingStoryGraphReader{
		node: storygraph.GraphNodeDetail{
			Node: storygraph.GraphNodeSummary{
				NodeID:    "node-1",
				GraphID:   "graph-123",
				ProjectID: "project-123",
				NodeType:  "character",
				Title:     "Ari",
				Lifecycle: "canon",
			},
			Aliases: []string{"A"},
			Labels:  []string{"protagonist"},
		},
		edge: storygraph.GraphEdgeDetail{
			Edge: storygraph.GraphEdgeSummary{
				EdgeID:       "edge-1",
				GraphID:      "graph-123",
				ProjectID:    "project-123",
				SourceNodeID: "node-1",
				TargetNodeID: "node-2",
				EdgeType:     "relationship",
				Label:        "ally",
				Lifecycle:    "canon",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphReader: reader})

	nodeRequest := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/story-graph/nodes/node-1", nil)
	nodeRequest.Header.Set("X-Tenant-Id", "tenant-123")
	nodeResponse := httptest.NewRecorder()
	server.ServeHTTP(nodeResponse, nodeRequest)
	if nodeResponse.Code != http.StatusOK {
		t.Fatalf("expected node status %d, got %d: %s", http.StatusOK, nodeResponse.Code, nodeResponse.Body.String())
	}
	if reader.nodeInput.TenantID != "tenant-123" || reader.nodeInput.ProjectID != "project-123" || reader.nodeInput.NodeID != "node-1" {
		t.Fatalf("reader lost node context: %#v", reader.nodeInput)
	}
	if !strings.Contains(nodeResponse.Body.String(), `"aliases":["A"]`) || strings.Contains(nodeResponse.Body.String(), "snippet") {
		t.Fatalf("unexpected node body: %s", nodeResponse.Body.String())
	}

	edgeRequest := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/story-graph/edges/edge-1", nil)
	edgeRequest.Header.Set("X-Tenant-Id", "tenant-123")
	edgeResponse := httptest.NewRecorder()
	server.ServeHTTP(edgeResponse, edgeRequest)
	if edgeResponse.Code != http.StatusOK {
		t.Fatalf("expected edge status %d, got %d: %s", http.StatusOK, edgeResponse.Code, edgeResponse.Body.String())
	}
	if reader.edgeInput.TenantID != "tenant-123" || reader.edgeInput.ProjectID != "project-123" || reader.edgeInput.EdgeID != "edge-1" {
		t.Fatalf("reader lost edge context: %#v", reader.edgeInput)
	}
	if !strings.Contains(edgeResponse.Body.String(), `"edge_id":"edge-1"`) || strings.Contains(edgeResponse.Body.String(), "credential_ref") {
		t.Fatalf("unexpected edge body: %s", edgeResponse.Body.String())
	}
}

func TestGetStoryGraphEvidenceLayoutAndClustersRoutesArePublicReadSide(t *testing.T) {
	reader := &recordingStoryGraphReader{
		evidence: storygraph.GraphEvidence{
			GraphID:   "graph-123",
			ProjectID: "project-123",
			OwnerType: "node",
			OwnerID:   "node-1",
			Limit:     25,
			Items: []storygraph.GraphEvidenceRecord{{
				EvidenceID: "evidence-1",
				GraphID:    "graph-123",
				ProjectID:  "project-123",
				OwnerType:  "node",
				OwnerID:    "node-1",
				SourceType: "segment",
				SourceID:   "segment-1",
				Confidence: 0.8,
				CreatedAt:  "2026-07-05T10:00:00Z",
				UpdatedAt:  "2026-07-05T10:01:00Z",
			}},
		},
		layout: storygraph.GraphLayout{
			GraphID:   "graph-123",
			ProjectID: "project-123",
			ViewID:    "world",
			Layout:    map[string]any{"engine": "dagre"},
			CreatedAt: "2026-07-05T10:00:00Z",
			UpdatedAt: "2026-07-05T10:01:00Z",
		},
		clusters: storygraph.GraphClusters{
			GraphID:   "graph-123",
			ProjectID: "project-123",
			Limit:     10,
			Items: []storygraph.GraphClusterRecord{{
				ClusterID:  "cluster-1",
				GraphID:    "graph-123",
				ProjectID:  "project-123",
				ClusterKey: "main",
				Title:      "Main cast",
				NodeCount:  4,
				Payload:    map[string]any{"tone": "public"},
				CreatedAt:  "2026-07-05T10:00:00Z",
				UpdatedAt:  "2026-07-05T10:01:00Z",
			}},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphReader: reader})

	requests := []struct {
		path     string
		expected string
	}{
		{path: "/v1/projects/project-123/story-graph/nodes/node-1/evidence?limit=25", expected: `"evidence_id":"evidence-1"`},
		{path: "/v1/projects/project-123/story-graph/edges/edge-1/evidence", expected: `"source_type":"segment"`},
		{path: "/v1/projects/project-123/story-graph/layouts/world", expected: `"engine":"dagre"`},
		{path: "/v1/projects/project-123/story-graph/clusters?limit=10", expected: `"cluster_key":"main"`},
	}
	for _, item := range requests {
		request := httptest.NewRequest(http.MethodGet, item.path, nil)
		request.Header.Set("X-Tenant-Id", "tenant-123")
		response := httptest.NewRecorder()

		server.ServeHTTP(response, request)

		if response.Code != http.StatusOK {
			t.Fatalf("expected %s to return status %d, got %d: %s", item.path, http.StatusOK, response.Code, response.Body.String())
		}
		if !strings.Contains(response.Body.String(), item.expected) {
			t.Fatalf("%s missing expected public field %s: %s", item.path, item.expected, response.Body.String())
		}
		for _, forbidden := range []string{"snippet", "raw_text", "prompt", "response", "body", "content", "api_key", "encrypted_api_key", "credential_ref"} {
			if strings.Contains(response.Body.String(), forbidden) {
				t.Fatalf("%s leaked forbidden field %q: %s", item.path, forbidden, response.Body.String())
			}
		}
	}
	if reader.evidenceInput.TenantID != "tenant-123" || reader.evidenceInput.ProjectID != "project-123" || reader.evidenceInput.OwnerType != "edge" || reader.evidenceInput.OwnerID != "edge-1" {
		t.Fatalf("reader lost evidence context: %#v", reader.evidenceInput)
	}
	if reader.layoutInput.TenantID != "tenant-123" || reader.layoutInput.ProjectID != "project-123" || reader.layoutInput.ViewID != "world" {
		t.Fatalf("reader lost layout context: %#v", reader.layoutInput)
	}
	if reader.clustersInput.TenantID != "tenant-123" || reader.clustersInput.ProjectID != "project-123" || reader.clustersInput.Limit != 10 {
		t.Fatalf("reader lost cluster context: %#v", reader.clustersInput)
	}
}

func TestGetStoryGraphEvidenceFullSnippetRequiresPermission(t *testing.T) {
	reader := &recordingStoryGraphReader{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/story-graph/nodes/node-1/evidence?include_full=true", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden {
		t.Fatalf("expected status %d, got %d: %s", http.StatusForbidden, response.Code, response.Body.String())
	}
	if reader.evidenceInput.OwnerID != "" {
		t.Fatalf("reader should not be called before evidence snippet permission: %#v", reader.evidenceInput)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "STORY_GRAPH_EVIDENCE_ACCESS_DENIED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestGetStoryGraphEvidenceFullSnippetWhenAuthorized(t *testing.T) {
	reader := &recordingStoryGraphReader{
		evidence: storygraph.GraphEvidence{
			GraphID:   "graph-123",
			ProjectID: "project-123",
			OwnerType: "node",
			OwnerID:   "node-1",
			Limit:     25,
			Items: []storygraph.GraphEvidenceRecord{{
				EvidenceID: "evidence-1",
				GraphID:    "graph-123",
				ProjectID:  "project-123",
				OwnerType:  "node",
				OwnerID:    "node-1",
				SourceType: "segment",
				SourceID:   "segment-1",
				Snippet:    "雨夜谈判原文证据",
				Confidence: 0.8,
				CreatedAt:  "2026-07-05T10:00:00Z",
				UpdatedAt:  "2026-07-05T10:01:00Z",
			}},
		},
	}
	access := &allowStoryGraphEvidenceAccessChecker{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, StoryGraphReader: reader, StoryGraphEvidenceAccess: access})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/story-graph/nodes/node-1/evidence?include_full=true&limit=25", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if !reader.evidenceInput.IncludeSnippet {
		t.Fatalf("expected reader to receive IncludeSnippet=true: %#v", reader.evidenceInput)
	}
	if access.input.TenantID != "tenant-123" || access.input.ProjectID != "project-123" || access.input.OwnerType != "node" || access.input.OwnerID != "node-1" || access.input.ActorID != "user-123" {
		t.Fatalf("access checker lost context: %#v", access.input)
	}
	if !strings.Contains(response.Body.String(), "雨夜谈判原文证据") {
		t.Fatalf("expected authorized snippet in response: %s", response.Body.String())
	}
}

func TestStartSeedRunCarriesTenantProjectUploadActorAndRequestContext(t *testing.T) {
	starter := &recordingSeedStarter{}
	sourceStore := &recordingSourceFileStore{
		validated: sourcefiles.ValidatedSourceFile{
			FileID:      "file-123",
			UploadID:    "upload-123",
			ProjectID:   "project-123",
			ObjectKey:   "projects/project-123/source-files/upload-123/book.txt",
			Filename:    "book.txt",
			MimeType:    "text/plain",
			SizeBytes:   2048,
			SHA256:      "abc123",
			ParseStatus: "uploaded",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: starter, SourceFileStore: sourceStore})
	requestBody := bytes.NewBufferString(`{
		"tenant_id":"evil-tenant",
		"upload_id":"upload-123",
		"options":{
			"language":"zh-CN",
			"analysis_depth":"standard",
			"tenant_id":"evil-option-tenant",
			"project_id":"evil-option-project",
			"prompt":"private prompt",
			"source_material":"private source",
			"draft":"private draft",
			"metadata":{"safe":"keep","api_key":"sk-private","credential_ref":"cred-private"}
		}
	}`)
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", requestBody)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-seed")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" || starter.input.UploadID != "upload-123" {
		t.Fatalf("starter lost tenant/project/upload context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req-seed" {
		t.Fatalf("starter lost actor/request context: %#v", starter.input)
	}
	if starter.input.SourceFileID != "file-123" ||
		starter.input.SourceObjectKey != "projects/project-123/source-files/upload-123/book.txt" ||
		starter.input.SourceFilename != "book.txt" ||
		starter.input.SourceMimeType != "text/plain" ||
		starter.input.SourceSizeBytes != 2048 ||
		starter.input.SourceSHA256 != "abc123" {
		t.Fatalf("starter did not receive internal source metadata: %#v", starter.input)
	}
	if starter.input.Options["language"] != "zh-CN" || starter.input.Options["analysis_depth"] != "standard" {
		t.Fatalf("starter lost seed options: %#v", starter.input.Options)
	}
	for _, forbidden := range []string{"tenant_id", "project_id", "prompt", "source_material", "draft"} {
		if _, exists := starter.input.Options[forbidden]; exists {
			t.Fatalf("seed options retained forbidden field %q: %#v", forbidden, starter.input.Options)
		}
	}
	metadata, ok := starter.input.Options["metadata"].(map[string]any)
	if !ok || metadata["safe"] != "keep" {
		t.Fatalf("starter lost safe seed metadata: %#v", starter.input.Options)
	}
	for _, forbidden := range []string{"api_key", "credential_ref"} {
		if _, exists := metadata[forbidden]; exists {
			t.Fatalf("seed options retained forbidden nested field %q: %#v", forbidden, starter.input.Options)
		}
	}
	if sourceStore.validateInput.TenantID != "tenant-123" || sourceStore.validateInput.ProjectID != "project-123" || sourceStore.validateInput.UploadID != "upload-123" {
		t.Fatalf("seed run did not validate source file scope: %#v", sourceStore.validateInput)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "seed-run-123" || body["project_id"] != "project-123" || body["workflow_type"] != workflows.SeedWorkflowType || body["status"] != "queued" {
		t.Fatalf("unexpected seed response: %#v", body)
	}
	for _, forbidden := range []string{"object_key", "source_object_key", "source_file_id", "source_sha256"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("seed start response leaked internal source metadata %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartSeedRunSanitizesSensitiveRequestIDBeforeStarter(t *testing.T) {
	starter := &recordingSeedStarter{}
	sourceStore := &recordingSourceFileStore{
		validated: sourcefiles.ValidatedSourceFile{
			FileID:      "file-123",
			UploadID:    "upload-123",
			ProjectID:   "project-123",
			ObjectKey:   "projects/project-123/source-files/upload-123/book.txt",
			Filename:    "book.txt",
			MimeType:    "text/plain",
			SizeBytes:   2048,
			SHA256:      "abc123",
			ParseStatus: "uploaded",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: starter, SourceFileStore: sourceStore})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", strings.NewReader(`{"upload_id":"upload-123"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-123/source-files/upload-123/book.txt draft=private manuscript=private")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.RequestID == "" {
		t.Fatal("expected seed starter to receive a replacement request id")
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-123/source-files", "draft", "manuscript"} {
		if strings.Contains(starter.input.RequestID, forbidden) {
			t.Fatalf("seed starter request id leaked forbidden text %q: %s", forbidden, starter.input.RequestID)
		}
	}
}

func TestErrorEnvelopeSanitizesSensitiveRequestIDHeader(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: &recordingSeedStarter{}, SourceFileStore: &recordingSourceFileStore{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", strings.NewReader(`{
		"upload_id":"upload-123",
		"api_key":"sk-hidden"
	}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-123/source-files/upload-123/book.txt draft=private manuscript=private")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d: %s", http.StatusBadRequest, response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) || !strings.Contains(body, `"message":"invalid seed run payload"`) {
		t.Fatalf("expected stable validation response, got %s", body)
	}
	if !strings.Contains(body, `"request_id":"`) {
		t.Fatalf("expected request id in error envelope, got %s", body)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-123/source-files", "draft", "manuscript"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("error envelope request id leaked forbidden text %q: %s", forbidden, body)
		}
	}
}

func TestStartSeedRunValidationErrorDoesNotEchoSensitiveUnknownField(t *testing.T) {
	starter := &recordingSeedStarter{}
	sourceStore := &recordingSourceFileStore{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: starter, SourceFileStore: sourceStore})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", strings.NewReader(`{
		"upload_id":"upload-123",
		"api_key":"sk-hidden"
	}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-seed-validation")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) ||
		!strings.Contains(body, `"message":"invalid seed run payload"`) ||
		!strings.Contains(body, `"request_id":"req-seed-validation"`) {
		t.Fatalf("expected stable seed validation failure, got %s", body)
	}
	for _, forbidden := range []string{"api_key", "sk-hidden", "prompt", "credential_ref", "draft", "manuscript"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("seed validation response leaked forbidden field/value %q: %s", forbidden, body)
		}
	}
	if starter.input.TenantID != "" || sourceStore.validateInput.TenantID != "" {
		t.Fatalf("validation failure should stop before source validation or seed starter: %#v %#v", sourceStore.validateInput, starter.input)
	}
}

func TestStartSeedRunSanitizesSourceFileValidationErrorAtHTTPBoundary(t *testing.T) {
	starter := &recordingSeedStarter{}
	sourceStore := &recordingSourceFileStore{
		validateErr: sourcefiles.NewAppError("SOURCE_FILE_QUERY_FAILED", "driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-123/source-files/upload-123/book.txt"),
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: starter, SourceFileStore: sourceStore})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", strings.NewReader(`{"upload_id":"upload-123"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-seed-source-validation")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if sourceStore.validateInput.TenantID != "tenant-123" ||
		sourceStore.validateInput.ProjectID != "project-123" ||
		sourceStore.validateInput.UploadID != "upload-123" {
		t.Fatalf("seed source validation lost trusted context: %#v", sourceStore.validateInput)
	}
	if starter.input.TenantID != "" {
		t.Fatalf("seed starter should not run after source file validation failure: %#v", starter.input)
	}
	body := response.Body.String()
	if !strings.Contains(body, `"code":"SOURCE_FILE_QUERY_FAILED"`) ||
		!strings.Contains(body, `"message":"source file query failed"`) ||
		!strings.Contains(body, `"request_id":"req-seed-source-validation"`) {
		t.Fatalf("expected stable source file error response, got %s", body)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-123/source-files", "draft", "manuscript"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("seed source validation error leaked forbidden text %q: %s", forbidden, body)
		}
	}
}

func TestStartSeedRunFailsClosedWithoutSourceFileBackendBeforeWorkflowStart(t *testing.T) {
	starter := &recordingSeedStarter{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: starter})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", bytes.NewBufferString(`{"upload_id":"upload-123"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-seed-source-unconfigured")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if starter.input.UploadID != "" {
		t.Fatalf("seed starter should not run without source file backend: %#v", starter.input)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_BACKEND_UNCONFIGURED" ||
		body.Error.Message != "source file backend is not configured" ||
		body.Error.RequestID != "req-seed-source-unconfigured" {
		t.Fatalf("unexpected error body: %#v", body)
	}
	for _, forbidden := range []string{"object_key", "source_object_key", "raw_text", "prompt", "api_key", "credential_ref", "draft", "manuscript"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("source backend failure leaked forbidden text %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestStartSeedRunFailsWhenUploadDoesNotBelongToTenantProject(t *testing.T) {
	starter := &recordingSeedStarter{}
	sourceStore := &recordingSourceFileStore{validateErr: sourcefiles.NewAppError("NOT_FOUND", "source file upload not found")}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: starter, SourceFileStore: sourceStore})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", bytes.NewBufferString(`{"upload_id":"upload-missing"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected status %d, got %d: %s", http.StatusNotFound, response.Code, response.Body.String())
	}
	if starter.input.UploadID != "" {
		t.Fatalf("seed starter should not be called when upload validation fails: %#v", starter.input)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "NOT_FOUND" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestStartSeedRunFailsWhenUploadIsNotCompleted(t *testing.T) {
	starter := &recordingSeedStarter{}
	sourceStore := &recordingSourceFileStore{validateErr: sourcefiles.NewAppError("SOURCE_FILE_NOT_UPLOADED", "source file upload must be completed before seed run")}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedStarter: starter, SourceFileStore: sourceStore})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", bytes.NewBufferString(`{"upload_id":"upload-pending"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusConflict {
		t.Fatalf("expected status %d, got %d: %s", http.StatusConflict, response.Code, response.Body.String())
	}
	if starter.input.UploadID != "" {
		t.Fatalf("seed starter should not be called when upload is pending: %#v", starter.input)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "SOURCE_FILE_NOT_UPLOADED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestStartSeedRunFailsClosedWithoutConfiguredStarter(t *testing.T) {
	sourceStore := &recordingSourceFileStore{
		validated: sourcefiles.ValidatedSourceFile{
			FileID:      "file-123",
			UploadID:    "upload-123",
			ProjectID:   "project-123",
			ObjectKey:   "projects/project-123/source-files/upload-123/book.txt",
			Filename:    "book.txt",
			MimeType:    "text/plain",
			SizeBytes:   2048,
			SHA256:      "abc123",
			ParseStatus: "uploaded",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SourceFileStore: sourceStore})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/seed-runs", bytes.NewBufferString(`{"upload_id":"upload-123"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if sourceStore.validateInput.TenantID != "tenant-123" ||
		sourceStore.validateInput.ProjectID != "project-123" ||
		sourceStore.validateInput.UploadID != "upload-123" {
		t.Fatalf("seed source validation lost trusted context: %#v", sourceStore.validateInput)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestGetWriterRunReturnsQueuedRunStatusFromAPI(t *testing.T) {
	starter := workflows.NewLocalWriterStarter()
	server := NewServer(Config{WriterStarter: starter, LLMResolver: boundWriterComposerResolver()})
	startRequest := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/writer-runs",
		bytes.NewBufferString(`{"mode":"draft","instruction":"写下一场谈判"}`),
	)
	startRequest.Header.Set("Content-Type", "application/json")
	startRequest.Header.Set("X-Tenant-Id", "tenant-123")
	startResponse := httptest.NewRecorder()
	server.ServeHTTP(startResponse, startRequest)
	if startResponse.Code != http.StatusAccepted {
		t.Fatalf("expected start status %d, got %d: %s", http.StatusAccepted, startResponse.Code, startResponse.Body.String())
	}
	var started map[string]string
	if err := json.NewDecoder(startResponse.Body).Decode(&started); err != nil {
		t.Fatalf("decode start response: %v", err)
	}

	getRequest := httptest.NewRequest(http.MethodGet, "/v1/writer-runs/"+started["run_id"], nil)
	getRequest.Header.Set("X-Tenant-Id", "tenant-123")
	getResponse := httptest.NewRecorder()
	server.ServeHTTP(getResponse, getRequest)

	if getResponse.Code != http.StatusOK {
		t.Fatalf("expected get status %d, got %d: %s", http.StatusOK, getResponse.Code, getResponse.Body.String())
	}
	var body map[string]string
	if err := json.NewDecoder(getResponse.Body).Decode(&body); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	if body["run_id"] != started["run_id"] || body["trace_id"] != started["trace_id"] || body["project_id"] != "project-123" || body["status"] != "queued" {
		t.Fatalf("unexpected get body: %#v", body)
	}
}

func TestGetWriterRunUsesConfiguredReader(t *testing.T) {
	reader := &recordingWriterReader{
		run: workflows.WriterRun{
			RunID:     "run-db",
			TraceID:   "trace-db",
			ProjectID: "project-db",
			Status:    "completed",
		},
	}
	server := NewServer(Config{
		WriterStarter: &recordingStarter{},
		WriterReader:  reader,
	})

	request := httptest.NewRequest(http.MethodGet, "/v1/writer-runs/run-db", nil)
	request.Header.Set("X-Tenant-Id", "tenant-db")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected get status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-db" || reader.input.RunID != "run-db" {
		t.Fatalf("reader did not receive tenant/run context: %#v", reader.input)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "run-db" || body["trace_id"] != "trace-db" || body["project_id"] != "project-db" || body["status"] != "completed" {
		t.Fatalf("unexpected body: %#v", body)
	}
}

func TestGetWorkflowRunUsesConfiguredReaderAndReturnsPublicMetadata(t *testing.T) {
	reader := &recordingWorkflowReader{
		run: workflows.WorkflowRun{
			RunID:        "run-db",
			WorkflowType: "seed_run",
			ProjectID:    "project-db",
			Status:       "running",
			Progress:     42,
			Message:      "reading chapter 2",
			ErrorCode:    "",
			ErrorMessage: "",
			CreatedAt:    "2026-07-04T01:00:00Z",
			UpdatedAt:    "2026-07-04T01:02:00Z",
		},
	}
	server := NewServer(Config{
		WriterStarter:  &recordingStarter{},
		WorkflowReader: reader,
	})

	request := httptest.NewRequest(http.MethodGet, "/v1/workflow-runs/run-db", nil)
	request.Header.Set("X-Tenant-Id", "tenant-db")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected get status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-db" || reader.input.RunID != "run-db" {
		t.Fatalf("reader did not receive tenant/run context: %#v", reader.input)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "run-db" || body["workflow_type"] != "seed_run" || body["project_id"] != "project-db" || body["status"] != "running" {
		t.Fatalf("unexpected body: %#v", body)
	}
	if body["progress"] != float64(42) || body["message"] != "reading chapter 2" {
		t.Fatalf("unexpected workflow progress body: %#v", body)
	}
	if _, ok := body["result_jsonb"]; ok {
		t.Fatalf("workflow response leaked result payload: %#v", body)
	}
	if _, ok := body["options_jsonb"]; ok {
		t.Fatalf("workflow response leaked options payload: %#v", body)
	}
	if _, ok := body["credential_ref"]; ok {
		t.Fatalf("workflow response leaked credential ref: %#v", body)
	}
}

func TestListSeedRunsUsesConfiguredReaderAndReturnsOnlyPublicMetadata(t *testing.T) {
	reader := &recordingSeedRunReader{
		runs: []workflows.WorkflowRun{
			{
				RunID:        "seed-run-1",
				WorkflowType: workflows.SeedWorkflowType,
				ProjectID:    "project-123",
				Status:       "running",
				Progress:     15,
				Message:      "parse_file pending",
				CreatedAt:    "2026-07-04T01:00:00Z",
				UpdatedAt:    "2026-07-04T01:01:00Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedRunReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/seed-runs", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.listInput.TenantID != "tenant-123" || reader.listInput.ProjectID != "project-123" {
		t.Fatalf("reader lost tenant/project context: %#v", reader.listInput)
	}
	var body listResponse[workflowRunResponse]
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) != 1 || body.Items[0].RunID != "seed-run-1" || body.Items[0].WorkflowType != workflows.SeedWorkflowType {
		t.Fatalf("unexpected seed runs body: %#v", body)
	}
	if body.Items[0].Progress != 15 || body.Items[0].Message != "parse_file pending" {
		t.Fatalf("unexpected seed run metadata: %#v", body.Items[0])
	}
}

func TestGetProjectReadinessUsesTenantProjectScopeAndReturnsPublicSnapshot(t *testing.T) {
	reader := &recordingProjectReadinessReader{
		snapshot: projectreadiness.Snapshot{
			SnapshotID:             "snapshot-1",
			ProjectID:              "project-123",
			RunID:                  "seed-run-1",
			ReadyAssetCount:        7,
			ReadyEntityCount:       5,
			ReadyRelationshipCount: 4,
			ReadyWorldRuleCount:    3,
			CreatedAt:              "2026-07-07T01:00:00Z",
			UpdatedAt:              "2026-07-07T01:05:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ProjectReadinessReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/readiness", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.ProjectID != "project-123" {
		t.Fatalf("reader lost tenant/project context: %#v", reader.input)
	}
	responseBody := response.Body.String()
	var body projectreadiness.Snapshot
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.SnapshotID != "snapshot-1" || body.RunID != "seed-run-1" || body.ReadyAssetCount != 7 {
		t.Fatalf("unexpected readiness response: %#v", body)
	}
	responseText := strings.ToLower(responseBody)
	for _, forbidden := range []string{"report", "body", "content_text", "prompt", "api_key", "credential_ref", "draft", "manuscript"} {
		if strings.Contains(responseText, forbidden) {
			t.Fatalf("readiness response leaked %q: %s", forbidden, responseBody)
		}
	}
}

func TestGetProjectReadinessSanitizesReaderErrorsAtHTTPBoundary(t *testing.T) {
	reader := &recordingProjectReadinessReader{
		err: &projectreadiness.AppError{
			Code:    "PROJECT_READINESS_QUERY_FAILED",
			Message: "driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden readiness report body",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ProjectReadinessReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/readiness", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	responseBody := response.Body.String()
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "PROJECT_READINESS_QUERY_FAILED" || body.Error.Message != "project readiness query failed" {
		t.Fatalf("unexpected error body: %#v", body)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "report body", "draft", "manuscript"} {
		if strings.Contains(responseBody, forbidden) {
			t.Fatalf("readiness error leaked %q: %s", forbidden, responseBody)
		}
	}
}

func TestGetProjectOverviewUsesTenantProjectScopeAndReturnsPublicRollup(t *testing.T) {
	reader := &recordingProjectOverviewReader{
		overview: projectoverview.Overview{
			ProjectID:                     "project-123",
			Status:                        "analyzing",
			SourceFileCount:               2,
			SeedRunCount:                  3,
			ActiveWorkflowRunID:           "workflow-1",
			ActiveWorkflowType:            "seed_pipeline",
			ActiveWorkflowStatus:          "running",
			ReadinessSnapshotID:           "snapshot-1",
			ReadinessRunID:                "seed-run-1",
			ReadyAssetCount:               7,
			ReadyEntityCount:              5,
			ReadyRelationshipCount:        4,
			ReadyWorldRuleCount:           3,
			AssetCount:                    11,
			GraphNodeCount:                9,
			GraphEdgeCount:                8,
			WorldlineSessionCount:         6,
			WorldlineEventCount:           4,
			CharacterInteractionCount:     5,
			WriterRunCount:                2,
			LLMActivityCount:              13,
			LLMTokenCount:                 377,
			LLMEnabledChannelCount:        2,
			LLMBoundModuleCount:           6,
			LLMMissingCoreModuleCount:     3,
			LLMSyncOKChannelCount:         1,
			LLMSyncFailedChannelCount:     1,
			LLMSyncPendingChannelCount:    0,
			LLMLatestSyncAt:               "2026-07-07T01:03:00Z",
			LatestFailedWorkflowRunID:     "failed-run-1",
			LatestFailedWorkflowType:      "seed_pipeline",
			LatestFailedWorkflowErrorCode: "LLM_MODULE_UNBOUND",
			LatestFailedWorkflowUpdatedAt: "2026-07-07T01:04:00Z",
			UpdatedAt:                     "2026-07-07T01:05:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ProjectOverviewReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/overview", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.ProjectID != "project-123" {
		t.Fatalf("reader lost tenant/project context: %#v", reader.input)
	}
	responseBody := response.Body.String()
	var body projectoverview.Overview
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.ProjectID != "project-123" || body.Status != "analyzing" || body.ReadyAssetCount != 7 {
		t.Fatalf("unexpected overview response: %#v", body)
	}
	if body.AssetCount != 11 || body.GraphNodeCount != 9 || body.GraphEdgeCount != 8 {
		t.Fatalf("unexpected asset/graph health response: %#v", body)
	}
	if body.WorldlineSessionCount != 6 || body.WorldlineEventCount != 4 || body.CharacterInteractionCount != 5 {
		t.Fatalf("unexpected worldline/character health response: %#v", body)
	}
	if body.WriterRunCount != 2 || body.LLMActivityCount != 13 || body.LLMTokenCount != 377 {
		t.Fatalf("unexpected writer/LLM health response: %#v", body)
	}
	if body.LLMEnabledChannelCount != 2 || body.LLMBoundModuleCount != 6 || body.LLMMissingCoreModuleCount != 3 {
		t.Fatalf("unexpected LLM configuration health response: %#v", body)
	}
	if body.LLMSyncOKChannelCount != 1 ||
		body.LLMSyncFailedChannelCount != 1 ||
		body.LLMSyncPendingChannelCount != 0 ||
		body.LLMLatestSyncAt != "2026-07-07T01:03:00Z" {
		t.Fatalf("unexpected LLM model sync health response: %#v", body)
	}
	if body.LatestFailedWorkflowRunID != "failed-run-1" ||
		body.LatestFailedWorkflowType != "seed_pipeline" ||
		body.LatestFailedWorkflowErrorCode != "LLM_MODULE_UNBOUND" ||
		body.LatestFailedWorkflowUpdatedAt != "2026-07-07T01:04:00Z" {
		t.Fatalf("unexpected latest failed workflow diagnostics response: %#v", body)
	}
	responseText := strings.ToLower(responseBody)
	for _, forbidden := range []string{"object_key", "raw_text", "parsed_text", "report_body", "content_text", "prompt", "api_key", "encrypted_api_key", "base_url", "credential_ref", "draft", "manuscript", "error_message"} {
		if strings.Contains(responseText, forbidden) {
			t.Fatalf("overview response leaked %q: %s", forbidden, responseBody)
		}
	}
}

func TestGetProjectOverviewSanitizesReaderErrorsAtHTTPBoundary(t *testing.T) {
	reader := &recordingProjectOverviewReader{
		err: &projectoverview.AppError{
			Code:    "PROJECT_OVERVIEW_QUERY_FAILED",
			Message: "driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden readiness report body draft manuscript",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, ProjectOverviewReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/overview", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	responseBody := response.Body.String()
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "PROJECT_OVERVIEW_QUERY_FAILED" || body.Error.Message != "project overview query failed" {
		t.Fatalf("unexpected error body: %#v", body)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "report body", "draft", "manuscript"} {
		if strings.Contains(responseBody, forbidden) {
			t.Fatalf("overview error leaked %q: %s", forbidden, responseBody)
		}
	}
}

func TestGetSeedRunRejectsNonSeedWorkflowRun(t *testing.T) {
	reader := &recordingSeedRunReader{
		getErr: &workflows.AppError{Code: "NOT_FOUND", Message: "seed run not found"},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedRunReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/seed-runs/writer-run-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected status %d, got %d: %s", http.StatusNotFound, response.Code, response.Body.String())
	}
	if reader.getInput.TenantID != "tenant-123" || reader.getInput.RunID != "writer-run-1" {
		t.Fatalf("reader lost tenant/run context: %#v", reader.getInput)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "NOT_FOUND" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestGetSeedRunEventsUsesWorkflowEventReaderAndRedactsSensitivePayload(t *testing.T) {
	seedReader := &recordingSeedRunReader{
		run: workflows.WorkflowRun{
			RunID:        "seed-run-1",
			WorkflowType: workflows.SeedWorkflowType,
			ProjectID:    "project-123",
			Status:       "running",
		},
	}
	eventReader := &recordingWorkflowEventReader{
		events: []workflows.WorkflowEvent{
			{
				EventID:   "evt-seed-2",
				RunID:     "seed-run-1",
				ProjectID: "project-123",
				Sequence:  2,
				EventType: "seed.stage.pending",
				Payload: map[string]any{
					"stage": "parse_file",
					"body":  "raw text must not leak",
				},
				CreatedAt: "2026-07-04T01:02:03Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedRunReader: seedReader, WorkflowEventReader: eventReader})
	request := httptest.NewRequest(http.MethodGet, "/v1/seed-runs/seed-run-1/events?after_event_id=evt-seed-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if seedReader.getInput.TenantID != "tenant-123" || seedReader.getInput.RunID != "seed-run-1" {
		t.Fatalf("seed reader lost tenant/run context: %#v", seedReader.getInput)
	}
	if eventReader.input.TenantID != "tenant-123" || eventReader.input.RunID != "seed-run-1" || eventReader.input.AfterEventID != "evt-seed-1" {
		t.Fatalf("event reader lost seed event context: %#v", eventReader.input)
	}
	var body listResponse[workflows.WorkflowEvent]
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) != 1 || body.Items[0].EventID != "evt-seed-2" || body.Items[0].Payload["stage"] != "parse_file" {
		t.Fatalf("unexpected seed events body: %#v", body)
	}
	if _, ok := body.Items[0].Payload["body"]; ok {
		t.Fatalf("seed event leaked raw body: %#v", body.Items[0].Payload)
	}
}

func TestGetWriterRunEventsReturnsEventsAfterQueryCursor(t *testing.T) {
	reader := &recordingWriterEventReader{
		events: []workflows.WriterEvent{
			{
				EventID:   "evt-2",
				RunID:     "run-123",
				ProjectID: "project-123",
				Sequence:  2,
				EventType: "writer.token",
				Payload:   map[string]any{"delta": "雨"},
				CreatedAt: "2026-07-04T01:02:03Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WriterEventReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/writer-runs/run-123/events?after_event_id=evt-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.RunID != "run-123" || reader.input.AfterEventID != "evt-1" {
		t.Fatalf("reader lost resume context: %#v", reader.input)
	}
	var body listResponse[workflows.WriterEvent]
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) != 1 || body.Items[0].EventID != "evt-2" || body.Items[0].Payload["delta"] != "雨" {
		t.Fatalf("unexpected events body: %#v", body)
	}
}

func TestGetWorkflowRunEventsReturnsEventsAfterQueryCursorAndSanitizesPayload(t *testing.T) {
	reader := &recordingWorkflowEventReader{
		events: []workflows.WorkflowEvent{
			{
				EventID:   "evt-2",
				RunID:     "run-123",
				ProjectID: "project-123",
				Sequence:  2,
				EventType: "stage_progress",
				Payload: map[string]any{
					"stage":               "parse",
					"source_file_id":      "file-123",
					"object_key":          "projects/project-123/source-files/upload-123/book.txt",
					"source_object_key":   "projects/project-123/source-files/upload-123/book.txt",
					"artifact_object_key": "projects/project-123/artifacts/artifact-123.txt",
					"segment_object_key":  "projects/project-123/segments/segment-123.txt",
					"source_sha256":       "sha-private",
					"raw_text":            "private source text",
					"credential_ref":      "cred-1",
					"nested": map[string]any{
						"api_key":           "secret",
						"source_object_key": "projects/project-123/source-files/upload-123/nested.txt",
						"safe":              "kept",
					},
				},
				CreatedAt: "2026-07-04T01:02:03Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorkflowEventReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/workflow-runs/run-123/events?after_event_id=evt-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.RunID != "run-123" || reader.input.AfterEventID != "evt-1" {
		t.Fatalf("reader lost resume context: %#v", reader.input)
	}
	var body listResponse[workflows.WorkflowEvent]
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) != 1 || body.Items[0].EventID != "evt-2" || body.Items[0].Payload["stage"] != "parse" {
		t.Fatalf("unexpected events body: %#v", body)
	}
	if body.Items[0].Payload["source_file_id"] != "file-123" {
		t.Fatalf("workflow event lost safe source file id: %#v", body.Items[0].Payload)
	}
	for _, forbidden := range []string{"credential_ref", "object_key", "source_object_key", "artifact_object_key", "segment_object_key", "source_sha256", "raw_text"} {
		if _, ok := body.Items[0].Payload[forbidden]; ok {
			t.Fatalf("workflow event leaked forbidden field %q: %#v", forbidden, body.Items[0].Payload)
		}
	}
	nested, ok := body.Items[0].Payload["nested"].(map[string]any)
	if !ok || nested["safe"] != "kept" {
		t.Fatalf("expected nested safe payload to remain, got %#v", body.Items[0].Payload)
	}
	if _, ok := nested["api_key"]; ok {
		t.Fatalf("workflow event leaked nested api key: %#v", body.Items[0].Payload)
	}
	if _, ok := nested["source_object_key"]; ok {
		t.Fatalf("workflow event leaked nested source object key: %#v", body.Items[0].Payload)
	}
}

func TestGetWorkflowRunEventsSSEUsesLastEventIDForResume(t *testing.T) {
	reader := &recordingWorkflowEventReader{
		events: []workflows.WorkflowEvent{
			{
				EventID:   "evt-2",
				RunID:     "run-123",
				ProjectID: "project-123",
				Sequence:  2,
				EventType: "stage_progress",
				Payload:   map[string]any{"stage": "parse"},
				CreatedAt: "2026-07-04T01:02:04Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorkflowEventReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/workflow-runs/run-123/events", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("Accept", "text/event-stream")
	request.Header.Set("Last-Event-ID", "evt-1")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.AfterEventID != "evt-1" {
		t.Fatalf("expected Last-Event-ID cursor, got %#v", reader.input)
	}
	rawBody := response.Body.String()
	if !strings.Contains(rawBody, "id: evt-2\n") || !strings.Contains(rawBody, "event: workflow.event\n") || !strings.Contains(rawBody, `"event_type":"stage_progress"`) {
		t.Fatalf("unexpected SSE body: %s", rawBody)
	}
}

func TestGetWriterRunEventsSSEUsesLastEventIDForResume(t *testing.T) {
	reader := &recordingWriterEventReader{
		events: []workflows.WriterEvent{
			{
				EventID:   "evt-2",
				RunID:     "run-123",
				ProjectID: "project-123",
				Sequence:  2,
				EventType: "writer.run.completed",
				Payload:   map[string]any{"status": "completed"},
				CreatedAt: "2026-07-04T01:02:04Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WriterEventReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/writer-runs/run-123/events", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("Accept", "text/event-stream")
	request.Header.Set("Last-Event-ID", "evt-1")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.AfterEventID != "evt-1" {
		t.Fatalf("expected Last-Event-ID cursor, got %#v", reader.input)
	}
	rawBody := response.Body.String()
	if !strings.Contains(rawBody, "id: evt-2\n") || !strings.Contains(rawBody, "event: workflow.event\n") || !strings.Contains(rawBody, `"event_type":"writer.run.completed"`) {
		t.Fatalf("unexpected SSE body: %s", rawBody)
	}
}

func TestCancelWriterRunCarriesTenantRunActorAndRequestContext(t *testing.T) {
	canceller := &recordingWriterCanceller{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WriterCanceller: canceller})
	request := httptest.NewRequest(http.MethodPost, "/v1/writer-runs/run-123/cancel", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-cancel")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "run-123" || body["status"] != "cancel_requested" {
		t.Fatalf("unexpected cancel response: %#v", body)
	}
	if canceller.input.TenantID != "tenant-123" || canceller.input.RunID != "run-123" {
		t.Fatalf("canceller lost tenant/run context: %#v", canceller.input)
	}
	if canceller.input.ActorUserID != "user-123" || canceller.input.RequestID != "req-cancel" {
		t.Fatalf("canceller lost actor/request context: %#v", canceller.input)
	}
}

func TestCancelWorkflowRunCarriesTenantRunActorAndRequestContext(t *testing.T) {
	canceller := &recordingWorkflowCanceller{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorkflowCanceller: canceller})
	request := httptest.NewRequest(http.MethodPost, "/v1/workflow-runs/run-123/cancel", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-cancel")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if canceller.input.TenantID != "tenant-123" || canceller.input.RunID != "run-123" {
		t.Fatalf("canceller lost tenant/run context: %#v", canceller.input)
	}
	if canceller.input.ActorUserID != "user-123" || canceller.input.RequestID != "req-cancel" {
		t.Fatalf("canceller lost actor/request context: %#v", canceller.input)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "run-123" || body["status"] != "cancel_requested" {
		t.Fatalf("unexpected cancel body: %#v", body)
	}
}

func TestCancelSeedRunVerifiesSeedRunAndCarriesActorContext(t *testing.T) {
	seedReader := &recordingSeedRunReader{
		run: workflows.WorkflowRun{
			RunID:        "seed-run-123",
			WorkflowType: workflows.SeedWorkflowType,
			ProjectID:    "project-123",
			Status:       "running",
		},
	}
	canceller := &recordingWorkflowCanceller{}
	server := NewServer(Config{
		WriterStarter:     &recordingStarter{},
		SeedRunReader:     seedReader,
		WorkflowCanceller: canceller,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/seed-runs/seed-run-123/cancel", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-seed-cancel")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if seedReader.getInput.TenantID != "tenant-123" || seedReader.getInput.RunID != "seed-run-123" {
		t.Fatalf("seed reader lost tenant/run context: %#v", seedReader.getInput)
	}
	if canceller.input.TenantID != "tenant-123" || canceller.input.RunID != "seed-run-123" {
		t.Fatalf("canceller lost tenant/run context: %#v", canceller.input)
	}
	if canceller.input.ActorUserID != "user-123" || canceller.input.RequestID != "req-seed-cancel" {
		t.Fatalf("canceller lost actor/request context: %#v", canceller.input)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "seed-run-123" || body["status"] != "cancel_requested" {
		t.Fatalf("unexpected cancel body: %#v", body)
	}
}

func TestCancelSeedRunRejectsNonSeedRunBeforeCallingBackend(t *testing.T) {
	seedReader := &recordingSeedRunReader{
		getErr: &workflows.AppError{Code: "NOT_FOUND", Message: "seed run not found"},
	}
	canceller := &recordingWorkflowCanceller{}
	server := NewServer(Config{
		WriterStarter:     &recordingStarter{},
		SeedRunReader:     seedReader,
		WorkflowCanceller: canceller,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/seed-runs/writer-run-123/cancel", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected status %d, got %d: %s", http.StatusNotFound, response.Code, response.Body.String())
	}
	if canceller.called {
		t.Fatalf("cancellation backend was called for non-seed run: %#v", canceller.input)
	}
}

func TestCancelWorkflowRunFailsClosedWhenBackendIsUnavailable(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/workflow-runs/run-123/cancel", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-cancel")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestRetrySeedRunVerifiesSeedRunAndCarriesActorContext(t *testing.T) {
	seedReader := &recordingSeedRunReader{
		run: workflows.WorkflowRun{
			RunID:        "seed-run-123",
			WorkflowType: workflows.SeedWorkflowType,
			ProjectID:    "project-123",
			Status:       "failed",
		},
	}
	retrier := &recordingWorkflowRetrier{}
	server := NewServer(Config{
		WriterStarter:   &recordingStarter{},
		SeedRunReader:   seedReader,
		WorkflowRetrier: retrier,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/seed-runs/seed-run-123/retry", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-seed-retry")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if seedReader.getInput.TenantID != "tenant-123" || seedReader.getInput.RunID != "seed-run-123" {
		t.Fatalf("seed reader lost tenant/run context: %#v", seedReader.getInput)
	}
	if retrier.input.TenantID != "tenant-123" || retrier.input.RunID != "seed-run-123" {
		t.Fatalf("retrier lost tenant/run context: %#v", retrier.input)
	}
	if retrier.input.ActorUserID != "user-123" || retrier.input.RequestID != "req-seed-retry" {
		t.Fatalf("retrier lost actor/request context: %#v", retrier.input)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "seed-run-123" || body["status"] != "retry_requested" {
		t.Fatalf("unexpected retry body: %#v", body)
	}
}

func TestRetrySeedRunFailsClosedWhenBackendIsUnavailable(t *testing.T) {
	seedReader := &recordingSeedRunReader{
		run: workflows.WorkflowRun{
			RunID:        "seed-run-123",
			WorkflowType: workflows.SeedWorkflowType,
			ProjectID:    "project-123",
			Status:       "failed",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, SeedRunReader: seedReader})
	request := httptest.NewRequest(http.MethodPost, "/v1/seed-runs/seed-run-123/retry", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-seed-retry")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORKFLOW_RETRY_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestRetryWorkflowRunCarriesTenantRunActorAndRequestContext(t *testing.T) {
	retrier := &recordingWorkflowRetrier{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, WorkflowRetrier: retrier})
	request := httptest.NewRequest(http.MethodPost, "/v1/workflow-runs/run-123/retry", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req-retry")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if retrier.input.TenantID != "tenant-123" || retrier.input.RunID != "run-123" {
		t.Fatalf("retrier lost tenant/run context: %#v", retrier.input)
	}
	if retrier.input.ActorUserID != "user-123" || retrier.input.RequestID != "req-retry" {
		t.Fatalf("retrier lost actor/request context: %#v", retrier.input)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["run_id"] != "run-123" || body["status"] != "retry_requested" {
		t.Fatalf("unexpected retry body: %#v", body)
	}
}

func TestRetryWorkflowRunFailsClosedWhenBackendIsUnavailable(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/workflow-runs/run-123/retry", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-retry")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORKFLOW_RETRY_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestCancelWriterRunFailsClosedWhenBackendIsUnavailable(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/writer-runs/run-123/cancel", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req-cancel")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit cancel backend error, got %#v", body)
	}
}

func TestStartAgentRuntimeHelloWithoutConfiguredStarterFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/agent-runtime/hello-runs", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d", http.StatusServiceUnavailable, response.Code)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestStartAgentRuntimeHelloCarriesContext(t *testing.T) {
	starter := &recordingHelloStarter{}
	server := NewServer(Config{
		WriterStarter:     &recordingStarter{},
		AgentHelloStarter: starter,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/agent-runtime/hello-runs", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req_hello")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("expected status %d, got %d: %s", http.StatusAccepted, response.Code, response.Body.String())
	}
	if starter.input.TenantID != "tenant-123" || starter.input.ProjectID != "project-123" {
		t.Fatalf("starter lost tenant/project context: %#v", starter.input)
	}
	if starter.input.ActorUserID != "user-123" || starter.input.RequestID != "req_hello" {
		t.Fatalf("starter lost actor/request context: %#v", starter.input)
	}
	var body map[string]string
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["workflow_type"] != "hello_agent" || body["status"] != "completed" || body["run_id"] == "" {
		t.Fatalf("unexpected response body: %#v", body)
	}
}

func TestStartWriterRunRejectsMissingTenantContext(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMResolver: boundWriterComposerResolver()})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/writer-runs", bytes.NewBufferString(`{"mode":"draft","instruction":"写"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusUnauthorized {
		t.Fatalf("expected status %d, got %d", http.StatusUnauthorized, response.Code)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "UNAUTHENTICATED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestStartWriterRunRejectsMissingLLMModuleBinding(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMResolver: llm.NewStaticResolver(nil)})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/writer-runs", bytes.NewBufferString(`{"mode":"draft","instruction":"写"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-Request-Id", "req_llm_missing")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "LLM_MODULE_UNBOUND" || body.Error.RequestID != "req_llm_missing" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestResolveLLMModuleBindingReturnsSanitizedResolution(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMResolver: boundWriterComposerResolver()})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/module-bindings/writer_composer/resolution", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	rawBody := response.Body.String()
	var body map[string]any
	if err := json.NewDecoder(strings.NewReader(rawBody)).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["module_key"] != "writer_composer" || body["channel_id"] != "channel-1" || body["model_id"] != "model-1" {
		t.Fatalf("unexpected resolution body: %#v", body)
	}
	if _, ok := body["api_key"]; ok {
		t.Fatalf("resolution leaked api_key: %#v", body)
	}
	if _, ok := body["encrypted_api_key"]; ok {
		t.Fatalf("resolution leaked encrypted_api_key: %#v", body)
	}
	if _, ok := body["credential_ref"]; ok {
		t.Fatalf("public resolution leaked internal credential_ref: %#v", body)
	}
}

func TestListLLMModulesCarriesTenantProjectContextAndReturnsSanitizedRegistry(t *testing.T) {
	registry := &recordingLLMModuleRegistry{
		modules: []llm.ModuleRecord{
			{
				ModuleKey:   "writer_composer",
				Group:       "Writer",
				Label:       "Writer Composer",
				Description: "Writes draft prose from a writing brief.",
			},
			{
				ModuleKey:   "story_ontology",
				Group:       "Seed / Graph",
				Label:       "Story Ontology",
				Description: "Generates the project story ontology.",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMModuleRegistry: registry})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/modules", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if registry.input.TenantID != "tenant-123" || registry.input.ProjectID != "project-123" {
		t.Fatalf("registry lost tenant/project context: %#v", registry.input)
	}
	rawBody := response.Body.String()
	for _, forbidden := range []string{"api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("module registry leaked %s: %s", forbidden, rawBody)
		}
	}
	if !strings.Contains(rawBody, `"module_key":"writer_composer"`) || !strings.Contains(rawBody, `"module_key":"story_ontology"`) {
		t.Fatalf("unexpected registry body: %s", rawBody)
	}
}

func TestGetLLMSettingsReturnsSanitizedTenantSnapshot(t *testing.T) {
	reader := &recordingLLMSettingsReader{
		snapshot: llm.SettingsSnapshot{
			Modules: []llm.ModuleRecord{
				{ModuleKey: "writer_composer", Group: "Writer", Label: "Writer Composer", Description: "Writes draft prose."},
			},
			Channels: []llm.ChannelRecord{
				{
					ChannelID:      "channel-1",
					Name:           "Draft Channel",
					Provider:       "openai-compatible",
					BaseURL:        "https://llm.example.test/v1",
					MaxConcurrency: 2,
					Enabled:        true,
					Scope:          "tenant",
					CreatedAt:      "2026-07-05T00:00:00Z",
					UpdatedAt:      "2026-07-05T00:00:00Z",
				},
			},
			TenantBindings: []llm.ModuleBindingRecord{
				{
					ModuleKey:   "writer_composer",
					Scope:       "tenant",
					ChannelID:   "channel-1",
					ChannelName: "Draft Channel",
					Provider:    "openai-compatible",
					ModelID:     "gpt-4.1-mini",
					Settings:    map[string]any{"max_concurrency": 1},
					UpdatedAt:   "2026-07-05T00:00:00Z",
				},
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMSettingsReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/llm/settings", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" {
		t.Fatalf("settings reader lost tenant context: %#v", reader.input)
	}
	rawBody := response.Body.String()
	for _, expected := range []string{`"modules"`, `"channels"`, `"tenant_bindings"`, "writer_composer", "Draft Channel"} {
		if !strings.Contains(rawBody, expected) {
			t.Fatalf("settings snapshot missing %s: %s", expected, rawBody)
		}
	}
	for _, forbidden := range []string{"api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("settings snapshot leaked %s: %s", forbidden, rawBody)
		}
	}
}

func TestGetLLMSettingsWithoutReaderFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/llm/settings", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "LLM_SETTINGS_BACKEND_UNCONFIGURED") {
		t.Fatalf("expected explicit settings backend error: %s", response.Body.String())
	}
}

func TestListLLMModuleBindingsReturnsSanitizedProjectScopedRows(t *testing.T) {
	store := &recordingLLMBindingStore{
		bindings: []llm.ModuleBindingRecord{
			{
				ModuleKey:     "writer_composer",
				Scope:         "project",
				ChannelID:     "channel-1",
				ChannelName:   "Draft Channel",
				ModelID:       "model-1",
				Provider:      "openai-compatible",
				BaseURL:       "https://llm.example.test/v1",
				SupportsTools: true,
				SupportsJSON:  true,
				Settings:      map[string]any{"temperature": 0.7},
				UpdatedAt:     "2026-07-04T00:00:00Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMBindingStore: store})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/module-bindings", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.listInput.TenantID != "tenant-123" || store.listInput.ProjectID != "project-123" {
		t.Fatalf("store lost tenant/project context: %#v", store.listInput)
	}
	rawBody := response.Body.String()
	for _, forbidden := range []string{"api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("binding list leaked %s: %s", forbidden, rawBody)
		}
	}
	if !strings.Contains(rawBody, `"module_key":"writer_composer"`) || !strings.Contains(rawBody, `"scope":"project"`) {
		t.Fatalf("unexpected binding list body: %s", rawBody)
	}
}

func TestUpsertLLMModuleBindingCarriesActorAndReturnsSanitizedBinding(t *testing.T) {
	store := &recordingLLMBindingStore{
		upserted: llm.ModuleBindingRecord{
			ModuleKey:     "writer_composer",
			Scope:         "project",
			ChannelID:     "channel-1",
			ChannelName:   "Draft Channel",
			ModelID:       "model-1",
			Provider:      "openai-compatible",
			BaseURL:       "https://llm.example.test/v1",
			SupportsTools: true,
			SupportsJSON:  true,
			Settings:      map[string]any{"temperature": 0.8},
			UpdatedAt:     "2026-07-04T00:00:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMBindingStore: store})
	request := httptest.NewRequest(
		http.MethodPut,
		"/v1/projects/project-123/llm/module-bindings/writer_composer",
		bytes.NewBufferString(`{"channel_id":"channel-1","model_id":"model-1","settings":{"temperature":0.8}}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.upsertInput.TenantID != "tenant-123" || store.upsertInput.ProjectID != "project-123" || store.upsertInput.ActorID != "user-123" {
		t.Fatalf("store lost tenant/project/actor context: %#v", store.upsertInput)
	}
	if store.upsertInput.ModuleKey != "writer_composer" || store.upsertInput.ChannelID != "channel-1" || store.upsertInput.ModelID != "model-1" {
		t.Fatalf("store lost binding payload: %#v", store.upsertInput)
	}
	if store.upsertInput.Settings["temperature"] != 0.8 {
		t.Fatalf("store lost settings: %#v", store.upsertInput.Settings)
	}
	rawBody := response.Body.String()
	if strings.Contains(rawBody, "api_key") || strings.Contains(rawBody, "credential_ref") {
		t.Fatalf("upsert response leaked credential material: %s", rawBody)
	}
	if !strings.Contains(rawBody, `"scope":"project"`) {
		t.Fatalf("unexpected upsert body: %s", rawBody)
	}
}

func TestDeleteLLMModuleBindingCarriesTenantProjectContext(t *testing.T) {
	store := &recordingLLMBindingStore{
		deleted: llm.ModuleBindingRecord{
			ModuleKey:     "writer_composer",
			Scope:         "project",
			ChannelID:     "channel-1",
			ChannelName:   "Draft Channel",
			ModelID:       "model-1",
			Provider:      "openai-compatible",
			BaseURL:       "https://llm.example.test/v1",
			SupportsTools: true,
			SupportsJSON:  true,
			Settings:      map[string]any{"temperature": 0.8},
			UpdatedAt:     "2026-07-04T00:00:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMBindingStore: store})
	request := httptest.NewRequest(http.MethodDelete, "/v1/projects/project-123/llm/module-bindings/writer_composer", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.deleteInput.TenantID != "tenant-123" || store.deleteInput.ProjectID != "project-123" || store.deleteInput.ModuleKey != "writer_composer" {
		t.Fatalf("store lost tenant/project/module context: %#v", store.deleteInput)
	}
	rawBody := response.Body.String()
	if strings.Contains(rawBody, "api_key") || strings.Contains(rawBody, "credential_ref") {
		t.Fatalf("delete response leaked credential material: %s", rawBody)
	}
	if !strings.Contains(rawBody, `"scope":"project"`) || !strings.Contains(rawBody, `"module_key":"writer_composer"`) {
		t.Fatalf("unexpected delete body: %s", rawBody)
	}
}

func TestListLLMModuleBindingsWithoutStoreFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/module-bindings", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "LLM_BINDING_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestListLLMChannelsReturnsSanitizedTenantProjectScopedRows(t *testing.T) {
	reader := &recordingLLMCatalogReader{
		channels: []llm.ChannelRecord{
			{
				ChannelID:      "channel-1",
				Name:           "Draft Channel",
				Provider:       "openai-compatible",
				BaseURL:        "https://llm.example.test/v1",
				MaxConcurrency: 4,
				Enabled:        true,
				LastSyncAt:     "2026-07-04T00:00:00Z",
				LastSyncStatus: "ok",
				Scope:          "tenant",
				CreatedAt:      "2026-07-04T00:00:00Z",
				UpdatedAt:      "2026-07-04T00:00:00Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMCatalogReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/channels", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.channelInput.TenantID != "tenant-123" || reader.channelInput.ProjectID != "project-123" {
		t.Fatalf("reader lost tenant/project context: %#v", reader.channelInput)
	}
	rawBody := response.Body.String()
	for _, forbidden := range []string{"api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("channel list leaked %s: %s", forbidden, rawBody)
		}
	}
	if !strings.Contains(rawBody, `"channel_id":"channel-1"`) || !strings.Contains(rawBody, `"scope":"tenant"`) {
		t.Fatalf("unexpected channel list body: %s", rawBody)
	}
}

func TestListLLMModelsCarriesChannelContextAndReturnsSanitizedRows(t *testing.T) {
	reader := &recordingLLMCatalogReader{
		models: []llm.ModelRecord{
			{
				ModelID:       "model-1",
				OwnedBy:       "provider-owner",
				ContextWindow: 128000,
				SupportsTools: true,
				SupportsJSON:  true,
				InputCost:     0.25,
				OutputCost:    1.25,
				CreatedAt:     "2026-07-04T00:00:00Z",
				UpdatedAt:     "2026-07-04T00:00:00Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMCatalogReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/channels/channel-1/models", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.modelInput.TenantID != "tenant-123" || reader.modelInput.ProjectID != "project-123" || reader.modelInput.ChannelID != "channel-1" {
		t.Fatalf("reader lost model context: %#v", reader.modelInput)
	}
	rawBody := response.Body.String()
	for _, forbidden := range []string{"api_key", "encrypted_api_key", "raw_payload_jsonb", "credential_ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("model list leaked %s: %s", forbidden, rawBody)
		}
	}
	if !strings.Contains(rawBody, `"model_id":"model-1"`) || !strings.Contains(rawBody, `"supports_tools":true`) {
		t.Fatalf("unexpected model list body: %s", rawBody)
	}
}

func TestCreateLLMChannelEncryptsCredentialAndReturnsSanitizedChannel(t *testing.T) {
	store := &recordingLLMChannelStore{
		created: llm.ChannelRecord{
			ChannelID:      "channel-1",
			Name:           "Draft Channel",
			Provider:       "openai-compatible",
			BaseURL:        "https://llm.example.test/v1",
			MaxConcurrency: 4,
			Enabled:        true,
			Scope:          "tenant",
			CreatedAt:      "2026-07-04T00:00:00Z",
			UpdatedAt:      "2026-07-04T00:00:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMChannelStore: store})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/llm/channels",
		bytes.NewBufferString(`{"name":"Draft Channel","provider":"openai-compatible","base_url":"https://llm.example.test/v1","api_key":"sk-secret","max_concurrency":4,"enabled":true}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("expected status %d, got %d: %s", http.StatusCreated, response.Code, response.Body.String())
	}
	if store.createInput.TenantID != "tenant-123" || store.createInput.Name != "Draft Channel" || store.createInput.APIKey != "sk-secret" {
		t.Fatalf("store lost create payload: %#v", store.createInput)
	}
	rawBody := response.Body.String()
	for _, forbidden := range []string{"api_key", "encrypted_api_key", "credential_ref", "sk-secret"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("create channel leaked %s: %s", forbidden, rawBody)
		}
	}
	if !strings.Contains(rawBody, `"channel_id":"channel-1"`) || !strings.Contains(rawBody, `"scope":"tenant"`) {
		t.Fatalf("unexpected create body: %s", rawBody)
	}
}

func TestPatchLLMChannelCarriesTenantContextAndReturnsSanitizedChannel(t *testing.T) {
	store := &recordingLLMChannelStore{
		updated: llm.ChannelRecord{
			ChannelID:      "channel-1",
			Name:           "Renamed Channel",
			Provider:       "openai-compatible",
			BaseURL:        "https://llm.example.test/v1",
			MaxConcurrency: 2,
			Enabled:        false,
			Scope:          "tenant",
			CreatedAt:      "2026-07-04T00:00:00Z",
			UpdatedAt:      "2026-07-04T00:00:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMChannelStore: store})
	request := httptest.NewRequest(
		http.MethodPatch,
		"/v1/llm/channels/channel-1",
		bytes.NewBufferString(`{"name":"Renamed Channel","base_url":"https://llm.example.test/v1","max_concurrency":2,"enabled":false}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.updateInput.TenantID != "tenant-123" || store.updateInput.ChannelID != "channel-1" || store.updateInput.APIKey != "" {
		t.Fatalf("store lost update context: %#v", store.updateInput)
	}
	if store.updateInput.Enabled {
		t.Fatalf("store lost disabled flag: %#v", store.updateInput)
	}
	rawBody := response.Body.String()
	if strings.Contains(rawBody, "api_key") || strings.Contains(rawBody, "encrypted_api_key") || strings.Contains(rawBody, "credential_ref") {
		t.Fatalf("patch channel leaked credential material: %s", rawBody)
	}
}

func TestDeleteLLMChannelDisablesTenantChannel(t *testing.T) {
	store := &recordingLLMChannelStore{
		deleted: llm.ChannelRecord{
			ChannelID:      "channel-1",
			Name:           "Draft Channel",
			Provider:       "openai-compatible",
			BaseURL:        "https://llm.example.test/v1",
			MaxConcurrency: 2,
			Enabled:        false,
			Scope:          "tenant",
			CreatedAt:      "2026-07-04T00:00:00Z",
			UpdatedAt:      "2026-07-04T00:00:00Z",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMChannelStore: store})
	request := httptest.NewRequest(http.MethodDelete, "/v1/llm/channels/channel-1", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.deleteInput.TenantID != "tenant-123" || store.deleteInput.ChannelID != "channel-1" {
		t.Fatalf("store lost delete context: %#v", store.deleteInput)
	}
	if !strings.Contains(response.Body.String(), `"enabled":false`) {
		t.Fatalf("expected disabled channel response: %s", response.Body.String())
	}
}

func TestSyncLLMChannelModelsCarriesTenantContextAndReturnsSanitizedModels(t *testing.T) {
	syncer := &recordingLLMModelSyncer{
		result: llm.ModelSyncResult{
			Channel: llm.ChannelRecord{
				ChannelID:      "channel-1",
				Name:           "Draft Channel",
				Provider:       "openai-compatible",
				BaseURL:        "https://llm.example.test/v1",
				MaxConcurrency: 2,
				Enabled:        true,
				LastSyncAt:     "2026-07-04T01:00:00Z",
				LastSyncStatus: "ok:2",
				Scope:          "tenant",
				CreatedAt:      "2026-07-04T00:00:00Z",
				UpdatedAt:      "2026-07-04T01:00:00Z",
			},
			Models: []llm.ModelRecord{
				{
					ModelID:   "gpt-4.1",
					OwnedBy:   "openai",
					CreatedAt: "2026-07-04T01:00:00Z",
					UpdatedAt: "2026-07-04T01:00:00Z",
				},
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMModelSyncer: syncer})
	request := httptest.NewRequest(http.MethodPost, "/v1/llm/channels/channel-1/sync-models", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if syncer.input.TenantID != "tenant-123" || syncer.input.ChannelID != "channel-1" {
		t.Fatalf("syncer lost tenant/channel context: %#v", syncer.input)
	}
	rawBody := response.Body.String()
	for _, forbidden := range []string{"api_key", "encrypted_api_key", "credential_ref", "raw_payload_jsonb"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("model sync response leaked %s: %s", forbidden, rawBody)
		}
	}
	if !strings.Contains(rawBody, `"last_sync_status":"ok:2"`) || !strings.Contains(rawBody, `"model_id":"gpt-4.1"`) {
		t.Fatalf("unexpected sync response: %s", rawBody)
	}
}

func TestCreateLLMChannelWithoutStoreFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/llm/channels",
		bytes.NewBufferString(`{"name":"Draft Channel","provider":"openai-compatible","base_url":"https://llm.example.test/v1","api_key":"sk-secret","max_concurrency":4,"enabled":true}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "LLM_CHANNEL_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestListLLMChannelsWithoutCatalogReaderFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/channels", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "LLM_CATALOG_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestListLLMActivityReturnsSanitizedTenantProjectScopedRows(t *testing.T) {
	reader := &recordingLLMTelemetryReader{
		activities: []llm.ActivityRecord{
			{
				ActivityID:       "activity-1",
				ProjectID:        "project-123",
				RunID:            "run_123",
				ModuleKey:        "writer_composer",
				ChannelID:        "channel-1",
				ModelID:          "model-1",
				Status:           "completed",
				PromptTokens:     11,
				CompletionTokens: 17,
				LatencyMS:        1200,
				CostEstimate:     0.0045,
				CreatedAt:        "2026-07-04T00:00:00Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMTelemetryReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/activity?run_id=run_123&module_key=writer_composer", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.activityInput.TenantID != "tenant-123" || reader.activityInput.ProjectID != "project-123" {
		t.Fatalf("reader lost tenant/project context: %#v", reader.activityInput)
	}
	if reader.activityInput.RunID != "run_123" || reader.activityInput.ModuleKey != "writer_composer" {
		t.Fatalf("reader lost filters: %#v", reader.activityInput)
	}
	rawBody := response.Body.String()
	var body map[string]any
	if err := json.NewDecoder(strings.NewReader(rawBody)).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	items := body["items"].([]any)
	item := items[0].(map[string]any)
	if item["activity_id"] != "activity-1" || item["status"] != "completed" {
		t.Fatalf("unexpected activity item: %#v", item)
	}
	for _, forbidden := range []string{"api_key", "encrypted_api_key", `"prompt"`, `"response"`, "credential_ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("activity response leaked %s: %s", forbidden, rawBody)
		}
	}
}

func TestListLLMActivitySanitizesReaderErrorPayloadAtHTTPBoundary(t *testing.T) {
	reader := &recordingLLMTelemetryReader{
		activities: []llm.ActivityRecord{
			{
				ActivityID: "activity-1",
				ProjectID:  "project-123",
				RunID:      "550e8400-e29b-41d4-a716-446655440000",
				ModuleKey:  "worldline_director",
				Status:     "failed",
				Error: map[string]any{
					"code":           "LLM_PROVIDER_ERROR",
					"message":        "provider failed",
					"api_key":        "sk-leaked",
					"prompt":         "private prompt",
					"candidate_body": "hidden candidate",
					"nested": map[string]any{
						"credential_ref":  "secret-ref",
						"source_material": "private source",
						"safe":            "visible",
					},
					"events": []any{
						map[string]any{"event_body": "secret event", "summary": "visible summary"},
					},
				},
				CreatedAt: "2026-07-04T00:00:00Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMTelemetryReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/activity?run_id=550e8400-e29b-41d4-a716-446655440000&module_key=worldline_director", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	rawBody := response.Body.String()
	var body map[string]any
	if err := json.NewDecoder(strings.NewReader(rawBody)).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	item := body["items"].([]any)[0].(map[string]any)
	errorPayload := item["error"].(map[string]any)
	if errorPayload["code"] != "LLM_PROVIDER_ERROR" || errorPayload["message"] != "provider failed" {
		t.Fatalf("expected safe error summary, got %#v", errorPayload)
	}
	nested := errorPayload["nested"].(map[string]any)
	if nested["safe"] != "visible" {
		t.Fatalf("expected safe nested value, got %#v", nested)
	}
	for _, forbidden := range []string{"api_key", "sk-leaked", "prompt", "private prompt", "candidate_body", "hidden candidate", "credential_ref", "secret-ref", "source_material", "private source", "event_body", "secret event"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("activity response leaked %q: %s", forbidden, rawBody)
		}
	}
}

func TestListLLMActivitySanitizesTelemetryQueryErrorAtHTTPBoundary(t *testing.T) {
	reader := &recordingLLMTelemetryReader{
		activityErr: &llm.AppError{
			Code:    "LLM_ACTIVITY_QUERY_FAILED",
			Message: "driver failed api_key=sk-leaked prompt=private credential_ref=secret-ref",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMTelemetryReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/activity?run_id=550e8400-e29b-41d4-a716-446655440000&module_key=worldline_director", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	rawBody := response.Body.String()
	var body errorEnvelope
	if err := json.NewDecoder(strings.NewReader(rawBody)).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "LLM_ACTIVITY_QUERY_FAILED" || body.Error.Message != "LLM activity query failed" {
		t.Fatalf("expected stable query error response, got %#v", body)
	}
	for _, forbidden := range []string{"api_key", "sk-leaked", "prompt", "private", "credential_ref", "secret-ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("activity query error leaked %q: %s", forbidden, rawBody)
		}
	}
}

func TestListLLMUsageReturnsTenantProjectScopedSummary(t *testing.T) {
	reader := &recordingLLMTelemetryReader{
		usage: []llm.UsageRecord{
			{
				UsageType: "llm_tokens",
				Quantity:  28,
				Unit:      "tokens",
				ModuleKey: "writer_composer",
				RunID:     "run_123",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMTelemetryReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/usage?run_id=run_123", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.usageInput.TenantID != "tenant-123" || reader.usageInput.ProjectID != "project-123" || reader.usageInput.RunID != "run_123" {
		t.Fatalf("reader lost usage context: %#v", reader.usageInput)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	items := body["items"].([]any)
	item := items[0].(map[string]any)
	if item["usage_type"] != "llm_tokens" || item["quantity"] != float64(28) || item["unit"] != "tokens" {
		t.Fatalf("unexpected usage item: %#v", item)
	}
}

func TestListLLMUsageSanitizesTelemetryQueryErrorAtHTTPBoundary(t *testing.T) {
	reader := &recordingLLMTelemetryReader{
		usageErr: &llm.AppError{
			Code:    "LLM_ACTIVITY_QUERY_FAILED",
			Message: "usage driver failed api_key=sk-leaked prompt=private credential_ref=secret-ref",
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, LLMTelemetryReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/usage?run_id=550e8400-e29b-41d4-a716-446655440000&module_key=worldline_director", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	rawBody := response.Body.String()
	var body errorEnvelope
	if err := json.NewDecoder(strings.NewReader(rawBody)).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "LLM_ACTIVITY_QUERY_FAILED" || body.Error.Message != "LLM activity query failed" {
		t.Fatalf("expected stable query error response, got %#v", body)
	}
	for _, forbidden := range []string{"api_key", "sk-leaked", "prompt", "private", "credential_ref", "secret-ref"} {
		if strings.Contains(rawBody, forbidden) {
			t.Fatalf("usage query error leaked %q: %s", forbidden, rawBody)
		}
	}
}

func TestListLLMActivityWithoutTelemetryReaderFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/activity", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "LLM_ACTIVITY_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestListAgentTraceEventsReturnsRedactedTenantProjectScopedRows(t *testing.T) {
	reader := &recordingTraceReader{
		events: []traces.EventRecord{
			{
				EventID:        "event-1",
				TraceID:        "trace-1",
				EventOrder:     1,
				EventType:      "prompt_snapshot",
				Payload:        map[string]any{},
				RedactionLevel: "full",
				CreatedAt:      "2026-07-04T00:00:00Z",
			},
		},
	}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, TraceReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/agent-traces/trace-1/events", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if reader.input.TenantID != "tenant-123" || reader.input.ProjectID != "project-123" || reader.input.TraceID != "trace-1" || reader.input.IncludeFull {
		t.Fatalf("reader lost trace context: %#v", reader.input)
	}
	rawBody := response.Body.String()
	if strings.Contains(rawBody, "写下一场") || strings.Contains(rawBody, "api_key") || strings.Contains(rawBody, "response_text") {
		t.Fatalf("redacted trace response leaked sensitive payload: %s", rawBody)
	}
}

func TestListAgentTraceEventsFullPayloadRequiresPermission(t *testing.T) {
	reader := &recordingTraceReader{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, TraceReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/agent-traces/trace-1/events?include_full=true", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden {
		t.Fatalf("expected status %d, got %d: %s", http.StatusForbidden, response.Code, response.Body.String())
	}
	if reader.input.TraceID != "" {
		t.Fatalf("reader should not be called before full trace permission: %#v", reader.input)
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "TRACE_ACCESS_DENIED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestListAgentTraceEventsFullPayloadWhenAuthorized(t *testing.T) {
	reader := &recordingTraceReader{
		events: []traces.EventRecord{
			{
				EventID:        "event-1",
				TraceID:        "trace-1",
				EventOrder:     1,
				EventType:      "prompt_snapshot",
				Payload:        map[string]any{"instruction": "写下一场雨夜谈判"},
				RedactionLevel: "full",
				CreatedAt:      "2026-07-04T00:00:00Z",
			},
		},
	}
	access := &allowTraceAccessChecker{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, TraceReader: reader, TraceAccessChecker: access})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/agent-traces/trace-1/events?include_full=true", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if !reader.input.IncludeFull || access.input.ActorID != "user-123" {
		t.Fatalf("full trace access context was not preserved: reader=%#v access=%#v", reader.input, access.input)
	}
	if !strings.Contains(response.Body.String(), "写下一场雨夜谈判") {
		t.Fatalf("expected full payload after authorization: %s", response.Body.String())
	}
}

func TestListAgentTraceEventsWithoutReaderFailsExplicitly(t *testing.T) {
	server := NewServer(Config{WriterStarter: &recordingStarter{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/agent-traces/trace-1/events", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "AGENT_TRACE_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestExportAgentTraceRequiresFullTracePermission(t *testing.T) {
	reader := &recordingTraceReader{}
	auditor := &recordingTraceExportAuditor{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, TraceReader: reader, TraceExportAuditor: auditor})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/agent-traces/trace-1/export", bytes.NewBufferString(`{"include_full":true}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden {
		t.Fatalf("expected status %d, got %d: %s", http.StatusForbidden, response.Code, response.Body.String())
	}
	if reader.input.TraceID != "" || auditor.input.TraceID != "" {
		t.Fatalf("export should not read or audit before full trace permission: reader=%#v auditor=%#v", reader.input, auditor.input)
	}
}

func TestExportAgentTraceAuditsAndReturnsEvents(t *testing.T) {
	reader := &recordingTraceReader{
		events: []traces.EventRecord{
			{
				EventID:        "event-1",
				TraceID:        "trace-1",
				EventOrder:     1,
				EventType:      "prompt_snapshot",
				Payload:        map[string]any{"instruction": "写下一场雨夜谈判"},
				RedactionLevel: "full",
				CreatedAt:      "2026-07-04T00:00:00Z",
			},
		},
	}
	access := &allowTraceAccessChecker{}
	auditor := &recordingTraceExportAuditor{}
	server := NewServer(Config{
		WriterStarter:      &recordingStarter{},
		TraceReader:        reader,
		TraceAccessChecker: access,
		TraceExportAuditor: auditor,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/agent-traces/trace-1/export", bytes.NewBufferString(`{"include_full":true}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	request.Header.Set("X-Request-Id", "req_export")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if !reader.input.IncludeFull || !auditor.input.IncludeFull || auditor.input.EventCount != 1 {
		t.Fatalf("export lost full trace or audit context: reader=%#v auditor=%#v", reader.input, auditor.input)
	}
	if auditor.input.ActorID != "user-123" || auditor.input.RequestID != "req_export" {
		t.Fatalf("audit lost actor/request context: %#v", auditor.input)
	}
	rawBody := response.Body.String()
	if !strings.Contains(rawBody, "写下一场雨夜谈判") || !strings.Contains(rawBody, `"trace_id":"trace-1"`) {
		t.Fatalf("unexpected export body: %s", rawBody)
	}
}

func TestExportAgentTraceWithoutAuditorFailsExplicitly(t *testing.T) {
	reader := &recordingTraceReader{}
	access := &allowTraceAccessChecker{}
	server := NewServer(Config{WriterStarter: &recordingStarter{}, TraceReader: reader, TraceAccessChecker: access})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-123/agent-traces/trace-1/export", bytes.NewBufferString(`{"include_full":false}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected status %d, got %d: %s", http.StatusServiceUnavailable, response.Code, response.Body.String())
	}
	var body errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Error.Code != "TRACE_AUDIT_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error body: %#v", body)
	}
}

func TestLLMFacilityAndTraceValidationErrorsDoNotEchoDecoderDetails(t *testing.T) {
	tests := []struct {
		name      string
		method    string
		path      string
		body      string
		message   string
		requestID string
	}{
		{
			name:      "module binding",
			method:    http.MethodPut,
			path:      "/v1/projects/project-123/llm/module-bindings/writer_composer",
			body:      `{"channel_id":"channel-1","model_id":"model-1","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid llm module binding payload",
			requestID: "req-llm-binding-validation",
		},
		{
			name:      "channel create",
			method:    http.MethodPost,
			path:      "/v1/llm/channels",
			body:      `{"name":"Draft Channel","provider":"openai-compatible","base_url":"https://llm.example.test/v1","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid llm channel payload",
			requestID: "req-llm-channel-create-validation",
		},
		{
			name:      "channel patch",
			method:    http.MethodPatch,
			path:      "/v1/llm/channels/channel-1",
			body:      `{"name":"Draft Channel","base_url":"https://llm.example.test/v1","api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid llm channel payload",
			requestID: "req-llm-channel-patch-validation",
		},
		{
			name:      "trace export",
			method:    http.MethodPost,
			path:      "/v1/projects/project-123/agent-traces/trace-1/export",
			body:      `{"include_full":false,"api_key":"sk-hidden","prompt":"private","credential_ref":"cred-hidden","draft":"private","manuscript":"private"}`,
			message:   "invalid trace export payload",
			requestID: "req-trace-export-validation",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := NewServer(Config{WriterStarter: &recordingStarter{}})
			request := httptest.NewRequest(tt.method, tt.path, strings.NewReader(tt.body))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Tenant-Id", "tenant-123")
			request.Header.Set("X-Request-Id", tt.requestID)
			response := httptest.NewRecorder()

			server.ServeHTTP(response, request)

			if response.Code != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d: %s", response.Code, response.Body.String())
			}
			body := response.Body.String()
			if !strings.Contains(body, `"code":"VALIDATION_FAILED"`) ||
				!strings.Contains(body, `"message":"`+tt.message+`"`) ||
				!strings.Contains(body, `"request_id":"`+tt.requestID+`"`) ||
				!strings.Contains(body, `"details":{}`) {
				t.Fatalf("expected stable LLM/trace validation failure, got %s", body)
			}
			for _, forbidden := range []string{
				`"details":{"error"`,
				"json:",
				"api_key",
				"sk-hidden",
				"prompt",
				"credential_ref",
				"draft",
				"manuscript",
			} {
				if strings.Contains(body, forbidden) {
					t.Fatalf("LLM/trace validation response leaked forbidden detail %q: %s", forbidden, body)
				}
			}
		})
	}
}

func TestLLMFacilityRoutesSanitizeStoreErrorMessagesAtHTTPBoundary(t *testing.T) {
	sensitiveMessage := "driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden draft=private manuscript=private"
	tests := []struct {
		name            string
		method          string
		path            string
		body            string
		config          Config
		expectedCode    string
		expectedMessage string
	}{
		{
			name:   "resolve binding query",
			method: http.MethodGet,
			path:   "/v1/projects/project-123/llm/module-bindings/writer_composer/resolution",
			config: Config{
				WriterStarter: &recordingStarter{},
				LLMResolver:   failingLLMResolver{err: &llm.AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_BINDING_QUERY_FAILED",
			expectedMessage: "LLM module binding query failed",
		},
		{
			name:   "list module bindings query",
			method: http.MethodGet,
			path:   "/v1/projects/project-123/llm/module-bindings",
			config: Config{
				WriterStarter:   &recordingStarter{},
				LLMBindingStore: &recordingLLMBindingStore{err: &llm.AppError{Code: "LLM_BINDING_QUERY_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_BINDING_QUERY_FAILED",
			expectedMessage: "LLM module binding query failed",
		},
		{
			name:   "upsert module binding update",
			method: http.MethodPut,
			path:   "/v1/projects/project-123/llm/module-bindings/writer_composer",
			body:   `{"channel_id":"channel-1","model_id":"model-1","settings":{}}`,
			config: Config{
				WriterStarter:   &recordingStarter{},
				LLMBindingStore: &recordingLLMBindingStore{err: &llm.AppError{Code: "LLM_BINDING_UPDATE_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_BINDING_UPDATE_FAILED",
			expectedMessage: "LLM module binding update failed",
		},
		{
			name:   "delete module binding",
			method: http.MethodDelete,
			path:   "/v1/projects/project-123/llm/module-bindings/writer_composer",
			config: Config{
				WriterStarter:   &recordingStarter{},
				LLMBindingStore: &recordingLLMBindingStore{err: &llm.AppError{Code: "LLM_BINDING_DELETE_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_BINDING_DELETE_FAILED",
			expectedMessage: "LLM module binding delete failed",
		},
		{
			name:   "list channels query",
			method: http.MethodGet,
			path:   "/v1/projects/project-123/llm/channels",
			config: Config{
				WriterStarter:    &recordingStarter{},
				LLMCatalogReader: &recordingLLMCatalogReader{err: &llm.AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_CATALOG_QUERY_FAILED",
			expectedMessage: "LLM catalog query failed",
		},
		{
			name:   "list models query",
			method: http.MethodGet,
			path:   "/v1/projects/project-123/llm/channels/channel-1/models",
			config: Config{
				WriterStarter:    &recordingStarter{},
				LLMCatalogReader: &recordingLLMCatalogReader{err: &llm.AppError{Code: "LLM_CATALOG_QUERY_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_CATALOG_QUERY_FAILED",
			expectedMessage: "LLM catalog query failed",
		},
		{
			name:   "settings query",
			method: http.MethodGet,
			path:   "/v1/llm/settings",
			config: Config{
				WriterStarter:     &recordingStarter{},
				LLMSettingsReader: &recordingLLMSettingsReader{err: &llm.AppError{Code: "LLM_SETTINGS_QUERY_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_SETTINGS_QUERY_FAILED",
			expectedMessage: "LLM settings query failed",
		},
		{
			name:   "create channel update",
			method: http.MethodPost,
			path:   "/v1/llm/channels",
			body:   `{"name":"Draft Channel","provider":"openai-compatible","base_url":"https://llm.example.test/v1","api_key":"sk-request","max_concurrency":4,"enabled":true}`,
			config: Config{
				WriterStarter:   &recordingStarter{},
				LLMChannelStore: &recordingLLMChannelStore{err: &llm.AppError{Code: "LLM_CHANNEL_UPDATE_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_CHANNEL_UPDATE_FAILED",
			expectedMessage: "LLM channel update failed",
		},
		{
			name:   "patch channel update",
			method: http.MethodPatch,
			path:   "/v1/llm/channels/channel-1",
			body:   `{"name":"Draft Channel","base_url":"https://llm.example.test/v1","max_concurrency":2,"enabled":true}`,
			config: Config{
				WriterStarter:   &recordingStarter{},
				LLMChannelStore: &recordingLLMChannelStore{err: &llm.AppError{Code: "LLM_CHANNEL_UPDATE_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_CHANNEL_UPDATE_FAILED",
			expectedMessage: "LLM channel update failed",
		},
		{
			name:   "delete channel update",
			method: http.MethodDelete,
			path:   "/v1/llm/channels/channel-1",
			config: Config{
				WriterStarter:   &recordingStarter{},
				LLMChannelStore: &recordingLLMChannelStore{err: &llm.AppError{Code: "LLM_CHANNEL_UPDATE_FAILED", Message: sensitiveMessage}},
			},
			expectedCode:    "LLM_CHANNEL_UPDATE_FAILED",
			expectedMessage: "LLM channel update failed",
		},
		{
			name:   "model sync query",
			method: http.MethodPost,
			path:   "/v1/llm/channels/channel-1/sync-models",
			config: Config{
				WriterStarter: &recordingStarter{},
				LLMModelSyncer: &recordingLLMModelSyncer{
					err: &llm.AppError{Code: "LLM_MODEL_SYNC_QUERY_FAILED", Message: sensitiveMessage},
				},
			},
			expectedCode:    "LLM_MODEL_SYNC_QUERY_FAILED",
			expectedMessage: "LLM model sync query failed",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := NewServer(tt.config)
			body := tt.body
			if body == "" {
				body = `{}`
			}
			request := httptest.NewRequest(tt.method, tt.path, strings.NewReader(body))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Tenant-Id", "tenant-123")
			request.Header.Set("X-Request-Id", "req-llm-store-error")
			response := httptest.NewRecorder()

			server.ServeHTTP(response, request)

			if response.Code < 400 {
				t.Fatalf("expected error status, got %d: %s", response.Code, response.Body.String())
			}
			var envelope errorEnvelope
			if err := json.NewDecoder(response.Body).Decode(&envelope); err != nil {
				t.Fatalf("decode response: %v", err)
			}
			if envelope.Error.Code != tt.expectedCode || envelope.Error.Message != tt.expectedMessage {
				t.Fatalf("expected stable LLM error %s/%q, got %#v", tt.expectedCode, tt.expectedMessage, envelope.Error)
			}
			if envelope.Error.RequestID != "req-llm-store-error" {
				t.Fatalf("request id not preserved: %#v", envelope.Error)
			}
			rawBody := response.Body.String()
			for _, forbidden := range []string{"prompt=hidden", "api_key", "sk-hidden", "credential_ref", "draft=private", "manuscript=private", "driver exploded"} {
				if strings.Contains(rawBody, forbidden) {
					t.Fatalf("LLM store error leaked forbidden detail %q: %s", forbidden, rawBody)
				}
			}
		})
	}
}

type recordingHelloStarter struct {
	input workflows.StartHelloAgentInput
}

func (s *recordingHelloStarter) StartHelloAgent(ctx context.Context, input workflows.StartHelloAgentInput) (workflows.HelloAgentRun, error) {
	s.input = input
	return workflows.HelloAgentRun{
		RunID:        "hello_run_123",
		ProjectID:    input.ProjectID,
		WorkflowType: "hello_agent",
		Status:       "completed",
	}, nil
}

type recordingLLMTelemetryReader struct {
	activityInput llm.ActivityQueryInput
	usageInput    llm.UsageQueryInput
	activities    []llm.ActivityRecord
	usage         []llm.UsageRecord
	activityErr   error
	usageErr      error
}

type recordingLLMSettingsReader struct {
	input    llm.SettingsInput
	snapshot llm.SettingsSnapshot
	err      error
}

type recordingLLMBindingStore struct {
	listInput   llm.ListModuleBindingsInput
	upsertInput llm.UpsertProjectModuleBindingInput
	deleteInput llm.DeleteProjectModuleBindingInput
	bindings    []llm.ModuleBindingRecord
	upserted    llm.ModuleBindingRecord
	deleted     llm.ModuleBindingRecord
	err         error
}

type recordingLLMCatalogReader struct {
	channelInput llm.CatalogQueryInput
	modelInput   llm.ModelQueryInput
	channels     []llm.ChannelRecord
	models       []llm.ModelRecord
	err          error
}

type recordingLLMChannelStore struct {
	createInput llm.CreateChannelInput
	updateInput llm.UpdateChannelInput
	deleteInput llm.DeleteChannelInput
	created     llm.ChannelRecord
	updated     llm.ChannelRecord
	deleted     llm.ChannelRecord
	err         error
}

type recordingLLMModuleRegistry struct {
	input   llm.ModuleRegistryInput
	modules []llm.ModuleRecord
	err     error
}

type recordingLLMModelSyncer struct {
	input  llm.ModelSyncInput
	result llm.ModelSyncResult
	err    error
}

type failingLLMResolver struct {
	err error
}

func (r failingLLMResolver) ResolveModuleBinding(context.Context, llm.ResolveModuleInput) (llm.ModuleResolution, error) {
	return llm.ModuleResolution{}, r.err
}

func (s *recordingLLMBindingStore) ListModuleBindings(ctx context.Context, input llm.ListModuleBindingsInput) ([]llm.ModuleBindingRecord, error) {
	s.listInput = input
	if s.err != nil {
		return nil, s.err
	}
	return s.bindings, nil
}

func (s *recordingLLMBindingStore) UpsertProjectModuleBinding(ctx context.Context, input llm.UpsertProjectModuleBindingInput) (llm.ModuleBindingRecord, error) {
	s.upsertInput = input
	if s.err != nil {
		return llm.ModuleBindingRecord{}, s.err
	}
	return s.upserted, nil
}

func (s *recordingLLMBindingStore) DeleteProjectModuleBinding(ctx context.Context, input llm.DeleteProjectModuleBindingInput) (llm.ModuleBindingRecord, error) {
	s.deleteInput = input
	if s.err != nil {
		return llm.ModuleBindingRecord{}, s.err
	}
	return s.deleted, nil
}

func (r *recordingLLMCatalogReader) ListChannels(ctx context.Context, input llm.CatalogQueryInput) ([]llm.ChannelRecord, error) {
	r.channelInput = input
	if r.err != nil {
		return nil, r.err
	}
	return r.channels, nil
}

func (r *recordingLLMCatalogReader) ListModels(ctx context.Context, input llm.ModelQueryInput) ([]llm.ModelRecord, error) {
	r.modelInput = input
	if r.err != nil {
		return nil, r.err
	}
	return r.models, nil
}

func (s *recordingLLMChannelStore) CreateChannel(ctx context.Context, input llm.CreateChannelInput) (llm.ChannelRecord, error) {
	s.createInput = input
	if s.err != nil {
		return llm.ChannelRecord{}, s.err
	}
	return s.created, nil
}

func (s *recordingLLMChannelStore) UpdateChannel(ctx context.Context, input llm.UpdateChannelInput) (llm.ChannelRecord, error) {
	s.updateInput = input
	if s.err != nil {
		return llm.ChannelRecord{}, s.err
	}
	return s.updated, nil
}

func (s *recordingLLMChannelStore) DeleteChannel(ctx context.Context, input llm.DeleteChannelInput) (llm.ChannelRecord, error) {
	s.deleteInput = input
	if s.err != nil {
		return llm.ChannelRecord{}, s.err
	}
	return s.deleted, nil
}

func (r *recordingLLMModuleRegistry) ListModules(ctx context.Context, input llm.ModuleRegistryInput) ([]llm.ModuleRecord, error) {
	r.input = input
	return r.modules, r.err
}

func (s *recordingLLMModelSyncer) SyncModels(ctx context.Context, input llm.ModelSyncInput) (llm.ModelSyncResult, error) {
	s.input = input
	return s.result, s.err
}

func (r *recordingLLMSettingsReader) GetSettings(ctx context.Context, input llm.SettingsInput) (llm.SettingsSnapshot, error) {
	r.input = input
	return r.snapshot, r.err
}

func (r *recordingLLMTelemetryReader) ListActivity(ctx context.Context, input llm.ActivityQueryInput) ([]llm.ActivityRecord, error) {
	r.activityInput = input
	if r.activityErr != nil {
		return nil, r.activityErr
	}
	return r.activities, nil
}

func (r *recordingLLMTelemetryReader) ListUsage(ctx context.Context, input llm.UsageQueryInput) ([]llm.UsageRecord, error) {
	r.usageInput = input
	if r.usageErr != nil {
		return nil, r.usageErr
	}
	return r.usage, nil
}

type recordingTraceReader struct {
	input  traces.EventQueryInput
	events []traces.EventRecord
}

func (r *recordingTraceReader) ListEvents(ctx context.Context, input traces.EventQueryInput) ([]traces.EventRecord, error) {
	r.input = input
	return r.events, nil
}

type allowTraceAccessChecker struct {
	input traces.AccessInput
}

func (c *allowTraceAccessChecker) CanViewFullTrace(ctx context.Context, input traces.AccessInput) error {
	c.input = input
	return nil
}

type allowStoryGraphEvidenceAccessChecker struct {
	input storygraph.EvidenceAccessInput
}

func (c *allowStoryGraphEvidenceAccessChecker) CanViewEvidenceSnippets(ctx context.Context, input storygraph.EvidenceAccessInput) error {
	c.input = input
	return nil
}

type recordingTraceExportAuditor struct {
	input traces.ExportAuditInput
}

func (a *recordingTraceExportAuditor) RecordExport(ctx context.Context, input traces.ExportAuditInput) error {
	a.input = input
	return nil
}

func boundWriterComposerResolver() *llm.StaticResolver {
	return llm.NewStaticResolver([]llm.ModuleResolution{
		{
			TenantID:      "tenant-123",
			ProjectID:     "project-123",
			ModuleKey:     "writer_composer",
			ChannelID:     "channel-1",
			ModelID:       "model-1",
			Provider:      "openai-compatible",
			BaseURL:       "https://llm.example.test/v1",
			CredentialRef: "credref-1",
			SupportsTools: true,
			SupportsJSON:  true,
			Settings:      map[string]any{"temperature": 0.7},
		},
	})
}

func derefString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func derefStringSlice(value *[]string) []string {
	if value == nil {
		return nil
	}
	return *value
}

func derefMap(value *map[string]any) map[string]any {
	if value == nil {
		return map[string]any{}
	}
	return *value
}
