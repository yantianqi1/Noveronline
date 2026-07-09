package workflows

import (
	"context"
	"errors"
	"strings"
	"testing"

	"go.temporal.io/sdk/client"
)

func TestDisabledWorkflowRetrierFailsClosed(t *testing.T) {
	retrier := NewDisabledWorkflowRetrier()

	_, err := retrier.RetryWorkflowRun(context.Background(), RetryWorkflowRunInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_RETRY_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected retry backend to fail closed, got %s (%v)", code, err)
	}
}

func TestDisabledSeedSegmentRetrierFailsClosed(t *testing.T) {
	retrier := NewDisabledSeedSegmentRetrier()

	_, err := retrier.RetrySeedSegments(context.Background(), RetrySeedSegmentsInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		RunID:       "run-1",
		SegmentIDs:  []string{"segment-1"},
		ActorUserID: "user-1",
		RequestID:   "req-1",
	})

	if code := ErrorCode(err); code != "SEED_SEGMENT_RETRY_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected seed segment retry backend to fail closed, got %s (%v)", code, err)
	}
	if strings.Contains(err.Error(), "segment-1") ||
		strings.Contains(err.Error(), "user-1") ||
		strings.Contains(err.Error(), "prompt") ||
		strings.Contains(err.Error(), "api_key") ||
		strings.Contains(err.Error(), "credential_ref") {
		t.Fatalf("seed segment retry disabled error leaked input: %v", err)
	}
}

func TestSQLSeedSegmentRetrierAdmitsExistingTerminalSegmentsWithSanitizedEvent(t *testing.T) {
	execer := &recordingTenantWriterAdmissionExecer{}
	retrier := NewSQLSeedSegmentRetrier(SQLSeedSegmentRetrierConfig{Execer: execer})

	retried, err := retrier.RetrySeedSegments(context.Background(), RetrySeedSegmentsInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		ProjectID:   "22222222-2222-4222-8222-222222222222",
		RunID:       "33333333-3333-4333-8333-333333333333",
		SegmentIDs:  []string{"77777777-7777-4777-8777-777777777777", "77777777-7777-4777-8777-777777777777", "88888888-8888-4888-8888-888888888888"},
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-segments",
	})

	if err != nil {
		t.Fatalf("retry seed segments: %v", err)
	}
	if retried.RunID != "33333333-3333-4333-8333-333333333333" || retried.Status != "retry_requested" || retried.RequestedCount != 2 {
		t.Fatalf("unexpected retry result: %#v", retried)
	}
	if execer.plainCalled || execer.tenantID != "11111111-1111-4111-8111-111111111111" || execer.projectID != "22222222-2222-4222-8222-222222222222" {
		t.Fatalf("segment retry admission did not use tenant/project context: %#v", execer)
	}
	for _, expected := range []string{
		"WITH requested_segments AS",
		"FROM text_segments",
		"workflow_runs.workflow_type = 'seed_pipeline'",
		"workflow_runs.status IN ('failed', 'cancelled')",
		"INSERT INTO seed_segment_retry_requests",
		"ON CONFLICT (tenant_id, run_id, segment_id)",
		"'seed.segments.retry_requested'",
		"segment_retry_guard AS",
		"COUNT(*) FROM segment_scope",
		"COUNT(*) FROM requested_segments",
		"1 / 0",
	} {
		if !strings.Contains(execer.query, expected) {
			t.Fatalf("segment retry admission query missing %q: %s", expected, execer.query)
		}
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, expected := range []string{
		"11111111-1111-4111-8111-111111111111",
		"22222222-2222-4222-8222-222222222222",
		"33333333-3333-4333-8333-333333333333",
		"77777777-7777-4777-8777-777777777777",
		"88888888-8888-4888-8888-888888888888",
		"retry_requested",
		"req-segments",
	} {
		if !strings.Contains(joinedArgs, expected) {
			t.Fatalf("segment retry admission args lost %q: %s", expected, joinedArgs)
		}
	}
	for _, forbidden := range []string{"object_key", "private/object.txt", "prompt", "provider", "raw body", "content", "api_key", "credential_ref", "draft", "manuscript"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("segment retry admission args leaked %q: %s", forbidden, joinedArgs)
		}
	}
	eventPayload := argsAsStrings([]any{execer.args[6]})[0]
	if strings.Contains(eventPayload, "44444444-4444-4444-8444-444444444444") ||
		strings.Contains(eventPayload, "segment_id") ||
		strings.Contains(eventPayload, "77777777-7777-4777-8777-777777777777") {
		t.Fatalf("segment retry public event payload leaked private/internal metadata: %s", eventPayload)
	}
}

