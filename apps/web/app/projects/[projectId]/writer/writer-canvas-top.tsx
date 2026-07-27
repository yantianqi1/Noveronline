"use client";

import { Check, ChevronDown, CloudOff, FilePlus2, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Chapter } from "@/lib/api/writer-types";

export type SaveState =
  | { kind: "idle" }
  | { kind: "dirty" }
  | { kind: "saving" }
  | { kind: "saved"; at: number }
  | { kind: "conflict"; message: string }
  | { kind: "error"; message: string };

/**
 * The writer's top-strip — the chapter switcher, live word count, save state,
 * and the new-chapter action. It renders nothing on its own; the workspace
 * mounts it into the single shared project top bar (via a portal) so the
 * writer has exactly one header row instead of a stacked second bar.
 */
export function WriterCanvasTop({
  bookTitle,
  chapters,
  activeChapter,
  wordCount,
  saveState,
  onSelectChapter,
  onNewChapter,
  busy,
}: {
  bookTitle: string;
  chapters: Chapter[];
  activeChapter: Chapter | null;
  wordCount: number;
  saveState: SaveState;
  onSelectChapter: (chapterId: string) => void;
  onNewChapter: () => void;
  busy: boolean;
}) {
  return (
    <div className="flex h-full min-w-0 flex-1 items-center gap-3">
      {/* Chapter switcher */}
      <ChapterSwitcher
        bookTitle={bookTitle}
        chapters={chapters}
        activeChapter={activeChapter}
        onSelect={onSelectChapter}
      />

      <span aria-hidden className="h-4 w-px shrink-0 bg-line" />

      {/* Word count */}
      <span className="shrink-0 text-caption tabular-nums text-muted">
        {wordCount > 0 ? `${wordCount} 字` : "尚未落笔"}
      </span>

      <div className="ml-auto flex shrink-0 items-center gap-3">
        <SaveIndicator state={saveState} />
        <button
          type="button"
          onClick={onNewChapter}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-panel border border-line bg-panel px-3 py-1.5 text-caption font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-50"
        >
          <FilePlus2 className="size-3.5" aria-hidden />
          新章节
        </button>
      </div>
    </div>
  );
}

function ChapterSwitcher({
  bookTitle,
  chapters,
  activeChapter,
  onSelect,
}: {
  bookTitle: string;
  chapters: Chapter[];
  activeChapter: Chapter | null;
  onSelect: (chapterId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex min-w-0 items-center gap-1.5 rounded-panel px-2 py-1.5 text-left transition-colors hover:bg-panel"
      >
        <span className="max-w-[140px] truncate font-serif text-md font-semibold text-ink">
          {bookTitle}
        </span>
        <span aria-hidden className="text-muted-soft">
          ›
        </span>
        <span className="max-w-[180px] truncate text-sm text-ink">
          {activeChapter ? activeChapter.title : "选择章节"}
        </span>
        <ChevronDown
          className={`size-3.5 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      {open ? (
        <div
          role="listbox"
          aria-label="章节列表"
          className="absolute left-0 top-full z-30 mt-1.5 w-[280px] overflow-hidden rounded-modal border border-line bg-panel shadow-lift"
        >
          <div className="max-h-[320px] overflow-y-auto py-1.5">
            {chapters.map((chapter) => {
              const active = chapter.chapter_id === activeChapter?.chapter_id;
              return (
                <button
                  key={chapter.chapter_id}
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onSelect(chapter.chapter_id);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm transition-colors ${
                    active ? "bg-accent-wash text-accent" : "text-ink hover:bg-paper"
                  }`}
                >
                  <span className="w-4 shrink-0">
                    {active ? <Check className="size-3.5" aria-hidden /> : null}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{chapter.title}</span>
                  <span className="shrink-0 text-caption text-muted">
                    {chapterStatusLabel(chapter.status)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SaveIndicator({ state }: { state: SaveState }) {
  if (state.kind === "idle") return null;

  if (state.kind === "dirty") {
    return <span className="text-caption text-muted">未保存的修改…</span>;
  }
  if (state.kind === "saving") {
    return (
      <span className="flex items-center gap-1.5 text-caption text-muted">
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
        正在保存
      </span>
    );
  }
  if (state.kind === "saved") {
    return (
      <span className="flex items-center gap-1.5 text-caption text-success">
        <Check className="size-3.5" aria-hidden />
        已保存
      </span>
    );
  }
  // conflict | error — honest, never a fake "saved".
  return (
    <span className="flex max-w-[300px] items-center gap-1.5 text-caption text-accent" role="alert">
      <CloudOff className="size-3.5 shrink-0" aria-hidden />
      <span className="truncate">{state.message}</span>
    </span>
  );
}

function chapterStatusLabel(status: string): string {
  switch (status) {
    case "planned":
      return "规划中";
    case "drafting":
      return "写作中";
    case "completed":
      return "已完成";
    default:
      return "";
  }
}
