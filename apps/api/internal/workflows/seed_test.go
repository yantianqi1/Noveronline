package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"go.temporal.io/sdk/client"
)

const validSeedSourceSHA256ForTest = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
const validSeedTenantIDForTest = "11111111-1111-4111-8111-111111111111"
const validSeedProjectIDForTest = "22222222-2222-4222-8222-222222222222"
const validSeedActorIDForTest = "44444444-4444-4444-8444-444444444444"
const validSeedUploadIDForTest = "55555555-5555-4555-8555-555555555555"
const validSeedSourceFileIDForTest = "66666666-6666-4666-8666-666666666666"
const validSeedRequestIDForTest = "req-1"
const validSeedSourceObjectKeyForTest = "projects/22222222-2222-4222-8222-222222222222/source-files/55555555-5555-4555-8555-555555555555/book.txt"

func TestDisabledSeedRunStarterFailsExplicitly(t *testing.T) {
	starter := NewDisabledSeedRunStarter()

	_, err := starter.StartSeedRun(context.Background(), StartSeedRunInput{
		TenantID:        validSeedTenantIDForTest,
		ProjectID:       validSeedProjectIDForTest,
		UploadID:        validSeedUploadIDForTest,
		ActorUserID:     validSeedActorIDForTest,
		SourceFileID:    validSeedSourceFileIDForTest,
		SourceObjectKey: validSeedSourceObjectKeyForTest,
		SourceFilename:  "book.txt",
		SourceMimeType:  "text/plain",
		SourceSizeBytes: 99,
		SourceSHA256:    validSeedSourceSHA256ForTest,
	})

	if code := ErrorCode(err); code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit unconfigured workflow backend, got %s (%v)", code, err)
	}
}

func TestTemporalSeedRunStarterStartsSeedWorkflowWithoutWaitingForCompletion(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:         temporalClient,
		TaskQueue:      SeedTaskQueue,
		AdmissionStore: &recordingSeedAdmissionStore{},
	})

	input := validSeedStartInput()
	input.Options = map[string]any{
		"language":       "zh-CN",
		"analysis_depth": "standard",
	}
	run, err := starter.StartSeedRun(context.Background(), input)

	if err != nil {
		t.Fatalf("start seed run: %v", err)
	}
	if run.RunID == "" || run.ProjectID != validSeedProjectIDForTest || run.WorkflowType != SeedWorkflowType || run.Status != "queued" {
		t.Fatalf("unexpected seed run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if temporalClient.options.TaskQueue != SeedTaskQueue || temporalClient.options.ID != "seed_run_"+run.RunID {
		t.Fatalf("unexpected workflow options: %#v", temporalClient.options)
	}
	if temporalClient.workflow != SeedWorkflowName {
		t.Fatalf("unexpected workflow name: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected seed workflow payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != validSeedTenantIDForTest || payload["project_id"] != validSeedProjectIDForTest || payload["run_id"] != run.RunID {
		t.Fatalf("lost run context payload: %#v", payload)
	}
	if payload["upload_id"] != validSeedUploadIDForTest || payload["actor_user_id"] != validSeedActorIDForTest || payload["request_id"] != validSeedRequestIDForTest {
		t.Fatalf("lost seed request metadata: %#v", payload)
	}
	if payload["source_file_id"] != validSeedSourceFileIDForTest ||
		payload["source_object_key"] != validSeedSourceObjectKeyForTest ||
		payload["source_filename"] != "book.txt" ||
		payload["source_mime_type"] != "text/plain" ||
		payload["source_size_bytes"] != int64(99) ||
		payload["source_sha256"] != validSeedSourceSHA256ForTest {
		t.Fatalf("lost internal source metadata in workflow payload: %#v", payload)
	}
	if payload["workflow_type"] != SeedWorkflowType || payload["trace_id"] == "" {
		t.Fatalf("lost workflow metadata: %#v", payload)
	}
	payloadJSON := mapToJSONForTest(t, payload)
	for _, forbidden := range []string{"raw_text", "raw_content", "file_content", "parsed_text"} {
		if strings.Contains(payloadJSON, forbidden) {
			t.Fatalf("seed workflow payload leaked raw file content field %q: %s", forbidden, payloadJSON)
		}
	}
	permissions := payload["permissions"].(map[string][]string)
	if got := permissions["seed_pipeline"][0]; got != "run" {
		t.Fatalf("expected seed permission, got %#v", permissions)
	}
	options := payload["options"].(map[string]any)
	if options["language"] != "zh-CN" || options["analysis_depth"] != "standard" {
		t.Fatalf("lost seed options: %#v", options)
	}
}

func TestTemporalSeedRunStarterSanitizesOptionsBeforeTemporalPayload(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:         temporalClient,
		TaskQueue:      SeedTaskQueue,
		AdmissionStore: &recordingSeedAdmissionStore{},
	})
	input := validSeedStartInput()
	input.Options = map[string]any{
		"language":        "zh-CN",
		"tenant_id":       "body-tenant",
		"project_id":      "body-project",
		"source-material": "private source material",
		"sourceMaterial":  "private camel source material",
		"reader": map[string]any{
			"depth":          "standard",
			"prompt":         "private prompt",
			"api_key":        "sk-hidden",
			"credential_ref": "cred-hidden",
			"api-key":        "sk-hyphen-hidden",
			"credential-ref": "cred-hyphen-hidden",
			"candidateBody":  "private camel candidate body",
		},
		"stages": []any{
			map[string]any{
				"name":                 "parse",
				"body":                 "private body",
				"encrypted_api_key":    "ciphertext",
				"candidate-event-body": "private candidate event",
				"candidateEventBody":   "private camel candidate event",
			},
			map[string]any{
				"name":       "segment",
				"raw_text":   "private source text",
				"raw-text":   "private hyphen raw text",
				"eventBody":  "private camel event body",
				"manuscript": "private manuscript",
			},
		},
	}

	run, err := starter.StartSeedRun(context.Background(), input)

	if err != nil {
		t.Fatalf("start seed run: %v", err)
	}
	if run.RunID == "" || !temporalClient.started {
		t.Fatalf("expected Temporal start, run=%#v started=%v", run, temporalClient.started)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected seed workflow payload map, got %#v", temporalClient.args)
	}
	options, ok := payload["options"].(map[string]any)
	if !ok {
		t.Fatalf("expected sanitized options map, got %#v", payload["options"])
	}
	if options["language"] != "zh-CN" {
		t.Fatalf("safe option was not preserved: %#v", options)
	}
	reader, ok := options["reader"].(map[string]any)
	if !ok || reader["depth"] != "standard" {
		t.Fatalf("safe nested option was not preserved: %#v", options)
	}
	encodedOptions := mapToJSONForTest(t, options)
	for _, forbidden := range []string{
		"tenant_id",
		"body-tenant",
		"project_id",
		"body-project",
		"source-material",
		"private source material",
		"sourceMaterial",
		"private camel source material",
		"prompt",
		"private prompt",
		"api_key",
		"sk-hidden",
		"api-key",
		"sk-hyphen-hidden",
		"encrypted_api_key",
		"ciphertext",
		"credential_ref",
		"cred-hidden",
		"credential-ref",
		"cred-hyphen-hidden",
		"body",
		"private body",
		"candidateBody",
		"private camel candidate body",
		"candidate-event-body",
		"private candidate event",
		"candidateEventBody",
		"private camel candidate event",
		"raw_text",
		"private source text",
		"raw-text",
		"private hyphen raw text",
		"eventBody",
		"private camel event body",
		"manuscript",
		"private manuscript",
	} {
		if strings.Contains(encodedOptions, forbidden) {
			t.Fatalf("seed Temporal options leaked forbidden text %q: %s", forbidden, encodedOptions)
		}
	}
}