func TestSQLSeedSegmentRetrierRejectsInvalidIDsBeforeSQL(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	retrier := NewSQLSeedSegmentRetrier(SQLSeedSegmentRetrierConfig{Execer: execer})

	_, err := retrier.RetrySeedSegments(context.Background(), RetrySeedSegmentsInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		ProjectID:   "22222222-2222-4222-8222-222222222222",
		RunID:       "33333333-3333-4333-8333-333333333333",
		SegmentIDs:  []string{"not-a-uuid", "77777777-7777-4777-8777-777777777777"},
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-segments",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected stable validation failure, got %s (%v)", code, err)
	}
	if execer.query != "" {
		t.Fatalf("invalid segment retry IDs reached SQL: %s", execer.query)
	}
	if strings.Contains(err.Error(), "not-a-uuid") || strings.Contains(err.Error(), "77777777") {
		t.Fatalf("validation error leaked segment ids: %v", err)
	}
}

func TestTemporalWorkflowRetrierRetriesStoredSeedRunWithSanitizedPayload(t *testing.T) {
	temporalClient := &recordingRetryTemporalClient{}
	store := &recordingWorkflowRetryStore{
		target: WorkflowRetryTarget{
			RunID:           "33333333-3333-4333-8333-333333333333",
			ProjectID:       "22222222-2222-4222-8222-222222222222",
			WorkflowType:    SeedWorkflowType,
			Status:          "failed",
			UploadID:        "55555555-5555-4555-8555-555555555555",
			SourceFileID:    "66666666-6666-4666-8666-666666666666",
			SourceObjectKey: "objects/private-source.txt",
			SourceFilename:  "novel.txt",
			SourceMimeType:  "text/plain",
			SourceSizeBytes: 42,
			SourceSHA256:    strings.Repeat("a", 64),
		},
	}
	retrier := NewTemporalWorkflowRetrier(TemporalWorkflowRetrierConfig{
		Client:    temporalClient,
		Store:     store,
		TaskQueue: "seed-heavy-test",
	})

	retried, err := retrier.RetryWorkflowRun(context.Background(), RetryWorkflowRunInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		RunID:       "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-retry",
	})

	if err != nil {
		t.Fatalf("retry seed workflow: %v", err)
	}
	if retried.RunID != "33333333-3333-4333-8333-333333333333" || retried.Status != "retry_requested" {
		t.Fatalf("unexpected retry result: %#v", retried)
	}
	if store.targetInput.TenantID != "11111111-1111-4111-8111-111111111111" || store.targetInput.RunID != "33333333-3333-4333-8333-333333333333" {
		t.Fatalf("store lost target context: %#v", store.targetInput)
	}
	if store.admitInput.TenantID != "11111111-1111-4111-8111-111111111111" ||
		store.admitInput.ProjectID != "22222222-2222-4222-8222-222222222222" ||
		store.admitInput.RunID != "33333333-3333-4333-8333-333333333333" ||
		store.admitInput.WorkflowType != SeedWorkflowType ||
		store.admitInput.TemporalWorkflowID != "seed_run_33333333-3333-4333-8333-333333333333_retry" ||
		store.admitInput.ActorUserID != "44444444-4444-4444-8444-444444444444" ||
		store.admitInput.RequestID != "req-retry" {
		t.Fatalf("store lost retry admission metadata: %#v", store.admitInput)
	}
	if temporalClient.workflowID != "seed_run_33333333-3333-4333-8333-333333333333_retry" ||
		temporalClient.workflowName != SeedWorkflowName ||
		temporalClient.options.TaskQueue != "seed-heavy-test" {
		t.Fatalf("unexpected temporal start: workflowID=%q name=%v options=%#v", temporalClient.workflowID, temporalClient.workflowName, temporalClient.options)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected map payload, got %#v", temporalClient.args)
	}
	if payload["run_id"] != "33333333-3333-4333-8333-333333333333" ||
		payload["workflow_type"] != SeedWorkflowType ||
		payload["source_file_id"] != "66666666-6666-4666-8666-666666666666" ||
		payload["source_mime_type"] != "text/plain" {
		t.Fatalf("payload lost required seed retry metadata: %#v", payload)
	}
	publicPayload := strings.Join(argsAsStrings(store.admitInput.PublicPayload), "\n")
	if strings.Contains(publicPayload, "objects/private-source.txt") ||
		strings.Contains(publicPayload, "aaaaaaaa") ||
		strings.Contains(publicPayload, "prompt") ||
		strings.Contains(publicPayload, "api_key") ||
		strings.Contains(publicPayload, "credential_ref") {
		t.Fatalf("public retry payload leaked private metadata: %s", publicPayload)
	}
}

