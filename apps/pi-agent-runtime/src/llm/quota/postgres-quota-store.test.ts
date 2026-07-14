import { describe, expect, it } from "vitest";

import {
  createPostgresQuotaStore,
  type QuotaQueryExecutor
} from "./postgres-quota-store.js";

class RecordingQuotaDb implements QuotaQueryExecutor {
  readonly queries: Array<{
    text: string;
    values: readonly unknown[];
    context?: { tenant_id: string; project_id?: string };
  }> = [];
  private readonly responses: Array<Record<string, unknown>[] | Error> = [];

  enqueue(response: Record<string, unknown>[] | Error): void {
    this.responses.push(response);
  }

  async query<T extends Record<string, unknown>>(
    text: string,
    values: readonly unknown[] = [],
    context?: { tenant_id: string; project_id?: string }
  ): Promise<{ rows: T[] }> {
    this.queries.push({ text, values, context });
    const response = this.responses.shift() ?? [];
    if (response instanceof Error) throw response;
    return { rows: response as T[] };
  }
}

const reserveRequest = {
  tenant_id: "tenant-1",
  project_id: "project-1",
  run_id: "run-1",
  module_key: "writer_orchestrator",
  channel_id: "channel-1",
  model_id: "model-1",
  provider_call_id: "pi-writer:v1:writer_orchestrator:orchestrator:0:hash",
  reserved_tokens: 4096,
  reserved_cost_micros: 16384,
  pricing_status: "billing_ready" as const,
  ttl_seconds: 300
};

