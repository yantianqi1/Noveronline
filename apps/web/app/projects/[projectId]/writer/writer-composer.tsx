"use client";

import { ArrowUp, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * The persistent composer — one calm primary action (send). Enter sends,
 * Shift+Enter makes a newline. Auto-grows to a few lines; disabled only while
 * a run is live, with the reason visible in the status line above it.
 *
 * Worldline attach (doc 25 §3.6): typing `@` opens a listbox of this project's
 * saved worldline paths; picking one attaches that worldline's session so the
 * next run follows its adopted plot timeline. The attach shows as a removable
 * chip above the input and rides the run start — it is never typed into prose.
 */
export type WorldlineAttachment = {
  /** The worldline simulation session whose canon events form the timeline. */
  session_id: string;
  /** The saved path the author picked, when one exists (enables deep-read). */
  path_id?: string;
  /** Display title shown on the chip. */
  title: string;
};

export type WorldlineMentionOption = {
  session_id: string;
  path_id?: string;
  title: string;
  summary?: string;
  /**
   * How many adopted (canon) events this worldline has. When 0, the option is
   * flagged "暂无已采纳事件" so the author knows attaching it yields an empty
   * timeline — the run would follow nothing.
   */
  canon_count?: number;
};

export function WriterComposer({
  onSend,
  disabled,
  placeholder,
  worldlineOptions,
  worldlineLoadError,
  attachedWorldline,
  onAttachWorldline,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder?: string;
  /** Saved worldline paths offered for `@`-attach; omit/empty hides the feature. */
  worldlineOptions?: WorldlineMentionOption[];
  /** A real backend read error; never silently turn an unavailable list into an empty list. */
  worldlineLoadError?: string | null;
  attachedWorldline?: WorldlineAttachment | null;
  onAttachWorldline?: (attachment: WorldlineAttachment | null) => void;
}) {
  const [value, setValue] = useState("");
  // Mention popup state: the `@` query text + where it started, or null when closed.
  const [mention, setMention] = useState<{ query: string; start: number } | null>(null);
  const [highlight, setHighlight] = useState(0);
  const areaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    area.style.height = "0px";
    area.style.height = `${Math.min(area.scrollHeight, 132)}px`;
  }, [value]);

  const filtered = (worldlineOptions ?? []).filter((option) => {
    if (!mention) return false;
    const q = mention.query.trim().toLowerCase();
    if (!q) return true;
    return (
      option.title.toLowerCase().includes(q) ||
      (option.summary ?? "").toLowerCase().includes(q)
    );
  });

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
    setMention(null);
  }

  function pickWorldline(option: WorldlineMentionOption) {
    onAttachWorldline?.({
      session_id: option.session_id,
      path_id: option.path_id,
      title: option.title,
    });
    // Remove the `@query` fragment from the text — the attach is structured, not prose.
    if (mention) {
      const before = value.slice(0, mention.start);
      const after = value.slice(areaRef.current?.selectionStart ?? value.length);
      setValue((before + after).replace(/\s{2,}/g, " "));
    }
    setMention(null);
    areaRef.current?.focus();
  }

  function handleChange(next: string, caret: number) {
    setValue(next);
    // Detect an active `@` mention: the last `@` at/left of the caret, either at
    // the start or right after whitespace, with no whitespace in the query itself.
    const uptoCaret = next.slice(0, caret);
    const at = uptoCaret.lastIndexOf("@");
    if (at >= 0 && (at === 0 || /\s/.test(uptoCaret[at - 1]))) {
      const query = uptoCaret.slice(at + 1);
      if (!/\s/.test(query)) {
        setMention({ query, start: at });
        setHighlight(0);
        return;
      }
    }
    setMention(null);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (mention && filtered.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHighlight((h) => (h + 1) % filtered.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setHighlight((h) => (h - 1 + filtered.length) % filtered.length);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        pickWorldline(filtered[highlight]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setMention(null);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const showMention = mention !== null && (worldlineOptions ?? []).length > 0;

  return (
    <div className="shrink-0 p-3">
      {worldlineLoadError ? (
        <p role="alert" className="mb-2 rounded-control border border-danger/35 bg-danger/5 px-3 py-2 text-caption text-danger">
          世界线暂时无法加载：{worldlineLoadError}
        </p>
      ) : null}
      {attachedWorldline ? (
        <div className="mb-2 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-control border border-gold/50 bg-gold/10 px-2.5 py-1 text-caption text-gold">
            <span className="font-medium">世界线</span>
            <span className="max-w-[220px] truncate">{attachedWorldline.title}</span>
            <button
              type="button"
              aria-label="移除世界线"
              onClick={() => onAttachWorldline?.(null)}
              className="grid size-4 place-items-center rounded-full transition-colors hover:bg-gold/20"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
          <span className="text-micro text-muted">下次起草将顺着这条世界线的剧情时间线</span>
        </div>
      ) : null}

      <div className="relative rounded-panel border border-line bg-panel px-3 py-2 transition-colors focus-within:border-accent/50">
        {showMention ? (
          <div
            role="listbox"
            aria-label="世界线列表"
            className="absolute bottom-full left-0 z-30 mb-1.5 w-[320px] overflow-hidden rounded-modal border border-line bg-panel shadow-lift"
          >
            <div className="max-h-[280px] overflow-y-auto py-1.5">
              {filtered.length === 0 ? (
                <div className="px-4 py-2.5 text-caption text-muted">没有匹配的世界线</div>
              ) : (
                filtered.map((option, index) => {
                  const noCanon = option.canon_count === 0;
                  return (
                    <button
                      key={option.path_id ?? option.session_id}
                      type="button"
                      role="option"
                      aria-selected={index === highlight}
                      onMouseEnter={() => setHighlight(index)}
                      onClick={() => pickWorldline(option)}
                      className={`flex w-full flex-col gap-0.5 px-4 py-2.5 text-left transition-colors ${
                        index === highlight ? "bg-accent-wash text-accent" : "text-ink hover:bg-paper"
                      }`}
                    >
                      <span className="flex items-center gap-2 text-sm">
                        <span className="truncate">{option.title}</span>
                        {noCanon ? (
                          <span className="shrink-0 rounded bg-muted/20 px-1.5 py-0.5 text-micro text-muted">
                            暂无已采纳事件
                          </span>
                        ) : null}
                      </span>
                      {option.summary ? (
                        <span className="truncate text-caption text-muted">{option.summary}</span>
                      ) : null}
                    </button>
                  );
                })
              )}
            </div>
          </div>
        ) : null}

        <textarea
          ref={areaRef}
          value={value}
          onChange={(event) => handleChange(event.target.value, event.target.selectionStart)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={disabled}
          placeholder={placeholder ?? "让合著者起草、续写或改写…输入 @ 可挂载一条世界线"}
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
          {(worldlineOptions ?? []).length > 0 ? (
            <span className="flex items-center gap-1 text-micro text-muted">
              <kbd className="kbd">@</kbd> 世界线
            </span>
          ) : null}
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
