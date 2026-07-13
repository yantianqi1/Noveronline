package characterconsole

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestDisabledStoreFailsClosedForInteractionMetadata(t *testing.T) {
	store := NewDisabledStore()

	_, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Mode:      "first_person",
	})

	if code := ErrorCode(err); code != "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected fail-closed character interaction backend error, got %s (%v)", code, err)
	}
}

func TestSQLStoreRejectsInvalidInteractionModeBeforeSQL(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{}
	store := NewSQLStore(SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
		NewID:   fixedCharacterConsoleIDs("interaction-1"),
	})

	_, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Mode:      "auto_agent_chat",
		Title:     "Invalid mode",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected invalid mode validation failure, got %s (%v)", code, err)
	}
	if queryer.query != "" {
		t.Fatalf("invalid interaction mode should fail before SQL, got query %s", queryer.query)
	}
}

func TestSQLStoreRejectsInvalidInteractionAnchorTypeBeforeSQL(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{}
	store := NewSQLStore(SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
		NewID:   fixedCharacterConsoleIDs("interaction-1"),
	})

	_, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
		TenantID:   "tenant-123",
		ProjectID:  "project-123",
		Mode:       "dialogue",
		AnchorType: "auto_runtime_chat",
		Title:      "Invalid anchor",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected invalid anchor type validation failure, got %s (%v)", code, err)
	}
	if queryer.query != "" {
		t.Fatalf("invalid anchor type should fail before SQL, got query %s", queryer.query)
	}
}

func TestSQLStoreRejectsInvalidInteractionStatusFilterBeforeSQL(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{}
	store := NewSQLStore(SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	})

	_, err := store.ListInteractions(context.Background(), ListInteractionsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Status:    "runtime_completed",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected invalid status validation failure, got %s (%v)", code, err)
	}
	if queryer.query != "" {
		t.Fatalf("invalid status filter should fail before SQL, got query %s", queryer.query)
	}
}

func TestSQLStoreRejectsInvalidInteractionStatusMutationBeforeSQL(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{}
	store := NewSQLStore(SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
	})

	_, err := store.UpdateInteractionStatus(context.Background(), UpdateInteractionStatusInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
		Status:        "runtime_completed",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected invalid status mutation validation failure, got %s (%v)", code, err)
	}
	if queryer.query != "" {
		t.Fatalf("invalid status mutation should fail before SQL, got query %s", queryer.query)
	}
}

func TestSQLStoreRejectsInvalidTurnEnumsBeforeSQL(t *testing.T) {
	for _, testCase := range []struct {
		name      string
		actorType string
		turnKind  string
	}{
		{name: "actor type", actorType: "llm_shadow", turnKind: "action"},
		{name: "turn kind", actorType: "user", turnKind: "agent_reply"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			queryer := &recordingCharacterConsoleQueryer{}
			store := NewSQLStore(SQLStoreConfig{
				Queryer: queryer,
				Execer:  queryer,
				NewID:   fixedCharacterConsoleIDs("turn-1"),
			})

			_, err := store.AppendTurn(context.Background(), AppendTurnInput{
				TenantID:      "tenant-123",
				InteractionID: "interaction-1",
				ActorType:     testCase.actorType,
				TurnKind:      testCase.turnKind,
				Summary:       "Invalid turn metadata",
			})

			if code := ErrorCode(err); code != "VALIDATION_FAILED" {
				t.Fatalf("expected invalid turn enum validation failure, got %s (%v)", code, err)
			}
			if queryer.query != "" {
				t.Fatalf("invalid turn enum should fail before SQL, got query %s", queryer.query)
			}
		})
	}
}

