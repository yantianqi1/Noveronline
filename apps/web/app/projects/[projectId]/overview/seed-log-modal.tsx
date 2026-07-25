"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";

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
            className="flex max-h-[78vh] w-[min(760px,100%)] flex-col overflow-hidden rounded-[13px] border border-black/50 bg-[#16130f] shadow-[0_30px_80px_-20px_rgba(0,0,0,0.7),inset_0_0_0_1px_rgba(247,236,210,0.06)]"
          >
            {/* title bar */}
            <div className="flex flex-none items-center gap-3 border-b border-[rgba(247,236,210,0.09)] bg-gradient-to-b from-[rgba(247,236,210,0.04)] to-transparent px-4 py-3">
              <span className="flex gap-1.5">
                <i className="size-2.5 rounded-full bg-[#b0563f]" />
                <i className="size-2.5 rounded-full bg-[#b08a3e]" />
                <i className="size-2.5 rounded-full bg-[#5d7a4e]" />
              </span>
              <span className="font-mono text-[12px] tracking-wide text-[rgba(247,236,210,0.72)]">
                seed · run <b className="font-semibold text-[#f1e6cf]">{runShort}</b> · event stream
              </span>
              <button
                ref={closeRef}
                type="button"
                onClick={onClose}
                aria-label="关闭日志"
                className="ml-auto grid size-7 place-items-center rounded-[7px] border border-[rgba(247,236,210,0.14)] text-[rgba(247,236,210,0.6)] transition-colors hover:border-[rgba(176,86,63,0.4)] hover:bg-[rgba(176,86,63,0.2)] hover:text-[#f1e6cf]"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>

            {/* the stream */}
            <div
              ref={scrollRef}
              className="seed-log-scroll flex-1 overflow-auto px-4 py-3.5 font-mono text-[12px] leading-[1.75] text-[#cdbf9f]"
            >
              {lines.length === 0 ? (
                <div className="py-6 text-center text-[rgba(205,191,159,0.5)]">
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
            <div className="flex flex-none items-center justify-between border-t border-[rgba(247,236,210,0.09)] px-4 py-2.5 font-mono text-[10.5px] tracking-wide text-[rgba(247,236,210,0.4)]">
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
      ? "text-[#7fae6e]"
      : line.level === "WARN"
        ? "text-[#d0a24a]"
        : line.level === "ERROR"
          ? "text-[#d96a52]"
          : "text-[#7ba0d6]";
  return (
    <div className="flex gap-3 whitespace-pre-wrap break-words py-px">
      <span className="flex-none tabular-nums text-[rgba(205,191,159,0.42)]">{line.ts}</span>
      <span className={`w-[52px] flex-none font-bold tracking-wide ${levelClass}`}>{line.level}</span>
      <span className={`flex-1 ${line.level === "ERROR" ? "text-[#e8a591]" : "text-[#d9cdaf]"}`}>
        {line.stage && <span className="text-[#b5a377]">[{line.stage}] </span>}
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
