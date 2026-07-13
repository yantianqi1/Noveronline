package manuscriptworkspace

import (
	"context"
	"fmt"
	"strings"

	"mirofish-novel/apps/api/internal/workflows"
)

const writerComposerModuleKey = "writer_composer"

// WriterCommandStarter adapts one-click workspace commands to the real Writer
// workflow admission path. Every generated result remains a candidate until a
// separate user adoption action is accepted.
type WriterCommandStarter struct {
	starter workflows.WriterStarter
}

func NewWriterCommandStarter(starter workflows.WriterStarter) *WriterCommandStarter {
	return &WriterCommandStarter{starter: starter}
}

func (s *WriterCommandStarter) StartWriter(ctx context.Context, input WriterStartInput) (StartedRun, error) {
	return s.start(ctx, input)
}

func (s *WriterCommandStarter) StartWorkflow(ctx context.Context, input WorkflowStartInput) (StartedRun, error) {
	return s.start(ctx, input)
}

func (s *WriterCommandStarter) start(ctx context.Context, input WriterStartInput) (StartedRun, error) {
	if s == nil || s.starter == nil {
		return StartedRun{}, commandBackendUnconfigured()
	}
	if !input.CandidateOnly {
		return StartedRun{}, validation("writer commands must remain candidate-only")
	}
	mode, instruction, err := commandWriterRequest(input)
	if err != nil {
		return StartedRun{}, err
	}
	options := cloneOptions(input.Options)
	options["module_key"] = writerComposerModuleKey
	options["candidate_only"] = true
	options["candidate_kind"] = input.CandidateKind
	options["command_run_id"] = input.CommandRunID
	options["command_type"] = input.CommandType
	options["chapter_id"] = input.TargetChapterID
	options["scene_id"] = input.TargetSceneID
	options["block_id"] = input.TargetBlockID

	run, err := s.starter.StartWriterRun(ctx, workflows.StartWriterRunInput{
		TenantID: input.TenantID, ProjectID: input.ProjectID, ActorUserID: input.ActorUserID,
		RequestID: input.RequestID, Mode: mode, Instruction: instruction, Options: options,
		WorkflowType: workflows.WriterWorkflowType,
	})
	if err != nil {
		return StartedRun{}, err
	}
	if strings.TrimSpace(run.RunID) == "" {
		return StartedRun{}, fmt.Errorf("writer workflow admission returned no run id")
	}
	return StartedRun{RunID: run.RunID}, nil
}

func commandWriterRequest(input WriterStartInput) (string, string, error) {
	switch input.CommandType {
	case CommandCompleteOutline:
		return "draft", "Produce a complete outline candidate for the selected chapter. Do not modify the active outline or canon.", nil
	case CommandAlignWords:
		return "draft", "Produce a revised prose candidate aligned to the requested word target. Do not replace manuscript content.", nil
	case CommandFillRelationships:
		return "draft", "Produce relationship candidates supported by the selected chapter context. Do not write graph or canon data.", nil
	case CommandContinueChapter:
		return "continue", "Continue the selected chapter as a new draft candidate. Do not adopt it into the manuscript.", nil
	default:
		return "", "", validation("command_type is not supported by the Writer workflow")
	}
}