func TestSQLStoreCreatesInteractionSessionWithPublicMetadataOnly(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{
		rows: &fakeCharacterConsoleRows{values: [][]any{{
			"interaction-1",
			"project-123",
			"worldline-session-1",
			"worldline_event",
			"event-1",
			"agent-1",
			"first_person",
			"active",
			"雨夜谈判前",
			"公开 anchor 摘要",
			"{}",
			"user-123",
			"2026-07-06T00:00:00Z",
			"2026-07-06T00:00:00Z",
		}}},
	}
	store := NewSQLStore(SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
		NewID:   fixedCharacterConsoleIDs("interaction-1"),
	})

	record, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
		TenantID:           "tenant-123",
		ProjectID:          "project-123",
		ActorUserID:        "user-123",
		RequestID:          "req-123",
		WorldlineSessionID: "worldline-session-1",
		AnchorType:         "worldline_event",
		AnchorID:           "event-1",
		POVAgentID:         "agent-1",
		Mode:               "first_person",
		Title:              "雨夜谈判前",
		Summary:            "公开 anchor 摘要",
		Metadata: map[string]any{
			"tone":           "tense",
			"prompt":         "must be stripped",
			"credential_ref": "must be stripped",
		},
	})

	if err != nil {
		t.Fatalf("create interaction: %v", err)
	}
	if record.InteractionID != "interaction-1" ||
		record.ProjectID != "project-123" ||
		record.WorldlineSessionID != "worldline-session-1" ||
		record.AnchorType != "worldline_event" ||
		record.POVAgentID != "agent-1" ||
		record.Mode != "first_person" ||
		record.Status != "active" {
		t.Fatalf("unexpected interaction metadata: %#v", record)
	}
	query := strings.ToLower(queryer.query)
	for _, required := range []string{
		"insert into character_interaction_sessions",
		"worldline_sessions",
		"tenant_id = $1::uuid",
		"project_id = $2::uuid",
		"session_id = nullif($4::text, '')::uuid",
	} {
		if !strings.Contains(query, required) {
			t.Fatalf("expected query to include %q, got %s", required, queryer.query)
		}
	}
	assertNoSensitiveCharacterConsoleSQL(t, queryer.query, queryer.args)
}

func TestSQLStoreUpdatesInteractionStatusAsMetadataOnly(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{
		rows: &fakeCharacterConsoleRows{values: [][]any{{
			"interaction-1",
			"project-123",
			"worldline-session-1",
			"worldline_event",
			"event-1",
			"agent-1",
			"first_person",
			"saved",
			"雨夜谈判前",
			"公开 anchor 摘要",
			`{"source":"worldline","prompt":"must not leak","safe":"kept"}`,
			"user-123",
			"2026-07-06T00:00:00Z",
			"2026-07-06T00:03:00Z",
		}}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, Execer: queryer})

	record, err := store.UpdateInteractionStatus(context.Background(), UpdateInteractionStatusInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
		ActorUserID:   "user-123",
		RequestID:     "req-save-123",
		Status:        "saved",
	})

	if err != nil {
		t.Fatalf("update interaction status: %v", err)
	}
	if record.InteractionID != "interaction-1" || record.Status != "saved" || record.Metadata["safe"] != "kept" {
		t.Fatalf("unexpected updated interaction metadata: %#v", record)
	}
	if containsSensitiveCharacterConsoleValue(record.Metadata) {
		t.Fatalf("updated interaction leaked sensitive metadata: %#v", record.Metadata)
	}
	query := strings.ToLower(queryer.query)
	for _, required := range []string{"update character_interaction_sessions", "where tenant_id", "interaction_id", "returning"} {
		if !strings.Contains(query, required) {
			t.Fatalf("expected update query to include %q, got %s", required, queryer.query)
		}
	}
	for _, forbidden := range []string{"character_interaction_turns", "worldline_events", "writer_drafts", "manuscript"} {
		if strings.Contains(query, forbidden) {
			t.Fatalf("status update must not touch runtime/draft tables %q: %s", forbidden, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "interaction-1", "saved"}) {
		t.Fatalf("unexpected update args: %#v", queryer.args)
	}
	assertNoSensitiveCharacterConsoleSQL(t, queryer.query, queryer.args)
}

