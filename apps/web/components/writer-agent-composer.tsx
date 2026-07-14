"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState, type FormEvent, type ReactNode } from "react";

import { type Locale, tx } from "../lib/locale";
import { humanizeFailure } from "../lib/user-facing-copy";
import { WriterComposerInput } from "./writer-composer-input";
import { useWriterRunSession } from "./writer-run-session";

export type WriterRunActionResult = {
  ok: boolean;
  code: string;
  message: string;
  runId?: string;
  traceId?: string;
};

type WriterAgentComposerProps = {
  locale: Locale;
  selectedChapterId: string;
  selectedSceneId: string;
  writerRunAction: (formData: FormData) => Promise<WriterRunActionResult>;
  /** Called after successful admission so the thread can show the user bubble immediately. */
  onQueued?: (payload: { instruction: string; runId: string }) => void;
  /** Called as soon as the user submits, before admission returns. */
  onSubmitStart?: (instruction: string) => void;
  children?: ReactNode;
};

/**
 * Client-side writer admission form: keeps instruction on failure, shows inline
 * errors, and navigates to the new run via router.replace (so RSC sees runId).
 *
 * While a run is streaming (session.busy), send stays locked so authors cannot
 * stack congested admissions. The user bubble + live status appear immediately.
 */
export function WriterAgentComposer({
  locale,
  selectedChapterId,
  selectedSceneId,
  writerRunAction,
  onQueued,
  onSubmitStart,
  children,
}: WriterAgentComposerProps) {
  const router = useRouter();
  const session = useWriterRunSession();
  const formRef = useRef<HTMLFormElement>(null);
  const [pending, setPending] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  const runBusy = session?.busy === true;
  const sendLocked = pending || runBusy;

  const onSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (sendLocked) {
        return;
      }
      const form = event.currentTarget;
      const formData = new FormData(form);
      const instruction = String(formData.get("instruction") ?? "").trim();
      if (!instruction) {
        return;
      }
      setPending(true);
      setErrorText(null);
      onSubmitStart?.(instruction);
      session?.beginSubmit(instruction);
      try {
        const result = await writerRunAction(formData);
        if (!result.ok) {
          setErrorText(humanizeFailure(locale, result.code, result.message || undefined));
          session?.failSubmit();
          return;
        }
        // Clear instruction only after successful queue admission.
        const instructionField = form.elements.namedItem("instruction");
        if (instructionField instanceof HTMLTextAreaElement) {
          instructionField.value = "";
          instructionField.dispatchEvent(new Event("input", { bubbles: true }));
        }
        if (result.runId) {
          onQueued?.({ instruction, runId: result.runId });
          session?.admitRun(result.runId);
          const next = new URLSearchParams(
            typeof window !== "undefined" ? window.location.search : "",
          );
          next.delete("writerRunStatus");
          next.delete("writerRunCode");
          next.delete("writerRunMessage");
          next.set("runId", result.runId);
          if (result.traceId) {
            next.set("traceId", result.traceId);
          }
          const qs = next.toString();
          const path = typeof window !== "undefined" ? window.location.pathname : "";
          // Use App Router navigation so searchParams include runId and the
          // conversation can load the new run (soft history edits are invisible to RSC).
          router.replace(qs ? `${path}?${qs}` : path, { scroll: false });
        }
      } catch {
        setErrorText(humanizeFailure(locale, "WORKFLOW_FAILED", undefined));
        session?.failSubmit();
      } finally {
        setPending(false);
      }
    },
    [locale, onQueued, onSubmitStart, router, sendLocked, session, writerRunAction],
  );

  return (
    <form
      ref={formRef}
      className="writer-agent-composer"
      data-pending={sendLocked ? "true" : "false"}
      onSubmit={onSubmit}
    >
      <input name="chapterId" type="hidden" value={selectedChapterId} />
      <input name="sceneId" type="hidden" value={selectedSceneId} />
      <label className="sr-only" htmlFor="writer-instruction">
        {tx(locale, "写作指令", "Instruction")}
      </label>
      <WriterComposerInput
        locale={locale}
        forcePending={pending}
        sendLocked={runBusy && !pending}
        lockHint={
          runBusy && !pending
            ? tx(locale, "写作助手正在处理，完成后可继续发送", "The assistant is working — send again when it finishes")
            : undefined
        }
      />
      {children}
      {errorText ? (
        <p className="writer-composer-inline-error" role="alert">
          {errorText}
        </p>
      ) : null}
    </form>
  );
}
