package assets

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLReaderListsSanitizedProjectAssets(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"asset-1",
				"project-123",
				"project",
				"character",
				"entity",
				"seed",
				"主角",
				"主角摘要",
				"seed_pipeline",
				"entity-1",
				true,
				false,
				`["主角"]`,
				`{"entity_id":"entity-1"}`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer, Limit: 25})

	items, err := reader.ListAssets(context.Background(), ListAssetsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("list assets: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected one asset, got %#v", items)
	}
	item := items[0]
	if item.AssetID != "asset-1" || item.Title != "主角" || item.AssetType != "character" {
		t.Fatalf("unexpected asset: %#v", item)
	}
	if item.Tags[0] != "主角" || item.Payload["entity_id"] != "entity-1" {
		t.Fatalf("expected decoded sanitized tags/payload, got %#v", item)
	}
	if !strings.Contains(queryer.query, "FROM assets") || !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected tenant/project scoped assets query, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "encrypted_api_key", "api_key", "raw_payload_jsonb"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("assets query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLReaderGetsSanitizedAssetByID(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"asset-1",
				"project-123",
				"project",
				"world_rule",
				"rule",
				"seed",
				"灵气规则",
				"公开摘要",
				"seed_pipeline",
				"world-rule-1",
				true,
				true,
				`["世界"]`,
				`{"world_rule_id":"world-rule-1"}`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	item, err := reader.GetAsset(context.Background(), GetAssetInput{
		TenantID: "tenant-123",
		AssetID:  "asset-1",
	})

	if err != nil {
		t.Fatalf("get asset: %v", err)
	}
	if item.AssetID != "asset-1" || item.Title != "灵气规则" || item.ProjectID != "project-123" {
		t.Fatalf("unexpected asset detail: %#v", item)
	}
	if item.Tags[0] != "世界" || item.Payload["world_rule_id"] != "world-rule-1" {
		t.Fatalf("expected decoded sanitized tags/payload, got %#v", item)
	}
	if !strings.Contains(queryer.query, "FROM assets") || !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "asset_id::text = $2") {
		t.Fatalf("expected tenant/asset scoped query, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "encrypted_api_key", "api_key", "raw_payload_jsonb", "credential_ref"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("asset detail query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "asset-1"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLReaderListsSanitizedAssetFacets(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{
				{"asset_type", "character", 3},
				{"category", "entity", 3},
				{"lifecycle", "seed", 5},
				{"source_kind", "seed_pipeline", 5},
				{"tag", "主角", 2},
			},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	facets, err := reader.ListFacets(context.Background(), ListFacetsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
	})

	if err != nil {
		t.Fatalf("list facets: %v", err)
	}
	if facets.AssetTypes[0].Value != "character" || facets.AssetTypes[0].Count != 3 {
		t.Fatalf("unexpected asset type facets: %#v", facets)
	}
	if facets.Categories[0].Value != "entity" || facets.Lifecycles[0].Value != "seed" || facets.Sources[0].Value != "seed_pipeline" || facets.Tags[0].Value != "主角" {
		t.Fatalf("unexpected facets: %#v", facets)
	}
	if !strings.Contains(queryer.query, "jsonb_array_elements_text") || !strings.Contains(queryer.query, "jsonb_typeof(tags_jsonb) = 'array'") {
		t.Fatalf("expected tag facets to expand tags_jsonb safely, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "FROM assets") || !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected tenant/project scoped facets query, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "encrypted_api_key", "api_key", "raw_payload_jsonb", "payload_jsonb", "credential_ref"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("asset facets query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLReaderSearchesSanitizedAssetIndex(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"doc-1",
				"asset",
				"asset-1",
				"project-123",
				"world_rule",
				"灵气规则",
				`["世界"]`,
				`{"asset_id":"asset-1"}`,
				2,
				3,
				"version-3",
				`[{"collection_id":"collection-1","title":"世界规则集","lifecycle":"canon"}]`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	items, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Query:     "灵气",
	})

	if err != nil {
		t.Fatalf("search assets: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected one search result, got %#v", items)
	}
	item := items[0]
	if item.SearchDocumentID != "doc-1" || item.Title != "灵气规则" {
		t.Fatalf("unexpected search result: %#v", item)
	}
	if item.Version.Count != 2 || item.Version.LatestVersion != 3 || item.Version.LatestVersionID != "version-3" {
		t.Fatalf("expected DB-backed version metadata, got %#v", item.Version)
	}
	if len(item.Collections) != 1 || item.Collections[0].CollectionID != "collection-1" || item.Collections[0].Title != "世界规则集" {
		t.Fatalf("expected DB-backed collection metadata, got %#v", item.Collections)
	}
	if !strings.Contains(queryer.query, "FROM global_search_index") || !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected tenant/project scoped search query, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "ILIKE") {
		t.Fatalf("expected explicit keyword filter, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "asset_versions") || !strings.Contains(queryer.query, "asset_collections") || !strings.Contains(queryer.query, "asset_collection_items") {
		t.Fatalf("expected version/collection metadata joins, got %s", queryer.query)
	}
	for _, forbidden := range []string{"content_text", "body_text", "encrypted_api_key", "api_key", "credential_ref", "object_key", "draft", "manuscript"} {
		if strings.Contains(strings.ToLower(queryer.query), forbidden) {
			t.Fatalf("asset search query selected forbidden field %q: %s", forbidden, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "%灵气%", 100}) {
		t.Fatalf("unexpected search args: %#v", queryer.args)
	}
}

func TestSQLReaderSearchAssetsDoesNotSelectOrReturnBody(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"doc-1",
				"asset",
				"asset-1",
				"project-123",
				"world_rule",
				"灵气规则",
				`["世界"]`,
				`{"asset_id":"asset-1"}`,
				0,
				0,
				"",
				`[]`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	items, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Query:     "灵气",
	})

	if err != nil {
		t.Fatalf("search assets: %v", err)
	}
	if len(items) != 1 || items[0].SearchDocumentID != "doc-1" || items[0].Title != "灵气规则" {
		t.Fatalf("unexpected search result: %#v", items)
	}
	selectList := strings.Split(queryer.query, "FROM global_search_index")[0]
	if strings.Contains(strings.ToLower(selectList), "search_doc.body") {
		t.Fatalf("asset search selected body in public row shape: %s", queryer.query)
	}
	raw, err := json.Marshal(items[0])
	if err != nil {
		t.Fatalf("marshal search item: %v", err)
	}
	if strings.Contains(string(raw), `"body"`) {
		t.Fatalf("search result exposed body field: %s", raw)
	}
}

func TestSQLReaderUsesTenantContextQueryerForAssetReadSide(t *testing.T) {
	tests := []struct {
		name string
		run  func(*SQLReader) error
		args []any
	}{
		{
			name: "list",
			run: func(reader *SQLReader) error {
				_, err := reader.ListAssets(context.Background(), ListAssetsInput{TenantID: "tenant-123", ProjectID: "project-123"})
				return err
			},
			args: []any{"tenant-123", "project-123", 100},
		},
		{
			name: "get",
			run: func(reader *SQLReader) error {
				_, err := reader.GetAsset(context.Background(), GetAssetInput{TenantID: "tenant-123", AssetID: "asset-1"})
				return err
			},
			args: []any{"tenant-123", "asset-1"},
		},
		{
			name: "facets",
			run: func(reader *SQLReader) error {
				_, err := reader.ListFacets(context.Background(), ListFacetsInput{TenantID: "tenant-123", ProjectID: "project-123"})
				return err
			},
			args: []any{"tenant-123", "project-123"},
		},
		{
			name: "search",
			run: func(reader *SQLReader) error {
				_, err := reader.SearchAssets(context.Background(), SearchAssetsInput{TenantID: "tenant-123", ProjectID: "project-123", Query: "灵气"})
				return err
			},
			args: []any{"tenant-123", "project-123", "%灵气%", 100},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			queryer := &recordingTenantSQLQueryer{rows: rowsForTenantAssetReadTest(test.name)}
			reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

			if err := test.run(reader); err != nil {
				t.Fatalf("%s query: %v", test.name, err)
			}
			if queryer.tenantID != "tenant-123" || queryer.query == "" {
				t.Fatalf("reader did not use tenant context queryer: %#v", queryer)
			}
			if !reflect.DeepEqual(queryer.args, test.args) {
				t.Fatalf("unexpected args: %#v", queryer.args)
			}
			if queryer.plainQueryCalled {
				t.Fatalf("reader fell back to plain query path despite tenant-aware queryer")
			}
		})
	}
}

