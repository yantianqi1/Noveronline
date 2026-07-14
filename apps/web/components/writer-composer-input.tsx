"use client";

import { LoaderCircle, Send } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { SubmitButton } from "./submit-button";
import { WriterModePicker } from "./writer-mode-picker";

type WriterComposerInputProps = {
  locale: Locale;
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
export function WriterComposerInput({ locale }: WriterComposerInputProps) {
  const [canSend, setCanSend] = useState(false);

  const onInput = useCallback((event: FormEvent<HTMLTextAreaElement>) => {
    const el = event.currentTarget;
    const value = el.value.trim();
    setCanSend(value.length > 0);
    syncTextareaHeight(el);
  }, []);

  return (
    <div className="writer-composer-input-row" data-can-send={canSend ? "true" : "false"}>
      <WriterModePicker locale={locale} variant="chip" />
      <textarea
        id="writer-instruction"
        name="instruction"
        placeholder={tx(locale, "写一段要发生什么…", "What should happen next…")}
        required
        rows={1}
        onInput={onInput}
      />
      <SubmitButton
        aria-label={tx(locale, "开始写作", "Start writer run")}
        className="writer-send-button"
        data-can-send={canSend ? "true" : "false"}
        disabled={!canSend}
        idleLabel={
          <>
            <Send aria-hidden="true" size={18} strokeWidth={1.75} />
            <span className="sr-only">
              <Bi zh="开始写作" en="Start writer run" />
            </span>
          </>
        }
        pendingLabel={
          <>
            <LoaderCircle aria-hidden="true" className="is-spinning" size={18} />
            <span className="sr-only">
              <Bi zh="启动中" en="Starting" />
            </span>
          </>
        }
        title={tx(locale, "开始写作", "Start writer run")}
        tone="secondary"
      />
    </div>
  );
}
