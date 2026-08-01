package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"regexp"
	"strings"
	"testing"
	"time"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/temporal"
)

func TestLocalWriterStarterCreatesQueuedRunWithContext(t *testing.T) {
	starter := NewLocalWriterStarter()
	run, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID:     "tenant-1",
		ProjectID:    "project-1",
		ActorUserID:  "user-1",
		RequestID:    "req-1",
		Mode:         "draft",
		Instruction:  "写一段正文",
		Options:      map[string]any{"asset_ids": []any{"asset-1"}},
		WorkflowType: "writer_run",
	})

	if err != nil {
		t.Fatalf("start writer run: %v", err)
	}
	if run.RunID == "" {
		t.Fatal("expected run id")
	}
	requireUUIDRunID(t, run.RunID)
	if run.TraceID != traceIDForRun(run.RunID) {
		t.Fatalf("expected trace id to derive from run id, got %#v", run)
	}
	if run.ProjectID != "project-1" || run.Mode != "draft" || run.Instruction != "写一段正文" || run.Status != "queued" {
		t.Fatalf("unexpected run: %#v", run)
	}
}

func TestLocalWriterStarterReadsCreatedRunWithinTenant(t *testing.T) {
	starter := NewLocalWriterStarter()
	run, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		Mode:        "draft",
		Instruction: "写一段正文",
	})
	if err != nil {
		t.Fatalf("start writer run: %v", err)
	}

	readRun, err := starter.GetWriterRun(context.Background(), GetWriterRunInput{
		TenantID: "tenant-1",
		RunID:    run.RunID,
	})
	if err != nil {
		t.Fatalf("get writer run: %v", err)
	}
	if readRun.RunID != run.RunID || readRun.TraceID != run.TraceID || readRun.ProjectID != "project-1" || readRun.Mode != "draft" || readRun.Instruction != "写一段正文" || readRun.Status != "queued" {
		t.Fatalf("unexpected run: %#v", readRun)
	}

	_, err = starter.GetWriterRun(context.Background(), GetWriterRunInput{
		TenantID: "tenant-2",
		RunID:    run.RunID,
	})
	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected tenant-isolated not found, got %s (%v)", code, err)
	}
}

func TestLocalWriterStarterRejectsMissingRequiredContext(t *testing.T) {
	starter := NewLocalWriterStarter()
	_, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID:    "tenant-1",
		ProjectID:   "",
		Mode:        "draft",
		Instruction: "写一段正文",
	})

	if err == nil {
		t.Fatal("expected missing context error")
	}
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("unexpected error code: %s", code)
	}
}

func TestSQLWriterReaderReadsPersistedRunWithinTenant(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"run-1",
				"project-1",
				"continue",
				"续写雨夜谈判",
				"completed",
			}},
		},
	}
	reader := NewSQLWriterReader(SQLWriterReaderConfig{Queryer: queryer})

	run, err := reader.GetWriterRun(context.Background(), GetWriterRunInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if err != nil {
		t.Fatalf("get writer run: %v", err)
	}
	if run.RunID != "run-1" || run.TraceID != traceIDForRun("run-1") || run.ProjectID != "project-1" || run.Mode != "continue" || run.Instruction != "续写雨夜谈判" || run.Status != "completed" {
		t.Fatalf("unexpected run: %#v", run)
	}
	if !strings.Contains(queryer.query, "FROM writer_runs") {
		t.Fatalf("expected writer_runs query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "run-1"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLWriterReaderReturnsNotFoundForMissingRun(t *testing.T) {
	queryer := &recordingWriterEventQueryer{rows: &fakeWriterEventRows{}}
	reader := NewSQLWriterReader(SQLWriterReaderConfig{Queryer: queryer})

	_, err := reader.GetWriterRun(context.Background(), GetWriterRunInput{
		TenantID: "tenant-1",
		RunID:    "run-missing",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected not found, got %s (%v)", code, err)
	}
}

func TestSQLWriterReaderUsesTenantContextForRefreshRecovery(t *testing.T) {
	queryer := &recordingTenantWriterEventQueryer{
		rows: &fakeWriterEventRows{values: [][]any{{"run-1", "project-1", "draft", "写下一场谈判", "completed"}}},
	}
	reader := NewSQLWriterReader(SQLWriterReaderConfig{Queryer: queryer})

	run, err := reader.GetWriterRun(context.Background(), GetWriterRunInput{TenantID: "tenant-1", RunID: "run-1"})
	if err != nil {
		t.Fatalf("get persisted writer run: %v", err)
	}
	if run.Status != "completed" || queryer.plainCalled || queryer.tenantID != "tenant-1" {
		t.Fatalf("writer refresh did not use persisted tenant-scoped run: run=%#v queryer=%#v", run, queryer)
	}
}

func TestSQLWriterReaderSanitizesUnexpectedQueryErrors(t *testing.T) {
	sensitiveErr := errors.New("driver leaked provider=raw prompt=hidden api_key=sk-hidden credential_ref=cred-1 object_key=projects/private draft=secret manuscript=secret")
	tests := []struct {
		name    string
		queryer WriterEventSQLQueryer
	}{
		{
			name:    "query error",
			queryer: &recordingWriterEventQueryer{err: sensitiveErr},
		},
		{
			name:    "rows error",
			queryer: &recordingWriterEventQueryer{rows: &fakeWriterEventRows{err: sensitiveErr}},
		},
		{
			name: "scan error",
			queryer: &recordingWriterEventQueryer{
				rows: &fakeWriterEventRows{
					values:  [][]any{{}},
					scanErr: sensitiveErr,
				},
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			reader := NewSQLWriterReader(SQLWriterReaderConfig{Queryer: test.queryer})

			_, err := reader.GetWriterRun(context.Background(), GetWriterRunInput{
				TenantID: "tenant-1",
				RunID:    "run-1",
			})

			if code := ErrorCode(err); code != "WORKFLOW_QUERY_FAILED" {
				t.Fatalf("expected workflow query failed, got %s (%v)", code, err)
			}
			if err == nil || err.Error() != "writer run query failed" {
				t.Fatalf("expected stable sanitized error, got %v", err)
			}
			for _, forbidden := range []string{"provider", "prompt", "api_key", "credential_ref", "object_key", "draft", "manuscript", "sk-hidden"} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("writer reader error leaked %q: %v", forbidden, err)
				}
			}
		})
	}
}

func TestDisabledManuscriptReaderFailsClosed(t *testing.T) {
	reader := NewDisabledManuscriptReader()

	_, err := reader.GetManuscript(context.Background(), GetManuscriptInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})
	if code := ErrorCode(err); code != "MANUSCRIPT_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected manuscript unconfigured error, got %s (%v)", code, err)
	}

	_, err = reader.GetManuscriptExport(context.Background(), GetManuscriptExportInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})
	if code := ErrorCode(err); code != "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected manuscript export unconfigured error, got %s (%v)", code, err)
	}
}

