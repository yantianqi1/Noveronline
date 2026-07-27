"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ScrollText, X } from "lucide-react";

import type { SeedRun, WorkflowEvent } from "@/lib/api/overview-types";
import { stageLabel } from "@/lib/api/seed";

/**
 * Seed run log modal ("查看日志") — the run's raw workflow event stream rendered
 * as a backend-style terminal: dark panel, monospace, one line per event
 * (timestamp · level · [stage] · message). Opens scrolled to the live tail.
 * Closes on outside-click, Esc, and the × button; focus returns to the trigger.
 */
export function SeedLogModal({
  open,
  run,
  events,
  live,
  onClose,
}: {
  open: boolean;
  run: SeedRun | null;
  events: WorkflowEvent[];
  live: boolean;
  onClose: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  // Esc closes.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // On open: jump to the live tail + move focus into the dialog.
  useEffect(() => {
    if (!open) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    closeRef.current?.focus();
  }, [open]);

  // While live, keep pinned to the tail as new events stream in.
  useEffect(() => {
    if (!open || !live) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events, open, live]);

  const lines = events.map(toLogLine);
  const errorCount = lines.filter((l) => l.level === "ERROR").length;
  const runShort = run ? run.run_id.slice(0, 6) : "—";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          className="fixed inset-0 z-[70] grid place-items-center bg-ink/45 p-5 backdrop-blur-[3px]"
          onMouseDown={(e) => {
            // outside-click closes (only when the backdrop itself is clicked)
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Seed 运行日志"
            initial={{ opacity: 0, y: 12, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.99 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="flex max-h-[78vh] w-[min(760px,100%)] flex-col overflow-hidden rounded-modal border border-ink-line bg-ink-surface shadow-ink"
          >
            {/* title bar — a real label, not imitation window furniture. The
                three coloured dots mimicked macOS traffic lights that closed
                nothing, and reused the semantic status colours for decoration. */}
            <div className="flex flex-none items-center gap-2 border-b border-ink-line bg-ink-surface-raised px-4 py-3">
              <ScrollText className="size-3.5 shrink-0 text-ink-text-muted" aria-hidden />
              <span className="font-mono text-caption tracking-wide text-ink-text-muted">
                seed · run <b className="font-semibold text-ink-text">{runShort}</b> · event stream
              </span>
              <button
                ref={closeRef}
                type="button"
                onClick={onClose}
                aria-label="关闭日志"
                className="ml-auto grid size-7 place-items-center rounded-control border border-ink-line text-ink-text-muted transition-colors hover:border-danger/50 hover:bg-danger/20 hover:text-ink-text"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>

            {/* the stream */}
            <div
              ref={scrollRef}
              className="seed-log-scroll flex-1 overflow-auto px-4 py-3.5 font-mono text-caption text-ink-text-muted"
            >
              {lines.length === 0 ? (
                <div className="py-6 text-center text-ink-text-muted opacity-60">
                  还没有事件。运行开始后会逐行输出在这里。
                </div>
              ) : (
                lines.map((line, i) => <LogLine key={i} line={line} />)
              )}
              {live && lines.length > 0 && (
                <div className="py-1">
                  <span className="seed-log-cursor" />
                </div>
              )}
            </div>

            {/* footer */}
            <div className="flex flex-none items-center justify-between border-t border-ink-line px-4 py-2.5 font-mono text-caption tracking-wide text-ink-text-muted">
              <span>
                {lines.length} events{errorCount > 0 ? ` · ${errorCount} errors` : ""}
              </span>
              <span>esc / 点击空白处关闭</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* -------------------------------------------------------------------------- */

type LogLineData = {
  ts: string;
  level: "INFO" | "OK" | "WARN" | "ERROR";
  stage: string | null;
  text: string;
};

function LogLine({ line }: { line: LogLineData }) {
  const levelClass =
    line.level === "OK"
      ? "text-success"
      : line.level === "WARN"
        ? "text-warning"
        : line.level === "ERROR"
          ? "text-danger"
          : "text-ink-text-muted";
  return (
    <div className="flex gap-3 whitespace-pre-wrap break-words py-px">
      <span className="flex-none tabular-nums text-ink-text-muted opacity-60">{line.ts}</span>
      <span className={`w-[52px] flex-none font-bold tracking-wide ${levelClass}`}>{line.level}</span>
      <span className={`flex-1 ${line.level === "ERROR" ? "text-danger" : "text-ink-text-muted"}`}>
        {line.stage && <span className="text-ink-text-muted">[{line.stage}] </span>}
        {line.text}
      </span>
    </div>
  );
}

/** Reduce one workflow event into a terminal line. */
function toLogLine(event: WorkflowEvent): LogLineData {
  const payload = event.payload ?? {};
  const stage = typeof payload.stage === "string" ? payload.stage : null;
  const message =
    (typeof payload.error_message === "string" && payload.error_message) ||
    (typeof payload.message === "string" && payload.message) ||
    event.event_type;

  let level: LogLineData["level"] = "INFO";
  if (event.event_type.includes("failed") || event.event_type === "workflow.failed") level = "ERROR";
  else if (event.event_type.includes("completed")) level = "OK";
  else if (event.event_type.includes("pending") || event.event_type.includes("start")) level = "WARN";

  return {
    ts: formatTime(event.created_at),
    level,
    stage: stage ? stageLabel(stage) : null,
    text: message,
  };
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