func TestTemporalSeedRunStarterRequiresSourceMetadataBeforeAdmission(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	admissionStore := &recordingSeedAdmissionStore{}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:         temporalClient,
		TaskQueue:      SeedTaskQueue,
		AdmissionStore: admissionStore,
	})

	input := validSeedStartInput()
	input.SourceObjectKey = ""
	_, err := starter.StartSeedRun(context.Background(), input)

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected source metadata validation failure, got %s (%v)", code, err)
	}
	if err == nil || err.Error() != "seed source metadata is incomplete" {
		t.Fatalf("unexpected validation error: %v", err)
	}
	for _, forbidden := range []string{"source_object_key", "object_key", "hash", "sha256", "projects/project-1/source-files"} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("validation error leaked forbidden text %q: %s", forbidden, err.Error())
		}
	}
	if admissionStore.input.RunID != "" {
		t.Fatalf("seed starter should fail before workflow admission, got %#v", admissionStore.input)
	}
	if temporalClient.started {
		t.Fatalf("seed starter should fail before Temporal start")
	}
}

func TestTemporalSeedRunStarterRejectsInvalidSourceHandoffBeforeAdmission(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(*StartSeedRunInput)
	}{
		{
			name: "unsupported MIME",
			mutate: func(input *StartSeedRunInput) {
				input.SourceMimeType = "application/json"
				input.SourceSHA256 = validSeedSourceSHA256ForTest
			},
		},
		{
			name: "malformed SHA256",
			mutate: func(input *StartSeedRunInput) {
				input.SourceMimeType = "text/plain; charset=utf-8"
				input.SourceSHA256 = "not-a-sha"
			},
		},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			temporalClient := &recordingSeedTemporalClient{}
			admissionStore := &recordingSeedAdmissionStore{}
			starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
				Client:         temporalClient,
				TaskQueue:      SeedTaskQueue,
				AdmissionStore: admissionStore,
			})
			input := validSeedStartInput()
			tt.mutate(&input)

			_, err := starter.StartSeedRun(context.Background(), input)

			if code := ErrorCode(err); code != "VALIDATION_FAILED" {
				t.Fatalf("expected invalid source handoff validation failure, got %s (%v)", code, err)
			}
			if err == nil || err.Error() != "seed source metadata is incomplete" {
				t.Fatalf("unexpected validation error: %v", err)
			}
			for _, forbidden := range []string{"application/json", "not-a-sha", "sha256", "hash", "object_key", "projects/project-1/source-files", "prompt", "api_key", "credential_ref", "draft", "manuscript"} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("validation error leaked forbidden text %q: %s", forbidden, err.Error())
				}
			}
			if admissionStore.input.RunID != "" {
				t.Fatalf("seed starter should fail before workflow admission, got %#v", admissionStore.input)
			}
			if temporalClient.started {
				t.Fatalf("seed starter should fail before Temporal start")
			}
		})
	}
}

