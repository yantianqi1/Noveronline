package worldline

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"reflect"
	"strings"
	"testing"

	"go.temporal.io/sdk/client"
)

func TestSQLSavedPathReaderListsTenantProjectScopedSanitizedRows(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"path-1",
			"session-1",
			"project-123",
			"雨夜谈判路线",
			"公开路径摘要",
			"saved",
			`["event-1","event-2"]`,
			"保持压迫感",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	reader := NewSQLSavedPathReader(SQLSavedPathReaderConfig{Queryer: queryer, Limit: 25})

	paths, err := reader.ListSavedPaths(context.Background(), ListSavedPathsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("list saved paths: %v", err)
	}
	if len(paths) != 1 {
		t.Fatalf("expected one saved path, got %#v", paths)
	}
	path := paths[0]
	if path.PathID != "path-1" || path.SessionID != "session-1" || path.ProjectID != "project-123" {
		t.Fatalf("unexpected saved path identity: %#v", path)
	}
	if !reflect.DeepEqual(path.SelectedEventIDs, []string{"event-1", "event-2"}) {
		t.Fatalf("unexpected event ids: %#v", path.SelectedEventIDs)
	}
	if path.WriterInstruction != "保持压迫感" || path.Summary != "公开路径摘要" {
		t.Fatalf("unexpected public metadata: %#v", path)
	}
	if !strings.Contains(queryer.query, "FROM worldline_saved_paths") {
		t.Fatalf("expected saved path table query, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected tenant/project scoped query, got %s", queryer.query)
	}
	if strings.Contains(strings.ToLower(queryer.query), "body_text") ||
		strings.Contains(strings.ToLower(queryer.query), "content_text") ||
		strings.Contains(strings.ToLower(queryer.query), "prompt") ||
		strings.Contains(strings.ToLower(queryer.query), "response") ||
		strings.Contains(strings.ToLower(queryer.query), "credential_ref") ||
		strings.Contains(strings.ToLower(queryer.query), "api_key") {
		t.Fatalf("saved path query selected sensitive fields: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
	if queryer.tenantID != "tenant-123" || queryer.tenantCalls != 1 {
		t.Fatalf("saved path reader skipped tenant context: %#v", queryer)
	}
}

func TestSQLSavedPathReaderReturnsNotFoundForEmptyProject(t *testing.T) {
	reader := NewSQLSavedPathReader(SQLSavedPathReaderConfig{Queryer: &recordingWorldlineQueryer{}})

	_, err := reader.ListSavedPaths(context.Background(), ListSavedPathsInput{
		TenantID:  "tenant-123",
		ProjectID: "",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error, got %s (%v)", code, err)
	}
}

func TestDisabledSavedPathStoreFailsClosed(t *testing.T) {
	store := NewDisabledSavedPathStore()

	_, err := store.CreateSavedPath(context.Background(), CreateSavedPathInput{
		TenantID:         "tenant-123",
		SessionID:        "session-1",
		Title:            "雨夜谈判路线",
		SelectedEventIDs: []string{"event-1"},
	})

	if code := ErrorCode(err); code != "WORLDLINE_SAVED_PATH_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed saved path backend error, got %s (%v)", code, err)
	}
}

func TestSQLSavedPathStoreCreatesSavedPathFromTenantSessionEventsAndWritesSanitizedEvent(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"11111111-1111-1111-1111-111111111111",
			"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
			"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
			"雨夜谈判路线",
			"公开路径摘要",
			"saved",
			`["dddddddd-dddd-dddd-dddd-dddddddddddd","eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"]`,
			"保持压迫感",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	store := NewSQLSavedPathStore(SQLSavedPathStoreConfig{
		Queryer: queryer,
		NewID: fixedWorldlineIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
		),
	})

	path, err := store.CreateSavedPath(context.Background(), CreateSavedPathInput{
		TenantID:          "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		SessionID:         "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		ActorUserID:       "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID:         "req-save-path-123",
		Title:             "雨夜谈判路线",
		Summary:           "公开路径摘要",
		SelectedEventIDs:  []string{"dddddddd-dddd-dddd-dddd-dddddddddddd", "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"},
		WriterInstruction: "保持压迫感",
	})

	if err != nil {
		t.Fatalf("create saved path: %v", err)
	}
	if path.PathID != "11111111-1111-1111-1111-111111111111" ||
		path.SessionID != "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" ||
		path.ProjectID != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
		path.Title != "雨夜谈判路线" ||
		path.WriterInstruction != "保持压迫感" {
		t.Fatalf("unexpected saved path metadata: %#v", path)
	}
	if !reflect.DeepEqual(path.SelectedEventIDs, []string{"dddddddd-dddd-dddd-dddd-dddddddddddd", "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}) {
		t.Fatalf("unexpected selected events: %#v", path.SelectedEventIDs)
	}
	query := strings.ToLower(queryer.query)
	for _, required := range []string{"insert into worldline_saved_paths", "worldline_sessions", "join worldline_events", "insert into workflow_events", "worldline.saved_path.created"} {
		if !strings.Contains(query, required) {
			t.Fatalf("expected %s query, got %s", required, queryer.query)
		}
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(query, forbidden) {
			t.Fatalf("saved path query mentioned forbidden field %q: %s", forbidden, queryer.query)
		}
	}
	for _, arg := range queryer.args {
		if value, ok := arg.(string); ok {
			for _, forbidden := range []string{"prompt", "response", "api_key", "credential_ref", "manuscript", "draft"} {
				if strings.Contains(strings.ToLower(value), forbidden) {
					t.Fatalf("saved path args leaked forbidden value: %#v", queryer.args)
				}
			}
		}
	}
	if queryer.tenantID != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
		queryer.actorUserID != "cccccccc-cccc-cccc-cccc-cccccccccccc" || queryer.actorCalls != 1 {
		t.Fatalf("saved path write skipped tenant actor context: %#v", queryer)
	}
}

func TestSQLSessionStoreStartsSessionWithWorkflowAdmissionAndSanitizedMetadata(t *testing.T) {
	execer := &recordingWorldlineExecer{
		results: []sql.Result{
			driver.RowsAffected(1),
			driver.RowsAffected(1),
			driver.RowsAffected(1),
		},
	}
	store := NewSQLSessionStore(SQLSessionStoreConfig{Execer: execer, NewID: fixedWorldlineIDs("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333")})

	run, err := store.StartSession(context.Background(), StartSessionInput{
		TenantID:     "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		ProjectID:    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		ActorUserID:  "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID:    "req-123",
		Goal:         "Explore the public consequence of a council betrayal",
		AnchorPathID: "dddddddd-dddd-dddd-dddd-dddddddddddd",
		Options: map[string]any{
			"mode":           "director",
			"prompt":         "must be stripped",
			"credential_ref": "must be stripped",
		},
	})

	if err != nil {
		t.Fatalf("start session: %v", err)
	}
	if run.RunID != "11111111-1111-1111-1111-111111111111" ||
		run.ProjectID != "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" ||
		run.WorkflowType != "worldline_session" ||
		run.Status != "queued" {
		t.Fatalf("unexpected run summary: %#v", run)
	}
	joinedQueries := strings.ToLower(strings.Join(execer.queries, "\n"))
	for _, required := range []string{"app_set_tenant_context", "insert into workflow_runs", "insert into workflow_events", "insert into worldline_sessions"} {
		if !strings.Contains(joinedQueries, required) {
			t.Fatalf("expected %s query, got %s", required, joinedQueries)
		}
	}
	for _, forbidden := range []string{"prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(joinedQueries, forbidden) {
			t.Fatalf("session admission query mentioned forbidden field %q: %s", forbidden, joinedQueries)
		}
	}
	for _, callArgs := range execer.args {
		for _, arg := range callArgs {
			if value, ok := arg.(string); ok && strings.Contains(value, "must be stripped") {
				t.Fatalf("session admission args leaked sanitized option value: %#v", execer.args)
			}
		}
	}
}