func TestSQLReaderSearchSanitizesNestedPayloadFields(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"doc-1",
				"asset",
				"asset-1",
				"project-123",
				"world_rule",
				"灵气规则",
				`["世界","api-key"]`,
				`{
					"asset_id":"asset-1",
					"prompt":"hidden prompt",
					"api-key":"sk-hidden",
					"encryptedApiKey":"encrypted-hidden",
					"encrypted_credential":"encrypted-hidden",
					"encrypted credential":"encrypted-hidden",
					"encryptedCredential":"encrypted-hidden",
					"credential ref":"cred-hidden",
					"source_object_key":"tenant/project/private.txt",
					"draft":"draft secret",
					"draft_text":"draft text secret",
					"draftText":"draft text secret",
					"Manuscript":"manuscript secret",
					"manuscript_text":"manuscript text secret",
					"manuscriptText":"manuscript text secret",
					"nested":{"content":"private body","safe":"visible"},
					"items":[{"raw text":"secret raw","label":"public"}]
				}`,
				0,
				0,
				"",
				`[]`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	items, err := reader.SearchAssets(context.Background(), SearchAssetsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Query:     "灵气",
	})

	if err != nil {
		t.Fatalf("search assets: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected one item, got %#v", items)
	}
	payload := items[0].Payload
	if payload["asset_id"] != "asset-1" {
		t.Fatalf("expected safe payload field to remain, got %#v", payload)
	}
	for _, key := range []string{"prompt", "api-key", "encryptedApiKey", "encrypted_credential", "encrypted credential", "encryptedCredential", "credential ref", "source_object_key", "draft", "draft_text", "draftText", "Manuscript", "manuscript_text", "manuscriptText"} {
		if _, ok := payload[key]; ok {
			t.Fatalf("payload leaked high-risk key %q: %#v", key, payload)
		}
	}
	nested, ok := payload["nested"].(map[string]any)
	if !ok || nested["safe"] != "visible" {
		t.Fatalf("expected nested safe field to remain, got %#v", payload["nested"])
	}
	if _, ok := nested["content"]; ok {
		t.Fatalf("nested payload leaked content field: %#v", nested)
	}
	itemsPayload, ok := payload["items"].([]any)
	if !ok || len(itemsPayload) != 1 {
		t.Fatalf("expected sanitized nested array, got %#v", payload["items"])
	}
	firstItem, ok := itemsPayload[0].(map[string]any)
	if !ok || firstItem["label"] != "public" {
		t.Fatalf("expected safe nested array value to remain, got %#v", itemsPayload[0])
	}
	if _, ok := firstItem["raw text"]; ok {
		t.Fatalf("nested array payload leaked raw text: %#v", firstItem)
	}
	if reflect.DeepEqual(items[0].Tags, []string{"世界", "api-key"}) {
		t.Fatalf("tags leaked high-risk variant: %#v", items[0].Tags)
	}
	if !reflect.DeepEqual(items[0].Tags, []string{"世界"}) {
		t.Fatalf("unexpected sanitized tags: %#v", items[0].Tags)
	}
}

