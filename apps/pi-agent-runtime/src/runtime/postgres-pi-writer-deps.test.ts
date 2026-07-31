import { createCipheriv, randomBytes } from "node:crypto";

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ComposeDraftRequest } from "../activities/pi-writer-activities.js";
import {
  createAesGcmCredentialDecryptor,
  createPostgresPiWriterDeps,
  createPgPoolQueryExecutor,
  type QueryExecutor
} from "./postgres-pi-writer-deps.js";

const pgMock = vi.hoisted(() => ({
  clients: [] as Array<{
    queries: { text: string; values?: readonly unknown[] }[];
    released: boolean;
    query<T extends Record<string, unknown>>(text: string, values?: readonly unknown[]): Promise<{ rows: T[] }>;
    release(): void;
  }>,
  directQueries: [] as { text: string; values?: readonly unknown[] }[],
  ended: false,
  reset() {
    this.clients = [];
    this.directQueries = [];
    this.ended = false;
  }
}));

vi.mock("pg", () => ({
  default: {
    Pool: class {
      constructor(readonly options: { connectionString: string }) {}

      async query<T extends Record<string, unknown>>(text: string, values?: readonly unknown[]): Promise<{ rows: T[] }> {
        pgMock.directQueries.push({ text, values });
        return { rows: [] as T[] };
      }

      async connect() {
        const client = {
          queries: [] as { text: string; values?: readonly unknown[] }[],
          released: false,
          async query<T extends Record<string, unknown>>(text: string, values?: readonly unknown[]): Promise<{ rows: T[] }> {
            this.queries.push({ text, values });
            return { rows: [{ ok: "yes" }] as unknown as T[] };
          },
          release() {
            this.released = true;
          }
        };
        pgMock.clients.push(client);
        return client;
      }

      async end(): Promise<void> {
        pgMock.ended = true;
      }
    }
  }
}));

class RecordingDb implements QueryExecutor {
  readonly queries: { text: string; values: readonly unknown[]; context?: { tenant_id: string; project_id?: string } }[] = [];
  private readonly responses: Record<string, unknown>[][] = [];

  enqueue(rows: Record<string, unknown>[]): void {
    this.responses.push(rows);
  }

  async query<T extends Record<string, unknown>>(
    text: string,
    values: readonly unknown[] = [],
    context?: { tenant_id: string; project_id?: string }
  ): Promise<{ rows: T[] }> {
    this.queries.push({ text, values, context });
    return { rows: (this.responses.shift() ?? []) as T[] };
  }
}

beforeEach(() => {
  pgMock.reset();
});

describe("createAesGcmCredentialDecryptor", () => {
  it("decrypts only the supported aes-256-gcm credential envelope", async () => {
    const key = randomBytes(32);
    const decrypt = createAesGcmCredentialDecryptor(key.toString("base64"));
    const encrypted = encryptCredential("sk-live", key);

    await expect(
      decrypt(encrypted, {
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        credential_ref: "channel-1"
      })
    ).resolves.toBe("sk-live");
    await expect(
      decrypt("sk-live", {
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        credential_ref: "channel-1"
      })
    ).rejects.toThrow("unsupported credential cipher");
  });
});

