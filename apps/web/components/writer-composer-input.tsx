"use client";

import { LoaderCircle, Send } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { SubmitButton } from "./submit-button";
import { WriterModePicker } from "./writer-mode-picker";

type WriterComposerInputProps = {
  locale: Locale;
  /** When parent owns submit (client form), mirror pending so send stays disabled. */
  forcePending?: boolean;
  /** Run is streaming: allow drafting the next note, but block send to avoid congestion. */
  sendLocked?: boolean;
  lockHint?: string;
};

const MAX_TEXTAREA_PX = 96;

function syncTextareaHeight(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_PX)}px`;
}

/**
 * Compact instruction row: mode chip + auto-growing field + gray send that
 * fades in when there is non-whitespace text (and stays submittable).
 */
export function WriterComposerInput({
  locale,
  forcePending = false,
  sendLocked = false,
  lockHint,
}: WriterComposerInputProps) {
  const [canSend, setCanSend] = useState(false);

  const onInput = useCallback((event: FormEvent<HTMLTextAreaElement>) => {
    const el = event.currentTarget;
    const value = el.value.trim();
    setCanSend(value.length > 0);
    syncTextareaHeight(el);
  }, []);

  const blocked = forcePending || sendLocked;

  // Single-frame composer aligned with mainstream agent chat: full-width
  // textarea on top, quiet tool row (mode left, send right) underneath.
  return (
    <>
      <div
        className="writer-composer-input-row"
        data-can-send={canSend && !blocked ? "true" : "false"}
        data-pending={blocked ? "true" : "false"}
      >
        <textarea
          id="writer-instruction"
          name="instruction"
          placeholder={
            sendLocked && !forcePending
              ? tx(locale, "写作助手处理中…可先记下下一段", "Assistant is working… you can draft the next note")
              : tx(locale, "写一段要发生什么…", "What should happen next…")
          }
          required
          rows={1}
          disabled={forcePending}
          onInput={onInput}
        />
        <div className="writer-composer-toolrow">
          <WriterModePicker locale={locale} variant="chip" />
          <SubmitButton
            aria-label={tx(locale, "开始写作", "Start writer run")}
            className="writer-send-button"
            data-can-send={canSend && !blocked ? "true" : "false"}
            disabled={!canSend || blocked}
            forcePending={forcePending}
            idleLabel={
              <>
                <Send aria-hidden="true" size={17} strokeWidth={1.75} />
                <span className="sr-only">
                  <Bi zh="开始写作" en="Start writer run" />
                </span>
              </>
            }
            pendingLabel={
              <>
                <LoaderCircle aria-hidden="true" className="is-spinning" size={17} />
                <span className="sr-only">
                  <Bi zh="启动中" en="Starting" />
                </span>
              </>
            }
            title={
              sendLocked && !forcePending
                ? lockHint || tx(locale, "写作助手正在处理", "Assistant is working")
                : tx(locale, "开始写作", "Start writer run")
            }
            tone="secondary"
          />
        </div>
      </div>
      {sendLocked && !forcePending && lockHint ? (
        <p className="writer-composer-lock-hint" role="status">
          {lockHint}
        </p>
      ) : null}
    </>
  );
}
