"use client";

import { Check, Copy, FileCheck2, PenLine, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { WriterRunEvent } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { humanizeFailure } from "../lib/user-facing-copy";
import { writerDraftText } from "../lib/writer-event-store";
import { Bi } from "./bilingual-text";
import { PublicErrorNotice } from "./public-error-notice";
import { SubmitButton } from "./submit-button";
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
  chapterId?: string;
  adoptDraftAction?: (formData: FormData) => Promise<DraftAdoptionActionResult>;
};

/**
 * Canvas-primary candidate draft (docs/refactor-saas/36 W2).
 * On phone, revealing prose auto-switches to the artifact pane.
 */
export function WriterCandidateSheet({
  locale,
  initialEvents,
  draftId,
  adopted: adoptedProp,
  chapterId = "",
  adoptDraftAction,
}: WriterCandidateSheetProps) {
  const router = useRouter();
  const stream = useWriterRunStream();
  const workbench = useWriterWorkbench();
  const events = stream?.events ?? initialEvents;
  const draftText = useMemo(() => writerDraftText(events), [events]);
  const active = stream?.active === true;
  const charCount = [...draftText].length;
  const revealedRef = useRef(false);
  const [pending, setPending] = useState(false);
  const [adoptedLocal, setAdoptedLocal] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const adopted = adoptedProp || adoptedLocal;

  useEffect(() => {
    if (!draftText || revealedRef.current) return;
    revealedRef.current = true;
    workbench?.revealArtifact({ badge: true });
  }, [draftText, workbench]);

  async function onAdopt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!adoptDraftAction || pending || adopted) return;
    setPending(true);
    setErrorText(null);
    try {
      const formData = new FormData(event.currentTarget);
      const result = await adoptDraftAction(formData);
      if (!result.ok) {
        setErrorText(humanizeFailure(locale, result.code, result.message || undefined));
        return;
      }
      setAdoptedLocal(true);
      router.refresh();
    } catch {
      setErrorText(humanizeFailure(locale, "DRAFT_ADOPTION_FAILED", undefined));
    } finally {
      setPending(false);
    }
  }

  if (!draftText && !active) {
    return null;
  }

  return (
    <section
      aria-label={tx(locale, "候选稿", "Candidate draft")}
      className="writer-candidate-sheet"
      data-adopted={adopted ? "true" : "false"}
      data-streaming={active && !draftText ? "pending" : active ? "true" : "false"}
      id="writer-candidate-sheet"
    >
      <span className="writer-candidate-badge">
        {adopted ? <Bi zh="正式手稿" en="Manuscript" /> : <Bi zh="候选稿" en="Candidate" />}
      </span>
      <div className="writer-candidate-prose">
        {draftText ? (
          draftText.split(/\n+/).map((paragraph, index) => <p key={`p-${index}`}>{paragraph}</p>)
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
            <Bi zh="已进入手稿" en="Adopted into manuscript" />
          </span>
        ) : (
          <span>
            <Bi zh="采用后才会进入你的正式手稿" en="Adopt to place this into your manuscript" />
          </span>
        )}
      </div>
      {!adopted && draftId ? (
        <div className="writer-candidate-actions">
          {errorText ? (
            <PublicErrorNotice
              message={<span>{errorText}</span>}
              title={<Bi zh="采用未完成" en="Adoption incomplete" />}
            />
          ) : null}
          {adoptDraftAction ? (
            <form className="writer-candidate-action-form" onSubmit={onAdopt}>
              <input name="draftId" type="hidden" value={draftId} />
              {chapterId ? <input name="chapterId" type="hidden" value={chapterId} /> : null}
              <SubmitButton
                className="writer-candidate-adopt"
                forcePending={pending}
                idleLabel={
                  <>
                    <FileCheck2 aria-hidden="true" size={16} />
                    <Bi zh="采用为手稿" en="Adopt into manuscript" />
                  </>
                }
                pendingLabel={<Bi zh="正在采用…" en="Adopting…" />}
              />
            </form>
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
            <Bi zh="继续修改" en="Keep editing" />
          </button>
        </div>
      ) : null}
      {adopted ? (
        <p className="form-hint writer-candidate-discard-hint">
          <Trash2 aria-hidden="true" size={14} />
          <Bi zh="已采用。可在下方手稿区继续编辑。" en="Adopted. Continue editing in the manuscript below." />
        </p>
      ) : null}
    </section>
  );
}
