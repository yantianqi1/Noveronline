package worldline

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"reflect"
	"strings"
	"testing"
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
	for _, required := range []string{"insert into worldline_saved_paths", "join worldline_sessions", "join worldline_events", "insert into workflow_events", "worldline.saved_path.created"} {
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
	for _, required := range []string{"insert into workflow_runs", "insert into workflow_events", "insert into worldline_sessions"} {
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
	starter := NewSQLStepStarter(SQLStepStarterConfig{
		Execer: execer,
		NewID: fixedWorldlineIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
		),
	})

	run, err := starter.StartStep(context.Background(), StartStepInput{
		TenantID:    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
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
		run.ProjectID != "" ||
		run.WorkflowType != "worldline_step" ||
		run.Status != "queued" {
		t.Fatalf("unexpected step run: %#v", run)
	}
	joinedQueries := strings.ToLower(strings.Join(execer.queries, "\n"))
	for _, required := range []string{"from worldline_sessions", "insert into workflow_runs", "insert into workflow_events", "worldline_step", "workflow.queued"} {
		if !strings.Contains(joinedQueries, required) {
			t.Fatalf("expected %s in step admission query, got %s", required, joinedQueries)
		}
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
	if !strings.Contains(queryer.query, "FROM worldline_sessions") {
		t.Fatalf("expected worldline_sessions query, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "project_id::text = $2") {
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
	if !strings.Contains(queryer.query, "session_id::text = $2") {
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
	for _, required := range []string{"insert into worldline_variables", "join worldline_sessions", "insert into workflow_events", "worldline.variable.injected"} {
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

func TestSQLPreparationStoreCreatesPreparationAdmissionAndSanitizedQueuedEvent(t *testing.T) {
	execer := &recordingWorldlineExecer{results: []sql.Result{driver.RowsAffected(1)}}
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
	query string
	args  []any
	rows  *fakeWorldlineRows
	err   error
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

type recordingWorldlineExecer struct {
	queries []string
	args    [][]any
	results []sql.Result
	err     error
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
