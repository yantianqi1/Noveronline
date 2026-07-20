"use client";

import { Check, Copy, FileCheck2, Loader2, PenLine, Undo2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { WriterRunEvent } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { humanizeFailure } from "../lib/user-facing-copy";
import { writerDraftText } from "../lib/writer-event-store";
import { Bi } from "./bilingual-text";
import { useWriterRunStream } from "./writer-run-stream";
import { useWriterWorkbench } from "./writer-workbench-context";

export type DraftAdoptionActionResult = {
  ok: boolean;
  code: string;
  message: string;
  blockId?: string;
};

type WriterDraftBlockProps = {
  locale: Locale;
  initialEvents: WriterRunEvent[];
  draftId: string;
  adopted: boolean;
  adoptedBlockId?: string;
  chapterId?: string;
  adoptDraftAction?: (formData: FormData) => Promise<DraftAdoptionActionResult>;
  undoAdoptionAction?: (formData: FormData) => Promise<DraftAdoptionActionResult>;
};

const CHIP_AUTO_DISMISS_MS = 8000;

/**
 * In-paper draft block — generated prose streams into the manuscript paper
 * itself, then settles into a real manuscript section. The text stays in one
 * place from first token to saved section, so the canvas never shows two
 * competing documents.
 *
 * States:
 * 1. **streaming**: ghost section at the end of the paper, prose grows live.
 * 2. **saving**: same ghost, header switches to "saving into manuscript".
 * 3. **adopted**: ghost collapses into a compact success chip (auto-dismiss);
 *    the real section flashes in place.
 * 4. **error**: auto-adoption failed — ghost turns amber with retry/copy.
 * 5. **withdrawn**: user undid the adoption — text remains here, out of the
 *    manuscript, with copy / keep-revising / close actions.
 */
export function WriterDraftBlock({
  locale,
  initialEvents,
  draftId,
  adopted: adoptedProp,
  adoptedBlockId = "",
  chapterId = "",
  adoptDraftAction,
  undoAdoptionAction,
}: WriterDraftBlockProps) {
  const router = useRouter();
  const stream = useWriterRunStream();
  const workbench = useWriterWorkbench();
  const events = stream?.events ?? initialEvents;
  const draftText = useMemo(() => writerDraftText(events), [events]);
  const active = stream?.active === true;
  const charCount = [...draftText].length;
  const revealedRef = useRef(false);
  const autoAdoptRef = useRef(false);
  const flashedBlockRef = useRef("");
  const [pending, setPending] = useState(false);
  const [undoPending, setUndoPending] = useState(false);
  const [adoptedLocal, setAdoptedLocal] = useState(false);
  const [localBlockId, setLocalBlockId] = useState("");
  const [undone, setUndone] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
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

  // Auto-adopt exactly once per finished run; undo remains a single user action.
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

  // After adoption, bring the landed section into view and flash it once so
  // "saved into manuscript" has a visible anchor instead of a silent mutation.
  useEffect(() => {
    if (!adopted || !blockId || flashedBlockRef.current === blockId) return;
    flashedBlockRef.current = blockId;
    let attempts = 0;
    const tryReveal = () => {
      const el = document.querySelector(`[data-block-id="${blockId}"]`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("is-flash");
        window.setTimeout(() => el.classList.remove("is-flash"), 1800);
        return;
      }
      attempts += 1;
      if (attempts < 6) window.setTimeout(tryReveal, 400);
    };
    const timer = window.setTimeout(tryReveal, 250);
    return () => window.clearTimeout(timer);
  }, [adopted, blockId]);

  // The success chip dismisses itself; the text stays as a normal section.
  useEffect(() => {
    if (!adopted || undone || dismissed || errorText) return;
    const timer = window.setTimeout(() => setDismissed(true), CHIP_AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [adopted, undone, dismissed, errorText]);

  if (!draftText && !active) {
    return null;
  }

  // --- Adopted: compact success chip; prose now lives in the paper itself ---
  if (adopted) {
    if (dismissed) return null;
    return (
      <div className="writer-draft-chip" data-draft-chip="adopted" role="status">
        <Check aria-hidden="true" size={15} className="writer-draft-chip-icon" />
        <span className="writer-draft-chip-text">
          <Bi zh={`已存入手稿（${charCount} 字）`} en={`Saved into manuscript (${charCount} chars)`} />
        </span>
        {undoAdoptionAction && blockId ? (
          <button
            className="writer-draft-chip-action"
            disabled={undoPending}
            onClick={() => void onUndo()}
            type="button"
          >
            <Undo2 aria-hidden="true" size={14} />
            {undoPending ? <Bi zh="撤回中…" en="Undoing…" /> : <Bi zh="撤回" en="Undo" />}
          </button>
        ) : null}
        {errorText ? <span className="writer-draft-chip-error">{errorText}</span> : null}
        <button
          aria-label={tx(locale, "关闭通知", "Dismiss")}
          className="writer-draft-chip-dismiss"
          onClick={() => setDismissed(true)}
          type="button"
        >
          <X aria-hidden="true" size={14} />
        </button>
      </div>
    );
  }

  // --- Ghost section inside the paper: streaming / saving / error / withdrawn ---
  if (undone && dismissed) return null;
  const ghostState = active ? "streaming" : undone ? "withdrawn" : errorText ? "error" : "saving";
  return (
    <article
      aria-label={tx(locale, "本次生成的正文", "Generated prose")}
      className="writer-manuscript-section writer-draft-block"
      data-draft-state={ghostState}
      id="writer-draft-block"
    >
      <div className="writer-draft-block-head" role="status">
        {ghostState === "streaming" ? (
          <>
            <span aria-hidden="true" className="writer-draft-block-dot" />
            <span className="writer-draft-block-label">
              {draftText ? (
                <Bi zh={`Writer 正在创作… ${charCount} 字`} en={`Writer is drafting… ${charCount} chars`} />
              ) : (
                <Bi zh="Writer 正在创作…" en="Writer is drafting…" />
              )}
            </span>
            <span className="writer-draft-block-hint">
              <Bi zh="写完后自动存入手稿" en="Will be saved automatically" />
            </span>
          </>
        ) : null}
        {ghostState === "saving" ? (
          <>
            <Loader2 aria-hidden="true" size={14} className="writer-save-spin" />
            <span className="writer-draft-block-label">
              <Bi zh="正在存入手稿…" en="Saving into your manuscript…" />
            </span>
          </>
        ) : null}
        {ghostState === "withdrawn" ? (
          <span className="writer-draft-block-label">
            <Bi zh="已撤回 · 这段正文未进入手稿" en="Removed · this text is not in the manuscript" />
          </span>
        ) : null}
        {ghostState === "error" ? (
          <span className="writer-draft-block-label">
            <Bi zh="存入手稿未完成" en="Could not save into manuscript" />
          </span>
        ) : null}
      </div>

      <div className="writer-draft-prose">
        {draftText ? (
          splitCandidateParagraphs(draftText).map((paragraph, index) => (
            <p key={`p-${index}`}>{paragraph}</p>
          ))
        ) : (
          <p className="writer-draft-placeholder">
            <Bi zh="正文正在生成…" en="Prose is being drafted…" />
          </p>
        )}
        {ghostState === "streaming" && draftText ? (
          <span aria-hidden="true" className="writer-draft-cursor" />
        ) : null}
      </div>

      {ghostState === "error" ? (
        <div className="writer-draft-block-actions">
          <p className="writer-draft-block-error" role="alert">{errorText}</p>
          {!undone && adoptDraftAction && draftId ? (
            <button
              className="writer-draft-block-primary"
              disabled={pending}
              onClick={() => void runAdoption()}
              type="button"
            >
              <FileCheck2 aria-hidden="true" size={16} />
              {pending ? <Bi zh="正在存入…" en="Saving…" /> : <Bi zh="重试存入手稿" en="Retry saving" />}
            </button>
          ) : null}
          <button
            className="writer-draft-block-secondary"
            onClick={() => {
              if (typeof navigator !== "undefined" && draftText) {
                void navigator.clipboard?.writeText(draftText);
              }
            }}
            type="button"
          >
            <Copy aria-hidden="true" size={15} />
            <Bi zh="复制正文" en="Copy text" />
          </button>
        </div>
      ) : null}

      {ghostState === "withdrawn" ? (
        <div className="writer-draft-block-actions">
          <button
            className="writer-draft-block-secondary"
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
            className="writer-draft-block-secondary"
            onClick={() => workbench?.setMobileView("conversation")}
            type="button"
          >
            <PenLine aria-hidden="true" size={15} />
            <Bi zh="继续和 Agent 修改" en="Keep revising with the Agent" />
          </button>
          <button
            className="writer-draft-block-secondary"
            onClick={() => setDismissed(true)}
            type="button"
          >
            <X aria-hidden="true" size={15} />
            <Bi zh="关闭" en="Close" />
          </button>
        </div>
      ) : null}
    </article>
  );
}

function splitCandidateParagraphs(text: string): string[] {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  const byBlank = normalized.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  if (byBlank.length > 1) return byBlank;
  const byLine = normalized.split(/\n+/).map((part) => part.trim()).filter(Boolean);
  return byLine.length > 0 ? byLine : [normalized];
}