func TestDisabledStepStarterFailsClosed(t *testing.T) {
	starter := NewDisabledStepStarter()

	_, err := starter.StartStep(context.Background(), StartStepInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
	})

	if code := ErrorCode(err); code != "WORLDLINE_STEP_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed step backend error, got %s (%v)", code, err)
	}
}

func TestSQLStepStarterAdmitsTenantSessionScopedStepAndWritesSanitizedQueuedEvent(t *testing.T) {
	execer := &recordingWorldlineExecer{}
	temporalClient := &recordingWorldlineTemporalClient{}
	starter := NewSQLStepStarter(SQLStepStarterConfig{
		Execer: execer,
		Client: temporalClient,
		NewID: fixedWorldlineIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
		),
	})

	run, err := starter.StartStep(context.Background(), StartStepInput{
		TenantID:    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		ProjectID:   "dddddddd-dddd-dddd-dddd-dddddddddddd",
		SessionID:   "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID:   "req-step-123",
		Mode:        "director",
		Options: map[string]any{
			"max_turns":       2,
			"prompt":          "must be stripped",
			"credential_ref":  "must be stripped",
			"manuscript_text": "must be stripped",
		},
	})

	if err != nil {
		t.Fatalf("start step: %v", err)
	}
	if run.RunID != "11111111-1111-1111-1111-111111111111" ||
		run.ProjectID != "dddddddd-dddd-dddd-dddd-dddddddddddd" ||
		run.WorkflowType != "worldline_step" ||
		run.Status != "queued" {
		t.Fatalf("unexpected step run: %#v", run)
	}
	if temporalClient.options.ID != "worldline_step_11111111-1111-1111-1111-111111111111" ||
		temporalClient.options.TaskQueue != "worldline-interactive" ||
		temporalClient.workflow != "WorldlineStepWorkflow" {
		t.Fatalf("unexpected Temporal handoff: %#v workflow=%#v", temporalClient.options, temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok || payload["session_id"] != "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" {
		t.Fatalf("unexpected Temporal payload: %#v", temporalClient.args)
	}
	contextPayload := payload["context"].(map[string]any)
	if contextPayload["project_id"] != "dddddddd-dddd-dddd-dddd-dddddddddddd" ||
		contextPayload["module_key"] != "worldline_director" {
		t.Fatalf("Temporal payload lost project/module context: %#v", contextPayload)
	}
	if _, exists := payload["options"].(map[string]any)["prompt"]; exists {
		t.Fatalf("Temporal payload retained private option: %#v", payload)
	}
	joinedQueries := strings.ToLower(strings.Join(execer.queries, "\n"))
	for _, required := range []string{"from worldline_sessions", "insert into workflow_runs", "insert into workflow_events", "worldline_step", "workflow.queued"} {
		if !strings.Contains(joinedQueries, required) {
			t.Fatalf("expected %s in step admission query, got %s", required, joinedQueries)
		}
	}
	if !strings.Contains(joinedQueries, "temporal_workflow_id") ||
		!strings.Contains(strings.Join(stringArgs(execer.args), " "), "worldline_step_11111111-1111-1111-1111-111111111111") {
		t.Fatalf("step admission did not persist Temporal workflow identity: queries=%s args=%#v", joinedQueries, execer.args)
	}
	for _, forbidden := range []string{"prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(joinedQueries, forbidden) {
			t.Fatalf("step admission query mentioned forbidden field %q: %s", forbidden, joinedQueries)
		}
	}
	for _, callArgs := range execer.args {
		for _, arg := range callArgs {
			if value, ok := arg.(string); ok && strings.Contains(value, "must be stripped") {
				t.Fatalf("step admission args leaked sanitized option value: %#v", execer.args)
			}
		}
	}
}

func TestSQLStepStarterCompensatesTemporalStartFailureInTenantActorContext(t *testing.T) {
	execer := &recordingTenantActorWorldlineExecer{}
	temporalClient := &recordingWorldlineTemporalClient{err: errors.New("private provider api_key=sk-hidden prompt=hidden")}
	starter := NewSQLStepStarter(SQLStepStarterConfig{
		Execer: execer,
		Client: temporalClient,
		NewID: fixedWorldlineIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
		),
	})

	_, err := starter.StartStep(context.Background(), StartStepInput{
		TenantID: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", ProjectID: "dddddddd-dddd-dddd-dddd-dddddddddddd",
		SessionID: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID: "req-step-failure", Mode: "director",
	})

	if ErrorCode(err) != "WORKFLOW_FAILED" || err.Error() != "failed to start worldline step workflow" {
		t.Fatalf("unexpected sanitized start failure: code=%s err=%v", ErrorCode(err), err)
	}
	if len(execer.queries) != 2 || len(execer.tenantIDs) != 2 || len(execer.actorUserIDs) != 2 {
		t.Fatalf("expected admission and compensation tenant transactions: %#v", execer)
	}
	for index := range execer.tenantIDs {
		if execer.tenantIDs[index] != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
			execer.actorUserIDs[index] != "cccccccc-cccc-cccc-cccc-cccccccccccc" {
			t.Fatalf("tenant actor context drifted: tenants=%#v actors=%#v", execer.tenantIDs, execer.actorUserIDs)
		}
	}
	compensationQuery := strings.ToLower(execer.queries[1])
	for _, required := range []string{"update workflow_runs", "status = 'failed'", "workflow.start_failed", "status = 'queued'"} {
		if !strings.Contains(compensationQuery, required) {
			t.Fatalf("compensation query missing %q: %s", required, compensationQuery)
		}
	}
	for _, forbidden := range []string{"sk-hidden", "prompt=hidden", "private provider"} {
		if strings.Contains(err.Error(), forbidden) || strings.Contains(strings.Join(stringArgs(execer.args), " "), forbidden) {
			t.Fatalf("start failure leaked private Temporal error %q", forbidden)
		}
	}
}