func TestSQLManuscriptReaderListsMetadataWithoutPrivateColumns(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"block-1",
				"project-1",
				"chapter-1",
				"draft-1",
				2,
				"accepted",
				1200,
				"2026-07-04T01:00:00Z",
				"2026-07-04T01:10:00Z",
			}},
		},
	}
	reader := NewSQLManuscriptReader(SQLManuscriptReaderConfig{Queryer: queryer})

	manuscript, err := reader.GetManuscript(context.Background(), GetManuscriptInput{
		TenantID:  " tenant-1 ",
		ProjectID: " project-1 ",
	})

	if err != nil {
		t.Fatalf("get manuscript: %v", err)
	}
	if manuscript.ProjectID != "project-1" || len(manuscript.Blocks) != 1 {
		t.Fatalf("unexpected manuscript: %#v", manuscript)
	}
	block := manuscript.Blocks[0]
	if block.BlockID != "block-1" || block.ChapterID != "chapter-1" || block.SourceDraftID != "draft-1" || block.BlockOrder != 2 || block.WordCount != 1200 {
		t.Fatalf("unexpected manuscript block: %#v", block)
	}
	if !strings.Contains(queryer.query, "FROM manuscript_blocks") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected tenant/project manuscript_blocks query, got %s", queryer.query)
	}
	assertManuscriptQueryOmitsPrivateColumns(t, queryer.query)
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "project-1"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLManuscriptReaderBuildsExportManifestWithoutPrivateColumns(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{
				{"block-1", "project-1", nil, "draft-1", 1, "accepted", 500, "2026-07-04T01:00:00Z", "2026-07-04T01:10:00Z"},
				{"block-2", "project-1", "chapter-2", nil, 2, "accepted", 700, "2026-07-04T01:20:00Z", "2026-07-04T01:30:00Z"},
			},
		},
	}
	reader := NewSQLManuscriptReader(SQLManuscriptReaderConfig{Queryer: queryer})

	manifest, err := reader.GetManuscriptExport(context.Background(), GetManuscriptExportInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		Format:    "docx",
	})

	if err != nil {
		t.Fatalf("get manuscript export: %v", err)
	}
	if manifest.ProjectID != "project-1" || manifest.Format != "metadata_manifest" || manifest.BlockCount != 2 || manifest.TotalWordCount != 1200 || manifest.Status != "ready" {
		t.Fatalf("unexpected export manifest: %#v", manifest)
	}
	if manifest.ExportedAt != "" {
		t.Fatalf("metadata-only export manifest should not claim exported artifact timestamp: %#v", manifest)
	}
	if len(manifest.Blocks) != 2 || manifest.Blocks[1].BlockID != "block-2" || manifest.Blocks[1].BlockOrder != 2 {
		t.Fatalf("unexpected manifest blocks: %#v", manifest.Blocks)
	}
	assertManuscriptQueryOmitsPrivateColumns(t, queryer.query)
}

func TestSQLManuscriptReaderNormalizesContentExportFormats(t *testing.T) {
	for _, format := range []string{"docx", "txt", "pdf"} {
		t.Run(format, func(t *testing.T) {
			queryer := &recordingWriterEventQueryer{
				rows: &fakeWriterEventRows{
					values: [][]any{{
						"block-1",
						"project-1",
						nil,
						nil,
						1,
						"available",
						100,
						"2026-07-04T01:00:00Z",
						"2026-07-04T01:10:00Z",
					}},
				},
			}
			reader := NewSQLManuscriptReader(SQLManuscriptReaderConfig{Queryer: queryer})

			manifest, err := reader.GetManuscriptExport(context.Background(), GetManuscriptExportInput{
				TenantID:  "tenant-1",
				ProjectID: "project-1",
				Format:    format,
			})

			if err != nil {
				t.Fatalf("get manuscript export: %v", err)
			}
			if manifest.Format != "metadata_manifest" {
				t.Fatalf("content export format %q should normalize to metadata_manifest: %#v", format, manifest)
			}
			if manifest.ExportedAt != "" {
				t.Fatalf("metadata-only manifest should not have exported_at for %q: %#v", format, manifest)
			}
		})
	}
}

func TestSQLManuscriptReaderSanitizesQueryFailures(t *testing.T) {
	sensitiveErr := errors.New("driver leaked content_text=private prompt=hidden api_key=sk-hidden credential_ref=cred-1 draft=secret manuscript=secret")
	tests := []struct {
		name string
		run  func(*SQLManuscriptReader) error
		code string
		msg  string
	}{
		{
			name: "manuscript query error",
			run: func(reader *SQLManuscriptReader) error {
				_, err := reader.GetManuscript(context.Background(), GetManuscriptInput{TenantID: "tenant-1", ProjectID: "project-1"})
				return err
			},
			code: "MANUSCRIPT_QUERY_FAILED",
			msg:  "manuscript query failed",
		},
		{
			name: "export query error",
			run: func(reader *SQLManuscriptReader) error {
				_, err := reader.GetManuscriptExport(context.Background(), GetManuscriptExportInput{TenantID: "tenant-1", ProjectID: "project-1"})
				return err
			},
			code: "MANUSCRIPT_EXPORT_QUERY_FAILED",
			msg:  "manuscript export query failed",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			reader := NewSQLManuscriptReader(SQLManuscriptReaderConfig{
				Queryer: &recordingWriterEventQueryer{err: sensitiveErr},
			})

			err := test.run(reader)

			if code := ErrorCode(err); code != test.code {
				t.Fatalf("expected %s, got %s (%v)", test.code, code, err)
			}
			if err.Error() != test.msg {
				t.Fatalf("expected stable public message %q, got %q", test.msg, err.Error())
			}
			assertManuscriptErrorSanitized(t, err)
		})
	}

	t.Run("scan error", func(t *testing.T) {
		reader := NewSQLManuscriptReader(SQLManuscriptReaderConfig{
			Queryer: &recordingWriterEventQueryer{
				rows: &fakeWriterEventRows{
					values:  [][]any{{}},
					scanErr: sensitiveErr,
				},
			},
		})

		_, err := reader.GetManuscript(context.Background(), GetManuscriptInput{TenantID: "tenant-1", ProjectID: "project-1"})

		if code := ErrorCode(err); code != "MANUSCRIPT_QUERY_FAILED" {
			t.Fatalf("expected stable scan failure code, got %s (%v)", code, err)
		}
		assertManuscriptErrorSanitized(t, err)
	})

	t.Run("close commit error", func(t *testing.T) {
		reader := NewSQLManuscriptReader(SQLManuscriptReaderConfig{
			Queryer: &recordingWriterEventQueryer{
				rows: &fakeWriterEventRows{
					values: [][]any{{
						"block-1",
						"project-1",
						nil,
						nil,
						1,
						"available",
						12,
						"2026-07-04T01:00:00Z",
						"2026-07-04T01:10:00Z",
					}},
					closeErr: sensitiveErr,
				},
			},
		})

		_, err := reader.GetManuscript(context.Background(), GetManuscriptInput{TenantID: "tenant-1", ProjectID: "project-1"})

		if code := ErrorCode(err); code != "MANUSCRIPT_QUERY_FAILED" {
			t.Fatalf("expected stable close failure code, got %s (%v)", code, err)
		}
		assertManuscriptErrorSanitized(t, err)
	})
}