describe("createPostgresPiWriterDeps", () => {
  it("queries world rules and character profiles through tenant/project RLS context without canon writes", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      rule_evidence_id: "rule-1",
      rule_text: "Magic always has a cost.",
      category: "magic",
      confidence: 0.9,
      source: "seed_evidence"
    }]);
    db.enqueue([{
      rule_evidence_id: "asset-rule-1",
      rule_text: "Rain always falls at the gate.",
      category: "world_rule",
      confidence: null,
      source: "canon_asset",
      lifecycle: "canon",
      title: "Rain Gate rule",
      summary: "Rain always falls at the gate."
    }]);
    db.enqueue([{
      entity_id: "entity-1",
      canonical_name: "Lin",
      entity_type: "character",
      importance: "primary",
      state_summary: "Hiding an injury.",
      aliases: ["Captain Lin"],
      source: "entity"
    }]);
    db.enqueue([{
      entity_id: "asset-char-1",
      canonical_name: "Mara",
      entity_type: "character",
      importance: null,
      state_summary: "Lead negotiator",
      aliases: [],
      source: "canon_asset",
      lifecycle: "canon",
      category: "cast"
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const request = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
    };

    await expect(deps.executeWriterTool!({ ...request, tool_name: "query_world_rules" })).resolves.toEqual({
      rules: [
        {
          rule_evidence_id: "rule-1",
          rule_text: "Magic always has a cost.",
          category: "magic",
          confidence: 0.9,
          source: "seed_evidence"
        },
        {
          rule_evidence_id: "asset-rule-1",
          rule_text: "Rain always falls at the gate.",
          category: "world_rule",
          confidence: null,
          source: "canon_asset",
          lifecycle: "canon",
          title: "Rain Gate rule",
          summary: "Rain always falls at the gate."
        }
      ]
    });
    await expect(deps.executeWriterTool!({ ...request, tool_name: "query_character_profile" })).resolves.toEqual({
      profiles: [
        {
          entity_id: "entity-1",
          canonical_name: "Lin",
          entity_type: "character",
          importance: "primary",
          state_summary: "Hiding an injury.",
          aliases: ["Captain Lin"],
          source: "entity"
        },
        {
          entity_id: "asset-char-1",
          canonical_name: "Mara",
          entity_type: "character",
          importance: null,
          state_summary: "Lead negotiator",
          aliases: [],
          source: "canon_asset",
          lifecycle: "canon",
          category: "cast"
        }
      ]
    });

    expect(db.queries).toHaveLength(4);
    for (const query of db.queries) {
      expect(query.context).toEqual({ tenant_id: "ten_1", project_id: "proj_1" });
      expect(query.values.slice(0, 2)).toEqual(["ten_1", "proj_1"]);
      expect(query.text).toMatch(/WHERE .*tenant_id = \$1.*project_id = \$2/s);
      expect(query.text).not.toMatch(/\b(?:INSERT|UPDATE|DELETE)\b/);
    }
    expect(db.queries[0]?.text).toContain("FROM world_rule_evidence");
    expect(db.queries[0]?.text).toContain("confidence::double precision AS confidence");
    expect(db.queries[1]?.text).toContain("FROM assets");
    expect(db.queries[1]?.text).toContain("world_rule");
    // Asset-sourced rules/profiles are spoiler-gated; no chapter target => NULL
    // (only always-visible assets pass).
    expect(db.queries[1]?.text).toContain("reveal_after_chapter_order IS NULL OR reveal_after_chapter_order <= $3");
    expect(db.queries[1]?.values[2]).toBeNull();
    expect(db.queries[2]?.text).toContain("FROM entities");
    expect(db.queries[2]?.text).toContain("entity_aliases");
    expect(db.queries[3]?.text).toContain("FROM assets");
    expect(db.queries[3]?.text).toContain("character");
    expect(db.queries[3]?.text).toContain("reveal_after_chapter_order IS NULL OR reveal_after_chapter_order <= $3");
    expect(db.queries[3]?.values[2]).toBeNull();
  });

  it("requires explicit worldline path selection and scopes manuscript context to active chapter blocks", async () => {
    const db = new RecordingDb();
    db.enqueue([{ chapter_id: "chapter-1", scene_id: "scene-1" }]);
    db.enqueue([{
      block_id: "block-1",
      chapter_id: "chapter-1",
      scene_id: "scene-1",
      block_order: 1,
      content_text: "Current scene prose.",
      word_count: 3
    }]);
    db.enqueue([{
      block_id: "block-2",
      chapter_id: "chapter-1",
      scene_id: "scene-0",
      block_order: 0,
      content_text: "Nearby chapter prose.",
      word_count: 3
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const request = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
    };

    await expect(deps.executeWriterTool!({ ...request, tool_name: "query_worldline_paths" })).resolves.toEqual({
      paths: [],
      canon_status: "reference_only",
      selection_required: true
    });

    await expect(deps.executeWriterTool!({ ...request, tool_name: "query_manuscript_context" })).resolves.toEqual({
      target: { chapter_id: "chapter-1", scene_id: "scene-1" },
      manuscript_blocks: [
        {
          block_id: "block-1",
          chapter_id: "chapter-1",
          scene_id: "scene-1",
          block_order: 1,
          content_text: "Current scene prose.",
          word_count: 3
        },
        {
          block_id: "block-2",
          chapter_id: "chapter-1",
          scene_id: "scene-0",
          block_order: 0,
          content_text: "Nearby chapter prose.",
          word_count: 3
        }
      ]
    });

    expect(db.queries).toHaveLength(3);
    expect(db.queries[0]?.text).toContain("FROM writer_runs");
    expect(db.queries[1]?.text).toContain("status = 'active'");
    expect(db.queries[1]?.text).toContain("scene_id = $3::uuid");
    expect(db.queries[2]?.text).toContain("status = 'active'");
    expect(db.queries[2]?.text).toContain("chapter_id = $3::uuid");
  });

  it("expands query_worldline_paths into author-ordered adopted events (doc 25 §3.3)", async () => {
    const db = new RecordingDb();
    // 1) saved path read (now returns session_id + selected_event_ids).
    db.enqueue([{
      path_id: "path-1",
      session_id: "sess-1",
      title: "黑化线",
      summary: "主角坠入魔道",
      lifecycle: "saved",
      writer_instruction: "突出堕落递进",
      selected_event_ids: '["ev-2","ev-1","ev-rejected"]'
    }]);
    // 2) event expansion read — only canon rows come back (rejected filtered by SQL).
    db.enqueue([
      { event_id: "ev-1", step: 1, title: "初遇", summary: "雨夜相逢", kind: "director", state_changes: '{"location":"城门","content":"不应公开"}' },
      { event_id: "ev-2", step: 2, title: "决裂", summary: "师门决裂", kind: "director" }
    ]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const request = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: ["path-1"],
      worldline_session_ids: [],
    };

    const result = await deps.executeWriterTool!({ ...request, tool_name: "query_worldline_paths" });

    // Events re-threaded in the author's saved order (ev-2 then ev-1), not step order;
    // the rejected/candidate id never surfaces.
    expect(result.canon_status).toBe("reference_only");
    const paths = result.paths as Array<{ path_id: string; session_id: string; events: Array<{ event_id: string }> }>;
    expect(paths).toHaveLength(1);
    expect(paths[0]?.path_id).toBe("path-1");
    expect(paths[0]?.session_id).toBe("sess-1");
    expect(paths[0]?.events.map((e) => e.event_id)).toEqual(["ev-2", "ev-1"]);
    expect(paths[0]?.events[1]).toMatchObject({ state_changes: { location: "城门" } });
    // The expansion query filters to adopted canon events only.
    expect(db.queries[1]?.text).toContain("FROM worldline_events");
    expect(db.queries[1]?.text).toContain("e.status = 'canon'");
  });

  it("prefetches the adopted worldline plot timeline ordered by step (doc 25 §3.2)", async () => {
    const db = new RecordingDb();
    db.enqueue([
      { event_id: "ev-1", session_id: "sess-1", step: 1, title: "初遇", summary: "雨夜相逢", kind: "director", state_changes: '{"location":"城门","content":"不应公开"}' },
      { event_id: "ev-2", session_id: "sess-1", step: 2, title: "决裂", summary: "师门决裂", kind: "director" }
    ]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const request = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: ["sess-1"],
      tool_name: "query_worldline_paths" as const
    };

    const result = await deps.loadWorldlineTimeline!(request);

    expect(result.timelines).toHaveLength(1);
    expect(result.timelines[0]?.session_id).toBe("sess-1");
    expect(result.timelines[0]?.events.map((e) => e.event_id)).toEqual(["ev-1", "ev-2"]);
    expect(result.timelines[0]?.events[0]).toMatchObject({ step: 1, title: "初遇", summary: "雨夜相逢" });
    expect(result.timelines[0]?.events[0].state_changes).toEqual({ location: "城门" });
    // Canon-only, ordered by step, scoped to the attached sessions.
    expect(db.queries[0]?.text).toContain("e.status = 'canon'");
    expect(db.queries[0]?.text).toContain("ORDER BY e.session_id, e.step ASC");
    expect(db.queries[0]?.values).toEqual(["ten_1", "proj_1", ["sess-1"]]);
  });

  it("does not globally truncate canon timelines across attached sessions", async () => {
    const db = new RecordingDb();
    db.enqueue(
      ["sess-1", "sess-2"].flatMap((sessionId) =>
        Array.from({ length: 61 }, (_, index) => ({
          event_id: `${sessionId}-event-${index + 1}`,
          session_id: sessionId,
          step: index + 1,
          title: `事件 ${index + 1}`,
          summary: "公开摘要",
          kind: "director"
        }))
      )
    );
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    const result = await deps.loadWorldlineTimeline!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: ["sess-1", "sess-2"],
      tool_name: "query_worldline_paths"
    });

    expect(result.timelines.map((timeline) => timeline.events)).toHaveLength(2);
    expect(result.timelines[0]?.events).toHaveLength(61);
    expect(result.timelines[1]?.events).toHaveLength(61);
    expect(db.queries[0]?.text).not.toMatch(/\bLIMIT\s+\$4\b/i);
  });

  it("returns an empty worldline timeline when no session is attached", async () => {
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const result = await deps.loadWorldlineTimeline!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
      tool_name: "query_worldline_paths"
    });
    expect(result).toEqual({ timelines: [] });
    expect(db.queries).toHaveLength(0);
  });

  it("sets tenant and project context on DB queries that touch RLS-backed runtime tables", async () => {
    const db = new RecordingDb();
    db.enqueue([{ encrypted_api_key: "ciphertext" }]);
    db.enqueue([]);
    db.enqueue([{ max_concurrency: 1 }]);
    db.enqueue([{ lock_id: "lock-1", lock_mode: "slot:0" }]);
    db.enqueue([{ draft_id: "draft-1" }]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([{ inserted: "1" }]);
    db.enqueue([{ writer_updated: "1", workflow_updated: "1" }]);
    db.enqueue([]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const context = { tenant_id: "ten_1", project_id: "proj_1" };

    await deps.resolveCredential({
      ...context,
      run_id: "run_1",
      module_key: "writer_composer",
      channel_id: "channel-1",
      credential_ref: "channel-1"
    });
    const lease = await deps.acquireLLMLease({
      ...context,
      run_id: "run_1",
      module_key: "writer_composer",
      channel_id: "channel-1",
      model_id: "model-1"
    });
    await deps.saveDraftRevision({
      ...context,
      run_id: "run_1",
      content: "雨夜谈判",
      status: "candidate"
    });
    await deps.recordLLMActivity({
      ...context,
      run_id: "run_1",
      module_key: "writer_composer",
      channel_id: "channel-1",
      model_id: "model-1",
      status: "completed"
    });
    await deps.recordUsageEvent({
      ...context,
      run_id: "run_1",
      module_key: "writer_composer",
      usage_type: "llm_tokens",
      quantity: 1,
      unit: "tokens",
      metadata: {}
    });
    await deps.recordAgentTraceEvent({
      ...context,
      run_id: "run_1",
      trace_id: "trace_1",
      module_key: "writer_composer",
      agent_name: "pi_writer",
      status: "running",
      event_order: 1,
      event_type: "prompt_snapshot",
      redaction_level: "summary",
      payload: {}
    });
    await deps.recordWorkflowEvent({
      ...context,
      run_id: "run_1",
      workflow_type: "writer_run",
      event_type: "writer.run.started",
      payload: { status: "running" }
    });
    await deps.updateWriterRunStatus({
      ...context,
      run_id: "run_1",
      status: "completed",
      draft_id: "draft-1"
    });
    await deps.releaseLLMLease({
      ...context,
      run_id: "run_1",
      lease_id: lease.lease_id,
      channel_id: lease.channel_id,
      lock_mode: lease.lock_mode
    });

    for (const query of db.queries) {
      expect(query.context).toEqual(context);
    }
  });

  it("wraps tenant-scoped pg pool queries with app_set_tenant_context on the same client", async () => {
    const executor = createPgPoolQueryExecutor("postgres://runtime");

    const result = await executor.query(
      "SELECT run_id FROM writer_runs WHERE tenant_id = $1",
      ["11111111-1111-4111-8111-111111111111"],
      {
        tenant_id: "11111111-1111-4111-8111-111111111111",
        project_id: "22222222-2222-4222-8222-222222222222"
      }
    );
    await executor.query("SELECT 1", []);
    await executor.close();

    expect(result.rows).toEqual([{ ok: "yes" }]);
    expect(pgMock.clients).toHaveLength(1);
    expect(pgMock.clients[0]?.queries.map((query) => query.text)).toEqual([
      "BEGIN",
      "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
      "SELECT run_id FROM writer_runs WHERE tenant_id = $1",
      "COMMIT"
    ]);
    expect(pgMock.clients[0]?.queries[1]?.values).toEqual([
      "11111111-1111-4111-8111-111111111111",
      "22222222-2222-4222-8222-222222222222"
    ]);
    expect(pgMock.clients[0]?.released).toBe(true);
    expect(pgMock.directQueries).toEqual([{ text: "SELECT 1", values: [] }]);
    expect(pgMock.ended).toBe(true);
  });

  it("resolves tenant-scoped credentials through the decryptor", async () => {
    const db = new RecordingDb();
    db.enqueue([{ encrypted_api_key: "ciphertext" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async (ciphertext, context) => `${ciphertext}:${context.tenant_id}:${context.run_id}`,
      composeDraft: async () => ({ content: "draft" })
    });

    const credential = await deps.resolveCredential({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_composer",
      channel_id: "channel-1",
      credential_ref: "channel-1"
    });

    expect(credential).toEqual({ apiKey: "ciphertext:ten_1:run_1" });
    expect(db.queries[0]?.text).toContain("FROM llm_channels");
    expect(db.queries[0]?.values).toEqual(["channel-1", "ten_1"]);
  });

  it("resolves module bindings with project tenant and platform fallback ranks", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      module_key: "writer_composer",
      channel_id: "platform-channel",
      model_id: "gpt-platform",
      provider: "openai-compatible",
      base_url: "https://llm.example/v1",
      credential_ref: "platform-channel",
      supports_tools: true,
      supports_json: true,
      settings_jsonb: { temperature: 0.1 }
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "unused",
      composeDraft: async () => ({ content: "unused" })
    });

    await expect(deps.resolveModuleBinding!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_composer"
    })).resolves.toMatchObject({ channel_id: "platform-channel", model_id: "gpt-platform" });

    expect(db.queries[0]?.context).toEqual({ tenant_id: "ten_1", project_id: "proj_1" });
    expect(db.queries[0]?.text).toContain("llm_platform_module_defaults");
    expect(db.queries[0]?.text).toContain("UNION ALL");
    expect(db.queries[0]?.text).toContain("2 AS binding_rank");
    expect(db.queries[0]?.text.match(/m\.enabled = TRUE/g)).toHaveLength(2);
    expect(db.queries[0]?.values).toEqual(["ten_1", "proj_1", "writer_composer"]);
  });

  it("ORs catalog supports_tools=false with chat-model inference", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      module_key: "writer_orchestrator",
      channel_id: "channel-1",
      model_id: "deepseek-v4-flash",
      provider: "openai-compatible",
      base_url: "https://llm.example/v1",
      credential_ref: "channel-1",
      supports_tools: false,
      supports_json: false,
      settings_jsonb: {}
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "unused",
      composeDraft: async () => ({ content: "unused" })
    });

    await expect(deps.resolveModuleBinding!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_orchestrator"
    })).resolves.toMatchObject({
      model_id: "deepseek-v4-flash",
      supports_tools: true,
      supports_json: true
    });
  });

  it("keeps tools unsupported for reasoning-only catalog rows", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      module_key: "writer_orchestrator",
      channel_id: "channel-1",
      model_id: "deepseek-reasoner",
      provider: "openai-compatible",
      base_url: "https://llm.example/v1",
      credential_ref: "channel-1",
      supports_tools: false,
      supports_json: false,
      settings_jsonb: {}
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "unused",
      composeDraft: async () => ({ content: "unused" })
    });

    await expect(deps.resolveModuleBinding!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_orchestrator"
    })).resolves.toMatchObject({
      model_id: "deepseek-reasoner",
      supports_tools: false,
      supports_json: false
    });
  });

  it("fails explicitly when the credential reference is unavailable", async () => {
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await expect(
      deps.resolveCredential({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        module_key: "writer_composer",
        channel_id: "channel-1",
        credential_ref: "missing-channel"
      })
    ).rejects.toThrow("LLM_CREDENTIAL_UNAVAILABLE");
  });

  it("wires quota reservation through the same tenant/project RLS context", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      decision: "reserved",
      reservation_id: "reservation-1",
      provider_call_id: "provider-call-1",
      status: "reserved",
      expires_at: "2026-07-10T12:05:00.000Z"
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "unused",
      composeDraft: async () => ({ content: "unused" })
    });

    await expect(deps.reserveLLMQuota!({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1",
      module_key: "writer_orchestrator", channel_id: "channel-1", model_id: "model-1",
      provider_call_id: "provider-call-1", reserved_tokens: 4096, reserved_cost_micros: 0,
      pricing_status: "pricing_unavailable", ttl_seconds: 300
    })).resolves.toMatchObject({ reservation_id: "reservation-1", status: "reserved" });

    expect(db.queries[0]?.context).toEqual({ tenant_id: "ten_1", project_id: "proj_1" });
    expect(db.queries[0]?.text).toContain("FROM llm_quota_policies");
    expect(db.queries[0]?.text).toContain("INSERT INTO llm_quota_reservations");
  });

  it("loads a completed candidate and finalized aggregate before activity replay", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      draft_id: "draft-existing",
      prompt_tokens: "10",
      completion_tokens: "20",
      cost_estimate: "0.0045"
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "unused",
      composeDraft: async () => ({ content: "unused" })
    });

    await expect(deps.findCompletedWriterRun!({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1"
    })).resolves.toEqual({
      draft_id: "draft-existing",
      usage: { prompt_tokens: 10, completion_tokens: 20, cost_estimate: 0.0045 }
    });
    expect(db.queries[0]?.text).toContain("writer.status = 'completed'");
    expect(db.queries[0]?.text).toContain("FROM llm_quota_reservations");
    expect(db.queries[0]?.context).toEqual({ tenant_id: "ten_1", project_id: "proj_1" });
  });

  it("persists activity provider-call identity without credential material", async () => {
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "unused" })
    });

    await deps.recordLLMActivity({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1",
      module_key: "writer_composer", channel_id: "channel-1", model_id: "model-1",
      provider_call_id: "provider-call-1", status: "completed",
      prompt_tokens: 11, completion_tokens: 17, cost_estimate: 0.0045
    });

    expect(db.queries[0]?.text).toContain("INSERT INTO llm_activity");
    expect(String(db.queries[0]?.values[11])).toContain("provider-call-1");
    expect(JSON.stringify(db.queries[0])).not.toContain("sk-live");
  });

  it("persists candidate drafts, llm activity, and usage without the decrypted key", async () => {
    const db = new RecordingDb();
    db.enqueue([{ draft_id: "draft-1" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async (request: ComposeDraftRequest) => ({
        content: `draft:${request.instruction}`,
        usage: { prompt_tokens: 11, completion_tokens: 17, cost_estimate: 0.0045 }
      })
    });

    await expect(
      deps.saveDraftRevision({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        chapter_id: "chapter-1",
        scene_id: "scene-1",
        content: "雨夜谈判",
        status: "candidate",
        metadata: { module_key: "writer_composer" }
      })
    ).resolves.toEqual({ draft_id: "draft-1" });
    await deps.recordLLMActivity({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_composer",
      channel_id: "channel-1",
      model_id: "model-1",
      status: "completed",
      prompt_tokens: 11,
      completion_tokens: 17,
      latency_ms: 123,
      cost_estimate: 0.0045
    });
    await deps.recordUsageEvent({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_composer",
      usage_type: "llm_tokens",
      quantity: 28,
      unit: "tokens",
      metadata: { channel_id: "channel-1", model_id: "model-1" }
    });

    expect(db.queries[0]?.text).toContain("INSERT INTO writer_drafts");
    expect(db.queries[0]?.text).toContain("FROM writer_runs, locked");
    expect(db.queries[0]?.text).toContain("FROM character_interaction_sessions AS interaction");
    expect(db.queries[0]?.text).toContain("FROM character_interaction_turns AS turn");
    expect(db.queries[0]?.text).toContain("writer_runs.options_jsonb->>'character_interaction_id'");
    expect(db.queries[0]?.text).toContain("writer_runs.status <> 'cancelled'");
    expect(db.queries[0]?.text).toContain("NULLIF($4, '')::uuid");
    expect(db.queries[0]?.text).toContain("NULLIF($5, '')::uuid");
    expect(db.queries[0]?.values).toEqual([
      "ten_1", "run_1", "proj_1", "chapter-1", "scene-1", "雨夜谈判", 4, "candidate"
    ]);
    expect(db.queries[1]?.text).toContain("INSERT INTO llm_activity");
    expect(db.queries[2]?.text).toContain("INSERT INTO usage_events");
    expect(JSON.stringify(db.queries)).not.toContain("sk-live");
  });

  it("does not let a late activity overwrite an explicitly cancelled run", async () => {
    const db = new RecordingDb();
    db.enqueue([{ writer_updated: "0", workflow_updated: "0" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "unused",
      composeDraft: async () => ({ content: "unused" })
    });

    await expect(deps.updateWriterRunStatus({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1", status: "failed",
      error: { code: "LLM_PROVIDER_ERROR", message: "provider call failed" }
    })).rejects.toThrow("WORKFLOW_RUN_NOT_FOUND");
    expect(db.queries[0]?.text.match(/status = 'cancelled'/g)).toHaveLength(2);
  });

  it("fails closed when the admitted Writer run or Character interaction source is missing", async () => {
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await expect(deps.saveDraftRevision({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      chapter_id: "chapter-1",
      scene_id: "scene-1",
      content: "must not be persisted without its source",
      status: "candidate"
    })).rejects.toThrow("WRITER_DRAFT_SAVE_FAILED");

    expect(db.queries).toHaveLength(1);
    expect(db.queries[0]?.text).toContain("COALESCE(writer_runs.options_jsonb->>'source', '') <> 'character_console'");
    expect(db.queries[0]?.text).toContain("turn.interaction_id = interaction.interaction_id");
  });

  it("persists agent trace headers and events without decrypted keys", async () => {
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await deps.recordAgentTraceEvent({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      trace_id: "trace_1",
      module_key: "writer_composer",
      agent_name: "pi_writer",
      status: "running",
      event_order: 1,
      event_type: "prompt_snapshot",
      redaction_level: "full",
      payload: { instruction: "写下一场雨夜谈判" }
    });

    expect(db.queries[0]?.text).toContain("INSERT INTO agent_traces");
    expect(db.queries[0]?.values).toEqual(["ten_1", "trace_1", "run_1", "proj_1", "writer_composer", "pi_writer", "running"]);
    expect(db.queries[1]?.text).toContain("INSERT INTO agent_trace_events");
    expect(db.queries[1]?.values).toEqual(["ten_1", "trace_1", 1, "prompt_snapshot", JSON.stringify({ instruction: "写下一场雨夜谈判" }), "full"]);
    expect(JSON.stringify(db.queries)).not.toContain("sk-live");
  });

  it("persists workflow events for writer stream replay without decrypted keys", async () => {
    const db = new RecordingDb();
    db.enqueue([{ inserted: "1" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await deps.recordWorkflowEvent({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      workflow_type: "writer_run",
      event_type: "writer.token",
      payload: { token: "雨" }
    });

    expect(db.queries[0]?.text).toContain("INSERT INTO workflow_events");
    expect(db.queries[0]?.text).toContain("COALESCE(MAX(sequence), 0) + 1");
    expect(db.queries[0]?.text).toContain("pg_advisory_xact_lock");
    expect(db.queries[0]?.text).toContain("FROM writer_runs");
    expect(db.queries[0]?.text).toContain("writer_runs.status <> 'cancelled'");
    expect(db.queries[0]?.values).toEqual([
      "ten_1",
      "run_1",
      "writer_run",
      "proj_1",
      "writer.token",
      JSON.stringify({ token: "雨" }),
      null
    ]);
    expect(JSON.stringify(db.queries)).not.toContain("sk-live");
  });

  it("requires writer admission parent rows and sanitizes workflow event payloads", async () => {
    const db = new RecordingDb();
    db.enqueue([{ inserted: "1" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await deps.recordWorkflowEvent({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      workflow_type: "writer_run",
      event_type: "writer.run.failed",
      payload: {
        status: "failed",
        public_summary: "provider failed",
        prompt: "private prompt",
        api_key: "sk-live",
        credential_ref: "credref-1",
        draft: "private draft",
        nested: {
          source_material: "private source",
          kept: "public nested"
        }
      }
    });

    expect(db.queries[0]?.text).toContain("FROM writer_runs");
    expect(db.queries[0]?.text).toContain("workflow_runs");
    const serialized = JSON.stringify(db.queries[0]?.values);
    for (const forbidden of [
      "private prompt",
      "sk-live",
      "credref-1",
      "private draft",
      "private source",
      "prompt",
      "api_key",
      "credential_ref",
      "source_material"
    ]) {
      expect(serialized).not.toContain(forbidden);
    }
    expect(serialized).toContain("provider failed");
    expect(serialized).toContain("public nested");
  });

  it("fails workflow event persistence when writer admission parent rows are missing", async () => {
    const db = new RecordingDb();
    db.enqueue([{ inserted: "0" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await expect(
      deps.recordWorkflowEvent({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_missing",
        workflow_type: "writer_run",
        event_type: "writer.run.started",
        payload: { status: "running" }
      })
    ).rejects.toThrow("WORKFLOW_RUN_NOT_FOUND");
  });

  it("updates writer and workflow run status without credential material", async () => {
    const db = new RecordingDb();
    db.enqueue([{ writer_updated: "1", workflow_updated: "1" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await deps.updateWriterRunStatus({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      status: "failed",
      error: {
        code: "LLM_PROVIDER_ERROR",
        message: "provider rejected request"
      }
    });

    expect(db.queries[0]?.text).toContain("UPDATE writer_runs");
    expect(db.queries[0]?.text).toContain("UPDATE workflow_runs");
    expect(db.queries[0]?.values).toEqual([
      "ten_1",
      "proj_1",
      "run_1",
      "failed",
      null,
      "LLM_PROVIDER_ERROR",
      "provider rejected request"
    ]);
    expect(JSON.stringify(db.queries)).not.toContain("sk-live");
  });

  it("fails explicitly when writer run status updates miss admission parent rows", async () => {
    const db = new RecordingDb();
    db.enqueue([{ writer_updated: "0", workflow_updated: "0" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await expect(
      deps.updateWriterRunStatus({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_missing",
        status: "running"
      })
    ).rejects.toThrow("WORKFLOW_RUN_NOT_FOUND");

    expect(db.queries[0]?.text).toContain("UPDATE writer_runs");
    expect(db.queries[0]?.text).toContain("UPDATE workflow_runs");
    expect(JSON.stringify(db.queries)).not.toContain("sk-live");
  });

  it("acquires and releases a channel concurrency slot through resource_locks", async () => {
    const db = new RecordingDb();
    db.enqueue([]);
    db.enqueue([{ max_concurrency: 2 }]);
    db.enqueue([]);
    db.enqueue([{ lock_id: "lock-1", lock_mode: "slot:1" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    const lease = await deps.acquireLLMLease({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_composer",
      channel_id: "channel-1",
      model_id: "model-1"
    });
    await deps.releaseLLMLease({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      lease_id: lease.lease_id,
      channel_id: lease.channel_id,
      lock_mode: lease.lock_mode
    });

    expect(lease).toEqual({ lease_id: "lock-1", channel_id: "channel-1", lock_mode: "slot:1" });
    expect(db.queries[0]?.text).toContain("DELETE FROM resource_locks");
    expect(db.queries[1]?.text).toContain("SELECT max_concurrency");
    expect(db.queries[2]?.values).toContain("slot:0");
    expect(db.queries[3]?.values).toContain("slot:1");
    expect(db.queries[4]?.text).toContain("DELETE FROM resource_locks");
    expect(db.queries[4]?.values).toEqual(["lock-1", "ten_1"]);
  });

  it("acquires and releases module-specific concurrency slots when configured", async () => {
    const db = new RecordingDb();
    db.enqueue([]);
    db.enqueue([{ max_concurrency: 2 }]);
    db.enqueue([{ lock_id: "channel-lock", lock_mode: "slot:0" }]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([{ lock_id: "module-lock", lock_mode: "slot:1" }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    const lease = await deps.acquireLLMLease({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      module_key: "writer_composer",
      channel_id: "channel-1",
      model_id: "model-1",
      module_max_concurrency: 2
    });
    await deps.releaseLLMLease({
      ...lease,
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1"
    });

    expect(lease).toEqual({
      lease_id: "channel-lock",
      channel_id: "channel-1",
      lock_mode: "slot:0",
      locks: [
        {
          lease_id: "channel-lock",
          resource_type: "llm_channel",
          resource_id: "channel-1",
          lock_mode: "slot:0"
        },
        {
          lease_id: "module-lock",
          resource_type: "llm_module",
          resource_id: "writer_composer",
          lock_mode: "slot:1"
        }
      ]
    });
    expect(db.queries[4]?.values).toContain("llm_module");
    expect(db.queries[4]?.values).toContain("writer_composer");
    expect(db.queries[6]?.values).toEqual(["channel-lock", "ten_1"]);
    expect(db.queries[7]?.values).toEqual(["module-lock", "ten_1"]);
  });

  it("releases the channel lock when module-specific concurrency is exhausted", async () => {
    const db = new RecordingDb();
    db.enqueue([]);
    db.enqueue([{ max_concurrency: 1 }]);
    db.enqueue([{ lock_id: "channel-lock", lock_mode: "slot:0" }]);
    db.enqueue([]);
    db.enqueue([]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await expect(
      deps.acquireLLMLease({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        module_key: "writer_composer",
        channel_id: "channel-1",
        model_id: "model-1",
        module_max_concurrency: 1
      })
    ).rejects.toThrow("LLM_CONCURRENCY_LIMITED");

    expect(db.queries[5]?.text).toContain("DELETE FROM resource_locks");
    expect(db.queries[5]?.values).toEqual(["channel-lock", "ten_1"]);
  });

  it("fails explicitly when all channel concurrency slots are occupied", async () => {
    const db = new RecordingDb();
    db.enqueue([]);
    db.enqueue([{ max_concurrency: 1 }]);
    db.enqueue([]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await expect(
      deps.acquireLLMLease({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        module_key: "writer_composer",
        channel_id: "channel-1",
        model_id: "model-1"
      })
    ).rejects.toThrow("LLM_CONCURRENCY_LIMITED");
  });

  it("search_assets runs keyword mode without touching embedding resolution and enforces the lifecycle gate", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      asset_id: "asset-1",
      asset_type: "world_rule",
      category: "magic",
      lifecycle: "canon",
      title: "Magic costs",
      summary: "Magic always has a cost.",
      content_text: "All magic exacts a price from the caster.",
      tags_jsonb: "[\"magic\"]",
      keyword_score: 0.5,
      vector_score: 0,
      recency_boost: 0.01,
      lifecycle_boost: 0.08,
      pinned_boost: 0,
      final_score: 0.59
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const request = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
    };

    const result = await deps.executeWriterTool!({
      ...request,
      tool_name: "search_assets",
      tool_args: { query: "magic cost", mode: "keyword" }
    });

    expect(result.mode_used).toBe("keyword");
    expect(result.degraded).toBe(false);
    expect(result.count).toBe(1);
    const assets = result.assets as Array<Record<string, unknown>>;
    const citations = result.citations as Array<Record<string, unknown>>;
    expect(assets[0]?.asset_id).toBe("asset-1");
    expect(assets[0]?.content_preview).toBe("All magic exacts a price from the caster.");
    expect(citations[0]).toMatchObject({ asset_id: "asset-1", channel: "search_assets" });

    // Exactly one DB query (the search) — no embedding binding/credential lookups.
    expect(db.queries).toHaveLength(1);
    const search = db.queries[0]!;
    expect(search.text).toContain("search_doc.source = 'asset'");
    expect(search.text).toContain("asset.lifecycle = ANY(input.lifecycles)");
    expect(search.text).toContain("asset.enabled = TRUE");
    expect(search.values[3]).toBe("keyword");          // mode
    expect(search.values[4]).toBeNull();                // embedding literal
    expect(search.values[7]).toEqual(["seed", "canon", "material"]); // lifecycle gate
    expect(search.values[8]).toBe(10);                  // default top_k
    expect(search.values[10]).toEqual(["%magic%", "%cost%"]); // tokenized terms, not whole-query ILIKE
  });

  it("search_assets tokenizes CJK queries so multi-word queries still hit", async () => {
    const db = new RecordingDb();
    db.enqueue([]); // keyword search -> rows irrelevant here
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await deps.executeWriterTool!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
      tool_name: "search_assets",
      tool_args: { query: "许七安的师门 打更人", mode: "keyword" }
    });

    const search = db.queries[0]!;
    // "的" splits the unsegmented run; each term matches independently.
    expect(search.values[10]).toEqual(["%许七安%", "%师门%", "%打更人%"]);
    expect(search.text).toContain("unnest(input.keyword_patterns)");
    expect(search.text).not.toContain("('%' || $3::text || '%')");
  });

  it("search_assets explicitly degrades to keyword when the embedding module is unbound", async () => {
    const db = new RecordingDb();
    db.enqueue([]);            // binding lookup returns no row -> LLM_MODULE_UNBOUND
    db.enqueue([]);            // keyword search returns no rows
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const request = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
    };

    const result = await deps.executeWriterTool!({
      ...request,
      tool_name: "search_assets",
      tool_args: { query: "师门 复命" }
    });

    expect(result.mode_used).toBe("keyword");
    expect(result.degraded).toBe(true);
    expect(result.degrade_reason).toMatch(/asset_search_embedding module is not bound/);
    expect(result.assets).toEqual([]);
    // binding lookup + search, but no credential lookup and no embedding fetch.
    expect(db.queries).toHaveLength(2);
    expect(db.queries[1]?.values[3]).toBe("keyword");
  });

  it("search_assets runs hybrid mode through the embedding binding and credential", async () => {
    const db = new RecordingDb();
    db.enqueue([{
      module_key: "asset_search_embedding",
      channel_id: "channel-emb",
      model_id: "text-embedding-3-small",
      provider: "openai-compatible",
      base_url: "https://llm.example.test/v1",
      credential_ref: "channel-emb",
      supports_tools: false,
      supports_json: false,
      settings_jsonb: {}
    }]);
    db.enqueue([{ encrypted_api_key: "cipher" }]);
    db.enqueue([{
      asset_id: "asset-9",
      asset_type: "world_rule",
      category: "sect",
      lifecycle: "canon",
      title: "师门戒律",
      summary: "回山须复命。",
      content_text: "弟子回山必须向掌门复命。",
      tags_jsonb: "[]",
      keyword_score: 0.4,
      vector_score: 0.9,
      recency_boost: 0.01,
      lifecycle_boost: 0.08,
      pinned_boost: 0,
      final_score: 0.76
    }]);
    const fetchCalls: { url: string; init: { headers: Record<string, string>; body: string } }[] = [];
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" }),
      fetchEmbedding: async (url, init) => {
        fetchCalls.push({ url, init });
        return { ok: true, status: 200, json: async () => ({ data: [{ index: 0, embedding: [0.1, 0.2, 0.3] }] }) };
      }
    });
    const request = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
    };

    const result = await deps.executeWriterTool!({
      ...request,
      tool_name: "search_assets",
      tool_args: { query: "师门 复命", top_k: 5 }
    });

    expect(result.mode_used).toBe("hybrid");
    expect(result.degraded).toBe(false);
    const hybridAssets = result.assets as Array<Record<string, unknown>>;
    expect(hybridAssets[0]?.asset_id).toBe("asset-9");

    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0]?.url).toBe("https://llm.example.test/v1/embeddings");
    expect(fetchCalls[0]?.init.headers.Authorization).toBe("Bearer sk-live");
    expect(JSON.parse(fetchCalls[0]?.init.body)).toEqual({ model: "text-embedding-3-small", input: ["师门 复命"] });

    const search = db.queries[2]!;
    expect(search.values[3]).toBe("hybrid");                 // mode
    expect(search.values[4]).toBe("[0.1,0.2,0.3]");          // embedding literal
    expect(search.values[5]).toBe("text-embedding-3-small"); // embedding model
    expect(search.values[8]).toBe(5);                         // top_k honored
  });

  it("search_assets rejects an empty query before any retrieval", async () => {
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await expect(
      deps.executeWriterTool!({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        selected_asset_ids: [],
        graph_node_ids: [],
        worldline_path_ids: [],
        worldline_session_ids: [],
        tool_name: "search_assets",
        tool_args: { query: "   " }
      })
    ).rejects.toThrow("search_assets requires a non-empty query");
    expect(db.queries).toHaveLength(0);
  });

  it("search_manuscript recalls non-adjacent prior prose via vector and degrades explicitly without embeddings", async () => {
    const base = {
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      chapter_id: "chapter-1",
      scene_id: "scene-1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
    };

    // Degraded path: embedding module unbound -> empty, mode_used unavailable.
    const degradedDb = new RecordingDb();
    degradedDb.enqueue([{ chapter_id: "chapter-1", scene_id: "scene-1" }]); // run target
    degradedDb.enqueue([]); // binding lookup -> unbound
    const degradedDeps = createPostgresPiWriterDeps({
      db: degradedDb,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const degraded = await degradedDeps.executeWriterTool!({
      ...base,
      tool_name: "search_manuscript",
      tool_args: { query: "夜探医院的伏笔" }
    });
    expect(degraded.mode_used).toBe("unavailable");
    expect(degraded.degraded).toBe(true);
    expect(degraded.manuscript_blocks).toEqual([]);
    expect(degraded.citations).toEqual([]);

    // Vector path: binding + credential + embedding, returns a prior block.
    const db = new RecordingDb();
    db.enqueue([{ chapter_id: "chapter-1", scene_id: "scene-1" }]);           // run target
    db.enqueue([{                                                              // binding
      module_key: "asset_search_embedding",
      channel_id: "channel-emb",
      model_id: "text-embedding-3-small",
      provider: "openai-compatible",
      base_url: "https://llm.example.test/v1",
      credential_ref: "channel-emb",
      supports_tools: false,
      supports_json: false,
      settings_jsonb: {}
    }]);
    db.enqueue([{ encrypted_api_key: "cipher" }]);                             // credential
    db.enqueue([{ cursor_order: 7 }]);                                         // cursor
    db.enqueue([{                                                              // vector hits
      block_id: "block-9",
      chapter_id: "chapter-3",
      scene_id: "scene-30",
      block_order: 3,
      content_text: "她在雨夜潜入医院,揭开了三年前的秘密。",
      word_count: 18,
      score: 0.88
    }]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" }),
      fetchEmbedding: async () => ({ ok: true, status: 200, json: async () => ({ data: [{ index: 0, embedding: [0.1, 0.2] }] }) })
    });
    const result = await deps.executeWriterTool!({
      ...base,
      tool_name: "search_manuscript",
      tool_args: { query: "夜探医院的伏笔", top_k: 3 }
    });
    expect(result.mode_used).toBe("vector");
    expect(result.degraded).toBe(false);
    expect(result.count).toBe(1);
    const blocks = result.manuscript_blocks as Array<Record<string, unknown>>;
    expect(blocks[0]?.block_id).toBe("block-9");
    expect(String(blocks[0]?.snippet)).toContain("雨夜潜入医院");
    const citations = result.citations as Array<Record<string, unknown>>;
    expect(citations[0]).toMatchObject({ block_id: "block-9", channel: "search_manuscript" });
    // Timeline gate: strictly-prior prose only — no "other scene" escape hatch
    // that used to readmit future blocks.
    const vectorQuery = db.queries[4]!;
    expect(vectorQuery.text).toContain("manuscript_block_embeddings");
    expect(vectorQuery.text).toContain("block.block_order < $5");
    expect(vectorQuery.text).not.toContain("IS DISTINCT FROM");
    expect(vectorQuery.values[4]).toBe(7);
    expect(vectorQuery.values[5]).toBe(3);
  });

  it("search_assets applies the spoiler gate with the current chapter order", async () => {
    const db = new RecordingDb();
    db.enqueue([{ chapter_order: 12 }]); // resolveCurrentChapterOrder
    db.enqueue([]);                       // keyword search -> no rows
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await deps.executeWriterTool!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      chapter_id: "chapter-1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
      tool_name: "search_assets",
      tool_args: { query: "凶手 动机", mode: "keyword" }
    });

    // Chapter order resolved first, then the gated search.
    expect(db.queries[0]?.text).toContain("FROM chapters");
    const search = db.queries[1]!;
    expect(search.text).toContain("reveal_after_chapter_order IS NULL OR asset.reveal_after_chapter_order <= $10");
    expect(search.values[9]).toBe(12);
  });

  it("search_assets recalls only always-visible assets when no chapter is targeted", async () => {
    const db = new RecordingDb();
    db.enqueue([]); // keyword search -> no rows; no chapter-order query (no chapter_id)
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    await deps.executeWriterTool!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
      tool_name: "search_assets",
      tool_args: { query: "凶手 动机", mode: "keyword" }
    });

    // No chapters lookup; the gate predicate gets NULL (only NULL-reveal assets pass).
    expect(db.queries).toHaveLength(1);
    expect(db.queries[0]?.values[9]).toBeNull();
  });

  it("search_assets keyed channel force-injects title and alias matches", async () => {
    const db = new RecordingDb();
    db.enqueue([]);                     // recent manuscript tail (chapter target, empty)
    db.enqueue([{ chapter_order: 5 }]); // resolveCurrentChapterOrder
    db.enqueue([ // candidate assets (title matching)
      { asset_id: "a-shifu", asset_type: "character", category: "cast", lifecycle: "canon", title: "师父", summary: "掌门", content_text: "师门掌门。", pinned: false },
      { asset_id: "a-rule", asset_type: "world_rule", category: "magic", lifecycle: "canon", title: "不相关规则", summary: "", content_text: "", pinned: false }
    ]);
    db.enqueue([ // character entity with alias "云峰" (canonical 云锋)
      { entity_id: "ent-yunfeng", canonical_name: "云锋", state_summary: "大师兄", alias: "云峰" }
    ]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    const result = await deps.executeWriterTool!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      chapter_id: "chapter-1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
      tool_name: "search_assets",
      tool_args: { query: "沈翠花回山见师父,大师兄云峰已在山下等候", channel: "keyed" }
    });

    const assets = result.assets as Array<Record<string, unknown>>;
    // Asset title "师父" matches; entity alias "云峰" matches 云锋; "不相关规则" does not.
    expect(result.count).toBe(2);
    const byId = new Map(assets.map((a) => [String(a.asset_id), a]));
    expect(byId.get("a-shifu")?.matched_key).toBe("师父");
    expect(byId.get("ent-yunfeng")?.matched_key).toBe("云峰");
    expect(byId.get("ent-yunfeng")?.title).toBe("云锋");
    expect(result.spoiler_gated).toBe(true);
    expect(result.current_chapter_order).toBe(5);
    // No embedding resolution on the keyed path (deterministic).
    expect(db.queries.some((q) => q.text.includes("llm_module_bindings"))).toBe(false);
  });

  it("fuse_recall merges channels via RRF without touching the DB", async () => {
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    const result = await deps.executeWriterTool!({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      worldline_session_ids: [],
      tool_name: "fuse_recall",
      tool_args: {
        channels: [
          { channel: "keyed", items: [{ asset_id: "a1", title: "师门戒律" }, { asset_id: "a2", title: "师父" }] },
          { channel: "hybrid", items: [{ asset_id: "a2", title: "师父" }, { asset_id: "a3", title: "旧事件" }] }
        ],
        top_k: 5
      }
    });

    const fused = result.fused as Array<Record<string, unknown>>;
    // a2 appears in both channels -> highest RRF score.
    expect(fused[0]?.id).toBe("a2");
    expect(fused[0]?.channels).toEqual(["keyed", "hybrid"]);
    expect(result.count).toBe(3);
    const citations = result.citations as Array<Record<string, unknown>>;
    expect(citations[0]?.channel).toBe("fuse_recall");
    // Pure function — no DB access.
    expect(db.queries).toHaveLength(0);
  });

  it("fuse_recall reranks the fused list via the injected executor and degrades on failure", async () => {
    // Rerank path: the activity-injected executor promotes a3 above the RRF order.
    const db = new RecordingDb();
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });
    const rerankCalls: Array<{ query: string; ids: string[] }> = [];
    const result = await deps.executeWriterTool!({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1",
      selected_asset_ids: [], graph_node_ids: [], worldline_path_ids: [], worldline_session_ids: [],
      tool_name: "fuse_recall",
      tool_args: {
        rerank: true,
        query: "师门复命",
        channels: [
          { channel: "keyed", items: [{ asset_id: "a1", title: "师门戒律", content_preview: "戒律" }] },
          { channel: "hybrid", items: [{ asset_id: "a2", title: "师父", content_preview: "师父" }, { asset_id: "a3", title: "旧事件", content_preview: "复命旧事" }] }
        ]
      },
      rerank_executor: async (query, candidates) => {
        rerankCalls.push({ query, ids: candidates.map((c) => c.id) });
        return ["a3", "a1", "a2"];
      }
    });
    const fused = result.fused as Array<Record<string, unknown>>;
    expect(result.reranked).toBe(true);
    expect(fused.map((f) => f.id)).toEqual(["a3", "a1", "a2"]);
    expect(rerankCalls).toEqual([{ query: "师门复命", ids: ["a1", "a2", "a3"] }]);
    // The rerank hop is the activity's job (quota + provider_call_id); the deps
    // layer itself never touches the DB for it.
    expect(db.queries).toHaveLength(0);

    // Degraded path: executor throws -> falls back to RRF order, flagged.
    const degraded = await deps.executeWriterTool!({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1",
      selected_asset_ids: [], graph_node_ids: [], worldline_path_ids: [], worldline_session_ids: [],
      tool_name: "fuse_recall",
      tool_args: {
        rerank: true, query: "x",
        channels: [
          { channel: "keyed", items: [{ asset_id: "b1", title: "甲" }] },
          { channel: "hybrid", items: [{ asset_id: "b1", title: "甲" }, { asset_id: "b2", title: "乙" }] }
        ]
      },
      rerank_executor: async () => { throw new Error("reranker unavailable"); }
    });
    expect(degraded.reranked).toBe(false);
    expect(degraded.rerank_degraded).toMatch(/reranker unavailable/);
    // RRF order preserved: b1 (both channels) first.
    expect((degraded.fused as Array<Record<string, unknown>>)[0]?.id).toBe("b1");

    // Rerank requested but no executor wired -> explicit, visible degradation.
    const unwired = await deps.executeWriterTool!({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1",
      selected_asset_ids: [], graph_node_ids: [], worldline_path_ids: [], worldline_session_ids: [],
      tool_name: "fuse_recall",
      tool_args: {
        rerank: true, query: "x",
        channels: [{ channel: "hybrid", items: [{ asset_id: "c1", title: "丙" }] }]
      }
    });
    expect(unwired.reranked).toBe(false);
    expect(unwired.rerank_degraded).toMatch(/not wired/);
  });

  it("loadAlwaysOnAssets returns only always_on canon inside the safety gates", async () => {
    const db = new RecordingDb();
    db.enqueue([{ chapter_order: 7 }]); // resolveCurrentChapterOrder
    db.enqueue([ // the always_on query (already filtered by the SQL WHERE clause)
      { asset_id: "a-law", asset_type: "world_rule", category: "law", lifecycle: "canon", title: "铁律", summary: "世界铁律", content_text: "不可违背。" },
      { asset_id: "a-style", asset_type: "style", category: "ban", lifecycle: "canon", title: "禁词", summary: "风格禁词", content_text: "禁用词汇表。" }
    ]);
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    const result = await deps.loadAlwaysOnAssets!({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1",
      chapter_id: "chapter-1",
      selected_asset_ids: [], graph_node_ids: [], worldline_path_ids: [], worldline_session_ids: [],
      tool_name: "search_assets",
      tool_args: { channel: "always_on" }
    });

    expect(result.assets).toHaveLength(2);
    expect(result.assets[0]).toMatchObject({ asset_id: "a-law", title: "铁律", channel: "always_on" });
    expect(result.assets[0]?.content_preview).toContain("不可违背");
    // The query enforces always_on + lifecycle whitelist + spoiler gate as SQL params.
    const query = db.queries.find((q) => q.text.includes("always_on = TRUE"));
    expect(query).toBeDefined();
    expect(query!.text).toContain("enabled = TRUE");
    expect(query!.text).toContain("reveal_after_chapter_order");
    expect(query!.values).toContain(7); // current chapter order passed to the spoiler gate
    // Deterministic channel: no embedding/LLM resolution.
    expect(db.queries.some((q) => q.text.includes("llm_module_bindings"))).toBe(false);
  });

  it("loadAlwaysOnAssets returns empty when no chapter is targeted (only always-visible)", async () => {
    const db = new RecordingDb();
    db.enqueue([]); // resolveCurrentChapterOrder -> no chapter -> NULL order
    db.enqueue([]); // always_on query: spoiler gate with NULL order returns nothing unrevealed
    const deps = createPostgresPiWriterDeps({
      db,
      decryptCredential: async () => "sk-live",
      composeDraft: async () => ({ content: "draft" })
    });

    const result = await deps.loadAlwaysOnAssets!({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1",
      selected_asset_ids: [], graph_node_ids: [], worldline_path_ids: [], worldline_session_ids: [],
      tool_name: "search_assets",
      tool_args: { channel: "always_on" }
    });

    expect(result.assets).toEqual([]);
    const query = db.queries.find((q) => q.text.includes("always_on = TRUE"));
    expect(query).toBeDefined();
    expect(query!.values).toContain(null); // NULL current order => only always-visible rows
  });
});

function encryptCredential(plaintext: string, key: Buffer): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [
    "aes-256-gcm",
    "v1",
    iv.toString("base64"),
    tag.toString("base64"),
    ciphertext.toString("base64")
  ].join(":");
}