func TestSQLStepStarterCompensationSurvivesCancelledRequestContext(t *testing.T) {
	execer := &recordingTenantActorWorldlineExecer{}
	temporalClient := &recordingWorldlineTemporalClient{err: context.Canceled}
	starter := NewSQLStepStarter(SQLStepStarterConfig{
		Execer: execer, Client: temporalClient,
		NewID: fixedWorldlineIDs("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"),
	})
	requestContext, cancelRequest := context.WithCancel(context.Background())
	cancelRequest()

	_, _ = starter.StartStep(requestContext, StartStepInput{
		TenantID: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", ProjectID: "dddddddd-dddd-dddd-dddd-dddddddddddd",
		SessionID: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
	})

	if len(execer.contextErrors) != 2 {
		t.Fatalf("expected admission and compensation contexts, got %#v", execer.contextErrors)
	}
	if !errors.Is(execer.contextErrors[0], context.Canceled) {
		t.Fatalf("admission should observe cancelled request context, got %v", execer.contextErrors[0])
	}
	if execer.contextErrors[1] != nil {
		t.Fatalf("compensation must detach from request cancellation, got %v", execer.contextErrors[1])
	}
}

func TestSQLStepStarterReturnsIdempotentRunWithoutStartingTemporalAgain(t *testing.T) {
	existing := StepRun{
		RunID: "99999999-9999-4999-8999-999999999999", ProjectID: "dddddddd-dddd-dddd-dddd-dddddddddddd",
		SessionID: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", WorkflowType: "worldline_step", Status: "running",
	}
	admission := &recordingWorldlineStepAdmissionExecer{run: existing, idempotent: true}
	temporalClient := &recordingWorldlineTemporalClient{}
	starter := NewSQLStepStarter(SQLStepStarterConfig{
		Execer: admission, Client: temporalClient,
		NewID: fixedWorldlineIDs("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"),
	})
	input := StartStepInput{
		TenantID: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", ProjectID: existing.ProjectID,
		SessionID: existing.SessionID, ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID: "req-idempotent", Mode: "director",
	}

	run, err := starter.StartStep(context.Background(), input)

	if err != nil || !reflect.DeepEqual(run, existing) {
		t.Fatalf("expected existing idempotent run, got run=%#v err=%v", run, err)
	}
	if !reflect.DeepEqual(admission.input, input) || admission.proposed.RunID != "11111111-1111-1111-1111-111111111111" {
		t.Fatalf("unexpected admission call: %#v", admission)
	}
	if len(temporalClient.args) != 0 {
		t.Fatalf("idempotent retry started Temporal again: %#v", temporalClient.args)
	}
}

func TestSQLStepStarterRejectsActiveStepWithoutStartingTemporal(t *testing.T) {
	admission := &recordingWorldlineStepAdmissionExecer{err: &AppError{
		Code: "WORLDLINE_STEP_ACTIVE", Message: "worldline session already has an active step",
	}}
	temporalClient := &recordingWorldlineTemporalClient{}
	starter := NewSQLStepStarter(SQLStepStarterConfig{
		Execer: admission, Client: temporalClient,
		NewID: fixedWorldlineIDs("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"),
	})

	_, err := starter.StartStep(context.Background(), StartStepInput{
		TenantID: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", ProjectID: "dddddddd-dddd-dddd-dddd-dddddddddddd",
		SessionID: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", RequestID: "req-overlap",
	})

	if ErrorCode(err) != "WORLDLINE_STEP_ACTIVE" || err.Error() != "worldline session already has an active step" {
		t.Fatalf("unexpected active-step error: code=%s err=%v", ErrorCode(err), err)
	}
	if len(temporalClient.args) != 0 {
		t.Fatalf("active overlap started Temporal: %#v", temporalClient.args)
	}
}

