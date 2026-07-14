"use client";

import { Check, Copy, FileCheck2, PenLine, Undo2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { WriterRunEvent } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { humanizeFailure } from "../lib/user-facing-copy";
import { writerDraftText } from "../lib/writer-event-store";
import { Bi } from "./bilingual-text";
import { PublicErrorNotice } from "./public-error-notice";
import { useWriterRunStream } from "./writer-run-stream";
import { useWriterWorkbench } from "./writer-workbench-context";

export type DraftAdoptionActionResult = {
  ok: boolean;
  code: string;
  message: string;
  blockId?: string;
};

type WriterCandidateSheetProps = {
  locale: Locale;
  initialEvents: WriterRunEvent[];
  draftId: string;
  adopted: boolean;
  adoptedBlockId?: string;
  chapterId?: string;
  adoptDraftAction?: (formData: FormData) => Promise<DraftAdoptionActionResult>;
  undoAdoptionAction?: (formData: FormData) => Promise<DraftAdoptionActionResult>;
};

/**
 * Canvas-primary candidate draft (docs/refactor-saas/36 W2).
 *
 * Auto-adoption: once the run finishes and prose is available, the draft is
 * saved into the manuscript automatically; the user gets a single visible
 * outcome ("已存入手稿") plus one undo action. Manual retry appears only when
 * the automatic save fails.
 */
export function WriterCandidateSheet({
  locale,
  initialEvents,
  draftId,
  adopted: adoptedProp,
  adoptedBlockId = "",
  chapterId = "",
  adoptDraftAction,
  undoAdoptionAction,
}: WriterCandidateSheetProps) {
  const router = useRouter();
  const stream = useWriterRunStream();
  const workbench = useWriterWorkbench();
  const events = stream?.events ?? initialEvents;
  const draftText = useMemo(() => writerDraftText(events), [events]);
  const active = stream?.active === true;
  const charCount = [...draftText].length;
  const revealedRef = useRef(false);
  const autoAdoptRef = useRef(false);
  const [pending, setPending] = useState(false);
  const [undoPending, setUndoPending] = useState(false);
  const [adoptedLocal, setAdoptedLocal] = useState(false);
  const [localBlockId, setLocalBlockId] = useState("");
  const [undone, setUndone] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const adopted = !undone && (adoptedProp || adoptedLocal);
  const blockId = localBlockId || adoptedBlockId;

  useEffect(() => {
    if (!draftText || revealedRef.current) return;
    revealedRef.current = true;
    workbench?.revealArtifact({ badge: true });
  }, [draftText, workbench]);

  async function runAdoption() {
    if (!adoptDraftAction || !draftId || pending || adopted || undone) return;
    setPending(true);
    setErrorText(null);
    try {
      const formData = new FormData();
      formData.set("draftId", draftId);
      if (chapterId) formData.set("chapterId", chapterId);
      const result = await adoptDraftAction(formData);
      if (!result.ok) {
        setErrorText(humanizeFailure(locale, result.code, result.message || undefined));
        return;
      }
      setAdoptedLocal(true);
      if (result.blockId) setLocalBlockId(result.blockId);
      router.refresh();
    } catch {
      setErrorText(humanizeFailure(locale, "DRAFT_ADOPTION_FAILED", undefined));
    } finally {
      setPending(false);
    }
  }

  // Auto-adopt exactly once when the run has finished and prose exists.
  useEffect(() => {
    if (autoAdoptRef.current) return;
    if (active || !draftText || !draftId || adopted || undone || !adoptDraftAction) return;
    autoAdoptRef.current = true;
    void runAdoption();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, draftText, draftId, adopted, undone, adoptDraftAction]);

  async function onUndo() {
    if (!undoAdoptionAction || !blockId || undoPending) return;
    setUndoPending(true);
    setErrorText(null);
    try {
      const formData = new FormData();
      formData.set("blockId", blockId);
      const result = await undoAdoptionAction(formData);
      if (!result.ok) {
        setErrorText(humanizeFailure(locale, result.code, result.message || undefined));
        return;
      }
      setUndone(true);
      setAdoptedLocal(false);
      router.refresh();
    } catch {
      setErrorText(humanizeFailure(locale, "DRAFT_ADOPTION_FAILED", undefined));
    } finally {
      setUndoPending(false);
    }
  }

  if (!draftText && !active) {
    return null;
  }

  return (
    <section
      aria-label={tx(locale, "本次生成的正文", "Generated prose")}
      className="writer-candidate-sheet"
      data-adopted={adopted ? "true" : "false"}
      data-streaming={active && !draftText ? "pending" : active ? "true" : "false"}
      id="writer-candidate-sheet"
    >
      <span className="writer-candidate-badge">
        {adopted ? (
          <Bi zh="已存入手稿" en="In manuscript" />
        ) : undone ? (
          <Bi zh="已撤回" en="Removed" />
        ) : active ? (
          <Bi zh="正在创作" en="Drafting" />
        ) : (
          <Bi zh="本次生成" en="This draft" />
        )}
      </span>
      <div className="writer-candidate-prose">
        {draftText ? (
          splitCandidateParagraphs(draftText).map((paragraph, index) => (
            <p key={`p-${index}`}>{paragraph}</p>
          ))
        ) : (
          <p className="writer-candidate-placeholder">
            <Bi zh="正文正在生成…" en="Prose is being drafted…" />
          </p>
        )}
        {active ? <span aria-hidden="true" className="writer-candidate-cursor" /> : null}
      </div>
      <div className="writer-candidate-meta">
        <span>
          {charCount} <Bi zh="字" en="chars" />
        </span>
        {adopted ? (
          <span className="writer-candidate-saved">
            <Check aria-hidden="true" size={14} />
            <Bi zh="已自动存入手稿，可在下方直接编辑" en="Saved into your manuscript — edit it below" />
          </span>
        ) : undone ? (
          <span>
            <Bi zh="已从手稿撤回，这段正文只保留在这里" en="Removed from the manuscript; the text stays here" />
          </span>
        ) : pending ? (
          <span>
            <Bi zh="正在存入手稿…" en="Saving into your manuscript…" />
          </span>
        ) : active ? (
          <span>
            <Bi zh="写完后会自动存入手稿" en="Will be saved into your manuscript automatically" />
          </span>
        ) : null}
      </div>
      {errorText ? (
        <div className="writer-candidate-actions">
          <PublicErrorNotice
            message={<span>{errorText}</span>}
            title={<Bi zh="存入手稿未完成" en="Could not save into manuscript" />}
          />
          {!adopted && !undone && adoptDraftAction && draftId ? (
            <button
              className="writer-candidate-adopt"
              disabled={pending}
              onClick={() => void runAdoption()}
              type="button"
            >
              <FileCheck2 aria-hidden="true" size={16} />
              {pending ? <Bi zh="正在存入…" en="Saving…" /> : <Bi zh="重试存入手稿" en="Retry saving" />}
            </button>
          ) : null}
        </div>
      ) : null}
      {!active && draftText ? (
        <div className="writer-candidate-actions">
          {adopted && undoAdoptionAction && blockId ? (
            <button
              className="writer-candidate-secondary"
              disabled={undoPending}
              onClick={() => void onUndo()}
              type="button"
            >
              <Undo2 aria-hidden="true" size={15} />
              {undoPending ? <Bi zh="正在撤回…" en="Undoing…" /> : <Bi zh="撤回，不放进手稿" en="Undo — remove from manuscript" />}
            </button>
          ) : null}
          <button
            className="writer-candidate-secondary"
            onClick={() => {
              if (typeof navigator !== "undefined" && draftText) {
                void navigator.clipboard?.writeText(draftText);
              }
            }}
            type="button"
          >
            <Copy aria-hidden="true" size={15} />
            <Bi zh="复制" en="Copy" />
          </button>
          <button
            className="writer-candidate-secondary"
            onClick={() => workbench?.setMobileView("conversation")}
            type="button"
          >
            <PenLine aria-hidden="true" size={15} />
            <Bi zh="继续和 Agent 修改" en="Keep revising with the Agent" />
          </button>
        </div>
      ) : null}
    </section>
  );
}

/** Prefer blank-line breaks; fall back to single newlines so long CJK drafts stay readable. */
function splitCandidateParagraphs(text: string): string[] {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  const byBlank = normalized.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  if (byBlank.length > 1) return byBlank;
  const byLine = normalized.split(/\n+/).map((part) => part.trim()).filter(Boolean);
  return byLine.length > 0 ? byLine : [normalized];
}
