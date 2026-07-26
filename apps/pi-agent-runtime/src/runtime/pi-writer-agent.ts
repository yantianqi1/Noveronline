import { Agent, type AgentEvent, type AgentTool } from "@earendil-works/pi-agent-core";
import {
  createModels,
  createProvider,
  type AssistantMessage,
  type Model
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { Object as ObjectSchema } from "typebox";

import type {
  CheckConsistencyRequest,
  CheckConsistencyResult,
  ComposeDraftRequest,
  ComposeDraftResult,
  ConsistencyViolation,
  OrchestrateWritingBriefRequest,
  OrchestrateWritingBriefResult,
  PlanRetrievalRequest,
  PlanRetrievalResult,
  RerankRecallRequest,
  RerankRecallResult,
  RetrievalPlan,
  RetrievalQuery,
  WriterToolName
} from "../activities/pi-writer-activities.js";
import { assertToolAllowed, ToolPermissionDenied } from "../tools/permissions.js";

const noArguments = ObjectSchema({}, { additionalProperties: false });

// The one retrieval tool that takes planning input from the orchestrator: a
// query string plus optional narrowing. All other tools stay argument-free.
const searchAssetsArguments = ObjectSchema(
  {
    query: { type: "string", description: "Retrieval intent describing the settings, prior scenes, or canon needed for this passage." },
    asset_types: { type: "array", items: { type: "string" }, description: "Optional asset_type filter such as world_rule, relationship, character." },
    top_k: { type: "number", description: "How many assets to return (default 10, max 25)." },
    mode: { type: "string", enum: ["keyword", "vector", "hybrid"], description: "Retrieval mode; defaults to hybrid and degrades to keyword when embeddings are unavailable." }
  },
  { additionalProperties: false }
);

const searchManuscriptArguments = ObjectSchema(
  {
    query: { type: "string", description: "What prior (non-adjacent) scene or foreshadowing to recall, in the novel's language." },
    top_k: { type: "number", description: "How many prior prose snippets to return (default 5, max 12)." }
  },
  { additionalProperties: false }
);

const queryAssetRelationshipsArguments = ObjectSchema(
  {
    asset_id: { type: "string", description: "The recalled asset whose related assets you want to bring out (1-hop expansion)." },
    relation_types: { type: "array", items: { type: "string" }, description: "Optional relation_type filter such as 师徒, 持有, 宗门." },
    top_k: { type: "number", description: "How many related assets to return (default 10, max 25)." }
  },
  { additionalProperties: false, required: ["asset_id"] }
);

const fuseRecallArguments = ObjectSchema(
  {
    channels: {
      type: "array",
      description: "One entry per recall channel you already ran (keyed/hybrid/manuscript), each with its best-first items.",
      items: {
        type: "object",
        properties: {
          channel: { type: "string" },
          items: { type: "array", items: { type: "object", additionalProperties: true } }
        },
        required: ["channel", "items"]
      }
    },
    top_k: { type: "number", description: "Cap the fused list (default: all, max 25)." },
    rerank: { type: "boolean", description: "Re-order the fused list with the writer_retrieval_rerank cross-encoder (degrades to RRF order if unavailable)." },
    query: { type: "string", description: "The writing intent to rerank against; required when rerank is true." }
  },
  { additionalProperties: false }
);

export function createPiWriterExecution() {
  return {
    orchestrateWritingBrief: async (request: OrchestrateWritingBriefRequest) => {
      const runtime = createRuntime(request);
      const tools = request.tool_names.map((name) => writerTool(name, request));
      let permissionError: ToolPermissionDenied | undefined;
      const agent = new Agent({
        initialState: {
          systemPrompt: orchestratorSystemPrompt(),
          model: runtime.model,
          thinkingLevel: request.thinking_level ?? "off",
          tools
        },
        streamFn: runtime.streamFn,
        getApiKey: (provider) => provider === runtime.providerId ? request.apiKey : undefined,
        toolExecution: request.tool_execution ?? "parallel",
        beforeToolCall: async ({ toolCall }) => {
          try {
            assertToolAllowed(toolCall.name, {
              tenant_id: request.tenant_id,
              project_id: request.project_id,
              run_id: request.run_id
            }, request.runtime_context);
            return undefined;
          } catch (error) {
            if (!(error instanceof ToolPermissionDenied)) throw error;
            permissionError = error;
            return { block: true, reason: error.message };
          }
        },
        sessionId: request.run_id
      });
      agent.subscribe(async (event) => request.onAgentEvent?.(event));
      await promptWithAbort(agent, orchestratorPrompt(request), request.abort_signal);
      if (permissionError) throw permissionError;
      const message = finalAssistantMessage(agent.state.messages);
      const content = assistantText(message);
      if (!content.trim()) throw new Error("Pi writer orchestrator returned an empty writing brief");
      return { writing_brief: content, usage: aggregateUsage(agent.state.messages) } satisfies OrchestrateWritingBriefResult;
    },
    composeDraft: async (request: ComposeDraftRequest) => {
      const runtime = createRuntime(request);
      const agent = new Agent({
        initialState: {
          systemPrompt: composerSystemPrompt(request),
          model: runtime.model,
          thinkingLevel: request.thinking_level ?? "off"
        },
        streamFn: runtime.streamFn,
        getApiKey: (provider) => provider === runtime.providerId ? request.apiKey : undefined,
        sessionId: request.run_id
      });
      agent.subscribe(async (event) => {
        const delta = textDelta(event);
        if (delta) await request.onToken?.(delta);
      });
      await promptWithAbort(agent, composerPrompt(request), request.abort_signal);
      const message = finalAssistantMessage(agent.state.messages);
      const content = assistantText(message);
      if (!content.trim()) throw new Error("Pi writer composer returned an empty draft");
      return { content, usage: messageUsage(message) } satisfies ComposeDraftResult;
    },
    planRetrieval: async (request: PlanRetrievalRequest) => {
      const runtime = createRuntime(request);
      const agent = new Agent({
        initialState: {
          systemPrompt: retrievalPlannerSystemPrompt(),
          model: runtime.model,
          thinkingLevel: request.thinking_level ?? "off"
        },
        streamFn: runtime.streamFn,
        getApiKey: (provider) => provider === runtime.providerId ? request.apiKey : undefined,
        sessionId: request.run_id
      });
      await promptWithAbort(agent, retrievalPlannerPrompt(request), request.abort_signal);
      const message = finalAssistantMessage(agent.state.messages);
      const content = assistantText(message);
      if (!content.trim()) throw new Error("Pi writer retrieval planner returned an empty plan");
      return {
        plan: parseRetrievalPlan(content),
        usage: messageUsage(message)
      } satisfies PlanRetrievalResult;
    },
    rerankRecall: async (request: RerankRecallRequest) => {
      const runtime = createRuntime(request);
      const agent = new Agent({
        initialState: {
          systemPrompt: rerankSystemPrompt(),
          model: runtime.model,
          thinkingLevel: request.thinking_level ?? "off"
        },
        streamFn: runtime.streamFn,
        getApiKey: (provider) => provider === runtime.providerId ? request.apiKey : undefined,
        sessionId: request.run_id
      });
      await promptWithAbort(agent, rerankPrompt(request), request.abort_signal);
      const message = finalAssistantMessage(agent.state.messages);
      const content = assistantText(message);
      if (!content.trim()) throw new Error("Pi writer reranker returned an empty ranking");
      return {
        ranked_ids: parseRerankIds(content, request.candidates),
        usage: messageUsage(message)
      } satisfies RerankRecallResult;
    },
    checkConsistency: async (request: CheckConsistencyRequest) => {
      const runtime = createRuntime(request);
      const agent = new Agent({
        initialState: {
          systemPrompt: consistencySystemPrompt(),
          model: runtime.model,
          thinkingLevel: request.thinking_level ?? "off"
        },
        streamFn: runtime.streamFn,
        getApiKey: (provider) => provider === runtime.providerId ? request.apiKey : undefined,
        sessionId: request.run_id
      });
      await promptWithAbort(agent, consistencyPrompt(request), request.abort_signal);
      const message = finalAssistantMessage(agent.state.messages);
      const content = assistantText(message);
      if (!content.trim()) throw new Error("Pi writer consistency checker returned an empty verdict");
      return {
        violations: parseConsistencyViolations(content, request.canon),
        usage: messageUsage(message)
      } satisfies CheckConsistencyResult;
    }
  };
}

const RETRIEVAL_QUERY_CHANNELS = new Set(["keyed", "hybrid", "graph", "manuscript"]);

function retrievalPlannerSystemPrompt(): string {
  return [
    "You are the MiroFish writer retrieval planner. Before any prose is written, decide what canon the writer must recall to keep a long novel consistent.",
    "Respond with ONLY a JSON object — no prose, no markdown fence — of the form:",
    '{"intent": "<continue_scene | rewrite_span | payoff_foreshadow | new_scene | ...>",',
    ' "coverage": ["characters:...", "world_rules:...", "plot_threads:...", "prior_scenes:..."],',
    ' "queries": [{"channel": "hybrid|keyed|graph|manuscript", "text": "<retrieval intent in the novel\'s language>", "asset_types": ["..."], "top_k": 8}],',
    ' "budget": {"max_context_tokens": 24000}}',
    "Rules: 2-5 queries. Use channel hybrid for settings/rules/relationships, keyed for proper names (characters, places, techniques), manuscript for prior scenes, graph for relationships. Write query text in the novel's own language (Chinese for Chinese novels). Never invent canon."
  ].join(" ");
}

function retrievalPlannerPrompt(request: PlanRetrievalRequest): string {
  return JSON.stringify({
    task: "Plan retrieval for this writing request.",
    mode: request.mode,
    instruction: request.instruction,
    chapter_id: request.chapter_id,
    scene_id: request.scene_id,
    author_selected_asset_ids: request.selected_asset_ids,
    target_words: request.target_words
  });
}

/** Parse + validate the planner's JSON into a RetrievalPlan; tolerant of fences. */
function parseRetrievalPlan(content: string): RetrievalPlan {
  const cleaned = content
    .replace(/^```(?:json)?/i, "")
    .replace(/```\s*$/, "")
    .trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("retrieval planner returned no JSON object");
  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned.slice(start, end + 1));
  } catch {
    throw new Error("retrieval planner returned invalid JSON");
  }
  const record = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  const queries = normalizeRetrievalQueries(record.queries);
  if (queries.length === 0) throw new Error("retrieval planner returned no usable queries");
  return {
    intent: typeof record.intent === "string" && record.intent.trim() ? record.intent.trim() : "continue_scene",
    coverage: Array.isArray(record.coverage) ? record.coverage.filter((c): c is string => typeof c === "string") : [],
    queries,
    ...(record.budget && typeof record.budget === "object" && !Array.isArray(record.budget)
      ? { budget: { max_context_tokens: positiveInt((record.budget as Record<string, unknown>).max_context_tokens) } }
      : {})
  };
}