func TestSQLStoreListsAndGetsTenantScopedInteractionsWithoutPrivateFields(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{
		rows: &fakeCharacterConsoleRows{values: [][]any{{
			"interaction-1",
			"project-123",
			"worldline-session-1",
			"scene",
			"scene-1",
			"agent-1",
			"dialogue",
			"active",
			"对话",
			"公开摘要",
			`{"source":"worldline"}`,
			"user-123",
			"2026-07-06T00:00:00Z",
			"2026-07-06T00:00:00Z",
		}}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, Execer: queryer, Limit: 25})

	items, err := store.ListInteractions(context.Background(), ListInteractionsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Status:    "active",
	})
	if err != nil {
		t.Fatalf("list interactions: %v", err)
	}
	if len(items) != 1 || items[0].InteractionID != "interaction-1" || items[0].Metadata["source"] != "worldline" {
		t.Fatalf("unexpected list result: %#v", items)
	}
	if !strings.Contains(strings.ToLower(queryer.query), "from character_interaction_sessions") {
		t.Fatalf("expected character_interaction_sessions list query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "active", 25}) {
		t.Fatalf("unexpected list args: %#v", queryer.args)
	}
	assertNoSensitiveCharacterConsoleSQL(t, queryer.query, queryer.args)

	queryer.rows = &fakeCharacterConsoleRows{values: [][]any{{
		"interaction-1",
		"project-123",
		"worldline-session-1",
		"scene",
		"scene-1",
		"agent-1",
		"dialogue",
		"active",
		"对话",
		"公开摘要",
		`{"source":"worldline"}`,
		"user-123",
		"2026-07-06T00:00:00Z",
		"2026-07-06T00:00:00Z",
	}}}
	record, err := store.GetInteraction(context.Background(), GetInteractionInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
	})
	if err != nil {
		t.Fatalf("get interaction: %v", err)
	}
	if record.InteractionID != "interaction-1" || record.Title != "对话" {
		t.Fatalf("unexpected detail result: %#v", record)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "interaction-1"}) {
		t.Fatalf("unexpected get args: %#v", queryer.args)
	}
	assertNoSensitiveCharacterConsoleSQL(t, queryer.query, queryer.args)
}

func TestSQLStoreUsesTenantContextQueryerForReadAndWritePaths(t *testing.T) {
	for _, testCase := range []struct {
		name   string
		run    func(*SQLStore) error
		tenant string
	}{
		{
			name: "create interaction",
			run: func(store *SQLStore) error {
				_, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
					TenantID:  "tenant-create",
					ProjectID: "project-123",
					Mode:      "dialogue",
				})
				return err
			},
			tenant: "tenant-create",
		},
		{
			name: "list interactions",
			run: func(store *SQLStore) error {
				_, err := store.ListInteractions(context.Background(), ListInteractionsInput{
					TenantID:  "tenant-list",
					ProjectID: "project-123",
				})
				return err
			},
			tenant: "tenant-list",
		},
		{
			name: "get interaction",
			run: func(store *SQLStore) error {
				_, err := store.GetInteraction(context.Background(), GetInteractionInput{
					TenantID:      "tenant-get",
					InteractionID: "interaction-1",
				})
				return err
			},
			tenant: "tenant-get",
		},
		{
			name: "append turn",
			run: func(store *SQLStore) error {
				_, err := store.AppendTurn(context.Background(), AppendTurnInput{
					TenantID:      "tenant-append",
					InteractionID: "interaction-1",
					ActorType:     "user",
					TurnKind:      "action",
				})
				return err
			},
			tenant: "tenant-append",
		},
		{
			name: "list turns",
			run: func(store *SQLStore) error {
				_, err := store.ListTurns(context.Background(), ListTurnsInput{
					TenantID:      "tenant-turns",
					InteractionID: "interaction-1",
				})
				return err
			},
			tenant: "tenant-turns",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			queryer := &recordingTenantCharacterConsoleQueryer{
				recordingCharacterConsoleQueryer: recordingCharacterConsoleQueryer{
					rows: &fakeCharacterConsoleRows{values: characterConsoleRowsErrValues(testCase.name)},
				},
			}
			store := NewSQLStore(SQLStoreConfig{
				Queryer: queryer,
				Execer:  queryer,
				NewID:   fixedCharacterConsoleIDs("interaction-1", "turn-1"),
			})

			if err := testCase.run(store); err != nil {
				t.Fatalf("run store path: %v", err)
			}
			if !queryer.usedTenantContext {
				t.Fatalf("expected store path to use tenant-context queryer")
			}
			if queryer.tenantID != testCase.tenant {
				t.Fatalf("expected tenant %q, got %q", testCase.tenant, queryer.tenantID)
			}
		})
	}
}

func TestSQLStoreReturnsRowsCloseErrorsAsStableQueryFailures(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{
		rows: &fakeCharacterConsoleRows{
			values: [][]any{{
				"interaction-1",
				"project-123",
				"worldline-session-1",
				"scene",
				"scene-1",
				"agent-1",
				"dialogue",
				"active",
				"对话",
				"公开摘要",
				"{}",
				"user-123",
				"2026-07-06T00:00:00Z",
				"2026-07-06T00:00:00Z",
			}},
			closeErr: errors.New("commit failed prompt=hidden api_key=sk-hidden credential_ref=secret"),
		},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, Execer: queryer})

	_, err := store.GetInteraction(context.Background(), GetInteractionInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
	})

	assertStableCharacterConsoleQueryFailure(t, err)
}

