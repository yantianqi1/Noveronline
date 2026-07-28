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
    <div className="shrink-0 p-3">
      <div className="rounded-panel border border-line bg-panel px-3 py-2 transition-colors focus-within:border-accent/50">
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
          placeholder={placeholder ?? "让合著者起草、续写或改写…"}
          aria-label="给合著者的指令"
          className="block max-h-[132px] w-full resize-none bg-transparent py-1.5 text-sm leading-relaxed text-ink placeholder:text-muted-soft focus:outline-none disabled:opacity-60"
        />
        <div className="mt-1.5 flex items-center gap-2">
          <span className="flex items-center gap-1 text-micro text-muted">
            <kbd className="kbd">⏎</kbd> 发送
          </span>
          <span className="flex items-center gap-1 text-micro text-muted">
            <kbd className="kbd">⇧⏎</kbd> 换行
          </span>
          <button
            type="button"
            onClick={submit}
            disabled={disabled || value.trim().length === 0}
            aria-label="发送"
            className="ml-auto grid size-[26px] shrink-0 place-items-center rounded-control bg-accent text-panel transition-all hover:bg-accent-strong disabled:opacity-40"
          >
            <ArrowUp className="size-3.5" aria-hidden />
          </button>
        </div>
      </div>
      <p className="mt-1.5 truncate px-1 text-micro text-muted">
        起草内容先作候选稿，经你采用才进手稿。
      </p>
    </div>
  );
}