func TestTemporalSeedRunStarterRejectsInvalidUUIDContextBeforeAdmission(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(*StartSeedRunInput)
	}{
		{name: "tenant", mutate: func(input *StartSeedRunInput) { input.TenantID = "tenant prompt=private api_key=sk-hidden" }},
		{name: "project", mutate: func(input *StartSeedRunInput) { input.ProjectID = "project prompt=private api_key=sk-hidden" }},
		{name: "upload", mutate: func(input *StartSeedRunInput) { input.UploadID = "upload prompt=private api_key=sk-hidden" }},
		{name: "actor", mutate: func(input *StartSeedRunInput) { input.ActorUserID = "actor prompt=private api_key=sk-hidden" }},
		{name: "source", mutate: func(input *StartSeedRunInput) { input.SourceFileID = "source prompt=private api_key=sk-hidden" }},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			temporalClient := &recordingSeedTemporalClient{}
			admissionStore := &recordingSeedAdmissionStore{}
			starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
				Client:         temporalClient,
				TaskQueue:      SeedTaskQueue,
				AdmissionStore: admissionStore,
			})
			input := validSeedStartInput()
			tt.mutate(&input)

			_, err := starter.StartSeedRun(context.Background(), input)

			if code := ErrorCode(err); code != "VALIDATION_FAILED" {
				t.Fatalf("expected invalid seed context validation failure, got %s (%v)", code, err)
			}
			if err == nil || err.Error() != "seed workflow context is invalid" {
				t.Fatalf("unexpected validation error: %v", err)
			}
			if admissionStore.input.RunID != "" || admissionStore.failureCalled {
				t.Fatalf("seed starter should fail before admission, got admission=%#v failure=%#v", admissionStore.input, admissionStore.failureInput)
			}
			if temporalClient.started {
				t.Fatal("seed starter should fail before Temporal start")
			}
			for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "private", "credential_ref", "object_key", "draft", "manuscript"} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("invalid seed context validation error leaked forbidden text %q: %s", forbidden, err.Error())
				}
			}
		})
	}
}

func TestTemporalSeedRunStarterFailsClosedWithoutAdmissionStore(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:    temporalClient,
		TaskQueue: SeedTaskQueue,
	})

	_, err := starter.StartSeedRun(context.Background(), validSeedStartInput())

	if code := ErrorCode(err); code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit admission backend failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start without seed admission store")
	}
}

func mapToJSONForTest(t *testing.T, value map[string]any) string {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	return string(encoded)
}

func validSeedStartInput() StartSeedRunInput {
	return StartSeedRunInput{
		TenantID:        validSeedTenantIDForTest,
		ProjectID:       validSeedProjectIDForTest,
		UploadID:        validSeedUploadIDForTest,
		ActorUserID:     validSeedActorIDForTest,
		RequestID:       validSeedRequestIDForTest,
		SourceFileID:    validSeedSourceFileIDForTest,
		SourceObjectKey: validSeedSourceObjectKeyForTest,
		SourceFilename:  "book.txt",
		SourceMimeType:  "text/plain",
		SourceSizeBytes: 99,
		SourceSHA256:    validSeedSourceSHA256ForTest,
	}
}

