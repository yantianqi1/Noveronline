package workflows

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

type recordingStyleExtractionWorkflowReader struct {
	input GetWorkflowRunInput
	run   WorkflowRun
	err   error
}

func (r *recordingStyleExtractionWorkflowReader) GetWorkflowRun(ctx context.Context, input GetWorkflowRunInput) (WorkflowRun, error) {
	r.input = input
	if r.err != nil {
		return WorkflowRun{}, r.err
	}
	return r.run, nil
}

func TestDisabledStyleExtractionStarterFailsClosed(t *testing.T) {
	starter := NewDisabledStyleExtractionStarter()

	_, err := starter.StartStyleExtraction(context.Background(), StartStyleExtractionInput{
		TenantID:     "tenant-1",
		ProjectID:    "project-1",
		MaterialText: "风格样本文本",
	})

	if code := ErrorCode(err); code != "STYLE_EXTRACTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected style extraction backend to fail closed, got %s (%v)", code, err)
	}
}

func TestTemporalStyleExtractionStarterStartsWorkflowWithoutWaitingForCompletion(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalStyleExtractionStarter(TemporalStyleExtractionConfig{
		Client:    temporalClient,
		TaskQueue: AssetIngestionTaskQueue,
	})

	run, err := starter.StartStyleExtraction(context.Background(), StartStyleExtractionInput{
		TenantID:      "tenant-1",
		ProjectID:     "project-1",
		ActorUserID:   "user-1",
		RequestID:     "req-1",
		MaterialText:  "这是作者文风样本正文，不应进入公开响应。",
		SourceAssetID: "asset-style-source-1",
		Scope:         "project",
		Options: map[string]any{
			"language": "zh-CN",
		},
	})

	if err != nil {
		t.Fatalf("start style extraction: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-1" || run.WorkflowType != StyleExtractionWorkflowType || run.Status != "queued" {
		t.Fatalf("unexpected style extraction run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if temporalClient.options.TaskQueue != AssetIngestionTaskQueue || temporalClient.options.ID != "style_extraction_"+run.RunID {
		t.Fatalf("unexpected workflow options: %#v", temporalClient.options)
	}
	if temporalClient.workflow != StyleExtractionWorkflowName {
		t.Fatalf("unexpected workflow name: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected style extraction workflow payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != "tenant-1" || payload["project_id"] != "project-1" || payload["run_id"] != run.RunID {
		t.Fatalf("lost run context payload: %#v", payload)
	}
	if payload["workflow_type"] != StyleExtractionWorkflowType || payload["module_key"] != StyleExtractionModuleKey || payload["trace_id"] == "" {
		t.Fatalf("lost workflow/module metadata: %#v", payload)
	}
	if payload["material_text"] != "这是作者文风样本正文，不应进入公开响应。" || payload["source_asset_id"] != "asset-style-source-1" || payload["scope"] != "project" {
		t.Fatalf("lost style extraction source context in internal payload: %#v", payload)
	}
	contextPayload, ok := payload["context"].(map[string]any)
	if !ok {
		t.Fatalf("expected context payload, got %#v", payload["context"])
	}
	if contextPayload["module_key"] != StyleExtractionModuleKey || contextPayload["workflow_type"] != StyleExtractionWorkflowType {
		t.Fatalf("lost style extraction context: %#v", contextPayload)
	}
	permissions := contextPayload["permissions"].(map[string][]string)
	if got := permissions[StyleExtractionModuleKey][0]; got != "run" {
		t.Fatalf("expected style extraction permission, got %#v", permissions)
	}
	payloadJSON := mapToJSONForTest(t, payload)
	for _, forbidden := range []string{"prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(payloadJSON, forbidden) {
			t.Fatalf("style extraction workflow payload leaked forbidden field %q: %s", forbidden, payloadJSON)
		}
	}
}

func TestTemporalStyleExtractionStarterPersistsAdmissionBeforeStartingWorkflow(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	admissionStore := &recordingStyleExtractionAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalStyleExtractionStarter(TemporalStyleExtractionConfig{
		Client:         temporalClient,
		TaskQueue:      AssetIngestionTaskQueue,
		AdmissionStore: admissionStore,
	})

	run, err := starter.StartStyleExtraction(context.Background(), StartStyleExtractionInput{
		TenantID:      "tenant-1",
		ProjectID:     "project-1",
		ActorUserID:   "user-1",
		RequestID:     "req-1",
		MaterialText:  "风格样本文本不应进入 admission payload",
		SourceAssetID: "asset-1",
		Scope:         "project",
	})

	if err != nil {
		t.Fatalf("start style extraction: %v", err)
	}
	if admissionStore.temporalWasStartedWhenCalled {
		t.Fatal("style extraction admission must be persisted before Temporal starts")
	}
	if admissionStore.input.TenantID != "tenant-1" || admissionStore.input.ProjectID != "project-1" || admissionStore.input.RunID != run.RunID {
		t.Fatalf("admission lost tenant/project/run context: %#v", admissionStore.input)
	}
	if admissionStore.input.WorkflowType != StyleExtractionWorkflowType || admissionStore.input.TemporalWorkflowID != "style_extraction_"+run.RunID {
		t.Fatalf("admission lost workflow metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.ActorUserID != "user-1" || admissionStore.input.RequestID != "req-1" {
		t.Fatalf("admission lost actor/request metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.SourceAssetID != "asset-1" || admissionStore.input.Scope != "project" || admissionStore.input.Status != "queued" {
		t.Fatalf("admission lost public request metadata: %#v", admissionStore.input)
	}
}

func TestTemporalStyleExtractionStarterDoesNotStartWorkflowWhenAdmissionFails(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalStyleExtractionStarter(TemporalStyleExtractionConfig{
		Client:    temporalClient,
		TaskQueue: AssetIngestionTaskQueue,
		AdmissionStore: &recordingStyleExtractionAdmissionStore{
			err: errors.New("insert workflow_runs failed"),
		},
	})

	_, err := starter.StartStyleExtraction(context.Background(), StartStyleExtractionInput{
		TenantID:     "tenant-1",
		ProjectID:    "project-1",
		MaterialText: "素材",
	})

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected style extraction admission failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when style extraction admission persistence fails")
	}
}

func TestSQLStyleExtractionAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLStyleExtractionAdmissionStore(SQLStyleExtractionAdmissionStoreConfig{Execer: execer})

	err := store.AdmitStyleExtractionRun(context.Background(), StyleExtractionAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       StyleExtractionWorkflowType,
		TemporalWorkflowID: "style_extraction_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-style-extraction",
		SourceAssetID:      "asset-source-1",
		Scope:              "project",
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit style extraction run: %v", err)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") || !strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected workflow run/event inserts, got %s", execer.query)
	}
	if strings.Contains(execer.query, "assets") || strings.Contains(execer.query, "global_search_index") {
		t.Fatalf("style extraction admission should not create assets/search rows: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"风格样本文本", "material_text", "credential_ref", "api_key", "encrypted_api_key", "prompt", "response", "body", "content", "draft", "manuscript"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("style extraction admission SQL args leaked sensitive field %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, "req-style-extraction") || !strings.Contains(joinedArgs, "asset-source-1") || !strings.Contains(joinedArgs, "project") {
		t.Fatalf("expected public request metadata in admission args, got %s", joinedArgs)
	}
	if _, err := json.Marshal(execer.args); err != nil {
		t.Fatalf("expected admission args to be JSON-safe: %v", err)
	}
}

func TestDisabledStyleExtractionReaderFailsClosed(t *testing.T) {
	reader := NewDisabledStyleExtractionReader()

	_, err := reader.GetStyleExtraction(context.Background(), GetStyleExtractionInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if code := ErrorCode(err); code != "STYLE_EXTRACTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected style extraction reader to fail closed, got %s (%v)", code, err)
	}
}

func TestWorkflowStyleExtractionReaderRequiresStyleExtractionWorkflowType(t *testing.T) {
	reader := NewWorkflowStyleExtractionReader(&recordingStyleExtractionWorkflowReader{
		run: WorkflowRun{
			RunID:        "asset-ingestion-run-1",
			WorkflowType: AssetIngestionWorkflowType,
			ProjectID:    "project-1",
			Status:       "queued",
		},
	})

	_, err := reader.GetStyleExtraction(context.Background(), GetStyleExtractionInput{
		TenantID: "tenant-1",
		RunID:    "asset-ingestion-run-1",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected non-style-extraction workflow to be hidden, got %s (%v)", code, err)
	}
}

func TestWorkflowStyleExtractionReaderReturnsPublicWorkflowMetadata(t *testing.T) {
	workflowReader := &recordingStyleExtractionWorkflowReader{
		run: WorkflowRun{
			RunID:        "style-extraction-run-1",
			WorkflowType: StyleExtractionWorkflowType,
			ProjectID:    "project-1",
			Status:       "failed",
			Progress:     10,
			Message:      "backend missing",
			ErrorCode:    "STYLE_EXTRACTION_BACKEND_UNCONFIGURED",
			ErrorMessage: "style extraction backend is not configured",
			CreatedAt:    "2026-07-05T00:00:00Z",
			UpdatedAt:    "2026-07-05T00:01:00Z",
		},
	}
	reader := NewWorkflowStyleExtractionReader(workflowReader)

	run, err := reader.GetStyleExtraction(context.Background(), GetStyleExtractionInput{
		TenantID: "tenant-1",
		RunID:    "style-extraction-run-1",
	})

	if err != nil {
		t.Fatalf("get style extraction: %v", err)
	}
	if workflowReader.input.TenantID != "tenant-1" || workflowReader.input.RunID != "style-extraction-run-1" {
		t.Fatalf("reader lost tenant/run scope: %#v", workflowReader.input)
	}
	if run.RunID != "style-extraction-run-1" || run.WorkflowType != StyleExtractionWorkflowType || run.Status != "failed" {
		t.Fatalf("unexpected workflow metadata: %#v", run)
	}
	joined := strings.Join([]string{run.Message, run.ErrorCode, run.ErrorMessage}, "\n")
	for _, forbidden := range []string{"material_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(joined, forbidden) {
			t.Fatalf("style extraction metadata leaked forbidden field %q: %s", forbidden, joined)
		}
	}
}

type recordingStyleExtractionAdmissionStore struct {
	input                        StyleExtractionAdmissionInput
	err                          error
	temporalStarted              func() bool
	temporalWasStartedWhenCalled bool
}

func (s *recordingStyleExtractionAdmissionStore) AdmitStyleExtractionRun(_ context.Context, input StyleExtractionAdmissionInput) error {
	s.input = input
	if s.temporalStarted != nil {
		s.temporalWasStartedWhenCalled = s.temporalStarted()
	}
	return s.err
}