func TestSQLSessionStoreListsAndGetsTenantScopedPublicSessions(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"session-1",
			"run-1",
			"project-123",
			"queued",
			"active",
			"Explore public consequence",
			"path-1",
			3,
			"user-1",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	store := NewSQLSessionStore(SQLSessionStoreConfig{Queryer: queryer, Limit: 20})

	sessions, err := store.ListSessions(context.Background(), ListSessionsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("list sessions: %v", err)
	}
	if len(sessions) != 1 {
		t.Fatalf("expected one session, got %#v", sessions)
	}
	session := sessions[0]
	if session.SessionID != "session-1" || session.RunID != "run-1" || session.Status != "queued" {
		t.Fatalf("unexpected session summary: %#v", session)
	}
	if session.CurrentStep != 3 {
		t.Fatalf("expected domain current_step 3, got %#v", session)
	}
	if !strings.Contains(queryer.query, "FROM worldline_sessions") {
		t.Fatalf("expected worldline_sessions query, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "MAX(e.step)") || !strings.Contains(queryer.query, "FROM worldline_events e") {
		t.Fatalf("expected domain-step subquery for current_step, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "s.tenant_id::text = $1") || !strings.Contains(queryer.query, "s.project_id::text = $2") {
		t.Fatalf("expected tenant/project scoped list query, got %s", queryer.query)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("session list selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}

	queryer.rows = &fakeWorldlineRows{values: [][]any{{
		"session-1",
		"run-1",
		"project-123",
		"queued",
		"active",
		"Explore public consequence",
		"path-1",
		0,
		"user-1",
		"2026-07-05T00:00:00Z",
		"2026-07-05T00:01:00Z",
	}}}
	detail, err := store.GetSession(context.Background(), GetSessionInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
	})
	if err != nil {
		t.Fatalf("get session: %v", err)
	}
	if detail.SessionID != "session-1" || detail.ProjectID != "project-123" {
		t.Fatalf("unexpected session detail: %#v", detail)
	}
	if detail.CurrentStep != 0 {
		t.Fatalf("expected current_step 0 before any domain event, got %#v", detail)
	}
	if !strings.Contains(queryer.query, "s.session_id::text = $2") {
		t.Fatalf("expected tenant/session scoped detail query, got %s", queryer.query)
	}
}

func TestSQLTimelineReaderListsSessionWorkflowEventsAsPublicMetadata(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"event-1",
			"session-1",
			"run-1",
			"project-123",
			"worldline.session.started",
			2,
			"running",
			"active",
			"Director opened the current-world experiment",
			"Public event summary",
			"director",
			"",
			"",
			"",
			"2026-07-05T00:00:00Z",
		}}},
	}
	reader := NewSQLTimelineReader(SQLTimelineReaderConfig{Queryer: queryer, Limit: 25})

	events, err := reader.ListTimeline(context.Background(), ListTimelineInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
	})

	if err != nil {
		t.Fatalf("list timeline: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("expected one timeline event, got %#v", events)
	}
	event := events[0]
	if event.EventID != "event-1" || event.SessionID != "session-1" || event.ProjectID != "project-123" || event.Sequence != 2 {
		t.Fatalf("unexpected timeline identity: %#v", event)
	}
	if event.Status != "running" || event.Lifecycle != "active" || event.Kind != "director" {
		t.Fatalf("unexpected timeline metadata: %#v", event)
	}
	if event.EventRefID != "" || event.AdoptedTitle != "" || event.AdoptedSummary != "" {
		t.Fatalf("unexpected adoption reference on a plain orchestration event: %#v", event)
	}
	if !strings.Contains(queryer.query, "FROM workflow_events") || !strings.Contains(queryer.query, "JOIN worldline_sessions") {
		t.Fatalf("expected workflow_events joined to worldline_sessions, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "s.tenant_id::text = $1") || !strings.Contains(queryer.query, "s.session_id::text = $2") {
		t.Fatalf("expected tenant/session scoped timeline query, got %s", queryer.query)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("timeline query selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "session-1", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
	if queryer.tenantID != "tenant-123" || queryer.tenantCalls != 1 {
		t.Fatalf("timeline reader skipped tenant context: %#v", queryer)
	}
}

func TestSQLTimelineReaderResolvesAdoptionToDomainEvent(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"orch-event-9",
			"session-1",
			"run-1",
			"project-123",
			"worldline.event.adopted",
			3,
			"canon",
			"canon_reference",
			"",
			"",
			"event_adoption",
			"domain-event-42",
			"王捕头赠别",
			"王捕头私下赠予许七安防身之物。",
			"2026-07-05T00:02:00Z",
		}}},
	}
	reader := NewSQLTimelineReader(SQLTimelineReaderConfig{Queryer: queryer, Limit: 25})

	events, err := reader.ListTimeline(context.Background(), ListTimelineInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
	})
	if err != nil {
		t.Fatalf("list timeline: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("expected one timeline event, got %#v", events)
	}
	event := events[0]
	if event.EventRefID != "domain-event-42" || event.AdoptedTitle != "王捕头赠别" || event.AdoptedSummary == "" {
		t.Fatalf("expected adoption to resolve to the referenced domain event, got %#v", event)
	}
	if !strings.Contains(queryer.query, "LEFT JOIN worldline_events ref") || !strings.Contains(queryer.query, "event_ref_id") {
		t.Fatalf("expected timeline to join the referenced domain event, got %s", queryer.query)
	}
}

func TestAdoptEventPayloadReferencesDomainEvent(t *testing.T) {
	// The adoption workflow_event should carry the referenced event id, not a
	// "Worldline event adopted" placeholder title.
	payload := map[string]any{
		"status":       "canon",
		"lifecycle":    "canon_reference",
		"kind":         "event_adoption",
		"event_ref_id": "domain-event-42",
		"event_id":     "domain-event-42",
		"adoption_id":  "adoption-1",
	}
	if payload["event_ref_id"] != payload["event_id"] {
		t.Fatalf("adoption payload should key the referenced event under event_ref_id")
	}
}

func TestDisabledEventReaderFailsClosed(t *testing.T) {
	reader := NewDisabledEventReader()

	_, err := reader.ListEvents(context.Background(), ListEventsInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
	})

	if code := ErrorCode(err); code != "WORLDLINE_EVENT_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed event backend error, got %s (%v)", code, err)
	}
}

func TestDisabledEventReaderGetEventFailsClosed(t *testing.T) {
	reader := NewDisabledEventReader()

	_, err := reader.GetEvent(context.Background(), GetEventInput{
		TenantID: "tenant-123",
		EventID:  "event-1",
	})

	if code := ErrorCode(err); code != "WORLDLINE_EVENT_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed event backend error, got %s (%v)", code, err)
	}
}