func TestTemporalSeedRunStarterPersistsAdmissionBeforeStartingWorkflow(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	admissionStore := &recordingSeedAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:         temporalClient,
		TaskQueue:      SeedTaskQueue,
		AdmissionStore: admissionStore,
	})

	input := validSeedStartInput()
	input.Options = map[string]any{"language": "zh-CN"}
	run, err := starter.StartSeedRun(context.Background(), input)

	if err != nil {
		t.Fatalf("start seed run: %v", err)
	}
	if admissionStore.temporalWasStartedWhenCalled {
		t.Fatal("seed admission must be persisted before Temporal starts")
	}
	if admissionStore.input.TenantID != validSeedTenantIDForTest || admissionStore.input.ProjectID != validSeedProjectIDForTest || admissionStore.input.RunID != run.RunID {
		t.Fatalf("admission lost tenant/project/run context: %#v", admissionStore.input)
	}
	if admissionStore.input.UploadID != validSeedUploadIDForTest || admissionStore.input.ActorUserID != validSeedActorIDForTest || admissionStore.input.RequestID != validSeedRequestIDForTest {
		t.Fatalf("admission lost upload/actor/request context: %#v", admissionStore.input)
	}
	if admissionStore.input.SourceFileID != validSeedSourceFileIDForTest {
		t.Fatalf("admission lost source file metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.WorkflowType != SeedWorkflowType || admissionStore.input.TemporalWorkflowID != "seed_run_"+run.RunID {
		t.Fatalf("admission lost workflow metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.Status != "queued" {
		t.Fatalf("expected queued admission status, got %#v", admissionStore.input)
	}
}

func TestTemporalSeedRunStarterDoesNotStartWorkflowWhenAdmissionFails(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:    temporalClient,
		TaskQueue: SeedTaskQueue,
		AdmissionStore: &recordingSeedAdmissionStore{
			err: errors.New("insert workflow_runs failed"),
		},
	})

	_, err := starter.StartSeedRun(context.Background(), validSeedStartInput())

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected seed admission failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when seed admission persistence fails")
	}
}

func TestTemporalSeedRunStarterPropagatesSeedSourceAdmissionFailure(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:    temporalClient,
		TaskQueue: SeedTaskQueue,
		AdmissionStore: &recordingSeedAdmissionStore{
			err: &AppError{Code: "SOURCE_FILE_NOT_UPLOADED", Message: "source file upload must be completed before seed run"},
		},
	})

	_, err := starter.StartSeedRun(context.Background(), validSeedStartInput())

	if code := ErrorCode(err); code != "SOURCE_FILE_NOT_UPLOADED" {
		t.Fatalf("expected source status failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when seed source status cannot be advanced")
	}
}

func TestTemporalSeedRunStarterSanitizesWorkflowStartErrors(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{
		err: errors.New("temporal failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-1/source-files/upload-1/book.txt source_object_key=projects/project-1/source-files/upload-1/book.txt draft=private manuscript=private"),
	}
	admissionStore := &recordingSeedAdmissionStore{}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:         temporalClient,
		TaskQueue:      SeedTaskQueue,
		AdmissionStore: admissionStore,
	})

	_, err := starter.StartSeedRun(context.Background(), validSeedStartInput())

	if code := ErrorCode(err); code != "WORKFLOW_FAILED" {
		t.Fatalf("expected workflow start failure, got %s (%v)", code, err)
	}
	if !temporalClient.started {
		t.Fatal("Temporal workflow should be attempted after seed admission succeeds")
	}
	if admissionStore.input.UploadID != validSeedUploadIDForTest {
		t.Fatalf("seed admission should happen before Temporal start, got %#v", admissionStore.input)
	}
	if !strings.Contains(err.Error(), "failed to start seed_pipeline workflow") {
		t.Fatalf("expected stable workflow start message, got %v", err)
	}
	for _, forbidden := range []string{
		"prompt",
		"api_key",
		"sk-hidden",
		"credential_ref",
		"object_key",
		"source_object_key",
		"projects/project-1/source-files",
		"draft",
		"manuscript",
	} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("workflow start error leaked forbidden text %q: %s", forbidden, err.Error())
		}
	}
}

func TestTemporalSeedRunStarterRecordsFailedAdmissionWhenWorkflowStartFails(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{
		err: errors.New("temporal failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-1/source-files/upload-1/book.txt draft=private manuscript=private"),
	}
	admissionStore := &recordingSeedAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{
		Client:         temporalClient,
		TaskQueue:      SeedTaskQueue,
		AdmissionStore: admissionStore,
	})

	_, err := starter.StartSeedRun(context.Background(), validSeedStartInput())

	if code := ErrorCode(err); code != "WORKFLOW_FAILED" {
		t.Fatalf("expected workflow start failure, got %s (%v)", code, err)
	}
	if !admissionStore.failureCalled {
		t.Fatal("expected admitted seed run to be marked failed after Temporal start failure")
	}
	if !admissionStore.failureTemporalWasStartedWhenCalled {
		t.Fatal("workflow start failure compensation should happen after Temporal start is attempted")
	}
	if admissionStore.failureInput.TenantID != validSeedTenantIDForTest ||
		admissionStore.failureInput.ProjectID != validSeedProjectIDForTest ||
		admissionStore.failureInput.UploadID != validSeedUploadIDForTest ||
		admissionStore.failureInput.SourceFileID != validSeedSourceFileIDForTest ||
		admissionStore.failureInput.WorkflowType != SeedWorkflowType ||
		admissionStore.failureInput.ActorUserID != validSeedActorIDForTest ||
		admissionStore.failureInput.RequestID != validSeedRequestIDForTest {
		t.Fatalf("failure compensation lost request context: %#v", admissionStore.failureInput)
	}
	if admissionStore.failureInput.RunID == "" || admissionStore.failureInput.TraceID == "" {
		t.Fatalf("failure compensation lost run/trace context: %#v", admissionStore.failureInput)
	}
	if admissionStore.failureInput.ErrorCode != "WORKFLOW_FAILED" ||
		admissionStore.failureInput.ErrorMessage != "failed to start seed_pipeline workflow" {
		t.Fatalf("unexpected public failure metadata: %#v", admissionStore.failureInput)
	}
	for _, forbidden := range []string{
		"prompt",
		"api_key",
		"sk-hidden",
		"credential_ref",
		"object_key",
		"projects/project-1/source-files",
		"draft",
		"manuscript",
	} {
		if strings.Contains(admissionStore.failureInput.ErrorMessage, forbidden) {
			t.Fatalf("failure compensation metadata leaked forbidden text %q: %#v", forbidden, admissionStore.failureInput)
		}
	}
}