func TestSQLArchiveMemoryReaderListsSanitizedMemories(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"memory-1",
				"asset-1",
				"project-123",
				"relationship",
				"canon",
				"公开记忆摘要",
				`{"relationship_id":"rel-1"}`,
				"seed_pipeline",
				"memory-ref-1",
				true,
				"2026-07-05T00:00:00Z",
				"2026-07-05T00:00:00Z",
			}},
		},
	}
	reader := NewSQLArchiveMemoryReader(SQLArchiveMemoryReaderConfig{Queryer: queryer})

	memories, err := reader.ListMemories(context.Background(), ListArchiveMemoriesInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		AssetID:   "asset-1",
	})

	if err != nil {
		t.Fatalf("list archive memories: %v", err)
	}
	if len(memories) != 1 {
		t.Fatalf("expected one memory, got %#v", memories)
	}
	memory := memories[0]
	if memory.MemoryID != "memory-1" || memory.MemoryType != "relationship" || memory.Summary != "公开记忆摘要" {
		t.Fatalf("unexpected archive memory: %#v", memory)
	}
	if memory.Payload["relationship_id"] != "rel-1" {
		t.Fatalf("expected decoded sanitized payload, got %#v", memory.Payload)
	}
	if !strings.Contains(queryer.query, "FROM archive_memories") || !strings.Contains(queryer.query, "JOIN assets") || !strings.Contains(queryer.query, "asset_id::text = $3") {
		t.Fatalf("expected tenant/project/asset scoped memory query, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "body_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("archive memory query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "asset-1", 50}) {
		t.Fatalf("unexpected memory args: %#v", queryer.args)
	}
}

func TestSQLArchiveMemoryReaderListsSanitizedMemoryEvents(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"event-1",
				"memory-1",
				"asset-1",
				"project-123",
				"adoption_requested",
				"candidate",
				`{"memory_id":"memory-1"}`,
				"user-123",
				"2026-07-05T00:00:00Z",
			}},
		},
	}
	reader := NewSQLArchiveMemoryReader(SQLArchiveMemoryReaderConfig{Queryer: queryer})

	events, err := reader.ListMemoryEvents(context.Background(), ListArchiveMemoryEventsInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		AssetID:   "asset-1",
	})

	if err != nil {
		t.Fatalf("list archive memory events: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("expected one event, got %#v", events)
	}
	event := events[0]
	if event.EventID != "event-1" || event.EventType != "adoption_requested" || event.Status != "candidate" {
		t.Fatalf("unexpected archive memory event: %#v", event)
	}
	if !strings.Contains(queryer.query, "FROM archive_memory_events") || !strings.Contains(queryer.query, "JOIN archive_memories") || !strings.Contains(queryer.query, "JOIN assets") {
		t.Fatalf("expected tenant/project/asset scoped memory event query, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "body_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("archive memory event query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "asset-1", 100}) {
		t.Fatalf("unexpected memory event args: %#v", queryer.args)
	}
}

func TestSQLArchiveMemoryReviewStoreAdoptsCandidateMemoryAndRecordsAudit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"memory-1",
				"asset-1",
				"project-123",
				"relationship",
				"canon",
				"公开记忆摘要",
				`{"relationship_id":"rel-1"}`,
				"asset_ingestion",
				"memory-ref-1",
				true,
				"2026-07-05T00:00:00Z",
				"2026-07-05T00:01:00Z",
			}},
		},
	}
	store := NewSQLArchiveMemoryReviewStore(SQLArchiveMemoryReviewStoreConfig{Queryer: queryer})

	memory, err := store.AdoptMemory(context.Background(), ArchiveMemoryReviewInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		MemoryID:  "memory-1",
		ActorID:   "user-123",
		RequestID: "req-memory-adopt",
	})

	if err != nil {
		t.Fatalf("adopt archive memory: %v", err)
	}
	if memory.MemoryID != "memory-1" || memory.Status != "canon" || memory.Summary != "公开记忆摘要" {
		t.Fatalf("unexpected adopted memory: %#v", memory)
	}
	if !strings.Contains(queryer.query, "UPDATE archive_memories") || !strings.Contains(queryer.query, "status = 'candidate'") {
		t.Fatalf("expected candidate-only archive memory update, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "INSERT INTO archive_memory_events") || !strings.Contains(queryer.query, "archive_memory.adopted") {
		t.Fatalf("expected archive memory adoption event insert, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "INSERT INTO audit_logs") || !strings.Contains(queryer.query, "archive_memory.adopt") {
		t.Fatalf("expected archive memory adoption audit insert, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "body_text", "prompt", "response", "api_key", "encrypted_api_key", "credential_ref"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("archive memory adoption query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "memory-1", "user-123", "req-memory-adopt"}) {
		t.Fatalf("unexpected archive memory adoption args: %#v", queryer.args)
	}
}

func TestSQLArchiveMemoryReviewStoreRejectsCandidateMemoryAndRecordsAudit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"memory-1",
				"asset-1",
				"project-123",
				"relationship",
				"rejected",
				"公开记忆摘要",
				`{"relationship_id":"rel-1"}`,
				"asset_ingestion",
				"memory-ref-1",
				false,
				"2026-07-05T00:00:00Z",
				"2026-07-05T00:01:00Z",
			}},
		},
	}
	store := NewSQLArchiveMemoryReviewStore(SQLArchiveMemoryReviewStoreConfig{Queryer: queryer})

	memory, err := store.RejectMemory(context.Background(), ArchiveMemoryReviewInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		MemoryID:  "memory-1",
		ActorID:   "user-123",
		RequestID: "req-memory-reject",
	})

	if err != nil {
		t.Fatalf("reject archive memory: %v", err)
	}
	if memory.MemoryID != "memory-1" || memory.Status != "rejected" || memory.Enabled {
		t.Fatalf("unexpected rejected memory: %#v", memory)
	}
	if !strings.Contains(queryer.query, "archive_memory.rejected") || !strings.Contains(queryer.query, "archive_memory.reject") {
		t.Fatalf("expected rejection event and audit entries, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "memory-1", "user-123", "req-memory-reject"}) {
		t.Fatalf("unexpected archive memory rejection args: %#v", queryer.args)
	}
}

