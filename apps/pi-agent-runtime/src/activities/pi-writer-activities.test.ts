import { describe, expect, it } from "vitest";

import {
  createPiWriterRunActivity,
  runPiWriterRunActivity,
  type ProviderStageCheckpoint,
  type WriterToolName
} from "./pi-writer-activities.js";
import { stableProviderCallId } from "../llm/quota/provider-call.js";

const basePayload = {
  tenant_id: "ten_1",
  project_id: "proj_1",
  run_id: "run_1",
  trace_id: "trace_1",
  requested_by: "usr_1",
  mode: "draft",
  instruction: "写下一场雨夜谈判",
  options: {
    module_key: "writer_composer",
    source: "character_console",
    character_interaction_id: "interaction-1",
    target_chapter_id: "chapter-1",
    target_scene_id: "scene-1"
  }
};

describe("runPiWriterRunActivity", () => {
  it("quota-gates both provider stages with stable identities and finalizes actual usage once", async () => {
    const lifecycle: string[] = [];
    const providerCalls: string[] = [];
    const finalized: Array<{ provider_call_id: string; prompt_tokens: number; completion_tokens: number }> = [];
    const activities: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
        supports_tools: module_key === "writer_orchestrator", supports_json: true,
        settings: { quota_reserved_tokens: 1000, input_cost: 1, output_cost: 2 }
      }),
      resolveCredential: async () => ({ apiKey: "private-key" }),
      reserveLLMQuota: async (request) => {
        lifecycle.push(`reserve:${request.module_key}`);
        return {
          reservation_id: `reservation-${request.module_key}`,
          provider_call_id: request.provider_call_id,
          status: "reserved",
          expires_at: "2026-07-10T12:05:00.000Z"
        };
      },
      acquireLLMLease: async (request) => {
        lifecycle.push(`lease:${request.module_key}`);
        return { lease_id: `lease-${request.module_key}`, channel_id: request.channel_id, lock_mode: "slot:0" };
      },
      releaseLLMLease: async (request) => { lifecycle.push(`release-lease:${request.channel_id}`); },
      releaseLLMQuota: async (request) => { lifecycle.push(`release-quota:${request.provider_call_id}`); },
      finalizeLLMQuota: async (request) => {
        lifecycle.push(`finalize:${request.provider_call_id}`);
        finalized.push(request);
      },
      executeWriterTool: async () => ({ authoritative: true }),
      orchestrateWritingBrief: async (request) => {
        lifecycle.push("provider:writer_orchestrator");
        providerCalls.push(request.provider_call_id ?? "");
        return { writing_brief: "private brief", usage: { prompt_tokens: 3, completion_tokens: 5, cost_estimate: 0.000013 } };
      },
      composeDraft: async (request) => {
        lifecycle.push("provider:writer_composer");
        providerCalls.push(request.provider_call_id ?? "");
        return { content: "candidate draft", usage: { prompt_tokens: 7, completion_tokens: 11, cost_estimate: 0.000029 } };
      },
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async (request) => { activities.push(`${request.module_key}:${request.provider_call_id}`); },
      recordUsageEvent: async () => { throw new Error("direct usage write must be owned by quota finalize"); },
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed", draft_id: "draft-1" });
    expect(providerCalls).toHaveLength(2);
    expect(providerCalls[0]).toMatch(/^pi-writer:v1:writer_orchestrator:orchestrator:0:/);
    expect(providerCalls[1]).toMatch(/^pi-writer:v1:writer_composer:composer:0:/);
    expect(new Set(providerCalls)).toHaveLength(2);
    expect(finalized.map(({ provider_call_id, prompt_tokens, completion_tokens }) => ({ provider_call_id, prompt_tokens, completion_tokens }))).toEqual([
      { provider_call_id: providerCalls[0], prompt_tokens: 3, completion_tokens: 5 },
      { provider_call_id: providerCalls[1], prompt_tokens: 7, completion_tokens: 11 }
    ]);
    expect(activities).toEqual([
      `writer_orchestrator:${providerCalls[0]}`,
      `writer_composer:${providerCalls[1]}`
    ]);
    expect(lifecycle).toEqual([
      "reserve:writer_orchestrator", "lease:writer_orchestrator", "provider:writer_orchestrator",
      `finalize:${providerCalls[0]}`, "release-lease:writer_orchestrator-channel",
      "reserve:writer_composer", "lease:writer_composer", "provider:writer_composer",
      `finalize:${providerCalls[1]}`, "release-lease:writer_composer-channel"
    ]);
  });

  it("releases reservation and lease when provider usage is missing", async () => {
    const lifecycle: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
        supports_tools: module_key === "writer_orchestrator", supports_json: true,
        settings: { quota_reserved_tokens: 1000 }
      }),
      resolveCredential: async () => ({ apiKey: "private-key" }),
      reserveLLMQuota: async (request) => {
        lifecycle.push("reserve");
        return {
          reservation_id: "reservation-1", provider_call_id: request.provider_call_id,
          status: "reserved", expires_at: "2026-07-10T12:05:00.000Z"
        };
      },
      finalizeLLMQuota: async () => { lifecycle.push("finalize"); },
      releaseLLMQuota: async () => { lifecycle.push("release-quota"); },
      acquireLLMLease: async (request) => {
        lifecycle.push("lease");
        return { lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" };
      },
      releaseLLMLease: async () => { lifecycle.push("release-lease"); },
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async () => {
        lifecycle.push("provider");
        return { writing_brief: "brief without usage" };
      },
      composeDraft: async () => { throw new Error("composer must not run"); },
      saveDraftRevision: async () => ({ draft_id: "unreachable" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({
      status: "failed",
      error: { code: "LLM_PROVIDER_USAGE_MISSING", message: "Pi writer provider usage is unavailable" }
    });
    expect(lifecycle).toEqual(["reserve", "lease", "provider", "release-lease", "release-quota"]);
  });

  it("returns a completed candidate replay before resolving bindings or calling providers", async () => {
    const called: string[] = [];
    const activity = createPiWriterRunActivity({
      findCompletedWriterRun: async () => ({
        draft_id: "draft-existing",
        usage: { prompt_tokens: 10, completion_tokens: 20, cost_estimate: 0.001 }
      }),
      resolveModuleBinding: async () => { called.push("binding"); throw new Error("unreachable"); },
      orchestrateWritingBrief: async () => { called.push("provider"); return { writing_brief: "unreachable" }; },
      executeWriterTool: async () => ({}),
      resolveCredential: async () => ({ apiKey: "unreachable" }),
      reserveLLMQuota: async () => { throw new Error("unreachable"); },
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async () => { throw new Error("unreachable"); },
      releaseLLMLease: async () => undefined,
      composeDraft: async () => { throw new Error("unreachable"); },
      saveDraftRevision: async () => ({ draft_id: "unreachable" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    });

    await expect(activity(basePayload)).resolves.toMatchObject({
      status: "completed",
      draft_id: "draft-existing",
      usage: { prompt_tokens: 10, completion_tokens: 20 }
    });
    expect(called).toEqual([]);
  });

  it("fails closed without re-calling a provider when the stable reservation is already finalized", async () => {
    let providerCalls = 0;
    let quotaReleases = 0;
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
        supports_tools: true, supports_json: true, settings: { quota_reserved_tokens: 1000 }
      }),
      resolveCredential: async () => ({ apiKey: "private-key" }),
      reserveLLMQuota: async (request) => ({
        reservation_id: "reservation-final", provider_call_id: request.provider_call_id,
        status: "finalized", expires_at: "2026-07-10T12:05:00.000Z",
        actual_prompt_tokens: 3, actual_completion_tokens: 5
      }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => { quotaReleases += 1; },
      acquireLLMLease: async () => { throw new Error("lease must not run"); },
      releaseLLMLease: async () => undefined,
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async () => { providerCalls += 1; return { writing_brief: "unreachable" }; },
      composeDraft: async () => ({ content: "unreachable" }),
      saveDraftRevision: async () => ({ draft_id: "unreachable" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "failed", error: { code: "LLM_PROVIDER_CALL_ALREADY_FINALIZED" } });
    expect(providerCalls).toBe(0);
    expect(quotaReleases).toBe(0);
  });

  it("recovers finalized provider stages from private activity checkpoints without re-calling providers", async () => {
    let providerCalls = 0;
    const releasedLeases: string[] = [];
    const checkpoints = new Map<string, ProviderStageCheckpoint>();
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-credential`,
        supports_tools: module_key === "writer_orchestrator", supports_json: true,
        settings: { quota_reserved_tokens: 1000 }
      }),
      resolveCredential: async () => ({ apiKey: "private-key" }),
      reserveLLMQuota: async (request) => ({
        reservation_id: `reservation-${request.module_key}`,
        provider_call_id: request.provider_call_id,
        status: "finalized",
        expires_at: "2026-07-10T12:05:00.000Z",
        actual_prompt_tokens: 3,
        actual_completion_tokens: 5
      }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async () => { throw new Error("checkpoint replay must not acquire a new lease"); },
      releaseLLMLease: async (request) => { releasedLeases.push(request.lease_id); },
      loadProviderStageCheckpoint: async (providerCallID) => checkpoints.get(providerCallID),
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async () => { providerCalls += 1; return { writing_brief: "unreachable" }; },
      composeDraft: async () => { providerCalls += 1; return { content: "unreachable" }; },
      saveDraftRevision: async () => ({ draft_id: "draft-recovered" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    });
    for (const [moduleKey, stage, result] of [
      ["writer_orchestrator", "orchestrator", { writing_brief: "checkpoint brief", usage: { prompt_tokens: 3, completion_tokens: 5 } }],
      ["writer_composer", "composer", { content: "checkpoint candidate", usage: { prompt_tokens: 7, completion_tokens: 11 } }]
    ] as const) {
      const providerCallID = stableProviderCallId({
        tenant_id: basePayload.tenant_id,
        project_id: basePayload.project_id,
        run_id: basePayload.run_id,
        module_key: moduleKey,
        stage,
        call_index: 0
      });
      checkpoints.set(providerCallID, {
        provider_call_id: providerCallID,
        result,
        reservation: {
          reservation_id: `reservation-${moduleKey}`,
          provider_call_id: providerCallID,
          status: "finalized",
          expires_at: "2026-07-10T12:05:00.000Z"
        },
        lease: { lease_id: `lease-${moduleKey}`, channel_id: `${moduleKey}-channel`, lock_mode: "slot:0" }
      });
    }

    await expect(activity(basePayload)).resolves.toMatchObject({ status: "completed", draft_id: "draft-recovered" });
    expect(providerCalls).toBe(0);
    expect(releasedLeases).toEqual(["lease-writer_orchestrator", "lease-writer_composer"]);
  });

  it("runs distinct bound orchestrator and composer stages with tool trace, token events, and one candidate draft", async () => {
    const bindings: string[] = [];
    const activities: string[] = [];
    const workflows: Array<{ type: string; payload: Record<string, unknown>; key?: string }> = [];
    const traces: string[] = [];
    const saved: string[] = [];
    const orchestratorTools: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => {
        bindings.push(module_key);
        return {
          module_key,
          channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
          base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
          supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
        };
      },
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({
        reservation_id: `reservation-${request.module_key}`,
        provider_call_id: request.provider_call_id,
        status: "reserved",
        expires_at: "2026-07-10T12:05:00.000Z"
      }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      executeWriterTool: async ({ tool_name }) => {
        if (tool_name === "query_world_rules") {
          return {
            rules: [{
              rule_evidence_id: "rule-1",
              rule_text: "Private rule body",
              evidence_text: "Private source excerpt",
              category: "magic",
              confidence: 0.9
            }]
          };
        }
        if (tool_name === "query_character_profile") {
          return {
            profiles: [{
              entity_id: "entity-1",
              canonical_name: "Lin",
              entity_type: "character",
              importance: "primary",
              state_summary: "Hiding an injury.",
              aliases: ["Private Alias"]
            }]
          };
        }
        return { tool_name, authoritative: true };
      },
      orchestrateWritingBrief: async (request) => {
        orchestratorTools.push(...request.tool_names);
        const execute = async (toolName: WriterToolName, toolCallId: string) => {
          await request.onAgentEvent?.({ type: "tool_execution_start", toolCallId, toolName, args: {} });
          const details = await request.executeTool(toolName, toolCallId);
          await request.onAgentEvent?.({
            type: "tool_execution_end", toolCallId, toolName,
            result: { content: [{ type: "text", text: "private tool context" }], details }, isError: false
          });
        };
        await execute("query_project_context", "call-project");
        await execute("query_world_rules", "call-world-rules");
        await execute("query_character_profile", "call-character-profile");
        return { writing_brief: "private brief", usage: { prompt_tokens: 3, completion_tokens: 5 } };
      },
      composeDraft: async (request) => {
        expect(request.writing_brief).toBe("private brief");
        await request.onToken?.("雨夜");
        await request.onToken?.("谈判");
        return { content: "雨夜谈判正文", usage: { prompt_tokens: 7, completion_tokens: 11 } };
      },
      saveDraftRevision: async (request) => {
        saved.push(`${request.status}:${request.chapter_id}:${request.scene_id}:${request.content}`);
        return { draft_id: "draft-1" };
      },
      recordLLMActivity: async (request) => { activities.push(`${request.module_key}:${request.status}`); },
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async (request) => { traces.push(`${request.module_key}:${request.event_type}:${request.redaction_level}`); },
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type, payload: request.payload, key: request.idempotency_key }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed", draft_id: "draft-1" });
    expect(bindings).toEqual(["writer_orchestrator", "writer_composer"]);
    expect(orchestratorTools).toEqual([
      "query_project_context",
      "query_chapter_scene",
      "query_assets",
      "search_assets",
      "search_manuscript",
      "fuse_recall",
      "query_world_rules",
      "query_character_profile",
      "query_graph_neighbors",
      "query_worldline_paths",
      "query_manuscript_context"
    ]);
    expect(activities).toEqual(["writer_orchestrator:completed", "writer_composer:completed"]);
    expect(saved).toEqual(["candidate:chapter-1:scene-1:雨夜谈判正文"]);
    expect(workflows.map((event) => event.type)).toEqual([
      "writer.run.started",
      "writer.tool.started", "writer.tool.completed",
      "writer.tool.started", "writer.tool.completed",
      "writer.tool.started", "writer.tool.completed",
      "writer.token", "writer.token",
      "writer.draft.saved", "writer.run.completed"
    ]);
    expect(workflows.map((event) => event.key)).toEqual([
      "run:started",
      "tool:call-project:started", "tool:call-project:completed",
      "tool:call-world-rules:started", "tool:call-world-rules:completed",
      "tool:call-character-profile:started", "tool:call-character-profile:completed",
      "composer:token:1", "composer:token:2",
      "draft:saved", "run:completed"
    ]);
    const worldRulePublic = workflows.find((event) => event.key === "tool:call-world-rules:completed")?.payload;
    expect(worldRulePublic?.result).toEqual({
      items: [{ rule_evidence_id: "rule-1", category: "magic", confidence: 0.9 }]
    });
    expect(JSON.stringify(worldRulePublic)).not.toContain("Private rule body");
    expect(JSON.stringify(worldRulePublic)).not.toContain("Private source excerpt");
    const characterPublic = workflows.find((event) => event.key === "tool:call-character-profile:completed")?.payload;
    expect(characterPublic?.result).toEqual({
      items: [{
        entity_id: "entity-1",
        canonical_name: "Lin",
        entity_type: "character",
        importance: "primary",
        state_summary: "Hiding an injury."
      }]
    });
    expect(JSON.stringify(characterPublic)).not.toContain("Private Alias");
    expect(traces).toContain("writer_orchestrator:tool_call:full");
    expect(traces).toContain("writer_orchestrator:tool_result:full");
    expect(traces).toContain("writer_composer:assistant_message:full");
  });

  it("runs the retrieval planner stage and steers the orchestrator with the plan", async () => {
    const bindings: string[] = [];
    const workflows: Array<{ type: string; payload: Record<string, unknown>; key?: string }> = [];
    const plans: Array<Record<string, unknown>> = [];
    let orchestratorPlan: unknown;
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => {
        bindings.push(module_key);
        return {
          module_key,
          channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
          base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
          supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
        };
      },
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({
        reservation_id: `reservation-${request.module_key}`,
        provider_call_id: request.provider_call_id,
        status: "reserved",
        expires_at: "2026-07-10T12:05:00.000Z"
      }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      planRetrieval: async (request) => {
        plans.push({ module_key: request.module_key, instruction: request.instruction });
        return {
          plan: {
            intent: "continue_scene",
            coverage: ["characters:沈翠花", "world_rules:师门戒律"],
            queries: [
              { channel: "hybrid", text: "师门 复命 戒律", asset_types: ["world_rule"], top_k: 8 },
              { channel: "keyed", text: "沈翠花 师父" }
            ]
          },
          usage: { prompt_tokens: 2, completion_tokens: 3 }
        };
      },
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async (request) => {
        orchestratorPlan = request.retrieval_plan;
        return { writing_brief: "planned brief", usage: { prompt_tokens: 3, completion_tokens: 5 } };
      },
      composeDraft: async () => ({ content: "正文", usage: { prompt_tokens: 7, completion_tokens: 11 } }),
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type, payload: request.payload, key: request.idempotency_key }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed", draft_id: "draft-1" });
    // Planner binding resolved before orchestrator/composer.
    expect(bindings[0]).toBe("writer_retrieval_planner");
    expect(plans[0]?.instruction).toBe("写下一场雨夜谈判");
    // The plan steered the orchestrator.
    expect(orchestratorPlan).toMatchObject({ intent: "continue_scene" });
    expect((orchestratorPlan as { queries: unknown[] }).queries).toHaveLength(2);
    // And it was persisted as a retrieval_plan.completed event.
    const planEvent = workflows.find((w) => w.type === "writer.retrieval_plan.completed");
    expect(planEvent?.payload.intent).toBe("continue_scene");
    expect(planEvent?.payload.queries).toHaveLength(2);
  });

  it("records retrieval_plan.skipped and proceeds when the planner is unbound", async () => {
    const workflows: Array<{ type: string }> = [];
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => {
        if (module_key === "writer_retrieval_planner") throw new Error("LLM_MODULE_UNBOUND: writer_retrieval_planner module is not bound");
        return {
          module_key,
          channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
          base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
          supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
        };
      },
      planRetrieval: async () => { throw new Error("should not be called"); },
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({ reservation_id: `r-${request.module_key}`, provider_call_id: request.provider_call_id, status: "reserved", expires_at: "2026-07-10T12:05:00.000Z" }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async (request) => {
        expect(request.retrieval_plan).toBeUndefined();
        return { writing_brief: "brief", usage: { prompt_tokens: 1, completion_tokens: 1 } };
      },
      composeDraft: async () => ({ content: "正文", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed" });
    expect(workflows.some((w) => w.type === "writer.retrieval_plan.skipped")).toBe(true);
  });

  it("trims over-budget recall and records context_budget.trimmed", async () => {
    const workflows: Array<{ type: string; payload: Record<string, unknown> }> = [];
    let packedAssets: unknown;
    const big = "很长的设定内容".repeat(40); // heavy CJK content to blow a tiny budget
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
        supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
      }),
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({ reservation_id: `r-${request.module_key}`, provider_call_id: request.provider_call_id, status: "reserved", expires_at: "2026-07-10T12:05:00.000Z" }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      planRetrieval: async () => ({
        plan: { intent: "continue_scene", coverage: [], queries: [{ channel: "hybrid", text: "x" }], budget: { max_context_tokens: 30 } },
        usage: { prompt_tokens: 1, completion_tokens: 1 }
      }),
      executeWriterTool: async ({ tool_name }) => {
        if (tool_name === "search_assets") {
          return {
            mode_used: "hybrid", degraded: false,
            assets: [
              { asset_id: "a1", title: "规则一", content_preview: big },
              { asset_id: "a2", title: "规则二", content_preview: big },
              { asset_id: "a3", title: "规则三", content_preview: big }
            ],
            citations: []
          };
        }
        return {};
      },
      orchestrateWritingBrief: async (request) => {
        const packedResult = await request.executeTool("search_assets", "call-search");
        packedAssets = (packedResult as { assets: unknown }).assets;
        return { writing_brief: "brief", usage: { prompt_tokens: 1, completion_tokens: 1 } };
      },
      composeDraft: async () => ({ content: "正文", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type, payload: request.payload }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed" });
    // Budget of 30 tokens cannot hold three ~600-token items; only some survive.
    expect((packedAssets as unknown[]).length).toBeLessThan(3);
    const trimEvent = workflows.find((w) => w.type === "writer.context_budget.trimmed");
    expect(trimEvent?.payload.budget_tokens).toBe(30);
    expect(Number(trimEvent?.payload.dropped_items)).toBeGreaterThan(0);
  });

  it("injects always_on canon as fuse_recall's top channel, untrimmed by the budget", async () => {
    const workflows: Array<{ type: string; payload: Record<string, unknown> }> = [];
    let fusedChannels: unknown;
    let loadCalled = false;
    const big = "很长的设定内容".repeat(60); // heavy recall that would blow a tiny budget
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
        supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
      }),
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({ reservation_id: `r-${request.module_key}`, provider_call_id: request.provider_call_id, status: "reserved", expires_at: "2026-07-10T12:05:00.000Z" }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      planRetrieval: async () => ({
        plan: { intent: "continue_scene", coverage: [], queries: [{ channel: "hybrid", text: "x" }], budget: { max_context_tokens: 10 } },
        usage: { prompt_tokens: 1, completion_tokens: 1 }
      }),
      loadAlwaysOnAssets: async () => {
        loadCalled = true;
        return {
          assets: [
            { asset_id: "law-1", asset_type: "world_rule", lifecycle: "canon", title: "世界铁律", content_preview: big }
          ]
        };
      },
      executeWriterTool: async ({ tool_name, tool_args }) => {
        if (tool_name === "fuse_recall") {
          fusedChannels = (tool_args as { channels?: unknown }).channels;
          return { fused: [], citations: [] };
        }
        return {};
      },
      orchestrateWritingBrief: async (request) => {
        // Tiny budget (10) + a heavy always_on asset: it must still reach fuse_recall
        // untrimmed, because constant canon never counts against the recall budget.
        await request.executeTool("fuse_recall", "call-fuse", { channels: [] });
        return { writing_brief: "brief", usage: { prompt_tokens: 1, completion_tokens: 1 } };
      },
      composeDraft: async () => ({ content: "正文", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type, payload: request.payload }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed" });
    expect(loadCalled).toBe(true);
    // always_on is prepended as the first (highest-priority) channel, content intact.
    const channels = fusedChannels as Array<{ channel: string; items: Array<{ asset_id: string; content_preview: string }> }>;
    expect(channels[0]?.channel).toBe("always_on");
    expect(channels[0]?.items[0]?.asset_id).toBe("law-1");
    expect(channels[0]?.items[0]?.content_preview).toBe(big);
  });

  it("treats always_on load failure as a visible no-op, not a run failure", async () => {
    const workflows: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
        supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
      }),
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({ reservation_id: `r-${request.module_key}`, provider_call_id: request.provider_call_id, status: "reserved", expires_at: "2026-07-10T12:05:00.000Z" }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      loadAlwaysOnAssets: async () => { throw new Error("assets table unreachable"); },
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async () => ({ writing_brief: "brief", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      composeDraft: async () => ({ content: "正文", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type, payload: request.payload }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed" });
    expect(workflows.some((w) => w.type === "writer.context_budget.trimmed" && typeof w.payload.always_on_error === "string")).toBe(true);
  });

  it("runs the consistency check and surfaces violations without failing the run", async () => {
    const workflows: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const canonUsed: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
        base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
        supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
      }),
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({ reservation_id: `r-${request.module_key}`, provider_call_id: request.provider_call_id, status: "reserved", expires_at: "2026-07-10T12:05:00.000Z" }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async () => ({ writing_brief: "brief", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      composeDraft: async () => ({ content: "沈翠花一剑斩了师父。", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      loadConsistencyCanon: async () => ({
        canon: [
          { kind: "world_rule", label: "师父不可杀", text: "师门戒律:不得伤害师长。" },
          { kind: "character_state", label: "师父", text: "健在,掌门。" }
        ]
      }),
      checkConsistency: async (request) => {
        canonUsed.push(...request.canon.map((c) => c.label));
        return {
          violations: [{ canon_label: "师父不可杀", conflict: "草稿写沈翠花斩了师父", severity: "major" }],
          usage: { prompt_tokens: 1, completion_tokens: 1 }
        };
      },
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type, payload: request.payload }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    // Run still completes; the violation is surfaced as an event, not an error.
    expect(result).toMatchObject({ status: "completed", draft_id: "draft-1" });
    expect(canonUsed).toContain("师父不可杀");
    const violationEvent = workflows.find((w) => w.type === "writer.consistency.violations");
    expect(violationEvent?.payload.major_count).toBe(1);
    expect((violationEvent?.payload.violations as unknown[]).length).toBe(1);
  });

  it("skips the consistency check visibly when the checker is unbound", async () => {
    const workflows: Array<{ type: string }> = [];
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => {
        if (module_key === "writer_consistency") throw new Error("LLM_MODULE_UNBOUND: writer_consistency module is not bound");
        return {
          module_key,
          channel_id: `${module_key}-channel`, model_id: `${module_key}-model`, provider: "openai-compatible",
          base_url: "http://127.0.0.1:1/v1", credential_ref: `${module_key}-channel`,
          supports_tools: module_key === "writer_orchestrator", supports_json: true, settings: {}
        };
      },
      resolveCredential: async ({ module_key }) => ({ apiKey: `key-for-${module_key}` }),
      reserveLLMQuota: async (request) => ({ reservation_id: `r-${request.module_key}`, provider_call_id: request.provider_call_id, status: "reserved", expires_at: "2026-07-10T12:05:00.000Z" }),
      finalizeLLMQuota: async () => undefined,
      releaseLLMQuota: async () => undefined,
      acquireLLMLease: async ({ channel_id }) => ({ lease_id: channel_id, channel_id, lock_mode: "slot:0" }),
      releaseLLMLease: async () => undefined,
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: async () => ({ writing_brief: "brief", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      composeDraft: async () => ({ content: "正文", usage: { prompt_tokens: 1, completion_tokens: 1 } }),
      loadConsistencyCanon: async () => { throw new Error("should not be called"); },
      checkConsistency: async () => { throw new Error("should not be called"); },
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async (request) => { workflows.push({ type: request.event_type }); },
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result).toMatchObject({ status: "completed" });
    expect(workflows.some((w) => w.type === "writer.consistency.skipped")).toBe(true);
  });

  it("fails the dual-stage run explicitly when writer_orchestrator is unbound", async () => {
    const activity = createPiWriterRunActivity({
      resolveModuleBinding: async ({ module_key }) => { throw new Error(`LLM_MODULE_UNBOUND: ${module_key} module is not bound`); },
      orchestrateWritingBrief: async () => ({ writing_brief: "unreachable" }),
      executeWriterTool: async () => ({}),
      resolveCredential: async () => ({ apiKey: "unreachable" }), acquireLLMLease: async () => ({ lease_id: "x", channel_id: "x", lock_mode: "x" }),
      composeDraft: async () => ({ content: "unreachable" }), releaseLLMLease: async () => undefined,
      saveDraftRevision: async () => ({ draft_id: "unreachable" }), recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined, recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined, updateWriterRunStatus: async () => undefined
    });

    const result = await activity(basePayload);

    expect(result.error).toEqual({ code: "LLM_MODULE_UNBOUND", message: "writer_orchestrator module is not bound" });
  });
  it("fails with LLM_MODULE_UNBOUND when the workflow payload has no resolved binding", async () => {
    const result = await runPiWriterRunActivity(basePayload);

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_MODULE_UNBOUND");
  });

  it("does not report missing binding once the Go control plane passed sanitized resolution", async () => {
    const result = await runPiWriterRunActivity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_PROVIDER_ERROR");
  });

  it("uses a stable public message when resolved credential is unavailable", async () => {
    const result = await runPiWriterRunActivity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_PROVIDER_ERROR");
    expect(result.error?.message).toBe("resolved LLM credential is unavailable");
    expect(result.error?.message).not.toContain("credential_ref");
  });

  it("uses credential resolver and provider before saving a candidate draft", async () => {
    const calls: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveCredential: async (request) => {
        calls.push(`credential:${request.credential_ref}:${request.run_id}`);
        return { apiKey: "sk-test" };
      },
      acquireLLMLease: async (request) => {
        calls.push(`lease:${request.channel_id}:${request.run_id}`);
        return { lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" };
      },
      composeDraft: async (request) => {
        calls.push(`compose:${request.apiKey}:${request.model_id}:${request.instruction}`);
        return {
          content: "雨敲在谈判桌边，沉默像一根绷紧的线。",
          usage: { prompt_tokens: 11, completion_tokens: 17 }
        };
      },
      releaseLLMLease: async (request) => {
        calls.push(`release:${request.lease_id}:${request.run_id}`);
      },
      saveDraftRevision: async (request) => {
        calls.push(`save:${request.status}:${request.content}`);
        return { draft_id: "draft-1" };
      },
      recordLLMActivity: async (request) => {
        calls.push(`activity:${request.status}:${request.prompt_tokens}:${request.completion_tokens}`);
      },
      recordUsageEvent: async (request) => {
        calls.push(`usage:${request.usage_type}:${request.quantity}:${request.unit}`);
      },
      recordAgentTraceEvent: async (request) => {
        calls.push(`trace:${request.event_order}:${request.event_type}:${request.redaction_level}:${request.trace_id}`);
      },
      recordWorkflowEvent: async (request) => {
        calls.push(`workflow:${request.event_type}:${request.run_id}`);
      },
      updateWriterRunStatus: async (request) => {
        calls.push(`status:${request.status}:${request.run_id}:${request.draft_id ?? ""}:${request.error?.code ?? ""}`);
      }
    });

    const result = await activity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    expect(result).toEqual({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      status: "completed",
      draft_id: "draft-1",
      usage: { prompt_tokens: 11, completion_tokens: 17 }
    });
    expect(calls).toEqual([
      "workflow:writer.run.started:run_1",
      "status:running:run_1::",
      "credential:credref-1:run_1",
      "lease:channel-1:run_1",
      "trace:1:prompt_snapshot:full:trace_1",
      "trace:2:llm_call_started:summary:trace_1",
      "compose:sk-test:model-1:写下一场雨夜谈判",
      "release:lease-1:run_1",
      "save:candidate:雨敲在谈判桌边，沉默像一根绷紧的线。",
      "workflow:writer.draft.saved:run_1",
      "activity:completed:11:17",
      "usage:llm_tokens:28:tokens",
      "trace:3:llm_call_completed:summary:trace_1",
      "trace:4:artifact_written:summary:trace_1",
      "workflow:writer.run.completed:run_1",
      "status:completed:run_1:draft-1:"
    ]);
  });

  it("passes module-specific max concurrency from binding settings to lease acquisition", async () => {
    const calls: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveCredential: async () => ({ apiKey: "sk-test" }),
      acquireLLMLease: async (request) => {
        calls.push(`module-limit:${request.module_max_concurrency ?? "none"}`);
        return { lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" };
      },
      composeDraft: async () => ({ content: "雨敲在谈判桌边，沉默像一根绷紧的线。" }),
      releaseLLMLease: async () => undefined,
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    });

    await activity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: { max_concurrency: 2 }
        }
      }
    });

    expect(calls).toContain("module-limit:2");
  });

  it("records failed llm activity when provider invocation fails", async () => {
    const calls: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveCredential: async (request) => {
        calls.push(`credential:${request.credential_ref}:${request.run_id}`);
        return { apiKey: "sk-test" };
      },
      acquireLLMLease: async (request) => {
        calls.push(`lease:${request.channel_id}:${request.run_id}`);
        return { lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" };
      },
      composeDraft: async (request) => {
        calls.push(`compose:${request.model_id}:${request.instruction}`);
        throw new Error("provider rejected request");
      },
      releaseLLMLease: async (request) => {
        calls.push(`release:${request.lease_id}:${request.run_id}`);
      },
      saveDraftRevision: async (request) => {
        calls.push(`save:${request.status}:${request.content}`);
        return { draft_id: "draft-1" };
      },
      recordLLMActivity: async (request) => {
        calls.push(`activity:${request.status}:${request.error?.code}:${request.error?.message}`);
      },
      recordUsageEvent: async (request) => {
        calls.push(`usage:${request.usage_type}:${request.quantity}`);
      },
      recordAgentTraceEvent: async (request) => {
        calls.push(`trace:${request.event_order}:${request.event_type}:${request.redaction_level}:${request.payload.error_code ?? ""}`);
      },
      recordWorkflowEvent: async (request) => {
        calls.push(`workflow:${request.event_type}:${request.payload.error_code ?? ""}`);
      },
      updateWriterRunStatus: async (request) => {
        calls.push(`status:${request.status}:${request.error?.code ?? ""}:${request.error?.message ?? ""}`);
      }
    });

    const result = await activity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_PROVIDER_ERROR");
    expect(calls).toEqual([
      "workflow:writer.run.started:",
      "status:running::",
      "credential:credref-1:run_1",
      "lease:channel-1:run_1",
      "trace:1:prompt_snapshot:full:",
      "trace:2:llm_call_started:summary:",
      "compose:model-1:写下一场雨夜谈判",
      "release:lease-1:run_1",
      "activity:failed:LLM_PROVIDER_ERROR:Pi writer provider call failed",
      "trace:3:error:summary:LLM_PROVIDER_ERROR",
      "workflow:writer.run.failed:LLM_PROVIDER_ERROR",
      "status:failed:LLM_PROVIDER_ERROR:Pi writer provider call failed"
    ]);
  });

  it("sanitizes provider failure messages before public result and persistence", async () => {
    const publicMessages: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveCredential: async () => ({ apiKey: "sk-test" }),
      acquireLLMLease: async (request) => ({ lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" }),
      composeDraft: async () => {
        throw new Error("provider rejected api_key=sk-live prompt=写下一场雨夜谈判 credential_ref=credref-1 draft=secret");
      },
      releaseLLMLease: async () => undefined,
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async (request) => {
        publicMessages.push(request.error?.message ?? "");
      },
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async (request) => {
        publicMessages.push(String(request.payload.message ?? ""));
      },
      recordWorkflowEvent: async (request) => {
        publicMessages.push(String(request.payload.message ?? ""));
      },
      updateWriterRunStatus: async (request) => {
        publicMessages.push(request.error?.message ?? "");
      }
    });

    const result = await activity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    publicMessages.push(result.error?.message ?? "");
    const serialized = JSON.stringify(publicMessages);
    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_PROVIDER_ERROR");
    expect(result.error?.message).toBe("Pi writer provider call failed");
    for (const forbidden of ["sk-live", "写下一场雨夜谈判", "credref-1", "credential_ref", "api_key", "secret"]) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("stabilizes credential failures before public result and failure persistence", async () => {
    const publicMessages: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveCredential: async () => {
        throw new Error("credential query failed api_key=sk-live credential_ref=credref-1 raw_text=secret");
      },
      acquireLLMLease: async (request) => ({ lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" }),
      composeDraft: async () => ({ content: "draft" }),
      releaseLLMLease: async () => undefined,
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async (request) => {
        publicMessages.push(request.error?.message ?? "");
      },
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async (request) => {
        publicMessages.push(String(request.payload.message ?? ""));
      },
      recordWorkflowEvent: async (request) => {
        publicMessages.push(String(request.payload.message ?? ""));
      },
      updateWriterRunStatus: async (request) => {
        publicMessages.push(request.error?.message ?? "");
      }
    });

    const result = await activity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    publicMessages.push(result.error?.message ?? "");
    expect(result.status).toBe("failed");
    expect(result.error?.message).toBe("Pi writer credential resolution failed");
    expect(publicMessages.every((message) => message === "Pi writer credential resolution failed" || message === "")).toBe(true);
    for (const forbidden of ["sk-live", "credref-1", "credential_ref", "api_key", "raw_text", "secret"]) {
      expect(JSON.stringify(publicMessages)).not.toContain(forbidden);
    }
  });

  it("stabilizes release and status failures without leaking secondary raw errors", async () => {
    const persistedMessages: string[] = [];
    const activity = createPiWriterRunActivity({
      resolveCredential: async () => ({ apiKey: "sk-test" }),
      acquireLLMLease: async (request) => ({ lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" }),
      composeDraft: async () => {
        throw new Error("provider failed api_key=sk-live prompt=private");
      },
      releaseLLMLease: async () => {
        throw new Error("release failed credential_ref=credref-1 raw_text=secret");
      },
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async (request) => {
        persistedMessages.push(request.error?.message ?? "");
      },
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async (request) => {
        persistedMessages.push(String(request.payload.message ?? ""));
      },
      recordWorkflowEvent: async (request) => {
        persistedMessages.push(String(request.payload.message ?? ""));
      },
      updateWriterRunStatus: async (request) => {
        if (request.status === "failed") {
          throw new Error("status update failed sql=UPDATE writer_runs api_key=sk-live");
        }
      }
    });

    const result = await activity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    const publicMessages = [...persistedMessages, result.error?.message ?? ""];
    expect(result.status).toBe("failed");
    expect(result.error?.message).toContain("Pi writer provider call failed");
    expect(result.error?.message).toContain("Pi writer LLM lease release failed");
    expect(result.error?.message).toContain("Pi writer status update failed");
    for (const message of persistedMessages.filter(Boolean)) {
      expect(message).toContain("Pi writer provider call failed");
      expect(message).toContain("Pi writer LLM lease release failed");
    }
    for (const forbidden of ["sk-live", "credref-1", "credential_ref", "api_key", "raw_text", "prompt", "private", "sql=UPDATE"]) {
      expect(JSON.stringify(publicMessages)).not.toContain(forbidden);
    }
  });

  it("fails explicitly when production provider deps omit the trace or workflow event writer", async () => {
    const activity = createPiWriterRunActivity({
      resolveCredential: async () => ({ apiKey: "sk-test" }),
      acquireLLMLease: async (request) => ({ lease_id: "lease-1", channel_id: request.channel_id, lock_mode: "slot:0" }),
      composeDraft: async () => ({ content: "draft" }),
      releaseLLMLease: async () => undefined,
      saveDraftRevision: async () => ({ draft_id: "draft-1" }),
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    });

    const result = await activity({
      ...basePayload,
      options: {
        module_key: "writer_composer",
        llm_resolution: {
          module_key: "writer_composer",
          channel_id: "channel-1",
          model_id: "model-1",
          provider: "openai-compatible",
          base_url: "https://llm.example.test/v1",
          credential_ref: "credref-1",
          supports_tools: true,
          supports_json: true,
          settings: {}
        }
      }
    });

    expect(result.status).toBe("failed");
    expect(result.error?.code).toBe("LLM_PROVIDER_ERROR");
    expect(result.error?.message).toContain("workflow event writer");
  });
});