describe("Postgres Pi writer quota store", () => {
  it("atomically recovers stale reservations, locks every applicable policy, and reserves capacity", async () => {
    const db = new RecordingQuotaDb();
    db.enqueue([{
      decision: "reserved",
      reservation_id: "reservation-1",
      provider_call_id: reserveRequest.provider_call_id,
      status: "reserved",
      expires_at: "2026-07-10T12:05:00.000Z"
    }]);
    const store = createPostgresQuotaStore(db);

    const reservation = await store.reserve(reserveRequest);

    expect(reservation).toEqual({
      reservation_id: "reservation-1",
      provider_call_id: reserveRequest.provider_call_id,
      status: "reserved",
      expires_at: "2026-07-10T12:05:00.000Z"
    });
    expect(db.queries).toHaveLength(1);
    const query = db.queries[0]!;
    expect(query.context).toEqual({ tenant_id: "tenant-1", project_id: "project-1" });
    for (const fragment of [
      "UPDATE llm_quota_reservations",
      "status = 'expired'",
      "FROM llm_quota_policies",
      "scope_type = 'tenant'",
      "scope_type = 'project'",
      "scope_type = 'module'",
      "pg_advisory_xact_lock",
      "usage_type = 'llm_tokens'",
      "usage_type = 'llm_cost_micros'",
      "status = 'reserved'",
      "INSERT INTO llm_quota_reservations",
      "provider_call_id"
    ]) {
      expect(query.text).toContain(fragment);
    }
    expect(query.values).toEqual([
      "tenant-1", "project-1", "run-1", "writer_orchestrator", "channel-1", "model-1",
      reserveRequest.provider_call_id, 4096, 16384, true, 300
    ]);
  });

  it.each([
    ["policy_unavailable", "LLM_QUOTA_POLICY_UNAVAILABLE"],
    ["pricing_unavailable", "LLM_QUOTA_PRICING_UNAVAILABLE"],
    ["tokens_exceeded", "LLM_QUOTA_TOKENS_EXCEEDED"],
    ["cost_exceeded", "LLM_QUOTA_COST_EXCEEDED"],
    ["concurrency_exceeded", "LLM_QUOTA_CONCURRENCY_EXCEEDED"],
    ["provider_call_conflict", "LLM_PROVIDER_CALL_CONFLICT"],
    ["reservation_closed", "LLM_QUOTA_RESERVATION_CLOSED"]
  ])("maps reserve decision %s to stable error %s", async (decision, code) => {
    const db = new RecordingQuotaDb();
    db.enqueue([{ decision }]);
    const store = createPostgresQuotaStore(db);

    await expect(store.reserve(reserveRequest)).rejects.toThrow(`${code}:`);
  });

  it("reserve SQL reopens released/expired rows for the same provider_call_id", async () => {
    const db = new RecordingQuotaDb();
    db.enqueue([{
      decision: "reserved",
      reservation_id: "reservation-reopened",
      provider_call_id: reserveRequest.provider_call_id,
      status: "reserved",
      expires_at: "2026-07-10T12:05:00.000Z"
    }]);
    const store = createPostgresQuotaStore(db);
    await expect(store.reserve(reserveRequest)).resolves.toMatchObject({
      reservation_id: "reservation-reopened",
      status: "reserved"
    });
    const query = db.queries[0]!;
    expect(query.text).toContain("THEN 'reopen'");
    expect(query.text).toContain("status IN ('released', 'expired')");
    expect(query.text).toContain("status = 'reserved'");
  });

  it("recognizes an exactly matching finalized provider call without reopening it", async () => {
    const db = new RecordingQuotaDb();
    db.enqueue([{
      decision: "finalized",
      reservation_id: "reservation-1",
      provider_call_id: reserveRequest.provider_call_id,
      status: "finalized",
      expires_at: "2026-07-10T12:05:00.000Z",
      actual_prompt_tokens: "11",
      actual_completion_tokens: "17",
      actual_cost_micros: "4500"
    }]);
    const store = createPostgresQuotaStore(db);

    await expect(store.reserve(reserveRequest)).resolves.toMatchObject({
      status: "finalized",
      actual_prompt_tokens: 11,
      actual_completion_tokens: 17,
      actual_cost_micros: 4500
    });
  });

  it("finalizes reservation and token/cost usage in one idempotent statement", async () => {
    const db = new RecordingQuotaDb();
    db.enqueue([{ decision: "finalized" }]);
    const store = createPostgresQuotaStore(db);

    await store.finalize({
      tenant_id: "tenant-1",
      project_id: "project-1",
      reservation_id: "reservation-1",
      provider_call_id: reserveRequest.provider_call_id,
      prompt_tokens: 11,
      completion_tokens: 17,
      actual_cost_micros: 4500,
      pricing_status: "billing_ready"
    });

    expect(db.queries).toHaveLength(1);
    const query = db.queries[0]!;
    expect(query.context).toEqual({ tenant_id: "tenant-1", project_id: "project-1" });
    expect(query.text).toContain("FOR UPDATE");
    expect(query.text).toContain("actual_prompt_tokens");
    expect(query.text).toContain("actual_completion_tokens");
    expect(query.text).toContain("actual_cost_micros");
    expect(query.text.match(/INSERT INTO usage_events/g)).toHaveLength(2);
    expect(query.text).toContain("'llm_tokens'");
    expect(query.text).toContain("'llm_cost_micros'");
    expect(query.text).toContain("provider_call_id");
    expect(query.values).toEqual([
      "tenant-1", "project-1", "reservation-1", reserveRequest.provider_call_id,
      11, 17, 4500, "billing_ready"
    ]);
  });

  it("releases unused reservations idempotently and hides database failures", async () => {
    const db = new RecordingQuotaDb();
    db.enqueue([{ decision: "released" }]);
    db.enqueue(new Error("sql=UPDATE llm_quota_reservations secret-row"));
    const store = createPostgresQuotaStore(db);
    const request = {
      tenant_id: "tenant-1",
      project_id: "project-1",
      reservation_id: "reservation-1",
      provider_call_id: reserveRequest.provider_call_id
    };

    await expect(store.release(request)).resolves.toBeUndefined();
    expect(db.queries[0]?.text).toContain("status = 'released'");
    expect(db.queries[0]?.text).toContain("status = 'reserved'");
    await expect(store.release(request)).rejects.toThrow("LLM_QUOTA_BACKEND_FAILED: LLM quota backend failed");
  });
});