func TestSQLAdoptionStoreAdoptsOnlyCandidateAssetAndRecordsAudit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"asset-1",
				"project-123",
				"project",
				"world_rule",
				"world",
				"canon",
				"灵气守恒",
				"灵气不可凭空生成。",
				"asset_ingestion",
				"asset-ingestion:run-1:1",
				true,
				false,
				`["world","rule"]`,
				`{"statement":"灵气只能从既有来源转化"}`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:01:00Z",
			}},
		},
	}
	store := NewSQLAdoptionStore(SQLAdoptionStoreConfig{Queryer: queryer})

	record, err := store.AdoptAsset(context.Background(), AdoptAssetInput{
		TenantID:        "tenant-123",
		AssetID:         "asset-1",
		ActorID:         "user-123",
		RequestID:       "req-adopt",
		TargetLifecycle: "canon",
	})

	if err != nil {
		t.Fatalf("adopt asset: %v", err)
	}
	if record.AssetID != "asset-1" || record.Lifecycle != "canon" || record.Title != "灵气守恒" {
		t.Fatalf("unexpected adopted asset: %#v", record)
	}
	if !strings.Contains(queryer.query, "UPDATE assets") || !strings.Contains(queryer.query, "lifecycle = 'candidate'") {
		t.Fatalf("expected candidate-only asset update, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "INSERT INTO audit_logs") || !strings.Contains(queryer.query, "asset.adopt") {
		t.Fatalf("expected asset adoption audit insert, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "api_key", "encrypted_api_key", "credential_ref", "material_text", "prompt", "response"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("adoption query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "asset-1", "canon", "user-123", "req-adopt"}) {
		t.Fatalf("unexpected adoption args: %#v", queryer.args)
	}
}

