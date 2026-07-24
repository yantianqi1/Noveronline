"use client";

import { Check, CheckCircle2, ChevronDown, CircleDashed, Feather, Loader2, Square, XCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import type { WriterSelection } from "@/lib/api/writer-client";
import type { ConsistencyViolation, RunCitation, RunStep } from "@/lib/api/writer-run";

import { useWriterRun, type LiveRun } from "./use-writer-run";

/**
 * The conversation rail — the single entry point to the Writer Agent. It is
 * deliberately subordinate to the manuscript canvas: quiet header, a thread of
 * author messages + one task card per request, and a persistent composer at the
 * foot. The agent never speaks in prose here; its output lives in the candidate
 * card. Each request owns its run end-to-end, so consecutive requests never
 * clobber one another: an adopted candidate settles into a calm history card.
 */

export type ConversationTurn =
  | { kind: "user"; id: string; body: string }
  | { kind: "task"; id: string; runId: string };

export function WriterRail({
  turns,
  selection,
  csrfToken,
  adoptedRunIds,
  adoptingDraftId,
  onAdopt,
  onCancelRun,
  onRunSettled,
}: {
  turns: ConversationTurn[];
  selection: WriterSelection | null;
  csrfToken: string | null;
  adoptedRunIds: ReadonlySet<string>;
  adoptingDraftId: string | null;
  onAdopt: (runId: string, draftId: string) => void;
  onCancelRun: (runId: string) => void;
  onRunSettled: (runId: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Keep the newest exchange in view as the thread grows.
  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns.length]);

  return (
    <div className="flex h-full flex-col">
      {/* Quiet header */}
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line-soft px-4">
        <span className="grid size-6 place-items-center rounded-[7px] bg-accent-wash text-accent">
          <Feather className="size-3" aria-hidden />
        </span>
        <span className="text-[13px] font-medium text-ink">合著者</span>
        <span className="ml-auto text-[11px] text-muted">常驻协作</span>
      </div>

      {/* Thread */}
      <div ref={scrollRef} className="min-h-0 basis-0 flex-1 overflow-y-auto px-4 py-4">
        {turns.length === 0 ? (
          <RailGreeting />
        ) : (
          <div className="flex flex-col gap-4">
            {turns.map((turn) =>
              turn.kind === "user" ? (
                <UserBubble key={turn.id} body={turn.body} />
              ) : (
                <TaskTurn
                  key={turn.id}
                  runId={turn.runId}
                  selection={selection}
                  csrfToken={csrfToken}
                  adopted={adoptedRunIds.has(turn.runId)}
                  adoptingDraftId={adoptingDraftId}
                  onAdopt={onAdopt}
                  onCancelRun={onCancelRun}
                  onSettled={onRunSettled}
                />
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function RailGreeting() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-accent-wash text-accent">
        <Feather className="size-5" aria-hidden />
      </span>
      <p className="mt-4 font-serif text-[15px] font-medium text-ink">让合著者帮你起草</p>
      <p className="mt-1.5 max-w-[230px] text-[12px] leading-relaxed text-muted">
        说一句想写什么——续写一段、起一个场景、或改写几句。它先给候选稿，经你采用才进手稿。
      </p>
    </div>
  );
}

function UserBubble({ body }: { body: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-[14px] rounded-br-[4px] bg-accent px-3.5 py-2.5 text-[13.5px] leading-relaxed text-white shadow-[0_6px_16px_-8px_rgba(143,33,27,0.5)]">
        {body}
      </div>
    </div>
  );
}

/**
 * One request's run, owned end-to-end: it polls its own event stream so a later
 * request never steals it. While live it streams the candidate; once the author
 * adopts, it settles into a calm history card. It polls only while its run is
 * active (settled turns re-render from a one-shot fetch, not an interval).
 */
function TaskTurn({
  runId,
  selection,
  csrfToken,
  adopted,
  adoptingDraftId,
  onAdopt,
  onCancelRun,
  onSettled,
}: {
  runId: string;
  selection: WriterSelection | null;
  csrfToken: string | null;
  adopted: boolean;
  adoptingDraftId: string | null;
  onAdopt: (runId: string, draftId: string) => void;
  onCancelRun: (runId: string) => void;
  onSettled: (runId: string) => void;
}) {
  const liveRun = useWriterRun(selection, csrfToken, runId);
  const settledRef = useRef(false);

  // Tell the workspace once when this run reaches a terminal phase.
  useEffect(() => {
    if (liveRun?.state.isTerminal && !settledRef.current) {
      settledRef.current = true;
      onSettled(runId);
    }
  }, [liveRun?.state.isTerminal, onSettled, runId]);

  if (!liveRun) return null;
  const { state } = liveRun;
  const candidate = state.candidateText
    ? { draftId: state.draftId ?? "", text: state.candidateText, complete: state.isTerminal && Boolean(state.draftId) }
    : null;

  // A fully-adopted run collapses into a quiet history card.
  if (adopted && candidate) {
    return <AdoptedCard text={candidate.text} />;
  }

  return (
    <div className="flex flex-col gap-3">
      <TaskCard liveRun={liveRun} onCancel={() => onCancelRun(runId)} />
      <ConsistencyNotice violations={state.consistencyViolations} />
      <CitationsRow citations={state.citations} degraded={state.citationsDegraded} />
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
function ConsistencyNotice({ violations }: { violations: ConsistencyViolation[] }) {
  if (violations.length === 0) return null;
  const major = violations.filter((v) => v.severity === "major").length;
  return (
    <div
      role="alert"
      className="rounded-[10px] border border-gold/50 bg-gold/10 px-3 py-2.5"
      aria-label="一致性提醒"
    >
      <div className="flex items-center gap-1.5 text-[12px] font-medium text-ink">
        <span className="grid size-4 place-items-center rounded-full bg-gold text-[10px] text-white">!</span>
        与设定可能有出入{major > 0 ? ` · ${major} 处较严重` : ""}
      </div>
      <ul className="mt-1.5 flex flex-col gap-1">
        {violations.slice(0, 4).map((v, i) => (
          <li key={i} className="text-[11.5px] leading-relaxed text-muted">
            <span className="text-ink/80">{v.canonLabel}</span>
            <span className="mx-1">·</span>
            {v.conflict}
          </li>
        ))}
        {violations.length > 4 ? (
          <li className="text-[11px] text-muted">另 {violations.length - 4} 处…</li>
        ) : null}
      </ul>
    </div>
  );
}

/** The recall chips — which settings/canon the agent grounded this draft in. */
function CitationsRow({ citations, degraded }: { citations: RunCitation[]; degraded: boolean }) {
  if (citations.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-0.5" aria-label="本轮召回的设定">
      <span className="text-[11px] text-muted">参考了</span>
      {citations.slice(0, 8).map((c) => (
        <span
          key={c.assetId}
          title={c.channel === "always_on" ? "常驻设定 · 每次写作都在场" : c.lifecycle ? `设定 · ${c.lifecycle}` : "设定"}
          className={
            c.channel === "always_on"
              ? "rounded-full border border-gold/60 bg-gold/10 px-2 py-0.5 text-[11px] text-ink"
              : "rounded-full border border-line-soft bg-panel px-2 py-0.5 text-[11px] text-ink/80"
          }
        >
          {c.channel === "always_on" ? "常驻 · " : ""}
          {c.title}
        </span>
      ))}
      {citations.length > 8 ? (
        <span className="text-[11px] text-muted">+{citations.length - 8}</span>
      ) : null}
      {degraded ? (
        <span className="text-[10.5px] text-muted" title="向量检索不可用，已退回关键词召回">
          ·关键词召回
        </span>
      ) : null}
    </div>
  );
}

/** The collapsible task status — one calm line that expands to its steps. */
function TaskCard({ liveRun, onCancel }: { liveRun: LiveRun; onCancel: () => void }) {
  const { state, cancelling } = liveRun;
  const live = !state.isTerminal;
  const [open, setOpen] = useState(false);
  const hasSteps = state.steps.length > 0;

  return (
    <div className="overflow-hidden rounded-[12px] border border-line bg-panel">
      <div className="flex items-center gap-1.5 px-3.5 py-3">
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
            <CheckCircle2 className="size-3.5 shrink-0 text-[#3f7a4a]" aria-hidden />
          ) : (
            <span className="size-3.5 shrink-0 rounded-full bg-accent/70" aria-hidden />
          )}
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{state.statusLine}</span>
          {hasSteps ? (
            <ChevronDown
              className={`size-3.5 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
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
            className="grid size-6 shrink-0 place-items-center rounded-[7px] text-muted transition-colors hover:bg-accent-wash hover:text-accent disabled:opacity-50"
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
            className="border-t border-line-soft"
          >
            <div className="flex flex-col gap-2 px-3.5 py-3">
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
    <li className="flex items-center gap-2 text-[12px]">
      {step.status === "running" ? (
        <Loader2 className="size-3 shrink-0 animate-spin text-gold" aria-hidden />
      ) : step.status === "completed" ? (
        <Check className="size-3 shrink-0 text-[#3f7a4a]" aria-hidden />
      ) : step.status === "error" ? (
        <XCircle className="size-3 shrink-0 text-accent" aria-hidden />
      ) : (
        <CircleDashed className="size-3 shrink-0 text-muted" aria-hidden />
      )}
      <span className={`min-w-0 flex-1 truncate ${step.status === "running" ? "text-ink" : "text-muted"}`}>
        {step.label}
      </span>
    </li>
  );
}

/** The candidate draft — old-gold dashed frame, vermilion only on adopt. */
function CandidateCard({
  candidate,
  adopting,
  onAdopt,
}: {
  candidate: { draftId: string; text: string; complete: boolean };
  adopting: boolean;
  onAdopt: () => void;
}) {
  const words = candidate.text.replace(/\s/g, "").length;
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="relative rounded-[12px] border border-dashed border-gold/60 bg-panel px-4 py-3.5"
    >
      {/* corner badge */}
      <span className="absolute -top-2 left-3 rounded-full bg-gold px-2 py-0.5 text-[10.5px] font-medium tracking-wide text-white">
        {candidate.complete ? "候选稿" : "起草中"}
      </span>

      <div className="mt-1.5 max-h-[280px] overflow-y-auto">
        <p className="whitespace-pre-wrap font-serif text-[14px] leading-[1.85] text-ink">
          {candidate.text}
          {!candidate.complete ? (
            <span className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-accent align-baseline" />
          ) : null}
        </p>
      </div>

      {candidate.complete ? (
        <div className="mt-3 flex items-center gap-2 border-t border-line-soft pt-3">
          <span className="text-[11.5px] text-muted">{words} 字</span>
          <button
            type="button"
            onClick={onAdopt}
            disabled={adopting}
            className="ml-auto rounded-[8px] bg-accent px-4 py-1.5 text-[12px] font-medium text-white shadow-[0_6px_14px_-6px_rgba(143,33,27,0.6)] transition-colors hover:bg-accent-strong disabled:opacity-60"
          >
            {adopting ? "采用中…" : "采用进手稿"}
          </button>
        </div>
      ) : null}
    </motion.div>
  );
}

/** A settled exchange: the adopted prose, kept as a calm read-only memory. */
function AdoptedCard({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-[12px] border border-line-soft/80 bg-panel/60 px-4 py-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left"
      >
        <CheckCircle2 className="size-3.5 shrink-0 text-[#3f7a4a]" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-[12px] text-muted">
          已采用 · {text.replace(/\s/g, "").length} 字进手稿
        </span>
        <ChevronDown className={`size-3.5 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
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
            <p className="mt-2.5 max-h-[220px] overflow-y-auto whitespace-pre-wrap border-t border-line-soft pt-2.5 font-serif text-[13px] leading-[1.8] text-muted">
              {text}
            </p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