func TestSQLStoreSanitizesReadSideJSONMetadata(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{
		rows: &fakeCharacterConsoleRows{values: [][]any{{
			"interaction-1",
			"project-123",
			"worldline-session-1",
			"scene",
			"scene-1",
			"agent-1",
			"dialogue",
			"active",
			"对话",
			"公开摘要",
			`{"source":"worldline","prompt":"must not leak","source_text":"public-looking source body","nested":{"api_key":"secret","candidate_body":"public-looking candidate body","safe":"kept"},"items":[{"credential_ref":"hidden","event_body":"public-looking event body","label":"visible"}]}`,
			"user-123",
			"2026-07-06T00:00:00Z",
			"2026-07-06T00:00:00Z",
		}}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, Execer: queryer})

	interaction, err := store.GetInteraction(context.Background(), GetInteractionInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
	})
	if err != nil {
		t.Fatalf("get interaction: %v", err)
	}
	if containsSensitiveCharacterConsoleValue(interaction.Metadata) {
		t.Fatalf("interaction metadata leaked sensitive fields: %#v", interaction.Metadata)
	}
	if nested, ok := interaction.Metadata["nested"].(map[string]any); !ok || nested["safe"] != "kept" {
		t.Fatalf("expected safe nested interaction metadata to remain: %#v", interaction.Metadata)
	}

	queryer.rows = &fakeCharacterConsoleRows{values: [][]any{{
		"turn-1",
		"interaction-1",
		"project-123",
		1,
		"user",
		"user-123",
		"action",
		"公开行动摘要",
		`{"intent":"threaten","response":"must not leak","nested":{"body":"hidden","source_material":"public-looking source material","safe":"kept"}}`,
		`{"public":true,"draft":"hidden","candidate_event_body":"public-looking candidate event body","items":[{"manuscript":"hidden","event_body":"public-looking event body","label":"visible"}]}`,
		"trace-1",
		"user-123",
		"2026-07-06T00:01:00Z",
	}}}
	turns, err := store.ListTurns(context.Background(), ListTurnsInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
	})
	if err != nil {
		t.Fatalf("list turns: %v", err)
	}
	if len(turns) != 1 {
		t.Fatalf("expected one turn, got %#v", turns)
	}
	if containsSensitiveCharacterConsoleValue(turns[0].Action) || containsSensitiveCharacterConsoleValue(turns[0].WorldStateDelta) {
		t.Fatalf("turn metadata leaked sensitive fields: action=%#v delta=%#v", turns[0].Action, turns[0].WorldStateDelta)
	}
	if nested, ok := turns[0].Action["nested"].(map[string]any); !ok || nested["safe"] != "kept" {
		t.Fatalf("expected safe nested turn action metadata to remain: %#v", turns[0].Action)
	}
}

func TestSQLStoreSanitizesRowsErrMessages(t *testing.T) {
	sensitiveErr := errors.New("rows failed prompt=hidden api_key=sk-hidden credential_ref=secret body=private manuscript=private")
	for _, testCase := range []struct {
		name string
		run  func(*SQLStore) error
	}{
		{
			name: "create interaction",
			run: func(store *SQLStore) error {
				_, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
					Mode:      "dialogue",
				})
				return err
			},
		},
		{
			name: "list interactions",
			run: func(store *SQLStore) error {
				_, err := store.ListInteractions(context.Background(), ListInteractionsInput{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
				})
				return err
			},
		},
		{
			name: "get interaction",
			run: func(store *SQLStore) error {
				_, err := store.GetInteraction(context.Background(), GetInteractionInput{
					TenantID:      "tenant-123",
					InteractionID: "interaction-1",
				})
				return err
			},
		},
		{
			name: "append turn",
			run: func(store *SQLStore) error {
				_, err := store.AppendTurn(context.Background(), AppendTurnInput{
					TenantID:      "tenant-123",
					InteractionID: "interaction-1",
					ActorType:     "user",
					TurnKind:      "dialogue",
				})
				return err
			},
		},
		{
			name: "list turns",
			run: func(store *SQLStore) error {
				_, err := store.ListTurns(context.Background(), ListTurnsInput{
					TenantID:      "tenant-123",
					InteractionID: "interaction-1",
				})
				return err
			},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			queryer := &recordingCharacterConsoleQueryer{
				rows: &fakeCharacterConsoleRows{
					values: characterConsoleRowsErrValues(testCase.name),
					err:    sensitiveErr,
				},
			}
			store := NewSQLStore(SQLStoreConfig{
				Queryer: queryer,
				Execer:  queryer,
				NewID:   fixedCharacterConsoleIDs("interaction-1", "turn-1"),
			})

			err := testCase.run(store)

			assertStableCharacterConsoleQueryFailure(t, err)
		})
	}
}