func TestSQLWriterEventReaderListsEventsAfterCursor(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				true,
				"evt-2",
				"run-1",
				"project-1",
				2,
				"writer.token",
				`{"delta":"雨"}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLWriterEventReader(SQLWriterEventReaderConfig{Queryer: queryer, Limit: 25})

	records, err := reader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID:     "tenant-1",
		RunID:        "run-1",
		AfterEventID: "evt-1",
	})

	if err != nil {
		t.Fatalf("list writer events: %v", err)
	}
	if len(records) != 1 || records[0].EventID != "evt-2" || records[0].Payload["delta"] != "雨" {
		t.Fatalf("unexpected records: %#v", records)
	}
	if !strings.Contains(queryer.query, "FROM workflow_events") || !strings.Contains(queryer.query, "after_cursor") {
		t.Fatalf("expected workflow event resume query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "run-1", "evt-1", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func assertManuscriptQueryOmitsPrivateColumns(t *testing.T, query string) {
	t.Helper()
	lowered := strings.ToLower(query)
	for _, forbidden := range []string{
		"content_text",
		"draft_text",
		"manuscript_text",
		"prompt",
		"response",
		"credential",
		"object_key",
		"raw_body",
		"raw_content",
	} {
		if strings.Contains(lowered, forbidden) {
			t.Fatalf("manuscript query selected private column %q: %s", forbidden, query)
		}
	}
}

func assertManuscriptErrorSanitized(t *testing.T, err error) {
	t.Helper()
	message := err.Error()
	for _, forbidden := range []string{"content_text", "prompt", "api_key", "sk-hidden", "credential_ref", "draft", "manuscript=secret", "private"} {
		if strings.Contains(message, forbidden) {
			t.Fatalf("manuscript error leaked %q: %s", forbidden, message)
		}
	}
}

func TestSQLWriterEventReaderRejectsMissingCursor(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				false,
				nil,
				nil,
				nil,
				nil,
				nil,
				nil,
				nil,
			}},
		},
	}
	reader := NewSQLWriterEventReader(SQLWriterEventReaderConfig{Queryer: queryer})

	_, err := reader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID:     "tenant-1",
		RunID:        "run-1",
		AfterEventID: "evt-missing",
	})

	if code := ErrorCode(err); code != "EVENT_CURSOR_NOT_FOUND" {
		t.Fatalf("expected cursor error, got %s (%v)", code, err)
	}
}

func TestSQLWriterEventReaderReplayCursorIsStrictlyExclusiveAndStable(t *testing.T) {
	queryer := &recordingWriterEventQueryer{rows: &fakeWriterEventRows{values: [][]any{
		{true, "evt-terminal", "run-1", "project-1", 101, "writer.run.completed", `{"status":"completed","draft_id":"draft-1"}`, "2026-07-10T01:00:00Z"},
	}}}
	reader := NewSQLWriterEventReader(SQLWriterEventReaderConfig{Queryer: queryer, Limit: 100})

	events, err := reader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID: "tenant-1", RunID: "run-1", AfterEventID: "evt-100",
	})
	if err != nil {
		t.Fatalf("replay terminal event: %v", err)
	}
	if len(events) != 1 || events[0].EventID != "evt-terminal" || events[0].EventType != "writer.run.completed" {
		t.Fatalf("terminal event was lost during replay: %#v", events)
	}
	if !strings.Contains(queryer.query, "sequence >") || strings.Contains(queryer.query, "sequence >=") {
		t.Fatalf("replay cursor must be exclusive to avoid duplicates: %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "ORDER BY sequence ASC") {
		t.Fatalf("replay must remain ordered by persisted sequence: %s", queryer.query)
	}
}

func TestSQLWriterEventReaderSanitizesPublicPayload(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				true,
				"evt-1",
				"run-1",
				"project-1",
				1,
				"writer.run.failed",
				`{"status":"failed","prompt":"private prompt","api_key":"sk-live","credential_ref":"credref-1","draft":"private draft","nested":{"source_material":"private source","kept":"public nested"}}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLWriterEventReader(SQLWriterEventReaderConfig{Queryer: queryer})

	records, err := reader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if err != nil {
		t.Fatalf("list writer events: %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("expected one event, got %#v", records)
	}
	payloadJSON, err := json.Marshal(records[0].Payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	serialized := string(payloadJSON)
	for _, forbidden := range []string{
		"private prompt",
		"sk-live",
		"credref-1",
		"private draft",
		"private source",
		"prompt",
		"api_key",
		"credential_ref",
		"source_material",
	} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("writer event payload leaked %q: %#v", forbidden, records[0].Payload)
		}
	}
	if records[0].Payload["status"] != "failed" {
		t.Fatalf("expected public status to remain: %#v", records[0].Payload)
	}
	nested, ok := records[0].Payload["nested"].(map[string]any)
	if !ok || nested["kept"] != "public nested" {
		t.Fatalf("expected public nested payload to remain: %#v", records[0].Payload)
	}
}