function normalizeRetrievalQueries(value: unknown): RetrievalQuery[] {
  if (!Array.isArray(value)) return [];
  const queries: RetrievalQuery[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const record = entry as Record<string, unknown>;
    const text = typeof record.text === "string" ? record.text.trim() : "";
    if (!text) continue;
    const channel = typeof record.channel === "string" && RETRIEVAL_QUERY_CHANNELS.has(record.channel)
      ? record.channel as RetrievalQuery["channel"]
      : "hybrid";
    const topK = positiveInt(record.top_k);
    const assetTypes = Array.isArray(record.asset_types)
      ? record.asset_types.filter((t): t is string => typeof t === "string" && t.trim() !== "")
      : undefined;
    queries.push({
      channel,
      text,
      ...(topK !== undefined ? { top_k: Math.min(25, Math.max(1, topK)) } : {}),
      ...(assetTypes && assetTypes.length > 0 ? { asset_types: assetTypes } : {})
    });
    if (queries.length >= 6) break;
  }
  return queries;
}

function positiveInt(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : undefined;
}

// ── Cross-encoder rerank (P2, doc 41 §4.6) ───────────────────────────────

function rerankSystemPrompt(): string {
  return [
    "You are the MiroFish writer retrieval reranker. Given a writing intent and a list of recalled canon/prose candidates, order them by how useful each is for writing the passage consistently.",
    "Respond with ONLY a JSON object — no prose, no markdown — of the form:",
    '{"ranked_ids": ["<candidate id>", "..."], "kept": <number>}',
    "Rank most-useful first. Drop candidates that are irrelevant to the intent. Preserve every id exactly as given; never invent ids."
  ].join(" ");
}