func TestSQLStoreSanitizesScanErrorMessages(t *testing.T) {
	sensitiveErr := errors.New("scan failed prompt=hidden api_key=sk-hidden credential_ref=secret body=private manuscript=private")
	for _, testCase := range []struct {
		name string
		run  func(*SQLStore) error
	}{
		{
			name: "create interaction",
			run: func(store *SQLStore) error {
				_, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
					Mode:      "dialogue",
				})
				return err
			},
		},
		{
			name: "list interactions",
			run: func(store *SQLStore) error {
				_, err := store.ListInteractions(context.Background(), ListInteractionsInput{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
				})
				return err
			},
		},
		{
			name: "get interaction",
			run: func(store *SQLStore) error {
				_, err := store.GetInteraction(context.Background(), GetInteractionInput{
					TenantID:      "tenant-123",
					InteractionID: "interaction-1",
				})
				return err
			},
		},
		{
			name: "append turn",
			run: func(store *SQLStore) error {
				_, err := store.AppendTurn(context.Background(), AppendTurnInput{
					TenantID:      "tenant-123",
					InteractionID: "interaction-1",
					ActorType:     "user",
					TurnKind:      "dialogue",
				})
				return err
			},
		},
		{
			name: "list turns",
			run: func(store *SQLStore) error {
				_, err := store.ListTurns(context.Background(), ListTurnsInput{
					TenantID:      "tenant-123",
					InteractionID: "interaction-1",
				})
				return err
			},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			queryer := &recordingCharacterConsoleQueryer{
				rows: &fakeCharacterConsoleRows{
					values:  characterConsoleRowsErrValues(testCase.name),
					scanErr: sensitiveErr,
				},
			}
			store := NewSQLStore(SQLStoreConfig{
				Queryer: queryer,
				Execer:  queryer,
				NewID:   fixedCharacterConsoleIDs("interaction-1", "turn-1"),
			})

			err := testCase.run(store)

			assertStableCharacterConsoleQueryFailure(t, err)
		})
	}
}

func TestSQLStoreAbortsTenantContextRowsOnScanFailure(t *testing.T) {
	for _, testCase := range []struct {
		name string
		run  func(*SQLStore) error
	}{
		{
			name: "create interaction",
			run: func(store *SQLStore) error {
				_, err := store.CreateInteraction(context.Background(), CreateInteractionInput{
					TenantID:  "tenant-123",
					ProjectID: "project-123",
					Mode:      "dialogue",
				})
				return err
			},
		},
		{
			name: "append turn",
			run: func(store *SQLStore) error {
				_, err := store.AppendTurn(context.Background(), AppendTurnInput{
					TenantID:      "tenant-123",
					InteractionID: "interaction-1",
					ActorType:     "user",
					TurnKind:      "dialogue",
				})
				return err
			},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			rows := &fakeCharacterConsoleRows{
				values:  characterConsoleRowsErrValues(testCase.name),
				scanErr: errors.New("scan failed prompt=hidden api_key=sk-hidden credential_ref=secret"),
			}
			queryer := &recordingTenantCharacterConsoleQueryer{
				recordingCharacterConsoleQueryer: recordingCharacterConsoleQueryer{rows: rows},
			}
			store := NewSQLStore(SQLStoreConfig{
				Queryer: queryer,
				Execer:  queryer,
				NewID:   fixedCharacterConsoleIDs("interaction-1", "turn-1"),
			})

			err := testCase.run(store)

			assertStableCharacterConsoleQueryFailure(t, err)
			if !rows.aborted {
				t.Fatalf("expected scan failure to abort tenant-scoped rows instead of committing/closing normally")
			}
		})
	}
}