func TestSQLWriterEventReaderUsesTenantContextQueryer(t *testing.T) {
	queryer := &recordingTenantWorkflowEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				true,
				"evt-1",
				"run-1",
				"project-1",
				1,
				"writer.run.started",
				`{"status":"running"}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLWriterEventReader(SQLWriterEventReaderConfig{Queryer: queryer, Limit: 25})

	records, err := reader.ListWriterEvents(context.Background(), ListWriterEventsInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if err != nil {
		t.Fatalf("list writer events: %v", err)
	}
	if len(records) != 1 || records[0].EventID != "evt-1" {
		t.Fatalf("unexpected writer events: %#v", records)
	}
	if queryer.tenantID != "tenant-1" || queryer.query == "" {
		t.Fatalf("writer event reader did not use tenant context queryer: %#v", queryer)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "run-1", "", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLWriterEventReaderSanitizesUnexpectedQueryErrors(t *testing.T) {
	sensitiveErr := errors.New("driver leaked prompt=hidden api_key=sk-hidden credential_ref=cred-1 object_key=projects/private raw_text=secret")
	tests := []struct {
		name    string
		queryer WriterEventSQLQueryer
	}{
		{
			name:    "query error",
			queryer: &recordingWriterEventQueryer{err: sensitiveErr},
		},
		{
			name:    "rows error",
			queryer: &recordingWriterEventQueryer{rows: &fakeWriterEventRows{err: sensitiveErr}},
		},
		{
			name: "scan error",
			queryer: &recordingWriterEventQueryer{
				rows: &fakeWriterEventRows{
					values:  [][]any{{}},
					scanErr: sensitiveErr,
				},
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			reader := NewSQLWriterEventReader(SQLWriterEventReaderConfig{Queryer: test.queryer})

			_, err := reader.ListWriterEvents(context.Background(), ListWriterEventsInput{
				TenantID: "tenant-1",
				RunID:    "run-1",
			})

			if code := ErrorCode(err); code != "WORKFLOW_EVENT_QUERY_FAILED" {
				t.Fatalf("expected stable writer event query code, got %s (%v)", code, err)
			}
			assertWorkflowEventReaderErrorSanitized(t, err)
		})
	}
}

func TestTemporalWriterStarterStartsPiWriterWorkflowWithoutWaitingForCompletion(t *testing.T) {
	temporalClient := &recordingWriterTemporalClient{}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client:    temporalClient,
		TaskQueue: WriterTaskQueue,
	})

	run, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		Mode:        "draft",
		Instruction: "写一段正文",
		Options: map[string]any{
			"module_key": "writer_composer",
			"asset_ids":  []any{"asset-1"},
		},
	})

	if err != nil {
		t.Fatalf("start writer workflow: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-1" || run.Status != "queued" {
		t.Fatalf("unexpected run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if run.TraceID != traceIDForRun(run.RunID) {
		t.Fatalf("expected trace id to derive from run id, got %#v", run)
	}
	if temporalClient.options.ID != "writer_run_"+run.RunID {
		t.Fatalf("unexpected workflow id: %#v", temporalClient.options)
	}
	if temporalClient.options.TaskQueue != WriterTaskQueue {
		t.Fatalf("unexpected task queue: %#v", temporalClient.options)
	}
	if temporalClient.workflow != PiWriterWorkflowName {
		t.Fatalf("unexpected workflow type: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected context payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != "tenant-1" || payload["project_id"] != "project-1" || payload["requested_by"] != "user-1" {
		t.Fatalf("lost writer runtime context: %#v", payload)
	}
	if payload["request_id"] != "req-1" || payload["run_id"] != run.RunID || payload["trace_id"] != run.TraceID {
		t.Fatalf("lost run/request/trace payload: %#v", payload)
	}
	if payload["workflow_type"] != WriterWorkflowType || payload["mode"] != "draft" || payload["instruction"] != "写一段正文" {
		t.Fatalf("lost writer request payload: %#v", payload)
	}
	options := payload["options"].(map[string]any)
	if options["module_key"] != "writer_composer" || options["asset_ids"].([]any)[0] != "asset-1" {
		t.Fatalf("lost writer options: %#v", options)
	}
}

func TestTemporalWriterStarterRunCacheIsBoundedAndDropsTerminalEntries(t *testing.T) {
	starter := NewTemporalWriterStarter(TemporalWriterConfig{})
	for index := 0; index < temporalWriterRunCacheLimit+25; index++ {
		starter.cacheRun(WriterRun{
			RunID:     fmt.Sprintf("run-%d", index),
			TenantID:  "tenant-1",
			ProjectID: "project-1",
			Status:    "queued",
		})
	}
	if len(starter.runs) > temporalWriterRunCacheLimit {
		t.Fatalf("run cache exceeded bound: %d", len(starter.runs))
	}

	starter.cacheRun(WriterRun{RunID: "terminal", TenantID: "tenant-1", Status: "completed"})
	if _, ok := starter.runs["terminal"]; ok {
		t.Fatal("terminal writer run should not remain in the starter cache")
	}
}

func TestTemporalWriterStarterPersistsAdmissionBeforeStartingWorkflow(t *testing.T) {
	temporalClient := &recordingWriterTemporalClient{}
	admissionStore := &recordingWriterAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client:         temporalClient,
		TaskQueue:      WriterTaskQueue,
		AdmissionStore: admissionStore,
	})

	run, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		Mode:        "draft",
		Instruction: "写一段正文",
		Options: map[string]any{
			"module_key": "writer_composer",
			"llm_resolution": map[string]any{
				"credential_ref": "llm_credential:secret",
				"provider":       "openai-compatible",
				"base_url":       "https://llm.example.test/v1",
				"channel_id":     "channel-secret",
				"model_id":       "model-secret",
				"settings":       map[string]any{"temperature": 0.7},
			},
		},
	})

	if err != nil {
		t.Fatalf("start writer workflow: %v", err)
	}
	if admissionStore.temporalWasStartedWhenCalled {
		t.Fatal("expected admission rows to persist before Temporal workflow start")
	}
	if admissionStore.input.RunID != run.RunID || admissionStore.input.TraceID != run.TraceID {
		t.Fatalf("admission lost run identifiers: %#v", admissionStore.input)
	}
	if admissionStore.input.TenantID != "tenant-1" || admissionStore.input.ProjectID != "project-1" {
		t.Fatalf("admission lost tenant/project context: %#v", admissionStore.input)
	}
	if admissionStore.input.TemporalWorkflowID != "writer_run_"+run.RunID {
		t.Fatalf("admission should know target Temporal workflow id, got %#v", admissionStore.input)
	}
	if admissionStore.input.ModuleKey != "writer_composer" || admissionStore.input.Status != "queued" {
		t.Fatalf("unexpected admission input: %#v", admissionStore.input)
	}
}

func TestTemporalWriterStarterDoesNotStartWorkflowWhenAdmissionFails(t *testing.T) {
	temporalClient := &recordingWriterTemporalClient{}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client:    temporalClient,
		TaskQueue: WriterTaskQueue,
		AdmissionStore: &recordingWriterAdmissionStore{
			err: errors.New("insert workflow_runs failed"),
		},
	})

	_, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		Mode:        "draft",
		Instruction: "写一段正文",
		Options:     map[string]any{"module_key": "writer_composer"},
	})

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected admission failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when admission persistence fails")
	}
}

func TestTemporalWriterStarterReplaysExistingAdmissionWithoutStartingWorkflow(t *testing.T) {
	temporalClient := &recordingWriterTemporalClient{}
	existing := WriterRun{
		RunID: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", TraceID: traceIDForRun("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
		TenantID: "tenant-1", ProjectID: "project-1", Mode: "draft", Instruction: "写一段正文", Status: "queued",
	}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client:    temporalClient,
		TaskQueue: WriterTaskQueue,
		AdmissionStore: &recordingWriterAdmissionStore{
			replay:    true,
			replayRun: existing,
		},
	})

	run, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID: "tenant-1", ProjectID: "project-1", RequestID: "req-replay",
		Mode: "draft", Instruction: "写一段正文",
		Options: map[string]any{"module_key": "writer_composer"},
	})
	if err != nil {
		t.Fatalf("replay writer run: %v", err)
	}
	if run.RunID != existing.RunID || run.TraceID != existing.TraceID {
		t.Fatalf("expected replayed run, got %#v", run)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start on request_id replay")
	}
}

func TestTemporalWriterStarterCompensatesWhenTemporalStartFails(t *testing.T) {
	temporalClient := &recordingWriterTemporalClient{err: errors.New("temporal unavailable")}
	admissionStore := &recordingWriterAdmissionStore{}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client: temporalClient, TaskQueue: WriterTaskQueue, AdmissionStore: admissionStore,
	})

	_, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "req-1",
		Mode: "draft", Instruction: "写一段正文",
		Options: map[string]any{"module_key": "writer_composer"},
	})
	if code := ErrorCode(err); code != "WORKFLOW_FAILED" {
		t.Fatalf("expected workflow failed, got %s (%v)", code, err)
	}
	if !admissionStore.compensateCalled {
		t.Fatal("expected compensation after Temporal start failure")
	}
	if admissionStore.compensateInput.TenantID != "tenant-1" || admissionStore.compensateInput.RequestID != "req-1" {
		t.Fatalf("compensation lost context: %#v", admissionStore.compensateInput)
	}
	if admissionStore.compensateInput.RunID == "" || admissionStore.compensateInput.RunID != admissionStore.input.RunID {
		t.Fatalf("compensation should target admitted run: compensate=%#v admit=%#v", admissionStore.compensateInput, admissionStore.input)
	}
}

func TestFailClosedWriterStarterRejectsStarts(t *testing.T) {
	starter := NewFailClosedWriterStarter()
	_, err := starter.StartWriterRun(context.Background(), StartWriterRunInput{
		TenantID: "tenant-1", ProjectID: "project-1", Mode: "draft", Instruction: "写一段正文",
	})
	if code := ErrorCode(err); code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected backend unconfigured, got %s (%v)", code, err)
	}
}

func TestTemporalWriterStarterCancelsTemporalWorkflowAndPersistsCancelledState(t *testing.T) {
	temporalClient := &recordingWriterTemporalClient{completionErr: temporal.NewCanceledError()}
	cancellationStore := &recordingWriterCancellationStore{temporalWaited: func() bool { return temporalClient.waited }}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client:            temporalClient,
		TaskQueue:         WriterTaskQueue,
		CancellationStore: cancellationStore,
	})

	cancelled, err := starter.CancelWriterRun(context.Background(), CancelWriterRunInput{
		TenantID:    "tenant-1",
		RunID:       "run-1",
		ActorUserID: "user-1",
		RequestID:   "req-cancel",
	})

	if err != nil {
		t.Fatalf("cancel writer workflow: %v", err)
	}
	if !temporalClient.cancelled {
		t.Fatal("expected Temporal cancel to be requested")
	}
	if temporalClient.cancelWorkflowID != "writer_run_run-1" || temporalClient.cancelRunID != "" {
		t.Fatalf("unexpected Temporal cancel target: workflow=%q run=%q", temporalClient.cancelWorkflowID, temporalClient.cancelRunID)
	}
	if !temporalClient.waited || cancellationStore.calledBeforeTemporalCompletion {
		t.Fatalf("public cancellation was persisted before Temporal cleanup completed: client=%#v store=%#v", temporalClient, cancellationStore)
	}
	if cancellationStore.input.TenantID != "tenant-1" || cancellationStore.input.RunID != "run-1" {
		t.Fatalf("cancellation store lost tenant/run context: %#v", cancellationStore.input)
	}
	if cancellationStore.input.ActorUserID != "user-1" || cancellationStore.input.RequestID != "req-cancel" {
		t.Fatalf("cancellation store lost actor/request context: %#v", cancellationStore.input)
	}
	if cancellationStore.input.Status != "cancelled" {
		t.Fatalf("expected persisted cancelled status, got %#v", cancellationStore.input)
	}
	if cancelled.RunID != "run-1" || cancelled.Status != "cancelled" {
		t.Fatalf("unexpected cancellation response: %#v", cancelled)
	}
}

func TestTemporalWriterStarterDoesNotExposeCancelledUntilTemporalCleanupCompletes(t *testing.T) {
	waitStarted := make(chan struct{}, 1)
	waitRelease := make(chan struct{})
	temporalClient := &recordingWriterTemporalClient{
		completionErr: temporal.NewCanceledError(), waitStarted: waitStarted, waitRelease: waitRelease,
	}
	cancellationStore := &recordingWriterCancellationStore{temporalWaited: func() bool { return temporalClient.waited }}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client: temporalClient, TaskQueue: WriterTaskQueue, CancellationStore: cancellationStore,
		CancellationWaitTimeout: time.Second,
	})
	result := make(chan error, 1)
	go func() {
		_, err := starter.CancelWriterRun(context.Background(), CancelWriterRunInput{TenantID: "tenant-1", RunID: "run-1"})
		result <- err
	}()

	select {
	case <-waitStarted:
	case <-time.After(time.Second):
		t.Fatal("writer cancellation did not wait for Temporal completion")
	}
	if cancellationStore.called {
		t.Fatal("writer cancellation became public before Pi cleanup completed")
	}
	close(waitRelease)
	if err := <-result; err != nil {
		t.Fatalf("cancel after cleanup: %v", err)
	}
	if !cancellationStore.called || cancellationStore.calledBeforeTemporalCompletion {
		t.Fatalf("writer cancellation was not persisted after cleanup: %#v", cancellationStore)
	}
}

func TestTemporalWriterStarterFailsClosedWhenCancellationCompletionIsUnconfirmed(t *testing.T) {
	for _, test := range []struct {
		name          string
		completionErr error
		expectedCode  string
	}{
		{name: "workflow completed before cancellation", completionErr: nil, expectedCode: "WORKFLOW_CANCEL_NOT_ACTIVE"},
		{name: "workflow terminal lookup failed", completionErr: errors.New("private temporal failure"), expectedCode: "WORKFLOW_CANCEL_CONFIRM_FAILED"},
	} {
		t.Run(test.name, func(t *testing.T) {
			temporalClient := &recordingWriterTemporalClient{completionErr: test.completionErr}
			store := &recordingWriterCancellationStore{}
			starter := NewTemporalWriterStarter(TemporalWriterConfig{Client: temporalClient, CancellationStore: store})
			_, err := starter.CancelWriterRun(context.Background(), CancelWriterRunInput{TenantID: "tenant-1", RunID: "run-1"})
			if code := ErrorCode(err); code != test.expectedCode {
				t.Fatalf("expected %s, got %s (%v)", test.expectedCode, code, err)
			}
			if store.called {
				t.Fatal("unconfirmed Temporal cancellation was persisted")
			}
			if strings.Contains(err.Error(), "private temporal failure") {
				t.Fatalf("cancellation confirmation leaked Temporal detail: %v", err)
			}
		})
	}
}

func TestTemporalWriterStarterDoesNotPersistCancelledStateWhenTemporalCancelFails(t *testing.T) {
	temporalClient := &recordingWriterTemporalClient{cancelErr: errors.New("temporal unavailable")}
	cancellationStore := &recordingWriterCancellationStore{}
	starter := NewTemporalWriterStarter(TemporalWriterConfig{
		Client:            temporalClient,
		TaskQueue:         WriterTaskQueue,
		CancellationStore: cancellationStore,
	})

	_, err := starter.CancelWriterRun(context.Background(), CancelWriterRunInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_CANCEL_FAILED" {
		t.Fatalf("expected workflow cancel failure, got %s (%v)", code, err)
	}
	if cancellationStore.called {
		t.Fatal("cancellation store should not update DB when Temporal did not accept cancellation")
	}
}

func TestSQLWriterAdmissionStorePersistsCancelledStatusAndWorkflowEvent(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLWriterAdmissionStore(SQLWriterAdmissionStoreConfig{Execer: execer})

	err := store.CancelWriterRun(context.Background(), WriterCancellationInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		RunID:       "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-cancel",
		Status:      "cancelled",
	})

	if err != nil {
		t.Fatalf("persist writer cancellation: %v", err)
	}
	if !strings.Contains(execer.query, "UPDATE writer_runs") || !strings.Contains(execer.query, "UPDATE workflow_runs") {
		t.Fatalf("expected writer/workflow run status updates, got %s", execer.query)
	}
	if !strings.Contains(execer.query, "writer.run.cancelled") || !strings.Contains(execer.query, "workflow_events") {
		t.Fatalf("expected cancelled workflow event insert, got %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	if strings.Contains(joinedArgs, "credential_ref") || strings.Contains(joinedArgs, "api_key") || strings.Contains(joinedArgs, "encrypted_api_key") {
		t.Fatalf("cancellation SQL args leaked credential material: %s", joinedArgs)
	}
	if !strings.Contains(joinedArgs, "req-cancel") || !strings.Contains(joinedArgs, "cancelled") {
		t.Fatalf("expected request/status metadata in cancellation args, got %s", joinedArgs)
	}
}

func TestSQLWriterAdmissionStoreUsesTenantContextForCancellationWrites(t *testing.T) {
	execer := &recordingTenantWriterAdmissionExecer{}
	store := NewSQLWriterAdmissionStore(SQLWriterAdmissionStoreConfig{Execer: execer})

	err := store.CancelWriterRun(context.Background(), WriterCancellationInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		RunID:       "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-cancel",
		Status:      "cancelled",
	})

	if err != nil {
		t.Fatalf("persist writer cancellation: %v", err)
	}
	if execer.plainCalled {
		t.Fatal("cancellation writes should use tenant-aware executor when available")
	}
	if execer.tenantID != "11111111-1111-4111-8111-111111111111" {
		t.Fatalf("tenant context was not passed before cancellation writes: %#v", execer)
	}
	if execer.projectID != "" {
		t.Fatalf("writer cancellation should not invent project context, got %#v", execer)
	}
	if !strings.Contains(execer.query, "UPDATE writer_runs") ||
		!strings.Contains(execer.query, "UPDATE workflow_runs") ||
		!strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected all cancellation RLS writes in tenant-scoped query, got %s", execer.query)
	}
}

func TestSQLWriterAdmissionStorePersistsWorkflowAndWriterRowsWithoutCredentialRefs(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLWriterAdmissionStore(SQLWriterAdmissionStoreConfig{Execer: execer})

	_, _, err := store.AdmitWriterRun(context.Background(), WriterAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       WriterWorkflowType,
		TemporalWorkflowID: "writer_run_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-1",
		Mode:               "draft",
		Status:             "queued",
		ModuleKey:          "writer_composer",
		Instruction:        "写一段正文",
		Options: map[string]any{
			"module_key": "writer_composer",
			"llm_resolution": map[string]any{
				"channel_id":     "chan-1",
				"credential_ref": "llm_credential:secret",
			},
			"prompt":          "private prompt",
			"body_text":       "private body",
			"draft":           "private draft",
			"source_material": "private source",
			"turn_summaries": []any{
				map[string]any{
					"summary":        "public summary",
					"candidate_body": "private candidate",
				},
			},
		},
	})

	if err != nil {
		t.Fatalf("admit writer run: %v", err)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") || !strings.Contains(execer.query, "INSERT INTO writer_runs") {
		t.Fatalf("expected workflow_runs and writer_runs inserts, got %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{
		"credential_ref",
		"llm_credential:secret",
		"private prompt",
		"private body",
		"private draft",
		"private source",
		"candidate_body",
		"private candidate",
	} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("admission SQL args leaked high-risk option %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, `"module_key":"writer_composer"`) {
		t.Fatalf("expected sanitized options JSON in args, got %s", joinedArgs)
	}
	if !strings.Contains(joinedArgs, "public summary") {
		t.Fatalf("expected public option metadata to remain in args, got %s", joinedArgs)
	}
}

func TestSQLWriterAdmissionStoreUsesTenantContextForAdmissionWrites(t *testing.T) {
	execer := &recordingTenantWriterAdmissionExecer{}
	store := NewSQLWriterAdmissionStore(SQLWriterAdmissionStoreConfig{Execer: execer})

	_, _, err := store.AdmitWriterRun(context.Background(), WriterAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       WriterWorkflowType,
		TemporalWorkflowID: "writer_run_33333333-3333-4333-8333-333333333333",
		Mode:               "draft",
		Status:             "queued",
		ModuleKey:          "writer_composer",
		Instruction:        "写一段正文",
		Options:            map[string]any{"module_key": "writer_composer"},
	})

	if err != nil {
		t.Fatalf("admit writer run: %v", err)
	}
	if execer.plainCalled {
		t.Fatal("admission writes should use tenant-aware executor when available")
	}
	if execer.tenantID != "11111111-1111-4111-8111-111111111111" || execer.projectID != "22222222-2222-4222-8222-222222222222" {
		t.Fatalf("tenant context was not passed before admission writes: %#v", execer)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") ||
		!strings.Contains(execer.query, "INSERT INTO writer_runs") ||
		!strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected all admission RLS writes in tenant-scoped query, got %s", execer.query)
	}
}

func TestSQLDraftAdoptionStoreAdoptsTenantScopedCandidateIntoManuscriptMetadataOnly(t *testing.T) {
	queryer := &recordingDraftAdoptionQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"33333333-3333-4333-8333-333333333333",
				"55555555-5555-4555-8555-555555555555",
				"22222222-2222-4222-8222-222222222222",
				"adopted",
				"66666666-6666-4666-8666-666666666666",
				"77777777-7777-4777-8777-777777777777",
				8,
			}},
		},
	}
	store := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{Queryer: queryer})

	result, err := store.AdoptDraft(context.Background(), DraftAdoptionInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-adopt",
		BlockOrder:  8,
	})

	if err != nil {
		t.Fatalf("adopt draft: %v", err)
	}
	if result.DraftID != "33333333-3333-4333-8333-333333333333" ||
		result.BlockID != "55555555-5555-4555-8555-555555555555" ||
		result.ProjectID != "22222222-2222-4222-8222-222222222222" ||
		result.Status != "adopted" ||
		result.BlockOrder != 8 {
		t.Fatalf("unexpected adoption result: %#v", result)
	}
	if !strings.Contains(queryer.query, "FROM writer_drafts") ||
		!strings.Contains(queryer.query, "status = 'candidate'") ||
		!strings.Contains(queryer.query, "INSERT INTO manuscript_blocks") ||
		!strings.Contains(queryer.query, "source_draft_id") ||
		!strings.Contains(queryer.query, "source_writer_run_id") ||
		!strings.Contains(queryer.query, "scene_id") ||
		!strings.Contains(queryer.query, "INSERT INTO manuscript_block_versions") ||
		!strings.Contains(queryer.query, "'adopt'") ||
		!strings.Contains(queryer.query, "UPDATE writer_drafts") ||
		!strings.Contains(queryer.query, "adopted_block_id") ||
		!strings.Contains(queryer.query, "COALESCE(MAX(block_order), 0) + 1") ||
		!strings.Contains(queryer.query, "FOR UPDATE") ||
		!strings.Contains(queryer.query, "INSERT INTO audit_logs") ||
		!strings.Contains(queryer.query, "writer.draft_adopted") ||
		!strings.Contains(queryer.query, "existing_adoption") {
		t.Fatalf("adoption SQL did not express candidate-to-manuscript transition: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{
		"11111111-1111-4111-8111-111111111111",
		"33333333-3333-4333-8333-333333333333",
		"44444444-4444-4444-8444-444444444444",
		"req-adopt",
		8,
		"",
	}) {
		t.Fatalf("unexpected adoption args: %#v", queryer.args)
	}
	resultJSON, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal result: %v", err)
	}
	for _, forbidden := range []string{"content_text", "body", "private draft", "manuscript"} {
		if strings.Contains(string(resultJSON), forbidden) {
			t.Fatalf("adoption result leaked forbidden field %q: %s", forbidden, resultJSON)
		}
	}
}

func TestSQLDraftAdoptionStoreReturnsExistingAdoptionWithoutCreatingAnotherBlock(t *testing.T) {
	queryer := &recordingDraftAdoptionQueryer{rows: &fakeWriterEventRows{values: [][]any{{
		"33333333-3333-4333-8333-333333333333",
		"55555555-5555-4555-8555-555555555555",
		"22222222-2222-4222-8222-222222222222",
		"adopted",
		nil,
		nil,
		4,
	}}}}
	store := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{Queryer: queryer})

	result, err := store.AdoptDraft(context.Background(), DraftAdoptionInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "retry-request",
	})
	if err != nil {
		t.Fatalf("retry explicit adoption: %v", err)
	}
	if result.Status != "adopted" || result.BlockID != "55555555-5555-4555-8555-555555555555" || result.BlockOrder != 4 {
		t.Fatalf("adoption retry did not return existing manuscript block: %#v", result)
	}
	if !strings.Contains(queryer.query, "status IN ('candidate', 'adopted')") ||
		!strings.Contains(queryer.query, "existing.block_id = draft_scope.adopted_block_id") {
		t.Fatalf("adoption retry SQL is not idempotent: %s", queryer.query)
	}
}

func TestSQLDraftAdoptionStoreClosesRowsBeforeOutboxHook(t *testing.T) {
	rows := &fakeWriterEventRows{values: [][]any{{
		"33333333-3333-4333-8333-333333333333",
		"55555555-5555-4555-8555-555555555555",
		"22222222-2222-4222-8222-222222222222",
		"adopted",
		nil,
		nil,
		1,
	}}}
	hook := &recordingDraftAdoptionOutboxHook{}
	store := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{
		Queryer:    &recordingDraftAdoptionQueryer{rows: rows},
		OutboxHook: hook,
	})

	if _, err := store.AdoptDraft(context.Background(), DraftAdoptionInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
	}); err != nil {
		t.Fatalf("adopt draft: %v", err)
	}
	if !hook.called {
		t.Fatal("expected outbox hook to run")
	}
	if !hook.rowsClosedAtCall {
		t.Fatal("outbox hook must run after adoption rows are closed")
	}
	if !rows.committed {
		t.Fatal("expected adoption transaction to commit")
	}
}

type recordingDraftAdoptionOutboxHook struct {
	called           bool
	rowsClosedAtCall bool
}

func (h *recordingDraftAdoptionOutboxHook) EnqueueAfterAdoptionInTx(_ context.Context, rows DraftAdoptionSQLRows, _ DraftAdoptionInput, _ DraftAdoptionResult) error {
	h.called = true
	if fake, ok := rows.(*fakeWriterEventRows); ok {
		h.rowsClosedAtCall = fake.closed
	}
	return nil
}

func TestSQLDraftAdoptionStoreFailsClosedForMissingCandidateDraft(t *testing.T) {
	queryer := &recordingDraftAdoptionQueryer{rows: &fakeWriterEventRows{}}
	store := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{Queryer: queryer})

	_, err := store.AdoptDraft(context.Background(), DraftAdoptionInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected missing candidate draft to fail closed, got %s (%v)", code, err)
	}
	if !strings.Contains(queryer.query, "status = 'candidate'") {
		t.Fatalf("expected candidate-only adoption query, got %s", queryer.query)
	}
}

func TestSQLDraftAdoptionStoreUsesTenantContextForAdoptionWrites(t *testing.T) {
	queryer := &recordingDraftAdoptionQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"33333333-3333-4333-8333-333333333333",
				"55555555-5555-4555-8555-555555555555",
				"22222222-2222-4222-8222-222222222222",
				"adopted",
				nil,
				nil,
				1,
			}},
		},
	}
	store := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{Queryer: queryer})

	_, err := store.AdoptDraft(context.Background(), DraftAdoptionInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
	})

	if err != nil {
		t.Fatalf("adopt draft: %v", err)
	}
	if queryer.tenantID != "11111111-1111-4111-8111-111111111111" || queryer.query == "" {
		t.Fatalf("adoption query did not use tenant context: %#v", queryer)
	}
}

func TestSQLDraftAdoptionStoreRollsBackWhenReturningRowCannotScan(t *testing.T) {
	rows := &fakeWriterEventRows{
		values:  [][]any{{"bad-row"}},
		scanErr: errors.New("scan failed after write CTE"),
	}
	queryer := &recordingDraftAdoptionQueryer{rows: rows}
	store := NewSQLDraftAdoptionStore(SQLDraftAdoptionStoreConfig{Queryer: queryer})

	_, err := store.AdoptDraft(context.Background(), DraftAdoptionInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
	})

	if code := ErrorCode(err); code != "DRAFT_ADOPTION_WRITE_FAILED" {
		t.Fatalf("expected write failure, got %s (%v)", code, err)
	}
	if rows.committed {
		t.Fatal("draft adoption should not commit after scan failure")
	}
	if !rows.rolledBack {
		t.Fatal("draft adoption should roll back after scan failure")
	}
}

func TestSQLDraftReviewStoreAdmitsReviewerWorkflowWithoutDraftTextOrCredentialRefs(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLDraftReviewStore(SQLDraftReviewStoreConfig{Execer: execer})

	result, err := store.StartDraftReview(context.Background(), StartDraftReviewInput{
		TenantID:    "11111111-1111-4111-8111-111111111111",
		ProjectID:   "22222222-2222-4222-8222-222222222222",
		DraftID:     "33333333-3333-4333-8333-333333333333",
		ActorUserID: "44444444-4444-4444-8444-444444444444",
		RequestID:   "req-review",
		Note:        "public note",
		Options: map[string]any{
			"severity_floor": "medium",
			"prompt":         "private prompt",
			"draft":          "private draft",
			"manuscript":     "private manuscript",
			"llm_resolution": map[string]any{
				"credential_ref": "llm_credential:secret",
			},
		},
	})

	if err != nil {
		t.Fatalf("start draft review: %v", err)
	}
	requireUUIDRunID(t, result.RunID)
	requireUUIDRunID(t, result.ReviewID)
	if result.DraftID != "33333333-3333-4333-8333-333333333333" ||
		result.ProjectID != "22222222-2222-4222-8222-222222222222" ||
		result.WorkflowType != WriterReviewWorkflowType ||
		result.Status != "queued" {
		t.Fatalf("unexpected review admission result: %#v", result)
	}
	if !strings.Contains(execer.query, "FROM writer_drafts") ||
		!strings.Contains(execer.query, "INSERT INTO draft_reviews") ||
		!strings.Contains(execer.query, "INSERT INTO workflow_runs") ||
		!strings.Contains(execer.query, "INSERT INTO workflow_events") ||
		!strings.Contains(execer.query, "project_id::text = $11") ||
		strings.Contains(execer.query, "content_text") {
		t.Fatalf("review admission SQL did not use metadata-only draft workflow admission: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"credential_ref", "llm_credential:secret", "private prompt", "private draft", "private manuscript", "public note", "openai-compatible", "llm.example.test", "channel-secret", "model-secret", "temperature"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("review admission SQL args leaked high-risk value %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, "severity_floor") {
		t.Fatalf("expected public review metadata to remain, got %s", joinedArgs)
	}
}

func TestSQLDraftReviewStoreRequiresProjectScope(t *testing.T) {
	store := NewSQLDraftReviewStore(SQLDraftReviewStoreConfig{Execer: &recordingWriterAdmissionExecer{}})

	_, err := store.StartDraftReview(context.Background(), StartDraftReviewInput{
		TenantID: "11111111-1111-4111-8111-111111111111",
		DraftID:  "33333333-3333-4333-8333-333333333333",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected project scope validation failure, got %s (%v)", code, err)
	}
}

func TestSQLDraftReviewStoreListsReviewMetadataAndIssuesWithoutBodies(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"55555555-5555-4555-8555-555555555555",
				"66666666-6666-4666-8666-666666666666",
				"33333333-3333-4333-8333-333333333333",
				"22222222-2222-4222-8222-222222222222",
				"completed",
				"99999999-9999-4999-8999-999999999999",
				"medium",
				"pov",
				"public summary",
				"public suggestion",
				"open",
				"2026-07-07T01:02:30Z",
				"2026-07-07T01:02:30Z",
				"2026-07-07T01:02:03Z",
				"2026-07-07T01:03:03Z",
			}},
		},
	}
	store := NewSQLDraftReviewStore(SQLDraftReviewStoreConfig{Queryer: queryer})

	result, err := store.ListDraftReviews(context.Background(), ListDraftReviewsInput{
		TenantID: "11111111-1111-4111-8111-111111111111",
		DraftID:  "33333333-3333-4333-8333-333333333333",
	})

	if err != nil {
		t.Fatalf("list draft reviews: %v", err)
	}
	if len(result.Reviews) != 1 || len(result.Reviews[0].Issues) != 1 {
		t.Fatalf("unexpected review list: %#v", result)
	}
	issue := result.Reviews[0].Issues[0]
	if issue.Summary != "public summary" || issue.Suggestion != "public suggestion" || issue.Category != "pov" {
		t.Fatalf("unexpected issue metadata: %#v", issue)
	}
	if !strings.Contains(queryer.query, "FROM draft_reviews") ||
		!strings.Contains(queryer.query, "LEFT JOIN draft_review_issues") ||
		!strings.Contains(queryer.query, "issues.project_id = reviews.project_id") ||
		!strings.Contains(queryer.query, "issues.draft_id = reviews.draft_id") ||
		strings.Contains(queryer.query, "content_text") ||
		strings.Contains(queryer.query, "prompt") {
		t.Fatalf("review read SQL should be metadata-only, got %s", queryer.query)
	}
	resultJSON, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal result: %v", err)
	}
	for _, forbidden := range []string{"content_text", "private draft", "prompt", "credential_ref", "api_key", "manuscript"} {
		if strings.Contains(string(resultJSON), forbidden) {
			t.Fatalf("review read result leaked forbidden field %q: %s", forbidden, resultJSON)
		}
	}
}

func requireUUIDRunID(t *testing.T, runID string) {
	t.Helper()
	if !uuidPattern.MatchString(runID) {
		t.Fatalf("expected UUID run id, got %q", runID)
	}
}

var uuidPattern = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

type recordingWriterEventQueryer struct {
	query string
	args  []any
	rows  *fakeWriterEventRows
	err   error
}

func (q *recordingWriterEventQueryer) QueryContext(ctx context.Context, query string, args ...any) (WriterEventSQLRows, error) {
	q.query = query
	q.args = append([]any(nil), args...)
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return nil, errors.New("no rows configured")
	}
	return q.rows, nil
}

type recordingTenantWriterEventQueryer struct {
	tenantID    string
	query       string
	args        []any
	rows        *fakeWriterEventRows
	err         error
	plainCalled bool
}

func (q *recordingTenantWriterEventQueryer) QueryContext(context.Context, string, ...any) (WriterEventSQLRows, error) {
	q.plainCalled = true
	return nil, errors.New("plain QueryContext should not be used for tenant-scoped writer queries")
}

func (q *recordingTenantWriterEventQueryer) QueryTenantContext(_ context.Context, tenantID string, query string, args ...any) (WriterEventSQLRows, error) {
	q.tenantID = tenantID
	q.query = query
	q.args = append([]any(nil), args...)
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return nil, errors.New("no rows configured")
	}
	return q.rows, nil
}

type recordingDraftAdoptionQueryer struct {
	tenantID string
	query    string
	args     []any
	rows     *fakeWriterEventRows
	err      error
}

func (q *recordingDraftAdoptionQueryer) QueryDraftAdoptionContext(_ context.Context, tenantID string, query string, args ...any) (DraftAdoptionSQLRows, error) {
	q.tenantID = tenantID
	q.query = query
	q.args = append([]any(nil), args...)
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return nil, errors.New("no rows configured")
	}
	return q.rows, nil
}

type fakeWriterEventRows struct {
	values     [][]any
	index      int
	err        error
	scanErr    error
	closeErr   error
	closed     bool
	committed  bool
	rolledBack bool
}

func (r *fakeWriterEventRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeWriterEventRows) Scan(dest ...any) error {
	if r.scanErr != nil {
		return r.scanErr
	}
	if r.index >= len(r.values) {
		return errors.New("scan past end")
	}
	row := r.values[r.index]
	r.index++
	for index, value := range row {
		switch target := dest[index].(type) {
		case *bool:
			*target = value.(bool)
		case *sql.NullString:
			if value == nil {
				*target = sql.NullString{}
			} else {
				*target = sql.NullString{String: value.(string), Valid: true}
			}
		case *sql.NullInt64:
			if value == nil {
				*target = sql.NullInt64{}
			} else {
				*target = sql.NullInt64{Int64: int64(value.(int)), Valid: true}
			}
		case *string:
			*target = value.(string)
		case *int:
			*target = value.(int)
		default:
			return errors.New("unsupported scan target")
		}
	}
	return nil
}

func (r *fakeWriterEventRows) Close() error {
	r.closed = true
	return r.closeErr
}

func (r *fakeWriterEventRows) Err() error {
	return r.err
}

func (r *fakeWriterEventRows) Commit() error {
	r.committed = true
	return nil
}

func (r *fakeWriterEventRows) Rollback() error {
	r.rolledBack = true
	return nil
}

func (r *fakeWriterEventRows) ExecContext(context.Context, string, ...any) (sql.Result, error) {
	return nil, nil
}

func (r *fakeWriterEventRows) QueryRowContext(context.Context, string, ...any) *sql.Row {
	return nil
}

type recordingWriterAdmissionStore struct {
	input                        WriterAdmissionInput
	err                          error
	temporalStarted              func() bool
	temporalWasStartedWhenCalled bool
	replay                       bool
	replayRun                    WriterRun
	compensateCalled             bool
	compensateInput              WriterCompensationInput
	compensateErr                error
}

func (s *recordingWriterAdmissionStore) AdmitWriterRun(_ context.Context, input WriterAdmissionInput) (WriterRun, bool, error) {
	s.input = input
	if s.temporalStarted != nil {
		s.temporalWasStartedWhenCalled = s.temporalStarted()
	}
	if s.err != nil {
		return WriterRun{}, false, s.err
	}
	if s.replay {
		return s.replayRun, true, nil
	}
	return WriterRun{
		RunID:       input.RunID,
		TraceID:     input.TraceID,
		TenantID:    input.TenantID,
		ProjectID:   input.ProjectID,
		Mode:        input.Mode,
		Instruction: input.Instruction,
		Status:      "queued",
	}, false, nil
}

func (s *recordingWriterAdmissionStore) CompensateWriterRunStart(_ context.Context, input WriterCompensationInput) error {
	s.compensateCalled = true
	s.compensateInput = input
	return s.compensateErr
}

type recordingWriterCancellationStore struct {
	input                          WriterCancellationInput
	err                            error
	called                         bool
	temporalWaited                 func() bool
	calledBeforeTemporalCompletion bool
}

func (s *recordingWriterCancellationStore) CancelWriterRun(_ context.Context, input WriterCancellationInput) error {
	s.input = input
	s.called = true
	if s.temporalWaited != nil && !s.temporalWaited() {
		s.calledBeforeTemporalCompletion = true
	}
	return s.err
}

type recordingWriterAdmissionExecer struct {
	query  string
	args   []any
	err    error
	result sql.Result
}

func (e *recordingWriterAdmissionExecer) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	e.query = query
	e.args = append([]any(nil), args...)
	if e.result != nil {
		return e.result, e.err
	}
	return fakeSQLResult{}, e.err
}

type recordingTenantWriterAdmissionExecer struct {
	tenantID    string
	projectID   string
	query       string
	args        []any
	err         error
	result      sql.Result
	plainCalled bool
}

func (e *recordingTenantWriterAdmissionExecer) ExecContext(context.Context, string, ...any) (sql.Result, error) {
	e.plainCalled = true
	return nil, errors.New("plain ExecContext should not be used for tenant-scoped admission writes")
}

func (e *recordingTenantWriterAdmissionExecer) ExecTenantContext(_ context.Context, tenantID string, projectID string, query string, args ...any) (sql.Result, error) {
	e.tenantID = tenantID
	e.projectID = projectID
	e.query = query
	e.args = append([]any(nil), args...)
	if e.result != nil {
		return e.result, e.err
	}
	return fakeSQLResult{}, e.err
}

type fakeSQLResult struct {
	rowsAffected    int64
	rowsAffectedSet bool
	rowsAffectedErr error
}

func (fakeSQLResult) LastInsertId() (int64, error) { return 0, nil }
func (r fakeSQLResult) RowsAffected() (int64, error) {
	if r.rowsAffectedErr != nil {
		return 0, r.rowsAffectedErr
	}
	if r.rowsAffectedSet {
		return r.rowsAffected, nil
	}
	return 1, nil
}

func argsAsStrings(args []any) []string {
	values := make([]string, 0, len(args))
	for _, arg := range args {
		values = append(values, strings.TrimSpace(reflect.ValueOf(arg).String()))
	}
	return values
}

type recordingWriterTemporalClient struct {
	started          bool
	cancelled        bool
	options          client.StartWorkflowOptions
	workflow         any
	args             []any
	cancelWorkflowID string
	cancelRunID      string
	err              error
	cancelErr        error
	completionErr    error
	waitStarted      chan struct{}
	waitRelease      <-chan struct{}
	waited           bool
}

func (c *recordingWriterTemporalClient) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.started = true
	c.options = options
	c.workflow = workflow
	c.args = append([]any(nil), args...)
	return nil, c.err
}

func (c *recordingWriterTemporalClient) CancelWorkflow(_ context.Context, workflowID string, runID string) error {
	c.cancelled = true
	c.cancelWorkflowID = workflowID
	c.cancelRunID = runID
	return c.cancelErr
}

func (c *recordingWriterTemporalClient) GetWorkflow(_ context.Context, workflowID string, runID string) client.WorkflowRun {
	return &recordingWriterCancellationRun{client: c, workflowID: workflowID, runID: runID}
}

type recordingWriterCancellationRun struct {
	client     *recordingWriterTemporalClient
	workflowID string
	runID      string
}

func (r *recordingWriterCancellationRun) GetID() string    { return r.workflowID }
func (r *recordingWriterCancellationRun) GetRunID() string { return r.runID }
func (r *recordingWriterCancellationRun) Get(ctx context.Context, _ any) error {
	r.client.waited = true
	if r.client.waitStarted != nil {
		select {
		case r.client.waitStarted <- struct{}{}:
		default:
		}
	}
	if r.client.waitRelease != nil {
		select {
		case <-r.client.waitRelease:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	return r.client.completionErr
}
func (r *recordingWriterCancellationRun) GetWithOptions(ctx context.Context, value any, _ client.WorkflowRunGetOptions) error {
	return r.Get(ctx, value)
}

func (c *recordingWriterTemporalClient) Close() {}
