"use client";

import { Check, Loader2, PenLine } from "lucide-react";
import { useMemo } from "react";

import type { Locale } from "../lib/locale";
import { writerDraftText } from "../lib/writer-event-store";
import { Bi } from "./bilingual-text";
import { useWriterRunStream } from "./writer-run-stream";
import { useWriterWorkbench } from "./writer-workbench-context";

/**
 * Canvas-header status pills: the single always-visible answer to "is my work
 * saved?". Shows live drafting progress while a run streams, plus the
 * manuscript edit save state reported by the in-place section editor.
 */
export function WriterCanvasStatus({ locale }: { locale: Locale }) {
  const workbench = useWriterWorkbench();
  const stream = useWriterRunStream();
  const events = stream?.events ?? [];
  const draftText = useMemo(() => writerDraftText(events), [events]);
  const drafting = stream?.active === true;
  const charCount = [...draftText].length;
  const saveState = workbench?.saveStatus.state ?? "idle";

  if (!drafting && saveState === "idle") return null;

  return (
    <div aria-live="polite" className="writer-canvas-status">
      {drafting ? (
        <span className="writer-status-pill" data-state="drafting" role="status">
          <span aria-hidden="true" className="writer-status-pill-dot" />
          {draftText ? (
            <Bi zh={`正在创作… ${charCount} 字`} en={`Drafting… ${charCount} chars`} />
          ) : (
            <Bi zh="正在创作…" en="Drafting…" />
          )}
        </span>
      ) : null}
      {saveState === "dirty" ? (
        <span className="writer-status-pill" data-state="dirty">
          <PenLine aria-hidden="true" size={12} />
          <Bi zh="未保存更改" en="Unsaved changes" />
        </span>
      ) : null}
      {saveState === "saving" ? (
        <span className="writer-status-pill" data-state="saving" role="status">
          <Loader2 aria-hidden="true" size={12} className="writer-save-spin" />
          <Bi zh="保存中…" en="Saving…" />
        </span>
      ) : null}
      {saveState === "saved" ? (
        <span className="writer-status-pill" data-state="saved" role="status">
          <Check aria-hidden="true" size={12} />
          <Bi zh="已保存" en="Saved" />
        </span>
      ) : null}
    </div>
  );
}