func TestSQLStoreAppendsAndListsTurnsAsMetadataWithoutAutoReply(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{
		rows: &fakeCharacterConsoleRows{values: [][]any{{
			"turn-1",
			"interaction-1",
			"project-123",
			1,
			"user",
			"user-123",
			"action",
			"我把剑放在桌上",
			"{}",
			"{}",
			"trace-1",
			"user-123",
			"2026-07-06T00:01:00Z",
		}}},
	}
	store := NewSQLStore(SQLStoreConfig{
		Queryer: queryer,
		Execer:  queryer,
		NewID:   fixedCharacterConsoleIDs("turn-1"),
	})

	turn, err := store.AppendTurn(context.Background(), AppendTurnInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
		ActorUserID:   "user-123",
		RequestID:     "req-turn-123",
		ActorType:     "user",
		ActorID:       "user-123",
		TurnKind:      "action",
		Summary:       "我把剑放在桌上",
		Action: map[string]any{
			"intent": "threaten",
			"prompt": "must be stripped",
		},
		WorldStateDelta: map[string]any{
			"public":  true,
			"api_key": "must be stripped",
		},
		TraceID: "trace-1",
	})

	if err != nil {
		t.Fatalf("append turn: %v", err)
	}
	if turn.TurnID != "turn-1" || turn.TurnOrder != 1 || turn.ActorType != "user" || turn.Summary == "" {
		t.Fatalf("unexpected turn metadata: %#v", turn)
	}
	query := strings.ToLower(queryer.query)
	for _, required := range []string{
		"insert into character_interaction_turns",
		"character_interaction_sessions",
		"pg_advisory_xact_lock",
		"coalesce(max(turn_order)",
		"tenant_id = $1::uuid",
		"interaction_id = $2::uuid",
		"$1::text || ':' || $2::text",
		"returning",
	} {
		if !strings.Contains(query, required) {
			t.Fatalf("expected append query to include %q, got %s", required, queryer.query)
		}
	}
	for _, forbidden := range []string{"agent_reply", "output_text", "chapter_draft", "manuscript"} {
		if strings.Contains(query, forbidden) {
			t.Fatalf("turn append query suggests fake generation/adoption field %q: %s", forbidden, queryer.query)
		}
	}
	assertNoSensitiveCharacterConsoleSQL(t, queryer.query, queryer.args)

	queryer.rows = &fakeCharacterConsoleRows{values: [][]any{{
		"turn-1",
		"interaction-1",
		"project-123",
		1,
		"user",
		"user-123",
		"action",
		"我把剑放在桌上",
		`{"intent":"threaten"}`,
		`{"public":true}`,
		"trace-1",
		"user-123",
		"2026-07-06T00:01:00Z",
	}}}
	turns, err := store.ListTurns(context.Background(), ListTurnsInput{
		TenantID:      "tenant-123",
		InteractionID: "interaction-1",
	})
	if err != nil {
		t.Fatalf("list turns: %v", err)
	}
	if len(turns) != 1 || turns[0].Action["intent"] != "threaten" {
		t.Fatalf("unexpected turns: %#v", turns)
	}
	assertNoSensitiveCharacterConsoleSQL(t, queryer.query, queryer.args)
}

