package manuscriptworkspace

import (
	"context"
	"errors"
	"testing"
)

type memoryCommandRepository struct {
	run         CommandRun
	replay      bool
	prepareErr  error
	queuedKind  string
	queuedRunID string
	failedCode  string
	matches     []LexiconMatch
}

func (r *memoryCommandRepository) PrepareCommand(_ context.Context, input CommandInput, spec commandSpec, _ string) (CommandRun, bool, error) {
	if r.prepareErr != nil {
		return CommandRun{}, false, r.prepareErr
	}
	if r.run.CommandRunID == "" {
		r.run = CommandRun{CommandRunID: "command-1", ProjectID: input.ProjectID, CommandType: input.CommandType,
			StarterKind: spec.starterKind, CandidateKind: spec.candidateKind, Status: "starting"}
	}
	return r.run, r.replay, nil
}

func (r *memoryCommandRepository) MarkCommandQueued(_ context.Context, _ Scope, _ string, kind, runID string) (CommandRun, error) {
	r.queuedKind, r.queuedRunID = kind, runID
	r.run.Status = "queued"
	if kind == "writer" {
		r.run.WriterRunID = runID
	} else {
		r.run.WorkflowRunID = runID
	}
	return r.run, nil
}

func (r *memoryCommandRepository) MarkCommandFailed(_ context.Context, _ Scope, _ string, code string) error {
	r.failedCode = code
	r.run.Status = "failed"
	return nil
}

func (r *memoryCommandRepository) ExecuteLexiconScan(_ context.Context, _ CommandInput, _ string) (CommandRun, []LexiconMatch, error) {
	r.run.Status = "completed"
	return r.run, r.matches, nil
}

func (r *memoryCommandRepository) GetCommand(context.Context, Scope, string) (CommandRun, error) {
	return r.run, nil
}

type recordingWriterStarter struct {
	input WriterStartInput
	calls int
	err   error
}

func (s *recordingWriterStarter) StartWriter(_ context.Context, input WriterStartInput) (StartedRun, error) {
	s.calls++
	s.input = input
	if s.err != nil {
		return StartedRun{}, s.err
	}
	return StartedRun{RunID: "writer-run-1"}, nil
}

type recordingWorkflowStarter struct {
	input WorkflowStartInput
	calls int
	err   error
}

func (s *recordingWorkflowStarter) StartWorkflow(_ context.Context, input WorkflowStartInput) (StartedRun, error) {
	s.calls++
	s.input = input
	if s.err != nil {
		return StartedRun{}, s.err
	}
	return StartedRun{RunID: "workflow-run-1"}, nil
}

func TestCommandAdmissionsUseRealStarterAndCandidateOnlyContract(t *testing.T) {
	tests := []struct {
		command, chapter, block, starterKind, candidateKind string
	}{
		{CommandCompleteOutline, "chapter-1", "", "workflow", "outline"},
		{CommandAlignWords, "", "block-1", "writer", "prose"},
		{CommandFillRelationships, "chapter-1", "", "workflow", "relationship"},
		{CommandContinueChapter, "chapter-1", "", "writer", "draft"},
	}
	for _, test := range tests {
		t.Run(test.command, func(t *testing.T) {
			repository := &memoryCommandRepository{}
			writer := &recordingWriterStarter{}
			workflow := &recordingWorkflowStarter{}
			service := NewCommandService(repository, writer, workflow)
			result, err := service.Admit(context.Background(), CommandInput{
				Scope: commandTestScope(), CommandType: test.command,
				TargetChapterID: test.chapter, TargetBlockID: test.block,
				Options: map[string]any{"target_words": 1200},
			})
			if err != nil || result.Run.Status != "queued" || repository.queuedKind != test.starterKind {
				t.Fatalf("admit result=%#v kind=%s err=%v", result, repository.queuedKind, err)
			}
			var input WriterStartInput
			if test.starterKind == "writer" {
				if writer.calls != 1 || workflow.calls != 0 {
					t.Fatalf("unexpected starter calls writer=%d workflow=%d", writer.calls, workflow.calls)
				}
				input = writer.input
			} else {
				if workflow.calls != 1 || writer.calls != 0 {
					t.Fatalf("unexpected starter calls writer=%d workflow=%d", writer.calls, workflow.calls)
				}
				input = workflow.input
			}
			if !input.CandidateOnly || input.CandidateKind != test.candidateKind || input.CommandRunID == "" {
				t.Fatalf("candidate boundary was not passed to starter: %#v", input)
			}
		})
	}
}

func TestCommandReplayDoesNotStartAgain(t *testing.T) {
	repository := &memoryCommandRepository{
		replay: true,
		run:    CommandRun{CommandRunID: "command-existing", Status: "queued", CandidateKind: "draft"},
	}
	writer := &recordingWriterStarter{}
	result, err := NewCommandService(repository, writer, nil).Admit(context.Background(), CommandInput{
		Scope: commandTestScope(), CommandType: CommandContinueChapter, TargetChapterID: "chapter-1",
	})
	if err != nil || !result.Replay || writer.calls != 0 {
		t.Fatalf("replay=%#v calls=%d err=%v", result, writer.calls, err)
	}
}

func TestStartFailureIsCompensatedWithoutCompletedState(t *testing.T) {
	repository := &memoryCommandRepository{}
	writer := &recordingWriterStarter{err: errors.New("private provider failure")}
	_, err := NewCommandService(repository, writer, nil).Admit(context.Background(), CommandInput{
		Scope: commandTestScope(), CommandType: CommandContinueChapter, TargetChapterID: "chapter-1",
	})
	if ErrorCode(err) != "COMMAND_START_FAILED" || repository.failedCode != "COMMAND_START_FAILED" || repository.run.Status != "failed" {
		t.Fatalf("error=%v compensated=%q status=%q", err, repository.failedCode, repository.run.Status)
	}
}

func TestLexiconScanIsDeterministicAndNeverCallsGenerationStarter(t *testing.T) {
	repository := &memoryCommandRepository{matches: []LexiconMatch{{EntryID: "entry-1", BlockID: "block-1", Term: "bad", Count: 2}}}
	writer := &recordingWriterStarter{}
	workflow := &recordingWorkflowStarter{}
	result, err := NewCommandService(repository, writer, workflow).Admit(context.Background(), CommandInput{
		Scope: commandTestScope(), CommandType: CommandScanLexicon,
	})
	if err != nil || result.Run.Status != "completed" || len(result.Matches) != 1 || writer.calls != 0 || workflow.calls != 0 {
		t.Fatalf("result=%#v writer=%d workflow=%d err=%v", result, writer.calls, workflow.calls, err)
	}
}

func commandTestScope() Scope {
	return Scope{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1"}
}
