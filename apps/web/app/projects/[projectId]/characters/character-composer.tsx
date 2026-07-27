"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { TURN_KINDS, type TurnKind } from "@/lib/api/character-console-types";
import { turnKindLabel } from "./character-scene-stream";

/**
 * The stage composer — a persistent bar at the foot of the scene. Four action
 * chips (我说 / 我做 / 我内心 / 我想影响) give the input a semantic prefix that
 * lands on `turn.turn_kind`; the auto-growing textarea keeps long actions
 * readable; the vermilion send is the one primary action on the stage.
 */

const KIND_HINTS: Record<TurnKind, string> = {
  say: "此刻，TA 想说…",
  do: "此刻，TA 做了…",
  think: "TA 心里在想…",
  influence: "TA 想影响谁、改变什么…",
};

export function CharacterComposer({
  disabled = false,
  busy = false,
  onSend,
}: {
  disabled?: boolean;
  busy?: boolean;
  onSend: (kind: TurnKind, text: string) => void;
}) {
  const [kind, setKind] = useState<TurnKind>("say");
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function autoGrow() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function submit() {
    const body = text.trim();
    if (!body || disabled || busy) return;
    onSend(kind, body);
    setText("");
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    });
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="shrink-0 border-t border-line bg-panel">
      {/* action-kind chips */}
      <div className="flex items-center gap-1.5 px-5 pt-3">
        {TURN_KINDS.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setKind(k)}
            aria-pressed={kind === k}
            className={cn(
              "rounded-panel px-3 py-1.5 text-caption font-medium transition-colors",
              kind === k
                ? "bg-accent-wash text-accent ring-1 ring-inset ring-accent/40"
                : "text-muted hover:bg-paper hover:text-ink",
            )}
          >
            {turnKindLabel(k)}
          </button>
        ))}
      </div>

      {/* input row */}
      <div className="flex items-end gap-3 px-5 pb-4 pt-2.5">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            autoGrow();
          }}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={disabled}
          placeholder={KIND_HINTS[kind]}
          className="max-h-[160px] flex-1 resize-none rounded-modal border border-line bg-paper px-4 py-3 font-serif text-base leading-relaxed text-ink outline-none transition-colors focus:border-accent/50 disabled:opacity-60"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || busy || !text.trim()}
          className="shrink-0 rounded-modal bg-accent px-5 py-3 text-sm font-medium text-panel shadow-hairline transition-colors hover:bg-accent-strong disabled:opacity-50"
        >
          {busy ? "送出…" : "发送"}
        </button>
      </div>
    </div>
  );
}