func TestSQLMutationStoreCreatesSanitizedManualAssetAndRecordsAudit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"asset-1",
				"project-123",
				"project",
				"note",
				"material",
				"material",
				"雨夜谈判素材",
				"公开摘要",
				"manual",
				"req-create",
				true,
				false,
				`["谈判"]`,
				`{"tone":"压迫"}`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	store := NewSQLMutationStore(SQLMutationStoreConfig{Queryer: queryer})

	record, err := store.CreateAsset(context.Background(), CreateAssetInput{
		TenantID:    "tenant-123",
		ProjectID:   "project-123",
		ActorID:     "user-123",
		RequestID:   "req-create",
		Scope:       "project",
		AssetType:   "note",
		Category:    "material",
		Lifecycle:   "material",
		Title:       "雨夜谈判素材",
		Summary:     "公开摘要",
		ContentText: "私有正文不应返回",
		Payload:     map[string]any{"tone": "压迫", "prompt": "remove me"},
		Tags:        []string{"谈判"},
		SourceKind:  "manual",
		SourceRef:   "req-create",
		Enabled:     boolPtr(true),
		Pinned:      boolPtr(false),
	})

	if err != nil {
		t.Fatalf("create asset: %v", err)
	}
	if record.AssetID != "asset-1" || record.Title != "雨夜谈判素材" || record.Lifecycle != "material" {
		t.Fatalf("unexpected created asset: %#v", record)
	}
	if _, ok := record.Payload["prompt"]; ok {
		t.Fatalf("expected high-risk payload fields to be stripped, got %#v", record.Payload)
	}
	if !strings.Contains(queryer.query, "INSERT INTO assets") || !strings.Contains(queryer.query, "INSERT INTO audit_logs") || !strings.Contains(queryer.query, "asset.create") {
		t.Fatalf("expected insert with audit log, got %s", queryer.query)
	}
	forbidden := []string{"encrypted_api_key", "api_key", "credential_ref", "material_text", "prompt", "response"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("create query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{
		"tenant-123",
		"project-123",
		"project",
		"note",
		"material",
		"material",
		"雨夜谈判素材",
		"公开摘要",
		"私有正文不应返回",
		`{"tone":"压迫"}`,
		`["谈判"]`,
		"manual",
		"req-create",
		true,
		false,
		"user-123",
		"req-create",
	}) {
		t.Fatalf("unexpected create args: %#v", queryer.args)
	}
}

