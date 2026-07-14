"use client";

import { Bot, LoaderCircle, Sparkles } from "lucide-react";
import { Suspense, useEffect, useRef, type ReactNode } from "react";

import type {
  WriterRunEventsSummary,
  WriterRunSummary,
} from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { summarizeWriterTaskStatus } from "../lib/writer-task-status";
import { Bi, FailureText } from "./bilingual-text";
import { PublicErrorNotice } from "./public-error-notice";
import {
  WriterAgentComposer,
  type WriterRunActionResult,
} from "./writer-agent-composer";
import { WriterLiveDraft } from "./writer-live-draft";
import { useWriterRunSession } from "./writer-run-session";
import { useWriterRunStream } from "./writer-run-stream";
import { WriterTransientToast } from "./writer-transient-toast";

export type WriterThreadMessageView = {
  role: string;
  body: string;
  created_at?: string;
  run_id?: string;
};

type ActionStatus = {
  status: string;
  code: string;
  message: string;
};

type WriterAgentThreadProps = {
  locale: Locale;
  projectId: string;
  tenantSlug: string;
  selectedChapterId: string;
  selectedSceneId: string;
  runSummary: WriterRunSummary | null;
  runActive: boolean;
  recoveredDraftId: string;
  draftIsAdopted: boolean;
  workflowEvents: WriterRunEventsSummary | null;
  threadMessages: WriterThreadMessageView[];
  writerRunStatus: ActionStatus | null;
  writerRunAction?: (formData: FormData) => Promise<WriterRunActionResult>;
  decideApprovalAction?: (formData: FormData) => Promise<void>;
  runControl?: ReactNode;
  contextPickers?: ReactNode;
};

/**
 * Conversation rail: persistent thread + current-run narrative + composer.
 * Keeps an optimistic user bubble until the server thread/run catches up, and
 * streams live status as soon as admission returns a run id.
 */