func TestSQLSeedAdmissionStoreRecordsWorkflowStartFailureAndReleasesSource(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})

	err := store.RecordSeedRunStartFailure(context.Background(), SeedStartFailureInput{
		TenantID:     "11111111-1111-4111-8111-111111111111",
		ProjectID:    "22222222-2222-4222-8222-222222222222",
		RunID:        "33333333-3333-4333-8333-333333333333",
		TraceID:      "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType: SeedWorkflowType,
		ActorUserID:  "44444444-4444-4444-8444-444444444444",
		RequestID:    "req-seed",
		UploadID:     "55555555-5555-4555-8555-555555555555",
		SourceFileID: "66666666-6666-4666-8666-666666666666",
		ErrorCode:    "WORKFLOW_FAILED",
		ErrorMessage: "failed to start seed_pipeline workflow prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=source draft=private manuscript=private",
	})

	if err != nil {
		t.Fatalf("record seed start failure: %v", err)
	}
	if !strings.Contains(execer.query, "UPDATE workflow_runs") ||
		!strings.Contains(execer.query, "status = 'failed'") ||
		!strings.Contains(execer.query, "error_code") ||
		!strings.Contains(execer.query, "error_message") ||
		!strings.Contains(execer.query, "UPDATE source_files") ||
		!strings.Contains(execer.query, "parse_status = 'uploaded'") ||
		!strings.Contains(execer.query, "parse_status = 'parsing'") ||
		!strings.Contains(execer.query, "AND file_id = $9::uuid") ||
		!strings.Contains(execer.query, "RETURNING upload_id, file_id") ||
		!strings.Contains(execer.query, "source_update.file_id::text") ||
		!strings.Contains(execer.query, "workflow.failed") ||
		!strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected workflow failure/source release query, got %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	if !strings.Contains(joinedArgs, "WORKFLOW_FAILED") ||
		!strings.Contains(joinedArgs, "failed to start seed_pipeline workflow") ||
		!strings.Contains(joinedArgs, "req-seed") ||
		!strings.Contains(joinedArgs, "55555555-5555-4555-8555-555555555555") ||
		!strings.Contains(joinedArgs, "66666666-6666-4666-8666-666666666666") {
		t.Fatalf("expected stable failure metadata in args, got %s", joinedArgs)
	}
	failurePayloadArg, ok := execer.args[7].(string)
	if !ok {
		t.Fatalf("expected workflow failed payload JSON string arg, got %#v", execer.args)
	}
	if strings.Contains(failurePayloadArg, "source_file_id") || strings.Contains(failurePayloadArg, "66666666-6666-4666-8666-666666666666") {
		t.Fatalf("seed start failure should derive source_file_id from released source row, got caller value in payload JSON: %s", failurePayloadArg)
	}
	for _, forbidden := range []string{
		"prompt",
		"api_key",
		"sk-hidden",
		"credential_ref",
		"object_key",
		"draft",
		"manuscript",
	} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("seed start failure compensation leaked forbidden text %q: %s", forbidden, joinedArgs)
		}
	}
}

func TestSQLSeedAdmissionStoreRequiresSourceFileIDForWorkflowStartFailure(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})

	err := store.RecordSeedRunStartFailure(context.Background(), SeedStartFailureInput{
		TenantID:     "11111111-1111-4111-8111-111111111111",
		ProjectID:    "22222222-2222-4222-8222-222222222222",
		RunID:        "33333333-3333-4333-8333-333333333333",
		TraceID:      "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType: SeedWorkflowType,
		ActorUserID:  "44444444-4444-4444-8444-444444444444",
		RequestID:    "req-seed",
		UploadID:     "55555555-5555-4555-8555-555555555555",
		ErrorCode:    "WORKFLOW_FAILED",
		ErrorMessage: "failed to start seed_pipeline workflow",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected source-scoped failure validation error, got %s (%v)", code, err)
	}
	if execer.query != "" {
		t.Fatalf("seed start failure compensation should not execute SQL without source_file_id, got %s", execer.query)
	}
}