function rerankPrompt(request: RerankRecallRequest): string {
  return JSON.stringify({
    task: "Rank these recalled candidates by usefulness for the writing intent.",
    intent: request.query,
    candidates: request.candidates.map((c) => ({
      id: c.id,
      title: c.title,
      text: c.text,
      channels: c.channels
    }))
  });
}

/** Parse the reranker's JSON into an ordered id list, validated against the candidates. */
function parseRerankIds(content: string, candidates: RerankRecallRequest["candidates"]): string[] {
  const cleaned = content.replace(/^```(?:json)?/i, "").replace(/```\s*$/, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("reranker returned no JSON object");
  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned.slice(start, end + 1));
  } catch {
    throw new Error("reranker returned invalid JSON");
  }
  const record = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  const validIds = new Set(candidates.map((c) => c.id));
  const ranked = Array.isArray(record.ranked_ids)
    ? record.ranked_ids.filter((id): id is string => typeof id === "string" && validIds.has(id))
    : [];
  // Any candidate the reranker dropped off the list is appended at the end so we
  // never silently lose recall — it just ranks low.
  const seen = new Set(ranked);
  for (const c of candidates) if (!seen.has(c.id)) ranked.push(c.id);
  return ranked;
}

// ── Consistency check (P2, doc 41 §4.7) ──────────────────────────────────