func TestSQLEventReaderListsTenantSessionScopedPublicCandidateMetadata(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"event-1",
			"session-1",
			"project-123",
			3,
			"密谈破裂",
			"公开候选事件摘要",
			"director",
			"candidate",
			"simulation",
			"0.86",
			`["agent-1","agent-2"]`,
			`{"tension":"raised"}`,
			"run-1",
			"user-1",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	reader := NewSQLEventReader(SQLEventReaderConfig{Queryer: queryer, Limit: 25})

	events, err := reader.ListEvents(context.Background(), ListEventsInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
		Status:    "candidate",
	})

	if err != nil {
		t.Fatalf("list events: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("expected one event, got %#v", events)
	}
	event := events[0]
	if event.EventID != "event-1" || event.SessionID != "session-1" || event.ProjectID != "project-123" || event.Step != 3 {
		t.Fatalf("unexpected event identity: %#v", event)
	}
	if event.Status != "candidate" || event.Lifecycle != "simulation" || event.Kind != "director" {
		t.Fatalf("unexpected event metadata: %#v", event)
	}
	if !reflect.DeepEqual(event.InvolvedAgentIDs, []string{"agent-1", "agent-2"}) {
		t.Fatalf("unexpected involved agents: %#v", event.InvolvedAgentIDs)
	}
	if event.StateChanges["tension"] != "raised" {
		t.Fatalf("unexpected state changes: %#v", event.StateChanges)
	}
	if !strings.Contains(queryer.query, "FROM worldline_events") || !strings.Contains(queryer.query, "JOIN worldline_sessions") {
		t.Fatalf("expected worldline_events joined to worldline_sessions, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "s.tenant_id::text = $1") || !strings.Contains(queryer.query, "s.session_id::text = $2") || !strings.Contains(queryer.query, "AND e.status = $3") {
		t.Fatalf("expected tenant/session/status scoped event query, got %s", queryer.query)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("event query selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "session-1", "candidate", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
	if queryer.tenantID != "tenant-123" || queryer.tenantCalls != 1 {
		t.Fatalf("event list reader skipped tenant context: %#v", queryer)
	}
}

func TestSQLEventReaderGetsTenantScopedPublicEventMetadata(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"event-1",
			"session-1",
			"project-123",
			3,
			"密谈破裂",
			"公开候选事件摘要",
			"director",
			"candidate",
			"simulation",
			"0.86",
			`["agent-1","agent-2"]`,
			`{"tension":"raised"}`,
			"run-1",
			"user-1",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	reader := NewSQLEventReader(SQLEventReaderConfig{Queryer: queryer, Limit: 25})

	event, err := reader.GetEvent(context.Background(), GetEventInput{
		TenantID: "tenant-123",
		EventID:  "event-1",
	})

	if err != nil {
		t.Fatalf("get event: %v", err)
	}
	if event.EventID != "event-1" || event.SessionID != "session-1" || event.ProjectID != "project-123" || event.Step != 3 {
		t.Fatalf("unexpected event identity: %#v", event)
	}
	if event.Status != "candidate" || event.Lifecycle != "simulation" || event.Kind != "director" {
		t.Fatalf("unexpected event metadata: %#v", event)
	}
	if !strings.Contains(queryer.query, "FROM worldline_events") || !strings.Contains(queryer.query, "JOIN worldline_sessions") {
		t.Fatalf("expected worldline_events joined to worldline_sessions, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "s.tenant_id::text = $1") || !strings.Contains(queryer.query, "e.event_id::text = $2") {
		t.Fatalf("expected tenant/event scoped event query, got %s", queryer.query)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("event owner query selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "event-1"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
	if queryer.tenantID != "tenant-123" || queryer.tenantCalls != 1 {
		t.Fatalf("event detail reader skipped tenant context: %#v", queryer)
	}
}

func TestDisabledEventAdoptionStoreFailsClosed(t *testing.T) {
	store := NewDisabledEventAdoptionStore()

	_, err := store.AdoptEvent(context.Background(), AdoptEventInput{
		TenantID: "tenant-123",
		EventID:  "event-1",
	})

	if code := ErrorCode(err); code != "WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed event adoption backend error, got %s (%v)", code, err)
	}
}

func TestDisabledEventMutationStoreFailsClosed(t *testing.T) {
	store := NewDisabledEventMutationStore()

	_, err := store.UpdateEvent(context.Background(), UpdateEventInput{
		TenantID: "tenant-123",
		EventID:  "event-1",
		Title:    "Edited title",
	})

	if code := ErrorCode(err); code != "WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed event mutation backend error, got %s (%v)", code, err)
	}
}

func TestSQLEventMutationStoreUpdatesTenantScopedCandidateAndWritesSanitizedEvent(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"dddddddd-dddd-dddd-dddd-dddddddddddd",
			"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
			"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
			3,
			"密谈缓和",
			"公开编辑后的候选事件摘要",
			"director_revision",
			"candidate",
			"simulation",
			"0.86",
			`["agent-1","agent-2"]`,
			`{"tension":"lowered"}`,
			"11111111-1111-1111-1111-111111111111",
			"cccccccc-cccc-cccc-cccc-cccccccccccc",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:02:00Z",
		}}},
	}
	store := NewSQLEventMutationStore(SQLEventMutationStoreConfig{
		Queryer: queryer,
		NewID:   fixedWorldlineIDs("33333333-3333-3333-3333-333333333333"),
	})

	event, err := store.UpdateEvent(context.Background(), UpdateEventInput{
		TenantID:    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		EventID:     "dddddddd-dddd-dddd-dddd-dddddddddddd",
		ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID:   "req-edit-event-123",
		Title:       "密谈缓和",
		Summary:     "公开编辑后的候选事件摘要",
		Kind:        "director_revision",
	})

	if err != nil {
		t.Fatalf("update event: %v", err)
	}
	if event.EventID != "dddddddd-dddd-dddd-dddd-dddddddddddd" ||
		event.Status != "candidate" ||
		event.Lifecycle != "simulation" ||
		event.Title != "密谈缓和" ||
		event.Summary != "公开编辑后的候选事件摘要" ||
		event.Kind != "director_revision" {
		t.Fatalf("unexpected updated event metadata: %#v", event)
	}
	query := strings.ToLower(queryer.query)
	for _, required := range []string{
		"update worldline_events",
		"status = 'candidate'",
		"insert into workflow_events",
		"worldline.event.updated",
	} {
		if !strings.Contains(query, required) {
			t.Fatalf("expected %s query, got %s", required, queryer.query)
		}
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(query, forbidden) {
			t.Fatalf("event mutation query mentioned forbidden field %q: %s", forbidden, queryer.query)
		}
	}
	for _, arg := range queryer.args {
		if value, ok := arg.(string); ok {
			for _, forbidden := range []string{"prompt", "response", "api_key", "credential_ref", "manuscript", "draft"} {
				if strings.Contains(strings.ToLower(value), forbidden) {
					t.Fatalf("event mutation args leaked forbidden value: %#v", queryer.args)
				}
			}
		}
	}
	if queryer.tenantID != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
		queryer.actorUserID != "cccccccc-cccc-cccc-cccc-cccccccccccc" || queryer.actorCalls != 1 {
		t.Fatalf("event mutation skipped tenant actor context: %#v", queryer)
	}
}

func TestSQLEventAdoptionStoreAdoptsTenantScopedCandidateAndWritesSanitizedEvents(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"dddddddd-dddd-dddd-dddd-dddddddddddd",
			"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
			"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
			3,
			"密谈破裂",
			"公开候选事件摘要",
			"director",
			"canon",
			"canon_reference",
			"0.86",
			`["agent-1","agent-2"]`,
			`{"tension":"raised"}`,
			"11111111-1111-1111-1111-111111111111",
			"cccccccc-cccc-cccc-cccc-cccccccccccc",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	store := NewSQLEventAdoptionStore(SQLEventAdoptionStoreConfig{
		Queryer: queryer,
		NewID: fixedWorldlineIDs(
			"22222222-2222-2222-2222-222222222222",
			"33333333-3333-3333-3333-333333333333",
		),
	})

	event, err := store.AdoptEvent(context.Background(), AdoptEventInput{
		TenantID:    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		EventID:     "dddddddd-dddd-dddd-dddd-dddddddddddd",
		ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID:   "req-adopt-event-123",
		Note:        "Adopt as current-world canon",
	})

	if err != nil {
		t.Fatalf("adopt event: %v", err)
	}
	if event.EventID != "dddddddd-dddd-dddd-dddd-dddddddddddd" ||
		event.SessionID != "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" ||
		event.ProjectID != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
		event.Status != "canon" ||
		event.Lifecycle != "canon_reference" {
		t.Fatalf("unexpected adopted event metadata: %#v", event)
	}
	query := strings.ToLower(queryer.query)
	for _, required := range []string{
		"update worldline_events",
		"status = 'candidate'",
		"insert into worldline_event_adoptions",
		"insert into workflow_events",
		"worldline.event.adopted",
	} {
		if !strings.Contains(query, required) {
			t.Fatalf("expected %s query, got %s", required, queryer.query)
		}
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(query, forbidden) {
			t.Fatalf("event adoption query mentioned forbidden field %q: %s", forbidden, queryer.query)
		}
	}
	for _, arg := range queryer.args {
		if value, ok := arg.(string); ok {
			for _, forbidden := range []string{"prompt", "response", "api_key", "credential_ref", "manuscript", "draft"} {
				if strings.Contains(strings.ToLower(value), forbidden) {
					t.Fatalf("event adoption args leaked forbidden value: %#v", queryer.args)
				}
			}
		}
	}
	if queryer.tenantID != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
		queryer.actorUserID != "cccccccc-cccc-cccc-cccc-cccccccccccc" || queryer.actorCalls != 1 {
		t.Fatalf("event adoption skipped tenant actor context: %#v", queryer)
	}
}

