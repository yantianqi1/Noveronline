"use client";

import { Check, CheckCircle2, ChevronDown, CircleDashed, Feather, FileCheck, Loader2, MapPin, Square, XCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import type { WriterSelection } from "@/lib/api/writer-client";
import type { ConsistencyViolation, RunCitation, RunStep } from "@/lib/api/writer-run";

import { useWriterRun, type LiveRun } from "./use-writer-run";
import { buildConversationTurns } from "./writer-turns";

export { buildConversationTurns };

/**
 * The conversation rail — the single entry point to the Writer Agent. It is
 * deliberately subordinate to the manuscript canvas: quiet header, a thread of
 * author messages + one task card per request, and a persistent composer at the
 * foot. The agent never speaks in prose here; its output lives in the candidate
 * card. Each request owns its run end-to-end, so consecutive requests never
 * clobber one another.
 *
 * Turns survive a reload: the workspace rebuilds them from the persistent
 * thread (a user message anchors the request, its run_id anchors the task),
 * and each task re-reads its run's event stream. Adoption settles the turn
 * into quiet history rows that keep the recall line and a link back to the
 * prose on the canvas — nothing about what the agent did is lost.
 */

export type ConversationTurn =
  | { kind: "user"; id: string; body: string; createdAt?: string }
  | { kind: "agent"; id: string; body: string; createdAt?: string }
  | { kind: "task"; id: string; runId: string; createdAt?: string };

/** A settled turn the workspace knows about (run adopted into the manuscript). */
export type SettledRunInfo = { blockId: string; chapterId: string };

export function WriterRail({
  turns,
  selection,
  csrfToken,
  adoptedRunIds,
  settledRuns,
  adoptingDraftId,
  onAdopt,
  onCancelRun,
  onRunSettled,
  onRevealAdopted,
  onTaskAdopted,
  hideHeader,
}: {
  turns: ConversationTurn[];
  selection: WriterSelection | null;
  csrfToken: string | null;
  adoptedRunIds: ReadonlySet<string>;
  /** run_id → manuscript block/chapter for every adopted turn. */
  settledRuns: ReadonlyMap<string, SettledRunInfo>;
  adoptingDraftId: string | null;
  onAdopt: (runId: string, draftId: string) => void;
  onCancelRun: (runId: string) => void;
  onRunSettled: (runId: string) => void;
  /** Scroll the canvas to the adopted prose (chapter switch included). */
  onRevealAdopted: (runId: string) => void;
  /** A live turn discovered its draft is adopted — fold it into settled state. */
  onTaskAdopted: (runId: string) => void;
  /** Render just the thread (no 合著者 header) — used when the rail sits inside
      the conversation/review tabbed dock, whose dock-head tabs own the title
      row. */
  hideHeader?: boolean;
}) {
  return (
    <div className="flex h-full flex-col">
      {!hideHeader && (
        <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line-soft px-4">
          <span className="grid size-6 place-items-center rounded-control bg-accent-wash text-accent">
            <Feather className="size-3" aria-hidden />
          </span>
          <span className="text-sm font-medium text-ink">合著者</span>
          <span className="ml-auto text-caption text-muted">常驻协作</span>
        </div>
      )}
      <WriterRailThread
        turns={turns}
        selection={selection}
        csrfToken={csrfToken}
        adoptedRunIds={adoptedRunIds}
        settledRuns={settledRuns}
        adoptingDraftId={adoptingDraftId}
        onAdopt={onAdopt}
        onCancelRun={onCancelRun}
        onRunSettled={onRunSettled}
        onRevealAdopted={onRevealAdopted}
        onTaskAdopted={onTaskAdopted}
      />
    </div>
  );
}

/** The scrolling thread alone — exported so the flip card's front face can host
    the conversation without the rail's own header. */
export function WriterRailThread({
  turns,
  selection,
  csrfToken,
  adoptedRunIds,
  settledRuns,
  adoptingDraftId,
  onAdopt,
  onCancelRun,
  onRunSettled,
  onRevealAdopted,
  onTaskAdopted,
}: {
  turns: ConversationTurn[];
  selection: WriterSelection | null;
  csrfToken: string | null;
  adoptedRunIds: ReadonlySet<string>;
  settledRuns: ReadonlyMap<string, SettledRunInfo>;
  adoptingDraftId: string | null;
  onAdopt: (runId: string, draftId: string) => void;
  onCancelRun: (runId: string) => void;
  onRunSettled: (runId: string) => void;
  onRevealAdopted: (runId: string) => void;
  onTaskAdopted: (runId: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Keep the newest exchange in view as the thread grows.
  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns.length]);

  const renderTurn = (turn: ConversationTurn) => {
    if (turn.kind === "user") return <UserBubble key={turn.id} body={turn.body} />;
    if (turn.kind === "agent") return <AgentLine key={turn.id} body={turn.body} />;
    return (
      <TaskTurn
        key={turn.id}
        runId={turn.runId}
        selection={selection}
        csrfToken={csrfToken}
        adopted={adoptedRunIds.has(turn.runId)}
        settled={settledRuns.get(turn.runId) ?? null}
        adoptingDraftId={adoptingDraftId}
        onAdopt={onAdopt}
        onCancelRun={onCancelRun}
        onSettled={onRunSettled}
        onRevealAdopted={onRevealAdopted}
        onTaskAdopted={onTaskAdopted}
      />
    );
  };

  return (
    <div ref={scrollRef} className="min-h-0 basis-0 flex-1 overflow-y-auto px-3.5 pb-2 pt-3">
      {turns.length === 0 ? (
        <RailGreeting />
      ) : (
        <div className="flex flex-col gap-5.5">
          {buildThreadBlocks(turns).map((block) =>
            block.kind === "day" ? (
              <DaySeparator key={block.key} label={block.label} />
            ) : (
              <div key={block.key} className="flex flex-col gap-2.5">
                {block.turns.map(renderTurn)}
              </div>
            ),
          )}
        </div>
      )}
    </div>
  );
}

type ThreadBlock =
  | { kind: "day"; key: string; label: string }
  | { kind: "turns"; key: string; turns: ConversationTurn[] };

/** Fold the flat turn list into display blocks: a message starts a turn, its
    task cards attach to it; a day separator anchors each new calendar day.
    Turns carry the persistent message's created_at; a local optimistic turn
    has none yet and is truthfully grouped under today. */
function buildThreadBlocks(turns: ConversationTurn[]): ThreadBlock[] {
  const groups: ConversationTurn[][] = [];
  for (const turn of turns) {
    if (turn.kind === "task" && groups.length > 0) groups[groups.length - 1].push(turn);
    else groups.push([turn]);
  }
  const blocks: ThreadBlock[] = [];
  let lastDayKey: string | null = null;
  for (const group of groups) {
    const createdAt = group[0].createdAt;
    const dayKey = createdAt ? dayKeyOf(createdAt) : dayKeyOf(new Date().toISOString());
    if (dayKey && dayKey !== lastDayKey) {
      blocks.push({ kind: "day", key: `day-${dayKey}`, label: createdAt ? dayLabel(createdAt) : "今天" });
      lastDayKey = dayKey;
    }
    blocks.push({ kind: "turns", key: group[0].id, turns: group });
  }
  return blocks;
}

/** Local calendar-day key for grouping; unparseable dates collapse to "". */
function dayKeyOf(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

/** Day separator label, relative to local today: 今天 / 昨天 / M月D日 / YYYY年M月D日. */
function dayLabel(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOf(now) - startOf(date)) / 86_400_000);
  if (diffDays <= 0) return "今天";
  if (diffDays === 1) return "昨天";
  if (date.getFullYear() === now.getFullYear()) return `${date.getMonth() + 1}月${date.getDate()}日`;
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

/** The day anchor — hairline with a centred quiet label, the thread's only clock. */
function DaySeparator({ label }: { label: string }) {
  return (
    <div className="flex select-none items-center gap-2.5 text-micro text-muted-soft">
      <span className="h-px flex-1 bg-line-soft" aria-hidden />
      {label}
      <span className="h-px flex-1 bg-line-soft" aria-hidden />
    </div>
  );
}

function RailGreeting() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-accent-wash text-accent">
        <Feather className="size-5" aria-hidden />
      </span>
      <p className="mt-4 font-serif text-md font-medium text-ink">让合著者帮你起草</p>
      <p className="mt-1.5 max-w-[230px] text-caption leading-relaxed text-muted">
        说一句想写什么——续写一段、起一个场景、或改写几句。它先给候选稿，经你采用才进手稿。
      </p>
    </div>
  );
}

