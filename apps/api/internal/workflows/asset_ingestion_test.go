package workflows

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

type recordingAssetIngestionWorkflowReader struct {
	input GetWorkflowRunInput
	run   WorkflowRun
	err   error
}

func (r *recordingAssetIngestionWorkflowReader) GetWorkflowRun(ctx context.Context, input GetWorkflowRunInput) (WorkflowRun, error) {
	r.input = input
	if r.err != nil {
		return WorkflowRun{}, r.err
	}
	return r.run, nil
}

func TestDisabledAssetIngestionStarterFailsClosed(t *testing.T) {
	starter := NewDisabledAssetIngestionStarter()

	_, err := starter.StartAssetIngestion(context.Background(), StartAssetIngestionInput{
		TenantID:     "tenant-1",
		ProjectID:    "project-1",
		MaterialText: "素材",
	})

	if code := ErrorCode(err); code != "ASSET_INGESTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected asset ingestion backend to fail closed, got %s (%v)", code, err)
	}
}

func TestTemporalAssetIngestionStarterStartsWorkflowWithoutWaitingForCompletion(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalAssetIngestionStarter(TemporalAssetIngestionConfig{
		Client:    temporalClient,
		TaskQueue: AssetIngestionTaskQueue,
	})

	run, err := starter.StartAssetIngestion(context.Background(), StartAssetIngestionInput{
		TenantID:     "tenant-1",
		ProjectID:    "project-1",
		ActorUserID:  "user-1",
		RequestID:    "req-1",
		MaterialText: "灵气不可凭空生成。这里是用户素材正文。",
		HintType:     "world_rule",
		Scope:        "project",
		Options: map[string]any{
			"language": "zh-CN",
		},
	})

	if err != nil {
		t.Fatalf("start asset ingestion: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-1" || run.WorkflowType != AssetIngestionWorkflowType || run.Status != "queued" {
		t.Fatalf("unexpected asset ingestion run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if temporalClient.options.TaskQueue != AssetIngestionTaskQueue || temporalClient.options.ID != "asset_ingestion_"+run.RunID {
		t.Fatalf("unexpected workflow options: %#v", temporalClient.options)
	}
	if temporalClient.workflow != AssetIngestionWorkflowName {
		t.Fatalf("unexpected workflow name: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected asset ingestion workflow payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != "tenant-1" || payload["project_id"] != "project-1" || payload["run_id"] != run.RunID {
		t.Fatalf("lost run context payload: %#v", payload)
	}
	if payload["actor_user_id"] != "user-1" || payload["request_id"] != "req-1" {
		t.Fatalf("lost actor/request metadata: %#v", payload)
	}
	if payload["workflow_type"] != AssetIngestionWorkflowType || payload["trace_id"] == "" {
		t.Fatalf("lost workflow metadata: %#v", payload)
	}
	if payload["material_text"] != "灵气不可凭空生成。这里是用户素材正文。" || payload["hint_type"] != "world_rule" || payload["scope"] != "project" {
		t.Fatalf("lost asset ingestion material context in internal workflow payload: %#v", payload)
	}
	contextPayload, ok := payload["context"].(map[string]any)
	if !ok {
		t.Fatalf("expected context payload, got %#v", payload["context"])
	}
	if contextPayload["tenant_id"] != "tenant-1" || contextPayload["project_id"] != "project-1" || contextPayload["run_id"] != run.RunID {
		t.Fatalf("lost agent context: %#v", contextPayload)
	}
	if contextPayload["module_key"] != AssetIngestionModuleKey || contextPayload["workflow_type"] != AssetIngestionWorkflowType {
		t.Fatalf("lost module/workflow context: %#v", contextPayload)
	}
	permissions := contextPayload["permissions"].(map[string][]string)
	if got := permissions[AssetIngestionModuleKey][0]; got != "run" {
		t.Fatalf("expected asset ingestion permission, got %#v", permissions)
	}
	payloadJSON := mapToJSONForTest(t, payload)
	for _, forbidden := range []string{"prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(payloadJSON, forbidden) {
			t.Fatalf("asset ingestion workflow payload leaked forbidden field %q: %s", forbidden, payloadJSON)
		}
	}
}

func TestTemporalAssetIngestionStarterPersistsAdmissionBeforeStartingWorkflow(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	admissionStore := &recordingAssetIngestionAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalAssetIngestionStarter(TemporalAssetIngestionConfig{
		Client:         temporalClient,
		TaskQueue:      AssetIngestionTaskQueue,
		AdmissionStore: admissionStore,
	})

	run, err := starter.StartAssetIngestion(context.Background(), StartAssetIngestionInput{
		TenantID:     "tenant-1",
		ProjectID:    "project-1",
		ActorUserID:  "user-1",
		RequestID:    "req-1",
		MaterialText: "用户素材正文不应进入 admission payload",
		HintType:     "note",
		Scope:        "project",
	})

	if err != nil {
		t.Fatalf("start asset ingestion: %v", err)
	}
	if admissionStore.temporalWasStartedWhenCalled {
		t.Fatal("asset ingestion admission must be persisted before Temporal starts")
	}
	if admissionStore.input.TenantID != "tenant-1" || admissionStore.input.ProjectID != "project-1" || admissionStore.input.RunID != run.RunID {
		t.Fatalf("admission lost tenant/project/run context: %#v", admissionStore.input)
	}
	if admissionStore.input.WorkflowType != AssetIngestionWorkflowType || admissionStore.input.TemporalWorkflowID != "asset_ingestion_"+run.RunID {
		t.Fatalf("admission lost workflow metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.ActorUserID != "user-1" || admissionStore.input.RequestID != "req-1" {
		t.Fatalf("admission lost actor/request metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.HintType != "note" || admissionStore.input.Scope != "project" || admissionStore.input.Status != "queued" {
		t.Fatalf("admission lost public request metadata: %#v", admissionStore.input)
	}
}

func TestTemporalAssetIngestionStarterDoesNotStartWorkflowWhenAdmissionFails(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalAssetIngestionStarter(TemporalAssetIngestionConfig{
		Client:    temporalClient,
		TaskQueue: AssetIngestionTaskQueue,
		AdmissionStore: &recordingAssetIngestionAdmissionStore{
			err: errors.New("insert workflow_runs failed"),
		},
	})

	_, err := starter.StartAssetIngestion(context.Background(), StartAssetIngestionInput{
		TenantID:     "tenant-1",
		ProjectID:    "project-1",
		MaterialText: "素材",
	})

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected asset ingestion admission failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when asset ingestion admission persistence fails")
	}
}

func TestSQLAssetIngestionAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLAssetIngestionAdmissionStore(SQLAssetIngestionAdmissionStoreConfig{Execer: execer})

	err := store.AdmitAssetIngestionRun(context.Background(), AssetIngestionAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       AssetIngestionWorkflowType,
		TemporalWorkflowID: "asset_ingestion_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-asset-ingestion",
		HintType:           "world_rule",
		Scope:              "project",
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit asset ingestion run: %v", err)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") || !strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected workflow run/event inserts, got %s", execer.query)
	}
	if strings.Contains(execer.query, "assets") || strings.Contains(execer.query, "global_search_index") {
		t.Fatalf("asset ingestion admission should not create assets/search rows: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"用户素材正文", "material_text", "credential_ref", "api_key", "encrypted_api_key", "prompt", "response", "body", "content", "draft", "manuscript"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("asset ingestion admission SQL args leaked sensitive field %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, "req-asset-ingestion") || !strings.Contains(joinedArgs, "world_rule") || !strings.Contains(joinedArgs, "project") {
		t.Fatalf("expected public request metadata in admission args, got %s", joinedArgs)
	}
	if _, err := json.Marshal(execer.args); err != nil {
		t.Fatalf("expected admission args to be JSON-safe: %v", err)
	}
}

func TestDisabledAssetIngestionReaderFailsClosed(t *testing.T) {
	reader := NewDisabledAssetIngestionReader()

	_, err := reader.GetAssetIngestion(context.Background(), GetAssetIngestionInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if code := ErrorCode(err); code != "ASSET_INGESTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected asset ingestion reader to fail closed, got %s (%v)", code, err)
	}
}

func TestWorkflowAssetIngestionReaderRequiresAssetIngestionWorkflowType(t *testing.T) {
	reader := NewWorkflowAssetIngestionReader(&recordingAssetIngestionWorkflowReader{
		run: WorkflowRun{
			RunID:        "writer-run-1",
			WorkflowType: WriterWorkflowType,
			ProjectID:    "project-1",
			Status:       "queued",
		},
	})

	_, err := reader.GetAssetIngestion(context.Background(), GetAssetIngestionInput{
		TenantID: "tenant-1",
		RunID:    "writer-run-1",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected non-asset-ingestion workflow to be hidden, got %s (%v)", code, err)
	}
}

func TestWorkflowAssetIngestionReaderReturnsPublicWorkflowMetadata(t *testing.T) {
	workflowReader := &recordingAssetIngestionWorkflowReader{
		run: WorkflowRun{
			RunID:        "asset-ingestion-run-1",
			WorkflowType: AssetIngestionWorkflowType,
			ProjectID:    "project-1",
			Status:       "failed",
			Progress:     10,
			Message:      "backend missing",
			ErrorCode:    "ASSET_INGESTION_BACKEND_UNCONFIGURED",
			ErrorMessage: "asset ingestion backend is not configured",
			CreatedAt:    "2026-07-04T00:00:00Z",
			UpdatedAt:    "2026-07-04T00:01:00Z",
		},
	}
	reader := NewWorkflowAssetIngestionReader(workflowReader)

	run, err := reader.GetAssetIngestion(context.Background(), GetAssetIngestionInput{
		TenantID: "tenant-1",
		RunID:    "asset-ingestion-run-1",
	})

	if err != nil {
		t.Fatalf("get asset ingestion: %v", err)
	}
	if workflowReader.input.TenantID != "tenant-1" || workflowReader.input.RunID != "asset-ingestion-run-1" {
		t.Fatalf("reader lost tenant/run scope: %#v", workflowReader.input)
	}
	if run.RunID != "asset-ingestion-run-1" || run.WorkflowType != AssetIngestionWorkflowType || run.Status != "failed" {
		t.Fatalf("unexpected workflow metadata: %#v", run)
	}
	joined := strings.Join([]string{run.Message, run.ErrorCode, run.ErrorMessage}, "\n")
	for _, forbidden := range []string{"material_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"} {
		if strings.Contains(joined, forbidden) {
			t.Fatalf("asset ingestion metadata leaked forbidden field %q: %s", forbidden, joined)
		}
	}
}

type recordingAssetIngestionAdmissionStore struct {
	input                        AssetIngestionAdmissionInput
	err                          error
	temporalStarted              func() bool
	temporalWasStartedWhenCalled bool
}

func (s *recordingAssetIngestionAdmissionStore) AdmitAssetIngestionRun(_ context.Context, input AssetIngestionAdmissionInput) error {
	s.input = input
	if s.temporalStarted != nil {
		s.temporalWasStartedWhenCalled = s.temporalStarted()
	}
	return s.err
}