func TestDisabledVariableStoreFailsClosed(t *testing.T) {
	store := NewDisabledVariableStore()

	_, err := store.InjectVariable(context.Background(), InjectVariableInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
		Name:      "亲族提前失踪",
	})

	if code := ErrorCode(err); code != "WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed variable backend error, got %s (%v)", code, err)
	}
}

func TestSQLVariableStoreInjectsVariableMetadataAndQueuedEvent(t *testing.T) {
	execer := &recordingWorldlineExecer{results: []sql.Result{driver.RowsAffected(1)}}
	store := NewSQLVariableStore(SQLVariableStoreConfig{
		Execer: execer,
		NewID: fixedWorldlineIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
		),
	})

	variable, err := store.InjectVariable(context.Background(), InjectVariableInput{
		TenantID:    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		SessionID:   "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID:   "req-variable-123",
		Name:        "主角亲族提前失踪",
		Description: "公开变量摘要",
		ImpactAxis:  "kinship_pressure",
		Locked:      true,
		Source:      "author",
	})

	if err != nil {
		t.Fatalf("inject variable: %v", err)
	}
	if variable.VariableID != "11111111-1111-1111-1111-111111111111" ||
		variable.SessionID != "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" ||
		variable.Name != "主角亲族提前失踪" ||
		variable.ImpactAxis != "kinship_pressure" ||
		!variable.Locked ||
		variable.Source != "author" {
		t.Fatalf("unexpected variable metadata: %#v", variable)
	}
	joinedQueries := strings.ToLower(strings.Join(execer.queries, "\n"))
	for _, required := range []string{"insert into worldline_variables", "worldline_sessions", "insert into workflow_events", "worldline.variable.injected"} {
		if !strings.Contains(joinedQueries, required) {
			t.Fatalf("expected %s query, got %s", required, joinedQueries)
		}
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(joinedQueries, forbidden) {
			t.Fatalf("variable injection query mentioned forbidden field %q: %s", forbidden, joinedQueries)
		}
	}
	for _, callArgs := range execer.args {
		for _, arg := range callArgs {
			if value, ok := arg.(string); ok {
				for _, forbidden := range []string{"must be stripped", "api_key", "credential_ref"} {
					if strings.Contains(value, forbidden) {
						t.Fatalf("variable injection args leaked forbidden value: %#v", execer.args)
					}
				}
			}
		}
	}
}

func TestSQLVariableStoreSetVariableLockedUpdatesAndReturnsCurrentRow(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"11111111-1111-1111-1111-111111111111",
			"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
			"project-123",
			"主角亲族提前失踪",
			"公开变量摘要",
			"kinship_pressure",
			true,
			"author",
			"user-1",
			"2026-07-05T00:00:00Z",
			"2026-07-26T00:00:00Z",
		}}},
	}
	store := NewSQLVariableStore(SQLVariableStoreConfig{Queryer: queryer})

	variable, err := store.SetVariableLocked(context.Background(), SetVariableLockedInput{
		TenantID:    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		SessionID:   "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		VariableID:  "11111111-1111-1111-1111-111111111111",
		ActorUserID: "cccccccc-cccc-cccc-cccc-cccccccccccc",
		Locked:      true,
	})

	if err != nil {
		t.Fatalf("set variable locked: %v", err)
	}
	if !variable.Locked || variable.VariableID != "11111111-1111-1111-1111-111111111111" {
		t.Fatalf("expected RETURNING row with locked=true, got %#v", variable)
	}
	if queryer.tenantID != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
		queryer.actorUserID != "cccccccc-cccc-cccc-cccc-cccccccccccc" {
		t.Fatalf("lock update bypassed tenant/actor context: tenant=%q actor=%q", queryer.tenantID, queryer.actorUserID)
	}
	if !strings.Contains(queryer.query, "UPDATE worldline_variables") ||
		!strings.Contains(queryer.query, "SET locked = $4") ||
		!strings.Contains(queryer.query, "RETURNING") {
		t.Fatalf("expected UPDATE … RETURNING lock query, got %s", queryer.query)
	}
	if len(queryer.args) != 4 || queryer.args[3] != true {
		t.Fatalf("expected locked value as the fourth bind, got %#v", queryer.args)
	}

	// Idempotent: PATCHing the same value again returns the current row (200).
	queryer.rows = &fakeWorldlineRows{values: [][]any{{
		"11111111-1111-1111-1111-111111111111",
		"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		"project-123",
		"主角亲族提前失踪",
		"公开变量摘要",
		"kinship_pressure",
		true,
		"author",
		"user-1",
		"2026-07-05T00:00:00Z",
		"2026-07-26T00:01:00Z",
	}}}
	again, err := store.SetVariableLocked(context.Background(), SetVariableLockedInput{
		TenantID:   "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		SessionID:  "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		VariableID: "11111111-1111-1111-1111-111111111111",
		Locked:     true,
	})
	if err != nil || !again.Locked {
		t.Fatalf("expected idempotent re-lock to succeed, got %#v (%v)", again, err)
	}
}