func TestSQLSeedAdmissionStoreRejectsInvalidUUIDContextBeforeAdmissionSQL(t *testing.T) {
	baseInput := SeedAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-seed",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       "66666666-6666-4666-8666-666666666666",
		Status:             "queued",
	}
	cases := []struct {
		name   string
		mutate func(*SeedAdmissionInput)
	}{
		{name: "tenant", mutate: func(input *SeedAdmissionInput) { input.TenantID = "tenant prompt=private api_key=sk-hidden" }},
		{name: "project", mutate: func(input *SeedAdmissionInput) { input.ProjectID = "project prompt=private api_key=sk-hidden" }},
		{name: "run", mutate: func(input *SeedAdmissionInput) { input.RunID = "run prompt=private api_key=sk-hidden" }},
		{name: "actor", mutate: func(input *SeedAdmissionInput) { input.ActorUserID = "actor prompt=private api_key=sk-hidden" }},
		{name: "upload", mutate: func(input *SeedAdmissionInput) { input.UploadID = "upload prompt=private api_key=sk-hidden" }},
		{name: "source", mutate: func(input *SeedAdmissionInput) { input.SourceFileID = "source prompt=private api_key=sk-hidden" }},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			execer := &recordingWriterAdmissionExecer{}
			store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})
			input := baseInput
			tt.mutate(&input)

			err := store.AdmitSeedRun(context.Background(), input)

			if code := ErrorCode(err); code != "VALIDATION_FAILED" {
				t.Fatalf("expected invalid UUID validation error, got %s (%v)", code, err)
			}
			if execer.query != "" {
				t.Fatalf("seed admission should not execute SQL with invalid UUID context, got %s", execer.query)
			}
			for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "private"} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("invalid UUID validation error leaked forbidden text %q: %s", forbidden, err.Error())
				}
			}
		})
	}
}

func TestSQLSeedAdmissionStoreRejectsInvalidUUIDContextBeforeStartFailureSQL(t *testing.T) {
	baseInput := SeedStartFailureInput{
		TenantID:     "11111111-1111-4111-8111-111111111111",
		ProjectID:    "22222222-2222-4222-8222-222222222222",
		RunID:        "33333333-3333-4333-8333-333333333333",
		TraceID:      "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType: SeedWorkflowType,
		ActorUserID:  "44444444-4444-4444-8444-444444444444",
		RequestID:    "req-seed",
		UploadID:     "55555555-5555-4555-8555-555555555555",
		SourceFileID: "66666666-6666-4666-8666-666666666666",
		ErrorCode:    "WORKFLOW_FAILED",
		ErrorMessage: "failed to start seed_pipeline workflow",
	}
	cases := []struct {
		name   string
		mutate func(*SeedStartFailureInput)
	}{
		{name: "tenant", mutate: func(input *SeedStartFailureInput) { input.TenantID = "tenant prompt=private api_key=sk-hidden" }},
		{name: "project", mutate: func(input *SeedStartFailureInput) { input.ProjectID = "project prompt=private api_key=sk-hidden" }},
		{name: "run", mutate: func(input *SeedStartFailureInput) { input.RunID = "run prompt=private api_key=sk-hidden" }},
		{name: "upload", mutate: func(input *SeedStartFailureInput) { input.UploadID = "upload prompt=private api_key=sk-hidden" }},
		{name: "source", mutate: func(input *SeedStartFailureInput) { input.SourceFileID = "source prompt=private api_key=sk-hidden" }},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			execer := &recordingWriterAdmissionExecer{}
			store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})
			input := baseInput
			tt.mutate(&input)

			err := store.RecordSeedRunStartFailure(context.Background(), input)

			if code := ErrorCode(err); code != "VALIDATION_FAILED" {
				t.Fatalf("expected invalid UUID validation error, got %s (%v)", code, err)
			}
			if execer.query != "" {
				t.Fatalf("seed start failure compensation should not execute SQL with invalid UUID context, got %s", execer.query)
			}
			for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "private"} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("invalid UUID validation error leaked forbidden text %q: %s", forbidden, err.Error())
				}
			}
		})
	}
}

func TestSQLSeedAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})
	callerSuppliedSourceFileID := "66666666-6666-4666-8666-666666666666"

	err := store.AdmitSeedRun(context.Background(), SeedAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-seed",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       callerSuppliedSourceFileID,
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit seed run: %v", err)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") || !strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected workflow run/event inserts, got %s", execer.query)
	}
	if strings.Contains(execer.query, "writer_runs") || strings.Contains(execer.query, "writer_drafts") {
		t.Fatalf("seed admission should not write writer tables: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"credential_ref", "api_key", "encrypted_api_key", "prompt", "response", "body", "content", "draft", "manuscript"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("seed admission SQL args leaked sensitive field %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, "req-seed") ||
		!strings.Contains(joinedArgs, "55555555-5555-4555-8555-555555555555") {
		t.Fatalf("expected request/upload metadata in admission args, got %s", joinedArgs)
	}
	eventPayloadArg, ok := execer.args[8].(string)
	if !ok {
		t.Fatalf("expected queued event payload JSON string arg, got %#v", execer.args)
	}
	if strings.Contains(eventPayloadArg, callerSuppliedSourceFileID) || strings.Contains(eventPayloadArg, "source_file_id") {
		t.Fatalf("seed admission should derive queued source_file_id from updated source row, got caller value in event payload arg: %s", eventPayloadArg)
	}
	if !strings.Contains(execer.query, "RETURNING upload_id, file_id") ||
		!strings.Contains(execer.query, "jsonb_build_object('source_file_id', source_update.file_id::text)") {
		t.Fatalf("seed admission queued event should derive source_file_id from source_update row, got query %s", execer.query)
	}
}

func TestSQLSeedAdmissionStoreScopesAdmissionToSourceFileID(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})
	sourceFileID := "66666666-6666-4666-8666-666666666666"

	err := store.AdmitSeedRun(context.Background(), SeedAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-seed",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       sourceFileID,
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit seed run: %v", err)
	}
	if !strings.Contains(execer.query, "AND file_id = $11::uuid") {
		t.Fatalf("seed admission must scope source update by source_file_id before Temporal handoff, got %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	if !strings.Contains(joinedArgs, sourceFileID) {
		t.Fatalf("expected source_file_id to be used as source row scope, got args %s", joinedArgs)
	}
}

func TestSQLSeedAdmissionStoreMarksUploadedSourceParsingBeforeWorkflowAdmission(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})

	err := store.AdmitSeedRun(context.Background(), SeedAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-seed",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       "66666666-6666-4666-8666-666666666666",
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit seed run: %v", err)
	}
	if !strings.Contains(execer.query, "UPDATE source_files") ||
		!strings.Contains(execer.query, "parse_status = 'parsing'") ||
		!strings.Contains(execer.query, "parse_status IN ('uploaded', 'parsed', 'failed', 'cancelled')") ||
		!strings.Contains(execer.query, "INSERT INTO workflow_runs") ||
		!strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("seed admission must advance uploaded source to parsing before workflow admission, got %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	if !strings.Contains(joinedArgs, "55555555-5555-4555-8555-555555555555") ||
		!strings.Contains(joinedArgs, "33333333-3333-4333-8333-333333333333") {
		t.Fatalf("expected upload and run ids in admission args, got %s", joinedArgs)
	}
}

func TestSQLSeedAdmissionStoreRejectsSourceThatIsNotUploadedWithoutWorkflowAdmission(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{
		result: fakeSQLResult{rowsAffected: 0, rowsAffectedSet: true},
	}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})

	err := store.AdmitSeedRun(context.Background(), SeedAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-seed",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       "66666666-6666-4666-8666-666666666666",
		Status:             "queued",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_NOT_UPLOADED" {
		t.Fatalf("expected SOURCE_FILE_NOT_UPLOADED, got %s (%v)", code, err)
	}
	for _, forbidden := range []string{"prompt", "api_key", "credential_ref", "object_key", "raw_text", "draft", "manuscript"} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("source status admission error leaked forbidden text %q: %s", forbidden, err.Error())
		}
	}
}

func TestSQLSeedAdmissionStoreSanitizesUnexpectedAdmissionError(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{
		err: errors.New("driver failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=source raw_text=secret draft=private manuscript=private"),
	}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})

	err := store.AdmitSeedRun(context.Background(), SeedAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-seed",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       "66666666-6666-4666-8666-666666666666",
		Status:             "queued",
	})

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected WORKFLOW_ADMISSION_FAILED, got %s (%v)", code, err)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "raw_text", "draft", "manuscript"} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("seed admission error leaked forbidden text %q: %s", forbidden, err.Error())
		}
	}
}