func TestSQLWorkflowRetryStorePersistsRetryAdmissionWithoutPartialWorkflowUpdate(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLWorkflowRetryStore(SQLWorkflowRetryStoreConfig{Execer: execer})

	err := store.AdmitWorkflowRetry(context.Background(), WorkflowRetryAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333_retry",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-retry",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       "66666666-6666-4666-8666-666666666666",
		PublicPayload:      []any{"status", "retry_requested", "object_key", "private/object.txt", "api_key", "secret"},
	})

	if err != nil {
		t.Fatalf("admit workflow retry: %v", err)
	}
	if !strings.Contains(execer.query, "WITH source_update AS") ||
		!strings.Contains(execer.query, "FROM source_update") ||
		!strings.Contains(execer.query, "temporal_workflow_id = $7") ||
		!strings.Contains(execer.query, "'workflow.retry_requested'") ||
		!strings.Contains(execer.query, "retry_admission_guard AS") ||
		!strings.Contains(execer.query, "COUNT(*) FROM source_update") ||
		!strings.Contains(execer.query, "COUNT(*) FROM workflow_update") ||
		!strings.Contains(execer.query, "1 / 0") {
		t.Fatalf("retry admission query must reset source, update temporal id, guard partial updates, and write retry event, got %s", execer.query)
	}
	workflowUpdateIndex := strings.Index(execer.query, "workflow_update AS")
	sourceUpdateIndex := strings.Index(execer.query, "source_update AS")
	if sourceUpdateIndex < 0 || workflowUpdateIndex < 0 || sourceUpdateIndex > workflowUpdateIndex {
		t.Fatalf("source_update must run before workflow_update to avoid partial retry state, got %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"private/object.txt", "api_key", "secret", "credential_ref", "prompt"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("retry admission args leaked %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, "seed_run_33333333-3333-4333-8333-333333333333_retry") ||
		!strings.Contains(joinedArgs, "retry_requested") {
		t.Fatalf("retry admission args lost public retry metadata: %s", joinedArgs)
	}
}

func TestTemporalWorkflowRetrierRejectsNonTerminalSeedRunBeforeTemporalStart(t *testing.T) {
	temporalClient := &recordingRetryTemporalClient{}
	store := &recordingWorkflowRetryStore{
		target: WorkflowRetryTarget{
			RunID:        "run-1",
			ProjectID:    "project-1",
			WorkflowType: SeedWorkflowType,
			Status:       "running",
		},
	}
	retrier := NewTemporalWorkflowRetrier(TemporalWorkflowRetrierConfig{Client: temporalClient, Store: store})

	_, err := retrier.RetryWorkflowRun(context.Background(), RetryWorkflowRunInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_RETRY_NOT_ALLOWED" {
		t.Fatalf("expected non-terminal retry rejection, got %s (%v)", code, err)
	}
	if temporalClient.workflowID != "" {
		t.Fatalf("temporal should not start for non-terminal run: %#v", temporalClient)
	}
	if store.admitInput.RunID != "" {
		t.Fatalf("retry admission should not run for non-terminal run: %#v", store.admitInput)
	}
}