func TestSQLMutationStorePatchesTenantScopedAssetAndRecordsAudit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"asset-1",
				"project-123",
				"project",
				"note",
				"material",
				"archived",
				"新标题",
				"新摘要",
				"manual",
				"req-create",
				false,
				true,
				`["更新"]`,
				`{"tone":"冷峻"}`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:01:00Z",
			}},
		},
	}
	store := NewSQLMutationStore(SQLMutationStoreConfig{Queryer: queryer})

	record, err := store.PatchAsset(context.Background(), PatchAssetInput{
		TenantID:  "tenant-123",
		AssetID:   "asset-1",
		ActorID:   "user-123",
		RequestID: "req-patch",
		Title:     stringPtr("新标题"),
		Summary:   stringPtr("新摘要"),
		Lifecycle: stringPtr("archived"),
		Payload:   mapPtr(map[string]any{"tone": "冷峻", "api_key": "remove me"}),
		Tags:      slicePtr([]string{"更新"}),
		Enabled:   boolPtr(false),
		Pinned:    boolPtr(true),
	})

	if err != nil {
		t.Fatalf("patch asset: %v", err)
	}
	if record.AssetID != "asset-1" || record.Title != "新标题" || record.Lifecycle != "archived" || record.Enabled {
		t.Fatalf("unexpected patched asset: %#v", record)
	}
	if _, ok := record.Payload["api_key"]; ok {
		t.Fatalf("expected high-risk payload fields to be stripped, got %#v", record.Payload)
	}
	if !strings.Contains(queryer.query, "UPDATE assets") || !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "asset_id::text = $2") {
		t.Fatalf("expected tenant/asset scoped patch, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "INSERT INTO audit_logs") || !strings.Contains(queryer.query, "asset.update") {
		t.Fatalf("expected asset update audit insert, got %s", queryer.query)
	}
	forbidden := []string{"encrypted_api_key", "api_key", "credential_ref", "material_text", "prompt", "response"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("patch query selected forbidden field %q: %s", field, queryer.query)
		}
	}
}

func TestSQLMutationStoreDeletesTenantScopedAssetAndRecordsAudit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"asset-1",
				"project-123",
				true,
			}},
		},
	}
	store := NewSQLMutationStore(SQLMutationStoreConfig{Queryer: queryer})

	deleted, err := store.DeleteAsset(context.Background(), DeleteAssetInput{
		TenantID:  "tenant-123",
		AssetID:   "asset-1",
		ActorID:   "user-123",
		RequestID: "req-delete",
	})

	if err != nil {
		t.Fatalf("delete asset: %v", err)
	}
	if deleted.AssetID != "asset-1" || deleted.ProjectID != "project-123" {
		t.Fatalf("unexpected delete result: %#v", deleted)
	}
	if !strings.Contains(queryer.query, "DELETE FROM assets") || !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "asset_id::text = $2") {
		t.Fatalf("expected tenant/asset scoped delete, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "INSERT INTO audit_logs") || !strings.Contains(queryer.query, "asset.delete") {
		t.Fatalf("expected asset delete audit insert, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "encrypted_api_key", "api_key", "credential_ref", "material_text", "prompt", "response", "payload_jsonb", "tags_jsonb"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("delete query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "asset-1", "user-123", "req-delete"}) {
		t.Fatalf("unexpected delete args: %#v", queryer.args)
	}
}

func TestSQLBulkActionStoreUpdatesTenantProjectAssetsAndRecordsBatchAudit(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"project-123",
				"set_lifecycle",
				"completed",
				2,
				2,
			}},
		},
	}
	store := NewSQLBulkActionStore(SQLBulkActionStoreConfig{Queryer: queryer})

	result, err := store.ApplyBulkAction(context.Background(), BulkActionInput{
		TenantID:        "tenant-123",
		ProjectID:       "project-123",
		ActorID:         "user-123",
		RequestID:       "req-bulk",
		Action:          "set_lifecycle",
		AssetIDs:        []string{"asset-1", "asset-2", "asset-1"},
		TargetLifecycle: "archived",
		Payload:         map[string]any{"prompt": "remove me", "note": "public batch note"},
	})

	if err != nil {
		t.Fatalf("bulk action assets: %v", err)
	}
	if result.ProjectID != "project-123" || result.Action != "set_lifecycle" || result.Status != "completed" || result.MatchedCount != 2 || result.UpdatedCount != 2 {
		t.Fatalf("unexpected bulk action result: %#v", result)
	}
	if !strings.Contains(queryer.query, "UPDATE assets") || !strings.Contains(queryer.query, "tenant_id::text = $1") || !strings.Contains(queryer.query, "project_id::text = $2") || !strings.Contains(queryer.query, "asset_id::text = ANY($3::text[])") {
		t.Fatalf("expected tenant/project scoped bulk update, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "INSERT INTO audit_logs") || !strings.Contains(queryer.query, "asset.bulk_action") {
		t.Fatalf("expected bulk action audit insert, got %s", queryer.query)
	}
	forbidden := []string{"content_text", "encrypted_api_key", "api_key", "credential_ref", "material_text", "prompt", "response", "payload_jsonb", "tags_jsonb"}
	for _, field := range forbidden {
		if strings.Contains(strings.ToLower(queryer.query), field) {
			t.Fatalf("bulk action query selected forbidden field %q: %s", field, queryer.query)
		}
	}
	if !reflect.DeepEqual(queryer.args, []any{
		"tenant-123",
		"project-123",
		[]string{"asset-1", "asset-2"},
		"set_lifecycle",
		"archived",
		"",
		false,
		false,
		false,
		false,
		`{"note":"public batch note"}`,
		"user-123",
		"req-bulk",
	}) {
		t.Fatalf("unexpected bulk action args: %#v", queryer.args)
	}
}