function UserBubble({ body }: { body: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-modal rounded-br-control border border-line-soft bg-paper-deep px-3.5 py-2.5 text-sm leading-relaxed text-ink">
        {body}
      </div>
    </div>
  );
}

/** A short agent status line that carries no run of its own (rare). */
function AgentLine({ body }: { body: string }) {
  return (
    <div className="flex items-start gap-2 px-0.5">
      <Feather className="mt-0.5 size-3 shrink-0 text-muted" aria-hidden />
      <p className="text-caption leading-relaxed text-muted">{body}</p>
    </div>
  );
}

/**
 * One request's run, owned end-to-end: it re-reads its own event stream so a
 * later request never steals it and a reload never loses it. While live it
 * streams the candidate; once the author adopts, it settles into quiet history
 * rows that keep the steps, the recall line, and a link to the prose on the
 * canvas. Settled runs stop polling — the events are all already durably
 * stored, one pass re-reads them.
 */
function TaskTurn({
  runId,
  selection,
  csrfToken,
  adopted,
  settled,
  adoptingDraftId,
  onAdopt,
  onCancelRun,
  onSettled,
  onRevealAdopted,
  onTaskAdopted,
}: {
  runId: string;
  selection: WriterSelection | null;
  csrfToken: string | null;
  adopted: boolean;
  settled: SettledRunInfo | null;
  adoptingDraftId: string | null;
  onAdopt: (runId: string, draftId: string) => void;
  onCancelRun: (runId: string) => void;
  onSettled: (runId: string) => void;
  onRevealAdopted: (runId: string) => void;
  onTaskAdopted: (runId: string) => void;
}) {
  const liveRun = useWriterRun(selection, csrfToken, runId);
  const settledRef = useRef(false);
  // Draft status is known only while the hook lives; the workspace's
  // adoptedRunIds (blocks on reload, this session's adopt click live) is the
  // authority once it's marked.
  const isAdopted = adopted || liveRun?.draft?.status === "adopted";

  // Tell the workspace once when this run reaches a terminal phase.
  useEffect(() => {
    if (liveRun?.state.isTerminal && !settledRef.current) {
      settledRef.current = true;
      onSettled(runId);
    }
  }, [liveRun?.state.isTerminal, onSettled, runId]);

  // A live turn learns its draft was adopted (its own adopt click, or another
  // surface) from the draft's authoritative status — tell the workspace so it
  // can pin the settled state against future reloads and re-renders.
  const draftStatus = liveRun?.draft?.status;
  useEffect(() => {
    if (!adopted && draftStatus === "adopted") {
      onTaskAdopted(runId);
    }
  }, [adopted, draftStatus, onTaskAdopted, runId]);

  if (!liveRun) return null;
  const { state } = liveRun;
  // Prefer the durable draft text (what was actually saved) over the token
  // stream; they agree, but the draft row is the record of truth.
  const candidateText = liveRun.draft?.contentText ?? state.candidateText;
  const draftId = liveRun.draft?.draftId ?? state.draftId;
  const candidate = candidateText
    ? { draftId: draftId ?? "", text: candidateText, complete: state.isTerminal && Boolean(draftId) }
    : null;

  // A fully-adopted run settles into quiet history rows that keep the whole
  // exchange legible: what it consulted, what it wrote, where it landed.
  if (isAdopted && candidate) {
    return (
      <SettledCard
        liveRun={liveRun}
        text={candidate.text}
        settled={settled}
        onRevealAdopted={() => onRevealAdopted(runId)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-2.5">
      <TaskCard liveRun={liveRun} onCancel={() => onCancelRun(runId)} />
      <ConsistencyNotice violations={state.consistencyViolations} status={state.consistencyStatus} />
      <CitationsRow citations={state.citations} degraded={state.citationsDegraded} trimmedItems={state.contextTrimmedItems} />
      {state.isTerminal && state.phase === "failed" ? (
        <p className="rounded-panel border border-danger/30 bg-danger-wash px-3 py-2 text-caption leading-relaxed text-danger">
          {state.terminalMessage ?? "这次起草没写成"}。换个说法再试一次，或稍后再发。
        </p>
      ) : null}
      {candidate ? (
        <CandidateCard
          candidate={candidate}
          adopting={adoptingDraftId === candidate.draftId}
          onAdopt={() => candidate.draftId && onAdopt(runId, candidate.draftId)}
        />
      ) : null}
    </div>
  );
}

/** A canon-contradiction warning — surfaced, never silent (doc 41 §4.7). */
function ConsistencyNotice({
  violations,
  status,
}: {
  violations: ConsistencyViolation[];
  status: "clean" | "skipped" | "degraded" | "violations" | null;
}) {
  if (violations.length === 0 && !status) return null;
  if (violations.length === 0) {
    const copy = status === "clean"
      ? "已对照当前设定检查 · 未发现明显冲突"
      : status === "skipped"
        ? "本次未执行一致性检查 · 审校模型未绑定"
        : "一致性检查未完成 · 结果不可用";
    return (
      <p className={`rounded-panel border px-3 py-2 text-caption leading-relaxed ${status === "degraded" ? "border-danger/30 bg-danger-wash text-danger" : "border-line-soft bg-paper/55 text-muted"}`}>
        {copy}
      </p>
    );
  }
  const major = violations.filter((v) => v.severity === "major").length;
  return (
    <div
      role="alert"
      className="rounded-panel border border-gold/50 bg-gold/10 px-3 py-2.5"
      aria-label="一致性提醒"
    >
      <div className="flex items-center gap-1.5 text-caption font-medium text-ink">
        <span className="grid size-4 place-items-center rounded-full bg-gold text-caption text-panel">!</span>
        与设定可能有出入{major > 0 ? ` · ${major} 处较严重` : ""}
      </div>
      <ul className="mt-1.5 flex flex-col gap-1">
        {violations.slice(0, 4).map((v, i) => (
          <li key={i} className="text-caption leading-relaxed text-muted">
            <span className="text-ink/80">{v.canonLabel}</span>
            <span className="mx-1">·</span>
            {v.conflict}
          </li>
        ))}
        {violations.length > 4 ? (
          <li className="text-caption text-muted">另 {violations.length - 4} 处…</li>
        ) : null}
      </ul>
    </div>
  );
}

/**
 * The recall drawer — a compact summary by default, with one expandable row
 * per recalled asset. The runtime only sends bounded previews, so authors can
 * audit what the agent actually saw without opening a separate debug panel.
 */
function CitationsRow({ citations, degraded, trimmedItems = 0 }: { citations: RunCitation[]; degraded: boolean; trimmedItems?: number }) {
  const [open, setOpen] = useState(false);
  const [openCitationId, setOpenCitationId] = useState<string | null>(null);
  if (citations.length === 0 && trimmedItems === 0) return null;
  return (
    <div className="ml-5.5 overflow-hidden rounded-panel border border-line-soft bg-paper/55" aria-label="本轮召回的设定">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-10 w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-paper-deep/60"
      >
        <span className="grid size-5 shrink-0 place-items-center rounded-full bg-accent-wash text-accent" aria-hidden>
          <Feather className="size-3" />
        </span>
        <span className="min-w-0 flex-1 text-caption text-muted">
          参考了 <span className="font-medium text-ink-soft">{citations.length} 项</span>
          {trimmedItems > 0 ? <span> · 另有 {trimmedItems} 条未带入</span> : null}
        </span>
        <span className="shrink-0 text-caption text-muted">{open ? "收起" : "查看召回内容"}</span>
        <ChevronDown className={`size-3.5 shrink-0 text-muted-soft transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="recall-list"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden border-t border-line-soft"
          >
            <ol className="flex flex-col gap-1 p-1.5">
              {citations.map((citation, index) => {
                const itemId = `${citation.assetId}-${index}`;
                return (
                  <CitationItem
                    key={itemId}
                    citation={citation}
                    index={index}
                    open={openCitationId === itemId}
                    onToggle={() => setOpenCitationId((current) => (current === itemId ? null : itemId))}
                  />
                );
              })}
            </ol>
            {degraded ? <p className="border-t border-line-soft px-3 py-2 text-micro text-muted">语义检索不可用，本轮已退回关键词召回。</p> : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function CitationItem({
  citation,
  index,
  open,
  onToggle,
}: {
  citation: RunCitation;
  index: number;
  open: boolean;
  onToggle: () => void;
}) {
  const previewLabel = citation.channel === "search_manuscript" ? "前文摘录" : "召回内容";
  const hasDetail = Boolean(citation.contentPreview || citation.summary);
  return (
    <li className="overflow-hidden rounded-control border border-transparent transition-colors hover:border-line-soft hover:bg-paper-deep/40">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-label={`${open ? "收起" : "查看"}第 ${index + 1} 条召回：${citation.title}`}
        className="flex min-h-11 w-full items-center gap-2 px-2 py-1.5 text-left"
      >
        <span className="grid size-5 shrink-0 place-items-center rounded-full border border-line bg-paper font-mono text-micro tabular-nums text-muted" aria-hidden>
          {index + 1}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-caption font-medium text-ink-soft">{citation.title}</span>
          <span className="mt-0.5 block truncate text-micro text-muted-soft">{citationMeta(citation)}</span>
        </span>
        <ChevronDown className={`size-3.5 shrink-0 text-muted-soft transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="citation-detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="mx-2 mb-2 rounded-control bg-panel/75 px-2.5 py-2.5">
              {citation.contentPreview ? (
                <>
                  <p className="text-micro font-medium text-muted">{previewLabel}</p>
                  <p className="mt-1 whitespace-pre-wrap break-words font-serif text-caption leading-relaxed text-ink-soft">
                    {citation.contentPreview}
                  </p>
                </>
              ) : null}
              {citation.summary && citation.summary !== citation.contentPreview ? (
                <div className={citation.contentPreview ? "mt-2 border-t border-line-soft pt-2" : ""}>
                  <p className="text-micro font-medium text-muted">摘要</p>
                  <p className="mt-1 whitespace-pre-wrap break-words text-caption leading-relaxed text-muted">{citation.summary}</p>
                </div>
              ) : null}
              {!hasDetail ? <p className="text-caption leading-relaxed text-muted">本轮只保留了这条来源的标题，没有可展开的内容预览。</p> : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </li>
  );
}

function citationMeta(citation: RunCitation): string {
  const parts = [citationChannelLabel(citation.channel)];
  if (citation.lifecycle && citation.lifecycle !== "常驻" && citation.lifecycle !== "前文") parts.push(citation.lifecycle);
  if (typeof citation.score === "number") parts.push(`相关度 ${Math.round(citation.score * 100)}%`);
  if (citation.relationType) parts.push(citation.relationType);
  return parts.join(" · ");
}

function citationChannelLabel(channel: string): string {
  switch (channel) {
    case "query_assets":
      return "已选资产";
    case "search_assets":
      return "语义召回";
    case "search_manuscript":
      return "前文呼应";
    case "always_on":
      return "常驻设定";
    case "关联带出":
      return "关联带出";
    case "fuse_recall":
      return "融合召回";
    default:
      return "故事资料";
  }
}

/** The collapsible task status — one calm line that expands to its steps. */
function TaskCard({ liveRun, onCancel }: { liveRun: LiveRun; onCancel: () => void }) {
  const { state, cancelling } = liveRun;
  const live = !state.isTerminal;
  const [open, setOpen] = useState(false);
  const hasSteps = state.steps.length > 0;

  return (
    <div>
      <div className="-mx-1.5 flex min-h-8 items-center gap-1.5 rounded-control px-1.5 py-1 transition-colors hover:bg-line/25">
        <button
          type="button"
          onClick={() => hasSteps && setOpen((v) => !v)}
          disabled={!hasSteps}
          aria-expanded={hasSteps ? open : undefined}
          className={`flex min-w-0 flex-1 items-center gap-2 text-left ${hasSteps ? "" : "cursor-default"}`}
        >
          {live ? (
            <Loader2 className="size-3.5 shrink-0 animate-spin text-accent" aria-hidden />
          ) : state.phase === "completed" ? (
            <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-hidden />
          ) : state.phase === "failed" ? (
            <span className="size-3.5 shrink-0 rounded-full bg-danger/70" aria-hidden />
          ) : (
            <span className="size-3.5 shrink-0 rounded-full bg-muted/50" aria-hidden />
          )}
          <span className="min-w-0 flex-1 truncate text-sm tabular-nums text-ink-soft">{state.statusLine}</span>
          {hasSteps ? (
            <ChevronDown
              className={`size-3 shrink-0 text-muted-soft transition-transform ${open ? "rotate-180" : ""}`}
              aria-hidden
            />
          ) : null}
        </button>
        {live ? (
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelling}
            aria-label="停止这次起草"
            className="grid size-6 shrink-0 place-items-center rounded-control text-muted transition-colors hover:bg-accent-wash hover:text-accent disabled:opacity-50"
          >
            <Square className="size-3" aria-hidden />
          </button>
        ) : null}
      </div>

      <AnimatePresence initial={false}>
        {open && hasSteps ? (
          <motion.ol
            key="steps"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="mb-1 ml-5.5 mt-0.5 flex flex-col gap-1.5">
              {state.steps.map((step) => (
                <StepRow key={step.id} step={step} />
              ))}
            </div>
          </motion.ol>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function StepRow({ step }: { step: RunStep }) {
  return (
    <li className="flex items-center gap-2 text-caption">
      {step.status === "running" ? (
        <Loader2 className="size-3 shrink-0 animate-spin text-gold" aria-hidden />
      ) : step.status === "completed" ? (
        <Check className="size-3 shrink-0 text-success" aria-hidden />
      ) : step.status === "error" ? (
        <XCircle className="size-3 shrink-0 text-danger" aria-hidden />
      ) : (
        <CircleDashed className="size-3 shrink-0 text-muted" aria-hidden />
      )}
      <span className={`min-w-0 flex-1 truncate ${step.status === "running" ? "text-ink" : "text-muted"}`}>
        {step.label}
      </span>
    </li>
  );
}

/** The candidate draft — hairline card (head / serif excerpt + fade toggle /
    foot); solid vermilion only on the adopt action. */
function CandidateCard({
  candidate,
  adopting,
  onAdopt,
}: {
  candidate: { draftId: string; text: string; complete: boolean };
  adopting: boolean;
  onAdopt: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const words = candidate.text.replace(/\s/g, "").length;
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="ml-5.5 overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div className="flex items-center gap-2 border-b border-line-soft px-3 py-2">
        <span className="text-micro font-semibold tracking-wider text-candidate">
          {candidate.complete ? "候选稿" : "起草中"}
        </span>
        <span className="ml-auto font-mono text-micro tabular-nums text-muted">
          {words.toLocaleString()} 字
        </span>
      </div>

      <div className="px-3.5 py-2.5">
        <p
          className={`whitespace-pre-wrap font-serif text-sm text-ink ${
            candidate.complete && !expanded ? "line-clamp-2" : ""
          }`}
        >
          {candidate.text}
          {!candidate.complete ? (
            <span className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-accent align-baseline" />
          ) : null}
        </p>
        {candidate.complete ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="mt-1 block text-caption text-muted transition-colors hover:text-accent"
          >
            全稿 {words.toLocaleString()} 字 · {expanded ? "收起" : "展开查看"}
          </button>
        ) : null}
      </div>

      {candidate.complete ? (
        <div className="flex items-center gap-2.5 border-t border-line-soft px-3 py-2">
          <span className="text-caption text-muted">采用后进入手稿末尾</span>
          <button
            type="button"
            onClick={onAdopt}
            disabled={adopting}
            className="ml-auto flex items-center gap-1.5 rounded-control bg-accent px-3 py-1.5 text-caption font-medium text-panel transition-colors hover:bg-accent-strong disabled:opacity-60"
          >
            {adopting ? "采用中…" : "采用进手稿"}
            <kbd className="kbd border-panel/35 bg-transparent px-1 py-0 text-panel/85">⌘⏎</kbd>
          </button>
        </div>
      ) : null}
    </motion.div>
  );
}

/**
 * A settled exchange: the adopted prose kept as a calm read-only run-row,
 * with the run's steps and recall line still attached, and a trail link that
 * reveals where the prose landed on the canvas.
 */
function SettledCard({
  liveRun,
  text,
  settled,
  onRevealAdopted,
}: {
  liveRun: LiveRun;
  text: string;
  settled: SettledRunInfo | null;
  onRevealAdopted: () => void;
}) {
  const [open, setOpen] = useState(false);
  const words = text.replace(/\s/g, "").length;
  return (
    <div className="flex flex-col gap-2.5">
      <TaskCard liveRun={liveRun} onCancel={() => {}} />
      <ConsistencyNotice violations={liveRun.state.consistencyViolations} status={liveRun.state.consistencyStatus} />
      <CitationsRow citations={liveRun.state.citations} degraded={liveRun.state.citationsDegraded} trimmedItems={liveRun.state.contextTrimmedItems} />
      <div>
        <div className="-mx-1.5 flex min-h-8 items-center gap-1.5 rounded-control px-1.5 py-1 transition-colors hover:bg-line/25">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="flex min-w-0 flex-1 items-center gap-2 text-left"
          >
            <FileCheck className="size-3.5 shrink-0 text-muted" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-sm tabular-nums text-ink-soft">
              已采用 · {words.toLocaleString()} 字进手稿
            </span>
            <ChevronDown className={`size-3 shrink-0 text-muted-soft transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
          </button>
          {settled ? (
            <button
              type="button"
              onClick={onRevealAdopted}
              className="flex shrink-0 items-center gap-1 rounded-control px-1.5 py-1 text-caption text-muted transition-colors hover:text-accent"
            >
              <MapPin className="size-3" aria-hidden />
              查看正文
            </button>
          ) : null}
        </div>
        <AnimatePresence initial={false}>
          {open ? (
            <motion.div
              key="body"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <p className="mt-1 max-h-[220px] overflow-y-auto whitespace-pre-wrap font-serif text-sm text-muted">
                {text}
              </p>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}