func TestTemporalWorkflowRetrierRecordsStableFailureWhenTemporalStartFails(t *testing.T) {
	temporalClient := &recordingRetryTemporalClient{err: errors.New("provider prompt hidden api_key=secret credential_ref=ref object_key=private")}
	store := &recordingWorkflowRetryStore{
		target: WorkflowRetryTarget{
			RunID:           "33333333-3333-4333-8333-333333333333",
			ProjectID:       "22222222-2222-4222-8222-222222222222",
			WorkflowType:    SeedWorkflowType,
			Status:          "failed",
			UploadID:        "55555555-5555-4555-8555-555555555555",
			SourceFileID:    "66666666-6666-4666-8666-666666666666",
			SourceObjectKey: "objects/private-source.txt",
			SourceFilename:  "novel.txt",
			SourceMimeType:  "text/plain",
			SourceSHA256:    strings.Repeat("b", 64),
		},
	}
	retrier := NewTemporalWorkflowRetrier(TemporalWorkflowRetrierConfig{Client: temporalClient, Store: store})

	_, err := retrier.RetryWorkflowRun(context.Background(), RetryWorkflowRunInput{
		TenantID: "11111111-1111-4111-8111-111111111111",
		RunID:    "33333333-3333-4333-8333-333333333333",
	})

	if code := ErrorCode(err); code != "WORKFLOW_RETRY_FAILED" {
		t.Fatalf("expected stable retry failure, got %s (%v)", code, err)
	}
	if store.failureInput.ErrorCode != "WORKFLOW_RETRY_FAILED" || store.failureInput.ErrorMessage != seedWorkflowRetryStartFailedMessage {
		t.Fatalf("expected stable persisted failure, got %#v", store.failureInput)
	}
	if strings.Contains(err.Error(), "api_key") || strings.Contains(err.Error(), "credential_ref") || strings.Contains(err.Error(), "object_key") || strings.Contains(err.Error(), "prompt") {
		t.Fatalf("retry error leaked sensitive text: %v", err)
	}
}

func TestSQLWorkflowRetryStoreGetsSeedRetryTargetWithTenantContext(t *testing.T) {
	queryer := &recordingTenantSeedRunQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"33333333-3333-4333-8333-333333333333",
				"22222222-2222-4222-8222-222222222222",
				SeedWorkflowType,
				"failed",
				"55555555-5555-4555-8555-555555555555",
				"66666666-6666-4666-8666-666666666666",
				"objects/private-source.txt",
				"novel.txt",
				"text/plain",
				42,
				strings.Repeat("a", 64),
			}},
		},
	}
	store := NewSQLWorkflowRetryStore(SQLWorkflowRetryStoreConfig{Queryer: queryer})

	target, err := store.GetWorkflowRetryTarget(context.Background(), WorkflowRetryTargetInput{
		TenantID: "11111111-1111-4111-8111-111111111111",
		RunID:    "33333333-3333-4333-8333-333333333333",
	})

	if err != nil {
		t.Fatalf("get retry target: %v", err)
	}
	if queryer.tenantID != "11111111-1111-4111-8111-111111111111" {
		t.Fatalf("retry target lookup did not use tenant context: %#v", queryer)
	}
	if target.WorkflowType != SeedWorkflowType || target.Status != "failed" || target.SourceSizeBytes != 42 {
		t.Fatalf("unexpected retry target: %#v", target)
	}
	if !strings.Contains(queryer.query, "FROM workflow_runs") ||
		!strings.Contains(queryer.query, "workflow.queued") ||
		!strings.Contains(queryer.query, "source_files") {
		t.Fatalf("retry target query must recover seed/source handoff, got %s", queryer.query)
	}
}

func TestSQLWorkflowRetryStoreAdmitsOnlyTerminalSeedRunAndSanitizesEvent(t *testing.T) {
	execer := &recordingTenantSeedAdmissionExecer{}
	store := NewSQLWorkflowRetryStore(SQLWorkflowRetryStoreConfig{Execer: execer})

	err := store.AdmitWorkflowRetry(context.Background(), WorkflowRetryAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333_retry",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-retry",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       "66666666-6666-4666-8666-666666666666",
		PublicPayload: []any{
			"status", "retry_requested",
			"prompt", "private prompt",
			"api_key", "sk-hidden",
			"credential_ref", "cred-hidden",
			"object_key", "objects/private-source.txt",
			"source_sha256", strings.Repeat("a", 64),
		},
	})

	if err != nil {
		t.Fatalf("admit workflow retry: %v", err)
	}
	if !execer.usedTenantContext || execer.usedPlainExec {
		t.Fatalf("retry admission did not use tenant context execer: %#v", execer)
	}
	if !strings.Contains(execer.query, "workflow_type = 'seed_pipeline'") ||
		!strings.Contains(execer.query, "status IN ('failed', 'cancelled')") ||
		!strings.Contains(execer.query, "workflow.retry_requested") ||
		!strings.Contains(execer.query, "UPDATE source_files") ||
		!strings.Contains(execer.query, "parse_status = 'parsing'") {
		t.Fatalf("retry admission query lost state-machine guards: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"private prompt", "sk-hidden", "cred-hidden", "objects/private-source.txt", strings.Repeat("a", 64)} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("retry admission args leaked %q: %s", forbidden, joinedArgs)
		}
	}
}

