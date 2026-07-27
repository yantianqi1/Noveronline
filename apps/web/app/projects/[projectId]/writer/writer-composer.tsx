"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * The persistent composer — one calm primary action (send). Enter sends,
 * Shift+Enter makes a newline. Auto-grows to a few lines; disabled only while
 * a run is live, with the reason visible in the status line above it.
 */
export function WriterComposer({
  onSend,
  disabled,
  placeholder,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder?: string;
}) {
  const [value, setValue] = useState("");
  const areaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    area.style.height = "0px";
    area.style.height = `${Math.min(area.scrollHeight, 132)}px`;
  }, [value]);

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  }

  return (
    <div className="shrink-0 border-t border-line-soft bg-panel/60 p-3">
      <div className="flex items-end gap-2 rounded-modal border border-line bg-panel px-3 py-2 shadow-panel transition-colors focus-within:border-accent/50">
        <textarea
          ref={areaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          rows={1}
          disabled={disabled}
          placeholder={placeholder ?? "让合著者起草、续写或改写… (Enter 发送)"}
          aria-label="给合著者的指令"
          className="max-h-[132px] flex-1 resize-none bg-transparent py-1.5 text-sm leading-relaxed text-ink placeholder:text-muted-soft focus:outline-none disabled:opacity-60"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || value.trim().length === 0}
          aria-label="发送"
          className="grid size-8 shrink-0 place-items-center rounded-panel bg-accent text-panel shadow-accent transition-all hover:bg-accent-strong disabled:opacity-40 disabled:shadow-none"
        >
          <ArrowUp className="size-4" aria-hidden />
        </button>
      </div>
      <p className="mt-1.5 px-1 text-caption leading-relaxed text-muted-soft">
        起草的内容先作候选稿，经你采用才进手稿。Shift+Enter 换行。
      </p>
    </div>
  );
}