func TestSQLVariableStoreSetVariableLockedReturnsNotFoundForUnknownVariable(t *testing.T) {
	queryer := &recordingWorldlineQueryer{rows: &fakeWorldlineRows{}}
	store := NewSQLVariableStore(SQLVariableStoreConfig{Queryer: queryer})

	_, err := store.SetVariableLocked(context.Background(), SetVariableLockedInput{
		TenantID:   "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		SessionID:  "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		VariableID: "dddddddd-dddd-dddd-dddd-dddddddddddd",
		Locked:     true,
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected NOT_FOUND for unknown variable, got %s (%v)", code, err)
	}
}

func TestSQLVariableStoreListsSessionVariablesInCreationOrder(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{
			{
				"11111111-1111-1111-1111-111111111111",
				"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
				"project-123",
				"亲族提前失踪",
				"公开变量摘要",
				"kinship_pressure",
				true,
				"author",
				"user-1",
				"2026-07-05T00:00:00Z",
				"2026-07-26T00:00:00Z",
			},
			{
				"22222222-2222-2222-2222-222222222222",
				"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
				"project-123",
				"未锁定变量",
				"",
				"",
				false,
				"author",
				"user-1",
				"2026-07-05T00:02:00Z",
				"2026-07-05T00:02:00Z",
			},
		}},
	}
	store := NewSQLVariableStore(SQLVariableStoreConfig{Queryer: queryer})

	variables, err := store.ListVariables(context.Background(), ListVariablesInput{
		TenantID:  "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		SessionID: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
	})

	if err != nil {
		t.Fatalf("list variables: %v", err)
	}
	if len(variables) != 2 || !variables[0].Locked || variables[1].Locked {
		t.Fatalf("unexpected variables: %#v", variables)
	}
	if queryer.tenantCalls != 1 || queryer.tenantID != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" {
		t.Fatalf("variable list bypassed tenant context: %#v", queryer)
	}
	if !strings.Contains(queryer.query, "FROM worldline_variables") ||
		!strings.Contains(queryer.query, "session_id = $2::uuid") {
		t.Fatalf("expected session-scoped variable list query, got %s", queryer.query)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("variable list selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}
}

func TestDisabledVariableStoreLockAndListFailClosed(t *testing.T) {
	store := NewDisabledVariableStore()

	if _, err := store.SetVariableLocked(context.Background(), SetVariableLockedInput{
		TenantID:   "tenant-123",
		SessionID:  "session-1",
		VariableID: "variable-1",
		Locked:     true,
	}); ErrorCode(err) != "WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed lock error, got %v", err)
	}
	if _, err := store.ListVariables(context.Background(), ListVariablesInput{
		TenantID:  "tenant-123",
		SessionID: "session-1",
	}); ErrorCode(err) != "WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed list error, got %v", err)
	}
}

func TestSQLPreparationStoreCreatesPreparationAdmissionAndSanitizedQueuedEvent(t *testing.T) {
	execer := &recordingTenantActorWorldlineExecer{
		recordingWorldlineExecer: recordingWorldlineExecer{results: []sql.Result{driver.RowsAffected(1)}},
	}
	store := NewSQLPreparationStore(SQLPreparationStoreConfig{
		Execer: execer,
		NewID: fixedWorldlineIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
			"33333333-3333-3333-3333-333333333333",
		),
	})

	preparation, err := store.CreatePreparation(context.Background(), CreatePreparationInput{
		TenantID:     "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		ProjectID:    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
		ActorUserID:  "cccccccc-cccc-cccc-cccc-cccccccccccc",
		RequestID:    "req-prepare-123",
		Goal:         "Prepare current-world council agents",
		AnchorPathID: "dddddddd-dddd-dddd-dddd-dddddddddddd",
		Options: map[string]any{
			"agent_count":       3,
			"prompt":            "must be stripped",
			"response":          "must be stripped",
			"encrypted_api_key": "must be stripped",
			"credential_ref":    "must be stripped",
		},
	})

	if err != nil {
		t.Fatalf("create preparation: %v", err)
	}
	if preparation.PrepareID != "22222222-2222-2222-2222-222222222222" ||
		preparation.RunID != "11111111-1111-1111-1111-111111111111" ||
		preparation.ProjectID != "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" ||
		preparation.WorkflowType != "worldline_preparation" ||
		preparation.Status != "queued" ||
		preparation.Lifecycle != "preparing" {
		t.Fatalf("unexpected preparation summary: %#v", preparation)
	}
	if len(execer.tenantIDs) != 1 || execer.tenantIDs[0] != "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" ||
		len(execer.actorUserIDs) != 1 || execer.actorUserIDs[0] != "cccccccc-cccc-cccc-cccc-cccccccccccc" {
		t.Fatalf("preparation admission bypassed tenant/actor context: tenant=%#v actor=%#v", execer.tenantIDs, execer.actorUserIDs)
	}

	joinedQueries := strings.ToLower(strings.Join(execer.queries, "\n"))
	for _, required := range []string{"insert into workflow_runs", "insert into worldline_preparations", "insert into workflow_events"} {
		if !strings.Contains(joinedQueries, required) {
			t.Fatalf("expected %s query, got %s", required, joinedQueries)
		}
	}
	for _, forbidden := range []string{"prompt", "response", "body_text", "content_text", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(joinedQueries, forbidden) {
			t.Fatalf("preparation admission query mentioned forbidden field %q: %s", forbidden, joinedQueries)
		}
	}
	for _, callArgs := range execer.args {
		for _, arg := range callArgs {
			if value, ok := arg.(string); ok && strings.Contains(value, "must be stripped") {
				t.Fatalf("preparation admission args leaked sanitized option value: %#v", execer.args)
			}
		}
	}
}

func TestSQLPreparationStoreListsPreparationsByProject(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"prepare-1",
			"run-1",
			"project-123",
			"worldline_preparation",
			"queued",
			"preparing",
			"Prepare council agents",
			"path-1",
			"user-1",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	store := NewSQLPreparationStore(SQLPreparationStoreConfig{Queryer: queryer, Limit: 20})

	preparations, err := store.ListPreparations(context.Background(), ListPreparationsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})
	if err != nil {
		t.Fatalf("list preparations: %v", err)
	}
	if len(preparations) != 1 || preparations[0].PrepareID != "prepare-1" {
		t.Fatalf("unexpected preparations: %#v", preparations)
	}
	if !strings.Contains(queryer.query, "FROM worldline_preparations") ||
		!strings.Contains(queryer.query, "project_id::text = $2") ||
		!strings.Contains(queryer.query, "ORDER BY updated_at DESC") ||
		!strings.Contains(queryer.query, "LIMIT 20") {
		t.Fatalf("expected project-scoped preparation list query, got %s", queryer.query)
	}
}