func TestSQLWorkflowRetryStoreRecordsStableStartFailureAndReleasesSource(t *testing.T) {
	execer := &recordingTenantSeedAdmissionExecer{}
	store := NewSQLWorkflowRetryStore(SQLWorkflowRetryStoreConfig{Execer: execer})

	err := store.RecordWorkflowRetryStartFailure(context.Background(), WorkflowRetryFailureInput{
		TenantID:     "11111111-1111-4111-8111-111111111111",
		ProjectID:    "22222222-2222-4222-8222-222222222222",
		RunID:        "33333333-3333-4333-8333-333333333333",
		WorkflowType: SeedWorkflowType,
		ActorUserID:  "44444444-4444-4444-8444-444444444444",
		RequestID:    "req-retry",
		UploadID:     "55555555-5555-4555-8555-555555555555",
		SourceFileID: "66666666-6666-4666-8666-666666666666",
		ErrorCode:    "provider prompt api_key credential_ref object_key",
		ErrorMessage: "provider prompt api_key credential_ref object_key",
	})

	if err != nil {
		t.Fatalf("record workflow retry start failure: %v", err)
	}
	if !strings.Contains(execer.query, "status = 'failed'") ||
		!strings.Contains(execer.query, "parse_status = 'uploaded'") ||
		!strings.Contains(execer.query, "workflow.failed") ||
		!strings.Contains(execer.query, "LEFT JOIN source_update ON TRUE") ||
		strings.Contains(execer.query, "CROSS JOIN source_update") {
		t.Fatalf("retry failure compensation query lost stable failure/source release without source-row dependency: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	if !strings.Contains(joinedArgs, "WORKFLOW_RETRY_FAILED") ||
		!strings.Contains(joinedArgs, seedWorkflowRetryStartFailedMessage) {
		t.Fatalf("retry failure args lost stable public failure: %s", joinedArgs)
	}
	if strings.Contains(joinedArgs, "provider prompt") ||
		strings.Contains(joinedArgs, "api_key") ||
		strings.Contains(joinedArgs, "credential_ref") ||
		strings.Contains(joinedArgs, "object_key") {
		t.Fatalf("retry failure args leaked private failure text: %s", joinedArgs)
	}
}

type recordingWorkflowRetryStore struct {
	targetInput  WorkflowRetryTargetInput
	target       WorkflowRetryTarget
	targetErr    error
	admitInput   WorkflowRetryAdmissionInput
	admitErr     error
	failureInput WorkflowRetryFailureInput
	failureErr   error
}

func (s *recordingWorkflowRetryStore) GetWorkflowRetryTarget(_ context.Context, input WorkflowRetryTargetInput) (WorkflowRetryTarget, error) {
	s.targetInput = input
	if s.targetErr != nil {
		return WorkflowRetryTarget{}, s.targetErr
	}
	return s.target, nil
}

func (s *recordingWorkflowRetryStore) AdmitWorkflowRetry(_ context.Context, input WorkflowRetryAdmissionInput) error {
	s.admitInput = input
	return s.admitErr
}

func (s *recordingWorkflowRetryStore) RecordWorkflowRetryStartFailure(_ context.Context, input WorkflowRetryFailureInput) error {
	s.failureInput = input
	return s.failureErr
}

type recordingRetryTemporalClient struct {
	options      client.StartWorkflowOptions
	workflowID   string
	workflowName any
	args         []any
	err          error
}

func (c *recordingRetryTemporalClient) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.options = options
	c.workflowID = options.ID
	c.workflowName = workflow
	c.args = args
	return nil, c.err
}

func (c *recordingRetryTemporalClient) CancelWorkflow(context.Context, string, string) error {
	return nil
}