export function WriterAgentThread({
  locale,
  projectId,
  tenantSlug,
  selectedChapterId,
  selectedSceneId,
  runSummary,
  runActive,
  recoveredDraftId,
  draftIsAdopted,
  workflowEvents,
  threadMessages,
  writerRunStatus,
  writerRunAction,
  decideApprovalAction,
  runControl,
  contextPickers,
}: WriterAgentThreadProps) {
  const run = runSummary?.ok === true ? runSummary : null;
  const session = useWriterRunSession();
  const stream = useWriterRunStream();
  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingInstruction = session?.pendingInstruction ?? null;
  const optimisticRunId = session?.optimisticRunId ?? null;

  useEffect(() => {
    if (!pendingInstruction) return;
    if (threadContainsUserInstruction(threadMessages, pendingInstruction)) {
      session?.clearPendingInstruction();
      return;
    }
    if (run && instructionsMatch(run.instruction, pendingInstruction)) {
      session?.clearPendingInstruction();
    }
  }, [pendingInstruction, threadMessages, run, session]);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    root.scrollTop = root.scrollHeight;
  }, [pendingInstruction, optimisticRunId, stream?.events.length, threadMessages.length]);

  const showRunInstruction =
    Boolean(run) &&
    !threadContainsUserInstruction(threadMessages, run!.instruction) &&
    !(pendingInstruction && instructionsMatch(pendingInstruction, run!.instruction));

  const showPending =
    Boolean(pendingInstruction) &&
    !threadContainsUserInstruction(threadMessages, pendingInstruction!) &&
    !(run && instructionsMatch(run.instruction, pendingInstruction!));

  const liveRunId = optimisticRunId || run?.run_id || "";
  const liveActive =
    stream && liveRunId && stream.runId === liveRunId
      ? stream.active
      : Boolean(optimisticRunId) || runActive;
  const showLiveRun = Boolean(liveRunId) && (Boolean(run) || Boolean(optimisticRunId));
  const showStarting =
    Boolean(pendingInstruction) && !showLiveRun && session?.busy === true;

  const hasThreadContent =
    threadMessages.length > 0 ||
    showPending ||
    showStarting ||
    showLiveRun ||
    Boolean(run) ||
    runSummary?.ok === false;

  const stageLabel = liveStageLabel(locale, run, workflowEvents, stream, showStarting);

  return (
    <section
      className="writer-agent-thread"
      aria-labelledby="writer-agent-thread-heading"
      data-thread-persistent={threadMessages.length > 0 ? "true" : "false"}
      data-busy={session?.busy ? "true" : "false"}
    >
      <header className="writer-agent-toolbar">
        <div className="writer-agent-identity">
          <span className="writer-agent-avatar">
            <Bot aria-hidden="true" size={19} />
          </span>
          <div>
            <h2 id="writer-agent-thread-heading">MiroFish Writer</h2>
            <small>{stageLabel}</small>
          </div>
        </div>
        {runControl}
      </header>

      <div className="writer-thread-scroll" ref={scrollRef}>
        {threadMessages.map((message, index) => (
          <article
            className={`writer-message writer-message-${message.role === "user" ? "user" : "agent"}`}
            key={`thread-${index}-${message.created_at ?? ""}`}
            data-thread-message="true"
          >
            <p>{message.body}</p>
          </article>
        ))}
        {showPending ? (
          <article className="writer-message writer-message-user" data-pending-message="true">
            <p>{pendingInstruction}</p>
          </article>
        ) : null}
        {runSummary?.ok === false ? (
          <PublicErrorNotice
            message={<FailureText />}
            title={<Bi zh="写作会话暂不可用" en="Writer session unavailable" />}
          />
        ) : showLiveRun ? (
          <>
            {showRunInstruction ? (
              <article className="writer-message writer-message-user">
                <p>{run!.instruction}</p>
              </article>
            ) : null}
            <article className="writer-message writer-message-agent" data-live-run="true">
              <WriterLiveDraft
                active={liveActive}
                decideApprovalAction={decideApprovalAction}
                initialEvents={
                  run?.run_id === liveRunId && workflowEvents?.ok === true
                    ? workflowEvents.items
                    : []
                }
                locale={locale}
                projectId={projectId}
                proseOnCanvas
                runId={liveRunId}
                tenantSlug={tenantSlug}
              />
              {recoveredDraftId && !draftIsAdopted ? (
                <p className="form-hint">
                  <Bi
                    zh="候选稿已放在右侧画布，采用后才会进入正式手稿。"
                    en="The candidate is on the canvas. Adopt it to place it into the manuscript."
                  />
                </p>
              ) : null}
            </article>
          </>
        ) : showStarting ? (
          <article className="writer-message writer-message-agent" data-starting="true">
            <p className="writer-agent-working" data-active="true">
              <LoaderCircle aria-hidden="true" className="is-spinning" size={17} />
              <span>
                <Bi zh="正在分析需求…" en="Understanding the request…" />
              </span>
            </p>
          </article>
        ) : !hasThreadContent ? (
          <div className="writer-agent-empty">
            <span>
              <Sparkles aria-hidden="true" size={24} />
            </span>
            <h2>
              <Bi zh="从下一段开始" en="Begin with the next passage" />
            </h2>
            <p>
              <Bi
                zh="在下方描述你想要的结果。候选稿会出现在左侧画布；采用后才会进入正式手稿。"
                en="Describe what you want below. The candidate appears on the canvas; adopt it into the manuscript."
              />
            </p>
          </div>
        ) : null}
      </div>

      <div className="writer-composer-dock">
        <Suspense fallback={null}>
          <WriterTransientToast locale={locale} status={writerRunStatus} />
        </Suspense>
        {writerRunAction ? (
          <WriterAgentComposer
            locale={locale}
            selectedChapterId={selectedChapterId}
            selectedSceneId={selectedSceneId}
            writerRunAction={writerRunAction}
          >
            {contextPickers}
          </WriterAgentComposer>
        ) : (
          <p className="form-hint">
            <Bi zh="当前无法开始写作任务。" en="Writer runs are currently unavailable." />
          </p>
        )}
      </div>
    </section>
  );
}

function liveStageLabel(
  locale: Locale,
  run: Extract<WriterRunSummary, { ok: true }> | null,
  workflowEvents: WriterRunEventsSummary | null,
  stream: ReturnType<typeof useWriterRunStream>,
  showStarting: boolean,
) {
  if (showStarting) return tx(locale, "正在分析需求", "Understanding the request");
  if (stream && stream.events.length > 0) {
    return summarizeWriterTaskStatus(locale, stream.events, stream.connection).line;
  }
  if (stream?.active) return tx(locale, "正在分析需求", "Understanding the request");
  if (!run) return tx(locale, "等待指令", "Ready for direction");
  const events = workflowEvents?.ok === true ? workflowEvents.items : [];
  return summarizeWriterTaskStatus(locale, events).line;
}

function instructionsMatch(left: string, right: string) {
  return left.trim() === right.trim();
}

function threadContainsUserInstruction(
  messages: readonly WriterThreadMessageView[],
  instruction: string,
) {
  const needle = instruction.trim();
  if (!needle) return false;
  return messages.some((message) => message.role === "user" && message.body.trim() === needle);
}