function consistencySystemPrompt(): string {
  return [
    "You are the MiroFish writer consistency checker. Given a draft and the canon it must respect (world rules and character states), find contradictions — 'broken canon' (吃书).",
    "Respond with ONLY a JSON object — no prose, no markdown — of the form:",
    '{"violations": [{"canon_label": "<the canon fact>", "conflict": "<what the draft wrongly claims>", "severity": "minor|major"}]}',
    "Only report genuine contradictions, not stylistic choices or things canon is silent about. An empty violations array means the draft is consistent."
  ].join(" ");
}

function consistencyPrompt(request: CheckConsistencyRequest): string {
  return JSON.stringify({
    task: "Find contradictions between this draft and canon.",
    draft: request.draft_text,
    canon: request.canon.map((c) => ({ kind: c.kind, label: c.label, text: c.text }))
  });
}

/** Parse + validate the consistency verdict against the supplied canon labels. */
function parseConsistencyViolations(
  content: string,
  canon: CheckConsistencyRequest["canon"]
): ConsistencyViolation[] {
  const cleaned = content.replace(/^```(?:json)?/i, "").replace(/```\s*$/, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("consistency checker returned no JSON object");
  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned.slice(start, end + 1));
  } catch {
    throw new Error("consistency checker returned invalid JSON");
  }
  const record = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  if (!Array.isArray(record.violations)) return [];
  const knownLabels = new Set(canon.map((c) => c.label));
  const violations: ConsistencyViolation[] = [];
  for (const entry of record.violations) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const v = entry as Record<string, unknown>;
    const label = typeof v.canon_label === "string" ? v.canon_label.trim() : "";
    const conflict = typeof v.conflict === "string" ? v.conflict.trim() : "";
    if (!label || !conflict) continue;
    violations.push({
      canon_label: label,
      conflict,
      severity: v.severity === "major" ? "major" : "minor"
    });
    // Keep the check honest: cap reported violations and prefer known canon labels.
    if (violations.length >= 20) break;
  }
  // Stable order: known-canon violations first, then by severity.
  return violations.sort((a, b) =>
    Number(knownLabels.has(b.canon_label)) - Number(knownLabels.has(a.canon_label)) ||
    (a.severity === b.severity ? 0 : a.severity === "major" ? -1 : 1)
  );
}