func TestSQLSeedAdmissionStoreUsesTenantContextExecerForAdmissionAndStartFailure(t *testing.T) {
	execer := &recordingTenantSeedAdmissionExecer{}
	store := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{Execer: execer})
	input := SeedAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-seed",
		UploadID:           "55555555-5555-4555-8555-555555555555",
		SourceFileID:       "66666666-6666-4666-8666-666666666666",
		Status:             "queued",
	}

	if err := store.AdmitSeedRun(context.Background(), input); err != nil {
		t.Fatalf("admit seed run: %v", err)
	}
	if !execer.usedTenantContext || execer.usedPlainExec {
		t.Fatalf("seed admission should use tenant context execer, got tenant=%v plain=%v", execer.usedTenantContext, execer.usedPlainExec)
	}
	if execer.tenantID != input.TenantID || execer.projectID != input.ProjectID {
		t.Fatalf("tenant context lost tenant/project scope: %#v", execer)
	}
	if !strings.Contains(execer.query, "UPDATE source_files") || !strings.Contains(execer.query, "INSERT INTO workflow_runs") {
		t.Fatalf("expected seed admission query through tenant context, got %s", execer.query)
	}

	execer.reset()
	if err := store.RecordSeedRunStartFailure(context.Background(), SeedStartFailureInput{
		TenantID:     input.TenantID,
		ProjectID:    input.ProjectID,
		RunID:        input.RunID,
		TraceID:      input.TraceID,
		WorkflowType: input.WorkflowType,
		ActorUserID:  input.ActorUserID,
		RequestID:    input.RequestID,
		UploadID:     input.UploadID,
		SourceFileID: input.SourceFileID,
		ErrorCode:    "WORKFLOW_FAILED",
		ErrorMessage: "failed to start seed_pipeline workflow",
	}); err != nil {
		t.Fatalf("record seed start failure: %v", err)
	}
	if !execer.usedTenantContext || execer.usedPlainExec {
		t.Fatalf("seed start failure compensation should use tenant context execer, got tenant=%v plain=%v", execer.usedTenantContext, execer.usedPlainExec)
	}
	if execer.tenantID != input.TenantID || execer.projectID != input.ProjectID {
		t.Fatalf("failure compensation lost tenant/project scope: %#v", execer)
	}
	if !strings.Contains(execer.query, "UPDATE workflow_runs") || !strings.Contains(execer.query, "UPDATE source_files") {
		t.Fatalf("expected seed start failure query through tenant context, got %s", execer.query)
	}
}

func TestTemporalSeedRunStarterRequiresUploadID(t *testing.T) {
	starter := NewTemporalSeedRunStarter(TemporalSeedRunConfig{Client: &recordingSeedTemporalClient{}})

	_, err := starter.StartSeedRun(context.Background(), StartSeedRunInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation failure, got %s (%v)", code, err)
	}
}

type recordingSeedTemporalClient struct {
	options  client.StartWorkflowOptions
	workflow any
	args     []any
	err      error
	started  bool
}

func (c *recordingSeedTemporalClient) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.started = true
	c.options = options
	c.workflow = workflow
	c.args = args
	return nil, c.err
}

func (c *recordingSeedTemporalClient) CancelWorkflow(context.Context, string, string) error {
	return errors.New("not used")
}

type recordingSeedAdmissionStore struct {
	input                               SeedAdmissionInput
	failureInput                        SeedStartFailureInput
	err                                 error
	failureErr                          error
	temporalStarted                     func() bool
	temporalWasStartedWhenCalled        bool
	failureTemporalWasStartedWhenCalled bool
	failureCalled                       bool
}

func (s *recordingSeedAdmissionStore) AdmitSeedRun(_ context.Context, input SeedAdmissionInput) error {
	s.input = input
	if s.temporalStarted != nil {
		s.temporalWasStartedWhenCalled = s.temporalStarted()
	}
	return s.err
}

func (s *recordingSeedAdmissionStore) RecordSeedRunStartFailure(_ context.Context, input SeedStartFailureInput) error {
	s.failureInput = input
	s.failureCalled = true
	if s.temporalStarted != nil {
		s.failureTemporalWasStartedWhenCalled = s.temporalStarted()
	}
	return s.failureErr
}

type recordingTenantSeedAdmissionExecer struct {
	tenantID          string
	projectID         string
	query             string
	args              []any
	usedTenantContext bool
	usedPlainExec     bool
	err               error
	result            sql.Result
}

func (e *recordingTenantSeedAdmissionExecer) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	e.usedPlainExec = true
	e.query = query
	e.args = append([]any(nil), args...)
	if e.result != nil {
		return e.result, e.err
	}
	return fakeSQLResult{}, e.err
}

func (e *recordingTenantSeedAdmissionExecer) ExecTenantContext(_ context.Context, tenantID string, projectID string, query string, args ...any) (sql.Result, error) {
	e.usedTenantContext = true
	e.tenantID = tenantID
	e.projectID = projectID
	e.query = query
	e.args = append([]any(nil), args...)
	if e.result != nil {
		return e.result, e.err
	}
	return fakeSQLResult{}, e.err
}

func (e *recordingTenantSeedAdmissionExecer) reset() {
	e.tenantID = ""
	e.projectID = ""
	e.query = ""
	e.args = nil
	e.usedTenantContext = false
	e.usedPlainExec = false
}
