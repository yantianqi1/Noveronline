package workflows

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"go.temporal.io/sdk/client"
)

type recordingDraftReviewAdmission struct {
	admitted      DraftReviewAdmission
	replayed      bool
	err           error
	compensated   bool
	temporalID    string
	compensateErr error
}

func (s *recordingDraftReviewAdmission) AdmitDraftReview(_ context.Context, _ StartDraftReviewInput, proposed DraftReviewAdmission, temporalID string) (DraftReviewAdmission, bool, error) {
	s.temporalID = temporalID
	if s.err != nil {
		return DraftReviewAdmission{}, false, s.err
	}
	if s.admitted.ReviewID == "" {
		s.admitted = proposed
	}
	return s.admitted, s.replayed, nil
}

func (s *recordingDraftReviewAdmission) CompensateDraftReviewStart(context.Context, StartDraftReviewInput, DraftReviewAdmission) error {
	s.compensated = true
	return s.compensateErr
}

type recordingDraftReviewTemporal struct {
	options client.StartWorkflowOptions
	name    any
	payload map[string]any
	err     error
	calls   int
}

func (c *recordingDraftReviewTemporal) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.calls++
	c.options = options
	c.name = workflow
	if len(args) == 1 {
		c.payload, _ = args[0].(map[string]any)
	}
	return nil, c.err
}

func (c *recordingDraftReviewTemporal) CancelWorkflow(context.Context, string, string) error {
	return nil
}

func draftReviewInput() StartDraftReviewInput {
	return StartDraftReviewInput{
		TenantID: "11111111-1111-4111-8111-111111111111", ProjectID: "22222222-2222-4222-8222-222222222222",
		DraftID: "33333333-3333-4333-8333-333333333333", ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID: "request-review-1", ModuleKey: WriterReviewerModuleKey,
		Options: map[string]any{"severity_floor": "medium", "prompt": "secret", "credential_ref": "secret-ref"},
	}
}

func TestTemporalDraftReviewStarterUsesStableIDAndPrivateIDOnlyPayload(t *testing.T) {
	admission := &recordingDraftReviewAdmission{}
	temporal := &recordingDraftReviewTemporal{}
	starter := NewTemporalDraftReviewStarter(TemporalDraftReviewConfig{Client: temporal, AdmissionStore: admission})

	review, err := starter.StartDraftReview(context.Background(), draftReviewInput())
	if err != nil {
		t.Fatalf("start review: %v", err)
	}
	if temporal.options.ID != "writer_review_"+review.ReviewID || admission.temporalID != temporal.options.ID {
		t.Fatalf("unstable Temporal id: options=%q admission=%q", temporal.options.ID, admission.temporalID)
	}
	if temporal.options.TaskQueue != WriterReviewTaskQueue || temporal.name != WriterReviewWorkflowName {
		t.Fatalf("unexpected Temporal target: %#v %v", temporal.options, temporal.name)
	}
	serialized := strings.ToLower(string(mustDraftReviewJSON(t, temporal.payload)))
	for _, forbidden := range []string{"secret", "severity_floor", "base_url", "credential_ref", "content_text", "draft_text", "provider"} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("Temporal payload leaked %q: %s", forbidden, serialized)
		}
	}
	contextPayload, ok := temporal.payload["context"].(map[string]any)
	if !ok || contextPayload["module_key"] != WriterReviewerModuleKey || contextPayload["workflow_type"] != WriterReviewWorkflowType {
		t.Fatalf("missing independent reviewer context: %#v", temporal.payload)
	}
}

func TestTemporalDraftReviewStarterReplayDoesNotStartTemporal(t *testing.T) {
	admission := &recordingDraftReviewAdmission{replayed: true, admitted: DraftReviewAdmission{
		ReviewID: "55555555-5555-4555-8555-555555555555", RunID: "66666666-6666-4666-8666-666666666666",
		DraftID: "33333333-3333-4333-8333-333333333333", ProjectID: "22222222-2222-4222-8222-222222222222",
		Status: "completed", WorkflowType: WriterReviewWorkflowType,
	}}
	temporal := &recordingDraftReviewTemporal{}
	starter := NewTemporalDraftReviewStarter(TemporalDraftReviewConfig{Client: temporal, AdmissionStore: admission})

	review, err := starter.StartDraftReview(context.Background(), draftReviewInput())
	if err != nil || review.Status != "completed" {
		t.Fatalf("replay failed: %#v %v", review, err)
	}
	if temporal.calls != 0 {
		t.Fatalf("replay started Temporal %d times", temporal.calls)
	}
}

func TestTemporalDraftReviewStarterCompensatesStartFailure(t *testing.T) {
	admission := &recordingDraftReviewAdmission{}
	temporal := &recordingDraftReviewTemporal{err: errors.New("provider draft secret")}
	starter := NewTemporalDraftReviewStarter(TemporalDraftReviewConfig{Client: temporal, AdmissionStore: admission})

	_, err := starter.StartDraftReview(context.Background(), draftReviewInput())
	if ErrorCode(err) != "WORKFLOW_FAILED" || !admission.compensated {
		t.Fatalf("expected compensated stable failure, got %v compensated=%v", err, admission.compensated)
	}
	if strings.Contains(err.Error(), "provider draft secret") {
		t.Fatalf("Temporal error leaked: %v", err)
	}
}

func TestDraftReviewPayloadHashIsStableAndSensitiveOptionsAreRemoved(t *testing.T) {
	input := draftReviewInput()
	first, options, err := draftReviewPayloadHash(input)
	if err != nil {
		t.Fatal(err)
	}
	second, _, err := draftReviewPayloadHash(input)
	if err != nil || first != second {
		t.Fatalf("payload hash is unstable: %q %q %v", first, second, err)
	}
	if strings.Contains(string(options), "secret") || !strings.Contains(string(options), "severity_floor") {
		t.Fatalf("unexpected public options: %s", options)
	}
	input.Options["severity_floor"] = "high"
	changed, _, _ := draftReviewPayloadHash(input)
	if changed == first {
		t.Fatal("different public payload produced the same fingerprint")
	}
}

func TestDraftReviewIssueStatusRejectsImplicitOrUnknownActions(t *testing.T) {
	store := NewSQLDraftReviewIssueStore(nil)
	input := UpdateDraftReviewIssueInput{
		TenantID: "11111111-1111-4111-8111-111111111111", ProjectID: "22222222-2222-4222-8222-222222222222",
		IssueID: "33333333-3333-4333-8333-333333333333", ActorUserID: "44444444-4444-4444-8444-444444444444",
		Version: "2026-07-10 00:00:00+00", Status: "open",
	}
	_, err := store.UpdateIssueStatus(context.Background(), input)
	if ErrorCode(err) != "VALIDATION_FAILED" {
		t.Fatalf("expected explicit terminal status validation, got %v", err)
	}
}

func TestDraftReviewRuntimeServiceFailsClosedWithoutMountedStartOrReadSides(t *testing.T) {
	service := NewDraftReviewRuntimeService(nil, nil)
	if _, err := service.StartDraftReview(context.Background(), draftReviewInput()); ErrorCode(err) != "WRITER_REVIEW_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected start mounting error: %v", err)
	}
	if _, err := service.ListDraftReviews(context.Background(), ListDraftReviewsInput{TenantID: "tenant", DraftID: "draft"}); ErrorCode(err) != "WRITER_REVIEW_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected read mounting error: %v", err)
	}
}

func mustDraftReviewJSON(t *testing.T, value any) []byte {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}