func TestSQLStoreListTurnsReturnsNotFoundWhenParentInteractionMissing(t *testing.T) {
	queryer := &recordingCharacterConsoleQueryer{rows: &fakeCharacterConsoleRows{}}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, Execer: queryer})

	turns, err := store.ListTurns(context.Background(), ListTurnsInput{
		TenantID:      "tenant-123",
		InteractionID: "missing-interaction",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected missing parent interaction to return NOT_FOUND, got %s (%v), turns=%#v", code, err, turns)
	}
	if !strings.Contains(strings.ToLower(queryer.query), "from character_interaction_sessions") {
		t.Fatalf("expected parent interaction scope query before listing turns, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "missing-interaction"}) {
		t.Fatalf("unexpected parent lookup args: %#v", queryer.args)
	}
}

func TestSQLStoreListsCharacterDialogueEventsWithCursorAndPublicPayload(t *testing.T) {
	rows := &fakeCharacterConsoleRows{values: [][]any{{
		true,
		"event-2",
		3,
		"character.turn.completed",
		`{"status":"completed","interaction_id":"interaction-1","prompt":"hidden","api_key":"sk-hidden","nested":{"credential_ref":"secret","count":1}}`,
		"2026-07-10T12:00:00Z",
	}}}
	queryer := &recordingTenantCharacterConsoleQueryer{
		recordingCharacterConsoleQueryer: recordingCharacterConsoleQueryer{rows: rows},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, Execer: queryer, Limit: 25})

	events, err := store.ListEvents(context.Background(), ListEventsInput{
		TenantID: "tenant-123", InteractionID: "interaction-1", AfterEventID: "event-1",
	})

	if err != nil {
		t.Fatalf("list character dialogue events: %v", err)
	}
	if !queryer.usedTenantContext || queryer.tenantID != "tenant-123" {
		t.Fatalf("event query did not use tenant context: used=%v tenant=%q", queryer.usedTenantContext, queryer.tenantID)
	}
	for _, required := range []string{"workflow_type = 'character_dialogue'", "payload_jsonb->>'interaction_id'", "after_cursor", "order by created_at, event_id", "limit $4"} {
		if !strings.Contains(strings.ToLower(queryer.query), required) {
			t.Fatalf("event query missing %q: %s", required, queryer.query)
		}
	}
	if len(queryer.args) != 4 || queryer.args[0] != "tenant-123" || queryer.args[1] != "interaction-1" || queryer.args[2] != "event-1" || queryer.args[3] != 25 {
		t.Fatalf("unexpected event query args: %#v", queryer.args)
	}
	if len(events) != 1 || events[0].EventID != "event-2" || events[0].InteractionID != "interaction-1" || events[0].Sequence != 3 {
		t.Fatalf("unexpected character dialogue events: %#v", events)
	}
	if _, found := events[0].Payload["prompt"]; found {
		t.Fatalf("public event payload leaked prompt: %#v", events[0].Payload)
	}
	if _, found := events[0].Payload["api_key"]; found {
		t.Fatalf("public event payload leaked api key: %#v", events[0].Payload)
	}
	nested, ok := events[0].Payload["nested"].(map[string]any)
	if !ok || nested["count"] != float64(1) {
		t.Fatalf("public event payload lost safe nested metadata: %#v", events[0].Payload)
	}
	if _, found := nested["credential_ref"]; found {
		t.Fatalf("public event payload leaked credential ref: %#v", events[0].Payload)
	}
}

func TestSQLStoreListCharacterDialogueEventsRejectsForeignCursor(t *testing.T) {
	rows := &fakeCharacterConsoleRows{values: [][]any{{
		false, nil, nil, nil, nil, nil,
	}}}
	queryer := &recordingTenantCharacterConsoleQueryer{
		recordingCharacterConsoleQueryer: recordingCharacterConsoleQueryer{rows: rows},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, Execer: queryer})

	_, err := store.ListEvents(context.Background(), ListEventsInput{
		TenantID: "tenant-123", InteractionID: "interaction-1", AfterEventID: "foreign-event",
	})

	if code := ErrorCode(err); code != "EVENT_CURSOR_NOT_FOUND" {
		t.Fatalf("expected foreign cursor rejection, got %s (%v)", code, err)
	}
	if !rows.aborted {
		t.Fatalf("foreign cursor should abort tenant-scoped rows")
	}
}

func assertNoSensitiveCharacterConsoleSQL(t *testing.T, query string, args []any) {
	t.Helper()
	lowerQuery := strings.ToLower(query)
	for _, forbidden := range []string{
		"input_text",
		"output_text",
		"body_text",
		"content_text",
		"source_text",
		"source_material",
		"prompt",
		"response",
		"api_key",
		"encrypted_api_key",
		"credential_ref",
		"candidate_body",
		"candidate_event_body",
		"event_body",
		"draft",
		"manuscript",
	} {
		if strings.Contains(lowerQuery, forbidden) {
			t.Fatalf("query mentioned forbidden private field %q: %s", forbidden, query)
		}
	}
	for _, arg := range args {
		if value, ok := arg.(string); ok {
			lowerValue := strings.ToLower(value)
			for _, forbidden := range []string{"must be stripped", "api_key", "credential_ref", "prompt", "response"} {
				if strings.Contains(lowerValue, forbidden) {
					t.Fatalf("sql arg leaked forbidden value %q: %#v", forbidden, args)
				}
			}
		}
	}
}

func characterConsoleRowsErrValues(name string) [][]any {
	switch name {
	case "append turn", "list turns":
		return [][]any{{
			"turn-1",
			"interaction-1",
			"project-123",
			1,
			"user",
			"user-123",
			"dialogue",
			"公开回合",
			"{}",
			"{}",
			"trace-1",
			"user-123",
			"2026-07-06T00:01:00Z",
		}}
	default:
		return [][]any{{
			"interaction-1",
			"project-123",
			"worldline-session-1",
			"scene",
			"scene-1",
			"agent-1",
			"dialogue",
			"active",
			"对话",
			"公开摘要",
			"{}",
			"user-123",
			"2026-07-06T00:00:00Z",
			"2026-07-06T00:00:00Z",
		}}
	}
}

