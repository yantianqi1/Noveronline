import { describe, expect, it } from "vitest";

import { createPiWriterRunActivity, runPiWriterRunActivity } from "./pi-writer-activities.js";

const basePayload = {
  tenant_id: "ten_1",
  project_id: "proj_1",
  run_id: "run_1",
  trace_id: "trace_1",
  requested_by: "usr_1",
  mode: "draft",
  instruction: "写下一场雨夜谈判",
  options: { module_key: "writer_composer" }
};

describe("runPiWriterRunActivity", () => {
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