func TestSQLPreparationStoreReadsPreparationAndPreparedAgentsAsPublicMetadata(t *testing.T) {
	queryer := &recordingWorldlineQueryer{
		rows: &fakeWorldlineRows{values: [][]any{{
			"prepare-1",
			"run-1",
			"project-123",
			"worldline_preparation",
			"queued",
			"preparing",
			"Prepare council agents",
			"path-1",
			"user-1",
			"2026-07-05T00:00:00Z",
			"2026-07-05T00:01:00Z",
		}}},
	}
	store := NewSQLPreparationStore(SQLPreparationStoreConfig{Queryer: queryer, Limit: 20})

	preparation, err := store.GetPreparation(context.Background(), GetPreparationInput{
		TenantID:  "tenant-123",
		PrepareID: "prepare-1",
	})
	if err != nil {
		t.Fatalf("get preparation: %v", err)
	}
	if preparation.PrepareID != "prepare-1" || preparation.RunID != "run-1" || preparation.Status != "queued" {
		t.Fatalf("unexpected preparation detail: %#v", preparation)
	}
	if !strings.Contains(queryer.query, "FROM worldline_preparations") {
		t.Fatalf("expected worldline_preparations query, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "prepare_id::text = $2") {
		t.Fatalf("expected tenant/prepare scoped query, got %s", queryer.query)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("preparation detail selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}

	queryer.rows = &fakeWorldlineRows{values: [][]any{{
		"agent-1",
		"prepare-1",
		"project-123",
		"林砚",
		"protagonist",
		"queued",
		"asset-1",
		"public agent summary",
		"2026-07-05T00:00:00Z",
		"2026-07-05T00:01:00Z",
	}}}
	agents, err := store.ListPreparedAgents(context.Background(), ListPreparedAgentsInput{
		TenantID:  "tenant-123",
		PrepareID: "prepare-1",
	})
	if err != nil {
		t.Fatalf("list prepared agents: %v", err)
	}
	if len(agents) != 1 {
		t.Fatalf("expected one prepared agent, got %#v", agents)
	}
	agent := agents[0]
	if agent.AgentID != "agent-1" || agent.PrepareID != "prepare-1" || agent.DisplayName != "林砚" {
		t.Fatalf("unexpected prepared agent: %#v", agent)
	}
	if !strings.Contains(queryer.query, "FROM worldline_prepared_agents") {
		t.Fatalf("expected prepared agents query, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "prepare_id::text = $2") {
		t.Fatalf("expected tenant/prepare scoped agents query, got %s", queryer.query)
	}
	for _, forbidden := range []string{"body_text", "content_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "manuscript", "draft"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("prepared agents query selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}
}

type recordingWorldlineQueryer struct {
	query       string
	args        []any
	rows        *fakeWorldlineRows
	err         error
	tenantID    string
	tenantCalls int
	actorUserID string
	actorCalls  int
}

func (q *recordingWorldlineQueryer) QueryContext(_ context.Context, query string, args ...any) (SQLRows, error) {
	q.query = query
	q.args = args
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return &fakeWorldlineRows{}, nil
	}
	return q.rows, nil
}

func (q *recordingWorldlineQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.tenantID = tenantID
	q.tenantCalls++
	return q.QueryContext(ctx, query, args...)
}

func (q *recordingWorldlineQueryer) QueryTenantActorContext(ctx context.Context, tenantID string, actorUserID string, query string, args ...any) (SQLRows, error) {
	q.tenantID = tenantID
	q.actorUserID = actorUserID
	q.actorCalls++
	return q.QueryContext(ctx, query, args...)
}

type recordingWorldlineExecer struct {
	queries []string
	args    [][]any
	results []sql.Result
	err     error
}

type recordingWorldlineTemporalClient struct {
	options  client.StartWorkflowOptions
	workflow any
	args     []any
	err      error
}

type recordingTenantActorWorldlineExecer struct {
	recordingWorldlineExecer
	tenantIDs     []string
	actorUserIDs  []string
	contextErrors []error
}

type recordingWorldlineStepAdmissionExecer struct {
	recordingWorldlineExecer
	input      StartStepInput
	proposed   StepRun
	run        StepRun
	idempotent bool
	err        error
}

func (e *recordingWorldlineStepAdmissionExecer) AdmitWorldlineStep(
	_ context.Context,
	input StartStepInput,
	proposed StepRun,
	_ string,
	_ string,
	_ string,
	_ string,
) (StepRun, bool, error) {
	e.input = input
	e.proposed = proposed
	if e.err != nil {
		return StepRun{}, false, e.err
	}
	return e.run, e.idempotent, nil
}

func (e *recordingTenantActorWorldlineExecer) ExecTenantActorContext(ctx context.Context, tenantID string, actorUserID string, query string, args ...any) (sql.Result, error) {
	e.tenantIDs = append(e.tenantIDs, tenantID)
	e.actorUserIDs = append(e.actorUserIDs, actorUserID)
	e.contextErrors = append(e.contextErrors, ctx.Err())
	return e.recordingWorldlineExecer.ExecContext(ctx, query, args...)
}

func stringArgs(calls [][]any) []string {
	values := []string{}
	for _, call := range calls {
		for _, arg := range call {
			if value, ok := arg.(string); ok {
				values = append(values, value)
			}
		}
	}
	return values
}

func (c *recordingWorldlineTemporalClient) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.options = options
	c.workflow = workflow
	c.args = args
	return nil, c.err
}

func (e *recordingWorldlineExecer) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	e.queries = append(e.queries, query)
	e.args = append(e.args, args)
	if e.err != nil {
		return nil, e.err
	}
	if len(e.results) == 0 {
		return driver.RowsAffected(1), nil
	}
	result := e.results[0]
	e.results = e.results[1:]
	return result, nil
}

func fixedWorldlineIDs(ids ...string) func() string {
	index := 0
	return func() string {
		if index >= len(ids) {
			return ids[len(ids)-1]
		}
		id := ids[index]
		index++
		return id
	}
}

type fakeWorldlineRows struct {
	values [][]any
	index  int
	err    error
}

func (r *fakeWorldlineRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeWorldlineRows) Scan(dest ...any) error {
	if r.index >= len(r.values) {
		return errors.New("scan past end")
	}
	row := r.values[r.index]
	r.index++
	for index := range dest {
		switch target := dest[index].(type) {
		case *string:
			*target = row[index].(string)
		case *int:
			*target = row[index].(int)
		case *bool:
			*target = row[index].(bool)
		default:
			return errors.New("unsupported scan target")
		}
	}
	return nil
}

func (r *fakeWorldlineRows) Close() error {
	return nil
}

func (r *fakeWorldlineRows) Err() error {
	return r.err
}
