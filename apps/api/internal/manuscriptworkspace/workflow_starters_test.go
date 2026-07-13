package manuscriptworkspace

import (
	"context"
	"testing"

	"mirofish-novel/apps/api/internal/workflows"
)

type recordingRealWriterStarter struct {
	input workflows.StartWriterRunInput
	calls int
}

func (s *recordingRealWriterStarter) StartWriterRun(_ context.Context, input workflows.StartWriterRunInput) (workflows.WriterRun, error) {
	s.calls++
	s.input = input
	return workflows.WriterRun{RunID: "writer-run-1", ProjectID: input.ProjectID, TenantID: input.TenantID}, nil
}

func TestWriterCommandStarterUsesRealWriterAdmissionAndCandidateOnlyOptions(t *testing.T) {
	real := &recordingRealWriterStarter{}
	starter := NewWriterCommandStarter(real)

	started, err := starter.StartWorkflow(context.Background(), WriterStartInput{
		TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1",
		CommandRunID: "command-1", CommandType: CommandCompleteOutline, TargetChapterID: "chapter-1",
		CandidateKind: "outline", CandidateOnly: true, Options: map[string]any{"target_words": 900},
	})
	if err != nil {
		t.Fatalf("start real Writer workflow: %v", err)
	}
	if started.RunID != "writer-run-1" || real.calls != 1 || real.input.Mode != "draft" {
		t.Fatalf("unexpected writer admission: started=%#v input=%#v", started, real.input)
	}
	if real.input.Options["candidate_only"] != true || real.input.Options["candidate_kind"] != "outline" ||
		real.input.Options["command_run_id"] != "command-1" || real.input.Options["module_key"] != writerComposerModuleKey {
		t.Fatalf("writer command lost candidate-only correlation: %#v", real.input.Options)
	}
	if real.input.Options["target_words"] != float64(900) {
		t.Fatalf("writer command lost caller options: %#v", real.input.Options)
	}
}

func TestWriterCommandStarterRejectsNonCandidateInvocationBeforeWriter(t *testing.T) {
	real := &recordingRealWriterStarter{}
	_, err := NewWriterCommandStarter(real).StartWriter(context.Background(), WriterStartInput{
		TenantID: "tenant-1", ProjectID: "project-1", CommandType: CommandContinueChapter,
	})
	if ErrorCode(err) != "VALIDATION_FAILED" || real.calls != 0 {
		t.Fatalf("non-candidate command reached Writer: calls=%d err=%v", real.calls, err)
	}
}