func TestDisabledAdoptionStoreFailsClosed(t *testing.T) {
	store := NewDisabledAdoptionStore()

	_, err := store.AdoptAsset(context.Background(), AdoptAssetInput{
		TenantID:        "tenant-123",
		AssetID:         "asset-1",
		TargetLifecycle: "canon",
	})

	if code := ErrorCode(err); code != "ASSET_ADOPTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit fail-closed adoption backend, got %s (%v)", code, err)
	}
}

func TestDisabledMutationStoreFailsClosed(t *testing.T) {
	store := NewDisabledMutationStore()

	_, err := store.CreateAsset(context.Background(), CreateAssetInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		AssetType: "note",
		Title:     "素材",
	})
	if code := ErrorCode(err); code != "ASSET_MUTATION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit fail-closed create backend, got %s (%v)", code, err)
	}

	_, err = store.PatchAsset(context.Background(), PatchAssetInput{TenantID: "tenant-123", AssetID: "asset-1"})
	if code := ErrorCode(err); code != "ASSET_MUTATION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit fail-closed patch backend, got %s (%v)", code, err)
	}

	_, err = store.DeleteAsset(context.Background(), DeleteAssetInput{TenantID: "tenant-123", AssetID: "asset-1"})
	if code := ErrorCode(err); code != "ASSET_MUTATION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit fail-closed delete backend, got %s (%v)", code, err)
	}
}

func TestDisabledBulkActionStoreFailsClosed(t *testing.T) {
	store := NewDisabledBulkActionStore()

	_, err := store.ApplyBulkAction(context.Background(), BulkActionInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		Action:    "disable",
		AssetIDs:  []string{"asset-1"},
	})

	if code := ErrorCode(err); code != "ASSET_BULK_ACTION_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected explicit fail-closed bulk action backend, got %s (%v)", code, err)
	}
}

