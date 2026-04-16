/**
 * SeedStepTracePanel — loads and displays prompt / response evidence for a seed step.
 */

import { useEffect, useRef, useState, type MutableRefObject } from "react";

import { getStepTrace } from "@/api/project";
import { cn } from "@/lib/utils";
import type { ChapterStep } from "./seed-pipeline-chapters";

interface TraceCall {
  call_id?: string;
  call_type?: string;
  module_label?: string;
  module_key?: string;
  model?: string;
  elapsed_ms?: number;
  messages?: Array<{ role: string; content: string }>;
  response_text?: string;
  error?: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

interface TraceArtifact {
  label?: string;
  kind?: string;
  content?: string;
}

interface TraceData {
  calls?: TraceCall[];
  artifacts?: TraceArtifact[];
}

const traceCache = new Map<string, TraceData>();

export default function SeedStepTracePanel({
  taskId,
  step,
}: {
  taskId: string;
  step: ChapterStep;
}) {
  const [loading, setLoading] = useState(false);
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [loadError, setLoadError] = useState("");
  const requestRef = useRef("");

  useEffect(() => {
    if (!taskId || !step.stepId || !step.hasTrace) {
      setTrace(null);
      setLoadError("");
      return;
    }
    void loadTrace({ taskId, stepId: step.stepId, setLoading, setTrace, setLoadError, requestRef });
  }, [taskId, step.stepId, step.hasTrace]);

  if (step.status === "active") return <TraceNotice text="步骤执行中，完成后会写入审计记录。" />;
  if (!step.hasTrace) return <NoTracePanel step={step} />;
  if (loading) return <TraceNotice text="正在读取审计记录..." pulse />;
  if (loadError) return <TraceNotice text={loadError} tone="error" />;
  if (!trace) return <TraceNotice text={`未读取到审计记录：${step.stepId}`} tone="error" />;
  return <TraceContent trace={trace} />;
}

async function loadTrace({
  taskId,
  stepId,
  setLoading,
  setTrace,
  setLoadError,
  requestRef,
}: {
  taskId: string;
  stepId: string;
  setLoading: (value: boolean) => void;
  setTrace: (value: TraceData | null) => void;
  setLoadError: (value: string) => void;
  requestRef: MutableRefObject<string>;
}) {
  const cacheKey = `${taskId}:${stepId}`;
  requestRef.current = cacheKey;
  if (traceCache.has(cacheKey)) {
    setTrace(traceCache.get(cacheKey)!);
    return;
  }
  setLoading(true);
  setLoadError("");
  try {
    const resp = await getStepTrace(taskId, stepId);
    const data = (resp?.data as TraceData) || null;
    if (requestRef.current !== cacheKey) return;
    if (!data) throw new Error(`空审计记录：${stepId}`);
    traceCache.set(cacheKey, data);
    setTrace(data);
  } catch (err) {
    if (requestRef.current !== cacheKey) return;
    setTrace(null);
    setLoadError(err instanceof Error ? err.message : `读取审计记录失败：${stepId}`);
  } finally {
    if (requestRef.current === cacheKey) setLoading(false);
  }
}

function TraceContent({ trace }: { trace: TraceData }) {
  const calls = trace.calls || [];
  const artifacts = trace.artifacts || [];
  if (!calls.length && !artifacts.length) return <TraceNotice text="审计记录为空。" tone="error" />;
  return (
    <div className="seed-trace-panel">
      {calls.map((call, idx) => (
        <CallSection key={call.call_id || idx} call={call} index={calls.length > 1 ? idx + 1 : undefined} />
      ))}
      {artifacts.length > 0 && (
        <section className="space-y-2">
          <TraceSectionTitle text={calls.length ? "处理产物" : "步骤产物"} />
          {artifacts.map((artifact, idx) => (
            <ArtifactSection key={`${artifact.label || "artifact"}_${idx}`} artifact={artifact} />
          ))}
        </section>
      )}
    </div>
  );
}

function CallSection({ call, index }: { call: TraceCall; index?: number }) {
  const title = call.module_label || call.module_key || "LLM 调用";
  return (
    <section className="rounded-lg border border-red-900/10 bg-white shadow-sm overflow-hidden seed-trace-call">
      <header className="flex flex-wrap items-center gap-2 border-b border-red-900/10 bg-red-50/50 px-3 py-2">
        {index && <span className="rounded-md bg-red-900 px-1.5 py-0.5 font-mono text-[10px] text-white">#{index}</span>}
        <strong className="text-sm">{title}</strong>
        <TraceChip text={call.call_type || "chat"} />
        <TraceChip text={call.model || "未记录模型"} />
        {typeof call.elapsed_ms === "number" && <TraceChip text={`${call.elapsed_ms}ms`} />}
        {call.usage?.total_tokens ? <TraceChip text={`${call.usage.total_tokens} tokens`} tone="green" /> : null}
      </header>
      <div className="grid gap-2 p-3 xl:grid-cols-2">
        <PromptBlock messages={call.messages || []} />
        <ResponseBlock call={call} />
      </div>
      {call.error && <div className="border-t border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{call.error}</div>}
    </section>
  );
}

function PromptBlock({ messages }: { messages: TraceCall["messages"] }) {
  return (
    <section className="min-w-0">
      <TraceSectionTitle text="发送给 LLM 的提示词" />
      <div className="mt-2 max-h-[420px] overflow-auto rounded-lg border border-border/70 bg-zinc-50 p-2.5">
        {messages?.length ? messages.map((msg, idx) => <MessageBlock key={idx} message={msg} />) : (
          <pre className="m-0 whitespace-pre-wrap break-words font-mono text-xs text-muted-foreground">未记录 messages。</pre>
        )}
      </div>
    </section>
  );
}

function ResponseBlock({ call }: { call: TraceCall }) {
  return (
    <section className="min-w-0">
      <TraceSectionTitle text="LLM 返回的真实内容" />
      <pre className="mt-2 max-h-[420px] overflow-auto rounded-lg border border-border/70 bg-zinc-50 p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
        {call.response_text || "未记录返回内容。"}
      </pre>
    </section>
  );
}

function MessageBlock({ message }: { message: { role: string; content: string } }) {
  return (
    <article className="mb-3 last:mb-0">
      <div className="mb-1 font-mono text-[10px] font-bold uppercase text-red-700">{message.role}</div>
      <pre className="m-0 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">{message.content}</pre>
    </article>
  );
}

function ArtifactSection({ artifact }: { artifact: TraceArtifact }) {
  return (
    <section className="rounded-lg border border-border/70 bg-white overflow-hidden">
      <header className="flex items-center gap-2 border-b bg-zinc-50 px-3 py-2">
        <strong className="text-xs text-muted-foreground">{artifact.label || "未命名产物"}</strong>
        {artifact.kind && <TraceChip text={artifact.kind} tone={artifact.kind === "json" ? "blue" : "green"} />}
      </header>
      <pre className="m-0 max-h-[360px] overflow-auto p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
        {artifact.content || ""}
      </pre>
    </section>
  );
}

function NoTracePanel({ step }: { step: ChapterStep }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-zinc-50 p-3">
      <div className="text-sm font-semibold text-foreground">{step.title}</div>
      <div className="mt-1 font-mono text-xs text-muted-foreground">
        {step.detail || "后端未标记审计记录；旧任务无法补回已发生的 LLM 调用。"}
      </div>
    </div>
  );
}

function TraceNotice({ text, tone = "muted", pulse = false }: { text: string; tone?: "muted" | "error"; pulse?: boolean }) {
  return (
    <div className={cn("rounded-lg border px-3 py-2 font-mono text-xs", tone === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-border bg-zinc-50 text-muted-foreground", pulse && "animate-pulse")}>
      {text}
    </div>
  );
}

function TraceSectionTitle({ text }: { text: string }) {
  return <div className="font-mono text-[11px] font-semibold text-muted-foreground">{text}</div>;
}

function TraceChip({ text, tone = "default" }: { text: string; tone?: "default" | "green" | "blue" }) {
  const toneClass = {
    default: "bg-white text-muted-foreground border-border",
    green: "bg-emerald-50 text-emerald-700 border-emerald-200",
    blue: "bg-sky-50 text-sky-700 border-sky-200",
  }[tone];
  return <span className={cn("rounded-md border px-1.5 py-0.5 font-mono text-[10px]", toneClass)}>{text}</span>;
}