function writerTool(name: WriterToolName, request: OrchestrateWritingBriefRequest): AgentTool<typeof noArguments | typeof searchAssetsArguments | typeof searchManuscriptArguments | typeof fuseRecallArguments | typeof queryAssetRelationshipsArguments> {
  const parameters =
    name === "search_assets" ? searchAssetsArguments
      : name === "search_manuscript" ? searchManuscriptArguments
        : name === "fuse_recall" ? fuseRecallArguments
          : name === "query_asset_relationships" ? queryAssetRelationshipsArguments
            : noArguments;
  return {
    name,
    label: name,
    description: toolDescription(name),
    parameters,
    executionMode: name === "save_draft_revision" ? "sequential" : "parallel",
    execute: async (toolCallId, params, signal) => {
      if (signal?.aborted) throw new Error("writer tool execution aborted");
      const details = await request.executeTool(name, toolCallId, params as Record<string, unknown>);
      return {
        content: [{ type: "text", text: JSON.stringify(details) }],
        details
      };
    }
  };
}

function createRuntime(request: ComposeDraftRequest | OrchestrateWritingBriefRequest | PlanRetrievalRequest | RerankRecallRequest | CheckConsistencyRequest) {
  const parentProviderCallID = request.provider_call_id?.trim();
  if (!parentProviderCallID) {
    throw new Error("LLM_PROVIDER_CALL_ID_INVALID: Pi writer provider call identity is required");
  }
  const providerId = `mirofish-${request.channel_id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const model = openAICompatibleModel(request, providerId);
  const provider = createProvider({
    id: providerId,
    name: `MiroFish ${request.provider}`,
    baseUrl: request.base_url,
    auth: { apiKey: { name: "MiroFish LLM Facility request key", resolve: async () => ({ auth: {} }) } },
    models: [model],
    api: openAICompletionsApi()
  });
  const models = createModels();
  models.setProvider(provider);
  const resolved = models.getModel(providerId, request.model_id);
  if (!resolved) throw new Error("Pi writer resolved model is unavailable");
  let turnIndex = 0;
  const streamFn = (model: Parameters<typeof models.streamSimple>[0], context: Parameters<typeof models.streamSimple>[1], options?: Parameters<typeof models.streamSimple>[2]) => {
    const turnCallID = `${parentProviderCallID}:turn:${turnIndex++}`;
    return models.streamSimple({
      ...model,
      headers: { ...model.headers, "Idempotency-Key": turnCallID, "X-MiroFish-Provider-Call-Parent": parentProviderCallID }
    }, context, options);
  };
  return { providerId, model: resolved, models, streamFn };
}

function openAICompatibleModel(request: ComposeDraftRequest | OrchestrateWritingBriefRequest | PlanRetrievalRequest | RerankRecallRequest | CheckConsistencyRequest, providerId: string): Model<"openai-completions"> {
  return {
    id: request.model_id,
    name: request.model_id,
    api: "openai-completions",
    provider: providerId,
    baseUrl: request.base_url,
    reasoning: Boolean(request.settings.reasoning),
    input: ["text"],
    cost: {
      input: numericSetting(request.settings, "input_cost") ?? 0,
      output: numericSetting(request.settings, "output_cost") ?? 0,
      cacheRead: 0,
      cacheWrite: 0
    },
    contextWindow: numericSetting(request.settings, "context_window") ?? 128000,
    maxTokens: numericSetting(request.settings, "max_tokens") ?? 4000,
    headers: providerRequestHeaders(request)
  };
}

function providerRequestHeaders(request: ComposeDraftRequest | OrchestrateWritingBriefRequest | PlanRetrievalRequest | RerankRecallRequest | CheckConsistencyRequest): Record<string, string> {
  const providerCallID = request.provider_call_id?.trim();
  if (!providerCallID) {
    throw new Error("LLM_PROVIDER_CALL_ID_INVALID: Pi writer provider call identity is required");
  }
  return {
    "Idempotency-Key": providerCallID,
    "X-MiroFish-Tenant-Id": request.tenant_id,
    "X-MiroFish-Project-Id": request.project_id,
    "X-MiroFish-Run-Id": request.run_id,
    "X-MiroFish-Module-Key": request.module_key
  };
}

function orchestratorSystemPrompt(): string {
  return "You are the MiroFish writer orchestrator. Call the available read tools before producing a concise writing brief. Never write or adopt manuscript content. Do not call save_draft_revision; the runtime persists the composer result explicitly.";
}

function orchestratorPrompt(request: OrchestrateWritingBriefRequest): string {
  return JSON.stringify({
    task: "Build a writing brief from authoritative project tools.",
    mode: request.mode,
    instruction: request.instruction,
    chapter_id: request.chapter_id,
    scene_id: request.scene_id,
    selected_asset_ids: request.selected_asset_ids,
    graph_node_ids: request.graph_node_ids,
    worldline_path_ids: request.worldline_path_ids,
    target_words: request.target_words,
    ...(request.retrieval_plan
      ? {
          retrieval_plan: {
            intent: request.retrieval_plan.intent,
            coverage: request.retrieval_plan.coverage,
            guidance: "A retrieval planner already analysed this request. For each planned query below, call search_assets with its text and asset_types. You may add calls for anything the plan missed, and use query_manuscript_context for the immediate scene. Cite what you use.",
            queries: request.retrieval_plan.queries.map((q) => ({
              text: q.text,
              asset_types: q.asset_types,
              top_k: q.top_k
            }))
          }
        }
      : {})
  });
}

function composerSystemPrompt(request: ComposeDraftRequest): string {
  const configured = typeof request.settings.system_prompt === "string" ? request.settings.system_prompt.trim() : "";
  if (request.mode === "revise") {
    return configured || "You revise selected novel prose. Return only the revised selection text. Do not wrap in quotes or commentary. Do not claim manuscript adoption.";
  }
  return configured || "Write original novel prose from the supplied writing brief. Return prose only. Do not claim manuscript adoption or review completion.";
}

function composerPrompt(request: ComposeDraftRequest): string {
  if (request.mode === "revise" && request.revise) {
    return JSON.stringify({
      task: "revise_selection",
      instruction: request.instruction,
      selection_text: request.revise.selection_text,
      block_id: request.revise.block_id,
      action: request.revise.action,
      writing_brief: request.writing_brief
    });
  }
  return JSON.stringify({
    instruction: request.instruction,
    writing_brief: request.writing_brief,
    target_words: request.target_words
  });
}

function finalAssistantMessage(messages: unknown[]): AssistantMessage {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index] as AssistantMessage;
    if (message?.role === "assistant") {
      if (message.stopReason === "error" || message.stopReason === "aborted") {
        throw new Error("Pi writer provider call failed");
      }
      return message;
    }
  }
  throw new Error("Pi writer provider returned no assistant message");
}

function assistantText(message: AssistantMessage): string {
  return message.content.filter((block) => block.type === "text").map((block) => block.text).join("");
}

function messageUsage(message: AssistantMessage): ComposeDraftResult["usage"] {
  return {
    prompt_tokens: message.usage.input,
    completion_tokens: message.usage.output,
    cost_estimate: message.usage.cost.total
  };
}

function aggregateUsage(messages: unknown[]): ComposeDraftResult["usage"] {
  const assistantMessages = messages.filter((message): message is AssistantMessage =>
    Boolean(message && typeof message === "object" && (message as AssistantMessage).role === "assistant")
  );
  return assistantMessages.reduce((total, message) => ({
    prompt_tokens: total.prompt_tokens + message.usage.input,
    completion_tokens: total.completion_tokens + message.usage.output,
    cost_estimate: (total.cost_estimate ?? 0) + message.usage.cost.total
  }), { prompt_tokens: 0, completion_tokens: 0, cost_estimate: 0 });
}

async function promptWithAbort(agent: Agent, prompt: string, signal?: AbortSignal): Promise<void> {
  if (!signal) {
    await agent.prompt(prompt);
    return;
  }
  if (signal.aborted) throw new Error("WORKFLOW_CANCELLED: Pi writer activity was cancelled");
  const abort = () => { void agent.abort(); };
  signal.addEventListener("abort", abort, { once: true });
  try {
    await agent.prompt(prompt);
    if (signal.aborted) throw new Error("WORKFLOW_CANCELLED: Pi writer activity was cancelled");
  } finally {
    signal.removeEventListener("abort", abort);
  }
}

function textDelta(event: AgentEvent): string {
  if (event.type !== "message_update" || event.assistantMessageEvent.type !== "text_delta") return "";
  return event.assistantMessageEvent.delta;
}

function numericSetting(settings: Record<string, unknown>, key: string): number | undefined {
  const value = settings[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function toolDescription(name: WriterToolName): string {
  const descriptions: Record<WriterToolName, string> = {
    query_project_context: "Read project title, genre, language, and status.",
    query_chapter_scene: "Read the requested chapter and scene identifiers plus existing draft metadata.",
    query_assets: "Read the author's explicitly selected project assets (by id) and their private writing context. Returns nothing when the author selected none — use search_assets for on-demand recall instead.",
    search_assets: "Semantic recall over project canon/seed/material assets. Supply a query describing what this passage needs (settings, rules, relationships, prior scenes). Returns ranked matches with citations; degrades to keyword when embeddings are unavailable.",
    search_manuscript: "Semantic recall over prior manuscript prose that is NOT adjacent to the current scene — foreshadowing and callbacks. Supply a query in the novel's language. Returns prior snippets with citations; unavailable when prose embeddings are not indexed.",
    fuse_recall: "Fuse several recall channels you already ran (keyed/hybrid/manuscript) into one RRF-ranked list. Pass each channel's best-first items; returns the merged ranking with per-item channels. Use before composing when you gathered recall from more than one channel.",
    query_world_rules: "Read extracted project world rules as private writing context.",
    query_character_profile: "Read project character identities, aliases, and current state as private writing context.",
    query_graph_neighbors: "Read explicitly selected story graph nodes and their direct relationships.",
    query_asset_relationships: "Bring out one recalled asset's 1-hop related assets (召回一个、带出一串) — its weapon, sect, allies, the relationship records themselves. Pass the recalled asset_id; returns related assets with relation_type and direction. Use after search_assets lands a character/setting whose connections matter for the passage.",
    query_worldline_paths: "Read explicitly selected saved worldline paths as non-canon references.",
    query_manuscript_context: "Read recently adopted manuscript blocks for continuation context.",
    save_draft_revision: "Reserved runtime persistence tool. The orchestrator must not call it."
  };
  return descriptions[name];
}