func TestReaderRejectsMissingContext(t *testing.T) {
	reader := NewSQLReader(SQLReaderConfig{Queryer: &recordingSQLQueryer{}})

	_, err := reader.ListAssets(context.Background(), ListAssetsInput{TenantID: "", ProjectID: "project-123"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for list, got %s (%v)", code, err)
	}

	_, err = reader.SearchAssets(context.Background(), SearchAssetsInput{TenantID: "tenant-123", ProjectID: "project-123"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for search, got %s (%v)", code, err)
	}

	_, err = reader.GetAsset(context.Background(), GetAssetInput{TenantID: "tenant-123"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for get, got %s (%v)", code, err)
	}

	_, err = reader.ListFacets(context.Background(), ListFacetsInput{TenantID: "tenant-123"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for facets, got %s (%v)", code, err)
	}
}

func TestMutationStoreRejectsMissingContextAndInvalidLifecycle(t *testing.T) {
	store := NewSQLMutationStore(SQLMutationStoreConfig{Queryer: &recordingSQLQueryer{}})

	_, err := store.CreateAsset(context.Background(), CreateAssetInput{TenantID: "", ProjectID: "project-123", AssetType: "note", Title: "素材"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for missing create tenant, got %s (%v)", code, err)
	}

	_, err = store.CreateAsset(context.Background(), CreateAssetInput{TenantID: "tenant-123", ProjectID: "project-123", AssetType: "note", Title: "素材", Lifecycle: "unknown"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for invalid create lifecycle, got %s (%v)", code, err)
	}

	_, err = store.PatchAsset(context.Background(), PatchAssetInput{TenantID: "tenant-123", AssetID: "asset-1", Lifecycle: stringPtr("unknown")})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for invalid patch lifecycle, got %s (%v)", code, err)
	}

	_, err = store.DeleteAsset(context.Background(), DeleteAssetInput{TenantID: "tenant-123"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for missing delete asset id, got %s (%v)", code, err)
	}
}

func TestAdoptionStoreRejectsMissingContextAndInvalidLifecycle(t *testing.T) {
	store := NewSQLAdoptionStore(SQLAdoptionStoreConfig{Queryer: &recordingSQLQueryer{}})

	_, err := store.AdoptAsset(context.Background(), AdoptAssetInput{TenantID: "", AssetID: "asset-1", TargetLifecycle: "canon"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for missing tenant, got %s (%v)", code, err)
	}

	_, err = store.AdoptAsset(context.Background(), AdoptAssetInput{TenantID: "tenant-123", AssetID: "asset-1", TargetLifecycle: "candidate"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for invalid target lifecycle, got %s (%v)", code, err)
	}
}

func TestBulkActionStoreRejectsMissingContextAndInvalidAction(t *testing.T) {
	store := NewSQLBulkActionStore(SQLBulkActionStoreConfig{Queryer: &recordingSQLQueryer{}})

	_, err := store.ApplyBulkAction(context.Background(), BulkActionInput{TenantID: "", ProjectID: "project-123", Action: "disable", AssetIDs: []string{"asset-1"}})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for missing tenant, got %s (%v)", code, err)
	}

	_, err = store.ApplyBulkAction(context.Background(), BulkActionInput{TenantID: "tenant-123", ProjectID: "project-123", Action: "unknown", AssetIDs: []string{"asset-1"}})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for invalid action, got %s (%v)", code, err)
	}

	_, err = store.ApplyBulkAction(context.Background(), BulkActionInput{TenantID: "tenant-123", ProjectID: "project-123", Action: "set_lifecycle", AssetIDs: []string{"asset-1"}, TargetLifecycle: "unknown"})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for invalid lifecycle, got %s (%v)", code, err)
	}

	_, err = store.ApplyBulkAction(context.Background(), BulkActionInput{TenantID: "tenant-123", ProjectID: "project-123", Action: "categorize", AssetIDs: []string{"asset-1"}})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error for missing category, got %s (%v)", code, err)
	}
}

func stringPtr(value string) *string {
	return &value
}

func boolPtr(value bool) *bool {
	return &value
}

func slicePtr(value []string) *[]string {
	return &value
}

func mapPtr(value map[string]any) *map[string]any {
	return &value
}

type recordingSQLQueryer struct {
	query string
	args  []any
	rows  *fakeSQLRows
	err   error
}

func (q *recordingSQLQueryer) QueryContext(_ context.Context, query string, args ...any) (SQLRows, error) {
	q.query = query
	q.args = args
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return &fakeSQLRows{}, nil
	}
	return q.rows, nil
}

type recordingTenantSQLQueryer struct {
	query            string
	args             []any
	tenantID         string
	rows             *fakeSQLRows
	err              error
	plainQueryCalled bool
}

func (q *recordingTenantSQLQueryer) QueryContext(_ context.Context, query string, args ...any) (SQLRows, error) {
	q.plainQueryCalled = true
	q.query = query
	q.args = args
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return &fakeSQLRows{}, nil
	}
	return q.rows, nil
}

func (q *recordingTenantSQLQueryer) QueryTenantContext(_ context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.tenantID = tenantID
	q.query = query
	q.args = args
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return &fakeSQLRows{}, nil
	}
	return q.rows, nil
}

func rowsForTenantAssetReadTest(name string) *fakeSQLRows {
	switch name {
	case "list", "get":
		return &fakeSQLRows{
			values: [][]any{{
				"asset-1",
				"project-123",
				"project",
				"world_rule",
				"rule",
				"seed",
				"灵气规则",
				"公开摘要",
				"seed_pipeline",
				"world-rule-1",
				true,
				false,
				`["世界"]`,
				`{"asset_id":"asset-1"}`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		}
	case "facets":
		return &fakeSQLRows{
			values: [][]any{{"asset_type", "world_rule", 1}},
		}
	case "search":
		return &fakeSQLRows{
			values: [][]any{{
				"doc-1",
				"asset",
				"asset-1",
				"project-123",
				"world_rule",
				"灵气规则",
				`["世界"]`,
				`{"asset_id":"asset-1"}`,
				0,
				0,
				"",
				`[]`,
				"2026-07-04T00:00:00Z",
				"2026-07-04T00:00:00Z",
			}},
		}
	default:
		return &fakeSQLRows{}
	}
}

type fakeSQLRows struct {
	values [][]any
	index  int
	err    error
}

func (r *fakeSQLRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeSQLRows) Scan(dest ...any) error {
	if r.index >= len(r.values) {
		return errors.New("scan past end")
	}
	row := r.values[r.index]
	r.index++
	for index := range dest {
		switch target := dest[index].(type) {
		case *string:
			*target = row[index].(string)
		case *bool:
			*target = row[index].(bool)
		case *int:
			*target = row[index].(int)
		default:
			return errors.New("unsupported scan target")
		}
	}
	return nil
}

func (r *fakeSQLRows) Close() error {
	return nil
}

func (r *fakeSQLRows) Err() error {
	return r.err
}
