import { createCipheriv, randomBytes } from "node:crypto";

import { describe, expect, it } from "vitest";

import type { QueryExecutor } from "./runtime/postgres-pi-writer-deps.js";
import { createWorkerActivityBundle } from "./worker.js";

class RecordingDb implements QueryExecutor {
  readonly queries: { text: string; values: readonly unknown[] }[] = [];
  closed = false;
  private readonly responses: Record<string, unknown>[][] = [];

  enqueue(rows: Record<string, unknown>[]): void {
    this.responses.push(rows);
  }

  async query<T extends Record<string, unknown>>(text: string, values: readonly unknown[] = []): Promise<{ rows: T[] }> {
    this.queries.push({ text, values });
    return { rows: (this.responses.shift() ?? []) as T[] };
  }

  async close(): Promise<void> {
    this.closed = true;
  }
}

const resolvedPayload = {
  tenant_id: "ten_1",
  project_id: "proj_1",
  run_id: "run_1",
  trace_id: "trace_1",
  requested_by: "usr_1",
  mode: "draft",
  instruction: "写下一场雨夜谈判",
  options: {
    module_key: "writer_composer",
    llm_resolution: {
      module_key: "writer_composer",
      channel_id: "channel-1",
      model_id: "model-1",
      provider: "openai-compatible",
      base_url: "https://llm.example.test/v1",
      credential_ref: "channel-1",
      supports_tools: true,
      supports_json: true,
      settings: {}
    }
  }
};

describe("createWorkerActivityBundle", () => {
  it("keeps the activity fail-closed when production runtime config is absent", async () => {
    const bundle = await createWorkerActivityBundle({ env: {} });

    const result = await bundle.activities.runPiWriterRunActivity(resolvedPayload);

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_PROVIDER_ERROR");
  });

  it("uses DB-backed fail-closed writes when the database is configured but the credential key is absent", async () => {
    const db = new RecordingDb();
    db.enqueue([{ inserted: "1" }]);
    db.enqueue([{ writer_updated: "1", workflow_updated: "1" }]);
    db.enqueue([{ encrypted_api_key: "aes-256-gcm:v1:ciphertext" }]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([{ inserted: "1" }]);
    db.enqueue([{ writer_updated: "1", workflow_updated: "1" }]);
    const calls: string[] = [];

    const bundle = await createWorkerActivityBundle({
      env: {
        DATABASE_URL: "postgres://mirofish:test@localhost:5432/mirofish"
      },
      createDb: async (databaseUrl) => {
        calls.push(`db:${databaseUrl}`);
        return db;
      },
      composeDraft: async (request) => {
        calls.push(`compose:${request.run_id}`);
        return { content: "should not compose without a credential key" };
      }
    });

    const result = await bundle.activities.runPiWriterRunActivity(resolvedPayload);
    await bundle.close();

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_PROVIDER_ERROR");
    expect(result.error?.message).toBe("Pi writer credential resolution failed");
    expect(calls).toEqual(["db:postgres://mirofish:test@localhost:5432/mirofish"]);
    expect(db.queries.map((query) => query.text)).toEqual([
      expect.stringContaining("INSERT INTO workflow_events"),
      expect.stringContaining("UPDATE writer_runs"),
      expect.stringContaining("FROM llm_channels"),
      expect.stringContaining("INSERT INTO llm_activity"),
      expect.stringContaining("INSERT INTO agent_traces"),
      expect.stringContaining("INSERT INTO agent_trace_events"),
      expect.stringContaining("INSERT INTO workflow_events"),
      expect.stringContaining("UPDATE writer_runs")
    ]);
    expect(JSON.stringify(db.queries)).not.toContain("sk-live");
    expect(db.closed).toBe(true);
  });

  it("wires DB-backed deps, explicit decryption, and composer when production config is present", async () => {
    const key = randomBytes(32);
    const db = new RecordingDb();
    db.enqueue([{ inserted: "1" }]);
    db.enqueue([{ writer_updated: "1", workflow_updated: "1" }]);
    db.enqueue([{ encrypted_api_key: encryptCredential("sk-live", key) }]);
    db.enqueue([]);
    db.enqueue([{ max_concurrency: 1 }]);
    db.enqueue([{ lock_id: "lock-1", lock_mode: "slot:0" }]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([{ draft_id: "draft-1" }]);
    db.enqueue([{ inserted: "1" }]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([]);
    db.enqueue([{ inserted: "1" }]);
    db.enqueue([{ writer_updated: "1", workflow_updated: "1" }]);
    const calls: string[] = [];

    const bundle = await createWorkerActivityBundle({
      env: {
        DATABASE_URL: "postgres://mirofish:test@localhost:5432/mirofish",
        LLM_CREDENTIAL_ENCRYPTION_KEY: key.toString("base64")
      },
      createDb: async (databaseUrl) => {
        calls.push(`db:${databaseUrl}`);
        return db;
      },
      composeDraft: async (request) => {
        calls.push(`compose:${request.apiKey}:${request.run_id}`);
        return {
          content: "雨敲在谈判桌边，沉默像一根绷紧的线。",
          usage: { prompt_tokens: 11, completion_tokens: 17 }
        };
      }
    });

    const result = await bundle.activities.runPiWriterRunActivity(resolvedPayload);
    await bundle.close();

    expect(result).toEqual({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      status: "completed",
      draft_id: "draft-1",
      usage: { prompt_tokens: 11, completion_tokens: 17 }
    });
    expect(calls).toEqual([
      "db:postgres://mirofish:test@localhost:5432/mirofish",
      "compose:sk-live:run_1"
    ]);
    expect(db.queries.map((query) => query.text)).toEqual([
      expect.stringContaining("INSERT INTO workflow_events"),
      expect.stringContaining("UPDATE writer_runs"),
      expect.stringContaining("FROM llm_channels"),
      expect.stringContaining("DELETE FROM resource_locks"),
      expect.stringContaining("SELECT max_concurrency"),
      expect.stringContaining("INSERT INTO resource_locks"),
      expect.stringContaining("INSERT INTO agent_traces"),
      expect.stringContaining("INSERT INTO agent_trace_events"),
      expect.stringContaining("INSERT INTO agent_traces"),
      expect.stringContaining("INSERT INTO agent_trace_events"),
      expect.stringContaining("DELETE FROM resource_locks"),
      expect.stringContaining("INSERT INTO writer_drafts"),
      expect.stringContaining("INSERT INTO workflow_events"),
      expect.stringContaining("INSERT INTO llm_activity"),
      expect.stringContaining("INSERT INTO usage_events"),
      expect.stringContaining("INSERT INTO agent_traces"),
      expect.stringContaining("INSERT INTO agent_trace_events"),
      expect.stringContaining("INSERT INTO agent_traces"),
      expect.stringContaining("INSERT INTO agent_trace_events"),
      expect.stringContaining("INSERT INTO workflow_events"),
      expect.stringContaining("UPDATE writer_runs")
    ]);
    expect(db.queries[0]?.text).toContain("INSERT INTO workflow_events");
    expect(JSON.stringify(db.queries)).not.toContain("sk-live");
    expect(db.closed).toBe(true);
  });
});

function encryptCredential(plaintext: string, key: Buffer): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  return [
    "aes-256-gcm",
    "v1",
    iv.toString("base64"),
    cipher.getAuthTag().toString("base64"),
    ciphertext.toString("base64")
  ].join(":");
}