func assertStableCharacterConsoleQueryFailure(t *testing.T, err error) {
	t.Helper()
	if code := ErrorCode(err); code != "CHARACTER_INTERACTION_QUERY_FAILED" {
		t.Fatalf("expected query failure code, got %s (%v)", code, err)
	}
	if err == nil || !strings.Contains(err.Error(), "character interaction") || !strings.Contains(err.Error(), "query failed") {
		t.Fatalf("expected stable query failure message, got %v", err)
	}
	for _, forbidden := range []string{"prompt", "api_key", "credential_ref", "body=private", "manuscript=private", "sk-hidden"} {
		if strings.Contains(strings.ToLower(err.Error()), forbidden) {
			t.Fatalf("rows.Err leaked forbidden text %q: %v", forbidden, err)
		}
	}
}

func containsSensitiveCharacterConsoleValue(value any) bool {
	switch typed := value.(type) {
	case map[string]any:
		for key, item := range typed {
			lowerKey := strings.ToLower(strings.TrimSpace(key))
			if isForbiddenCharacterConsoleTestField(lowerKey) {
				return true
			}
			if containsSensitiveCharacterConsoleValue(item) {
				return true
			}
		}
	case []any:
		for _, item := range typed {
			if containsSensitiveCharacterConsoleValue(item) {
				return true
			}
		}
	case string:
		lowerValue := strings.ToLower(typed)
		for _, forbidden := range []string{"must not leak", "secret", "hidden"} {
			if strings.Contains(lowerValue, forbidden) {
				return true
			}
		}
	}
	return false
}

func isForbiddenCharacterConsoleTestField(field string) bool {
	switch field {
	case "input_text", "output_text", "body_text", "content_text", "material_text", "source_material", "source_text", "prompt", "response", "body", "content", "raw_body", "raw_content", "raw_text", "api_key", "apikey", "encrypted_api_key", "credential_ref", "candidate_body", "candidate_event_body", "event_body", "draft", "manuscript":
		return true
	default:
		return false
	}
}

type recordingCharacterConsoleQueryer struct {
	query string
	args  []any
	rows  *fakeCharacterConsoleRows
}

func (q *recordingCharacterConsoleQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.query = query
	q.args = append([]any(nil), args...)
	if q.rows == nil {
		return &fakeCharacterConsoleRows{}, nil
	}
	q.rows.index = 0
	return q.rows, nil
}

func (q *recordingCharacterConsoleQueryer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	q.query = query
	q.args = append([]any(nil), args...)
	return driver.RowsAffected(1), nil
}

type recordingTenantCharacterConsoleQueryer struct {
	recordingCharacterConsoleQueryer
	usedTenantContext bool
	tenantID          string
}

func (q *recordingTenantCharacterConsoleQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.usedTenantContext = true
	q.tenantID = tenantID
	return q.QueryContext(ctx, query, args...)
}

type fakeCharacterConsoleRows struct {
	values   [][]any
	index    int
	err      error
	scanErr  error
	closeErr error
	closed   bool
	aborted  bool
}

func (r *fakeCharacterConsoleRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeCharacterConsoleRows) Scan(dest ...any) error {
	if r.scanErr != nil {
		return r.scanErr
	}
	row := r.values[r.index]
	r.index++
	for i := range dest {
		switch pointer := dest[i].(type) {
		case *bool:
			*pointer = row[i].(bool)
		case *string:
			*pointer = row[i].(string)
		case *int:
			*pointer = row[i].(int)
		case *sql.NullString:
			if row[i] == nil {
				*pointer = sql.NullString{}
			} else {
				*pointer = sql.NullString{String: row[i].(string), Valid: true}
			}
		case *sql.NullInt64:
			if row[i] == nil {
				*pointer = sql.NullInt64{}
			} else {
				*pointer = sql.NullInt64{Int64: int64(row[i].(int)), Valid: true}
			}
		default:
			return nil
		}
	}
	return nil
}

func (r *fakeCharacterConsoleRows) Close() error {
	r.closed = true
	return r.closeErr
}

func (r *fakeCharacterConsoleRows) Abort() error {
	r.aborted = true
	r.closed = true
	return nil
}

func (r *fakeCharacterConsoleRows) Err() error { return r.err }

func fixedCharacterConsoleIDs(ids ...string) func() string {
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
