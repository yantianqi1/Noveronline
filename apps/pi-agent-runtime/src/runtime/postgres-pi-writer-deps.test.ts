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
      confidence: 0.9
    }]);
    db.enqueue([{
      entity_id: "entity-1",
      canonical_name: "Lin",
      entity_type: "character",
      importance: "primary",
      state_summary: "Hiding an injury.",
      aliases: ["Captain Lin"]
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
      worldline_path_ids: []
    };

    await expect(deps.executeWriterTool!({ ...request, tool_name: "query_world_rules" })).resolves.toEqual({
      rules: [{
        rule_evidence_id: "rule-1",
        rule_text: "Magic always has a cost.",
        category: "magic",
        confidence: 0.9
      }]
    });
    await expect(deps.executeWriterTool!({ ...request, tool_name: "query_character_profile" })).resolves.toEqual({
      profiles: [{
        entity_id: "entity-1",
        canonical_name: "Lin",
        entity_type: "character",
        importance: "primary",
        state_summary: "Hiding an injury.",
        aliases: ["Captain Lin"]
      }]
    });

    expect(db.queries).toHaveLength(2);
    for (const query of db.queries) {
      expect(query.context).toEqual({ tenant_id: "ten_1", project_id: "proj_1" });
      expect(query.values).toEqual(["ten_1", "proj_1"]);
      expect(query.text).toMatch(/WHERE .*tenant_id = \$1.*project_id = \$2/s);
      expect(query.text).not.toMatch(/\b(?:INSERT|UPDATE|DELETE)\b/);
    }
    expect(db.queries[0]?.text).toContain("FROM world_rule_evidence");
    expect(db.queries[0]?.text).toContain("confidence::double precision AS confidence");
    expect(db.queries[1]?.text).toContain("FROM entities");
    expect(db.queries[1]?.text).toContain("entity_aliases");
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
