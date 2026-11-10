"use client";

import { Check, ChevronDown, FilePlus2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Chapter } from "@/lib/api/writer-types";

export type SaveState =
  | { kind: "idle" }
  | { kind: "dirty" }
  | { kind: "saving" }
  | { kind: "saved"; at: number }
  | { kind: "conflict"; message: string }
  | { kind: "error"; message: string };

/** The canvas views the author can switch between. */
export type CanvasView = "manuscript" | "chapters" | "review" | "tools";

/**
 * The writer's top-strip — the chapter switcher, the centred segmented view
 * tabs (manuscript only this wave), live word count, save state, and the
 * new-chapter action. It renders nothing on its own; the workspace mounts it
 * into the single shared project top bar (via a portal) so the writer has
 * one shared header whose controls wrap on narrower screens.
 */
export function WriterCanvasTop({
  bookTitle,
  chapters,
  activeChapter,
  wordCount,
  saveState,
  activeView,
  onSelectView,
  onSelectChapter,
  onNewChapter,
  busy,
}: {
  bookTitle: string;
  chapters: Chapter[];
  activeChapter: Chapter | null;
  wordCount: number;
  saveState: SaveState;
  activeView: CanvasView;
  onSelectView: (view: CanvasView) => void;
  onSelectChapter: (chapterId: string) => void;
  onNewChapter: () => void;
  busy: boolean;
}) {
  return (
    <div className="writer-canvas-top flex h-full min-w-0 flex-1 items-center gap-3">
      {/* Chapter switcher */}
      <div className="writer-chapter-controls flex min-w-0 flex-1 items-center">
        <ChapterSwitcher
          bookTitle={bookTitle}
          chapters={chapters}
          activeChapter={activeChapter}
          onSelect={onSelectChapter}
        />
      </div>

      {/* Canvas view tabs — centred between switcher and status cluster. */}
      <ViewTabs activeView={activeView} onSelect={onSelectView} />

      <div className="writer-save-controls flex min-w-0 flex-1 items-center justify-end gap-3">
        {/* Word count */}
        <span className="writer-word-count shrink-0 font-mono text-caption tabular-nums text-muted">
          {wordCount > 0 ? `${wordCount.toLocaleString("en-US")} 字` : "尚未落笔"}
        </span>
        {saveState.kind !== "idle" ? <div className="writer-save-feedback min-w-0"><SaveIndicator state={saveState} /></div> : null}
        <span aria-hidden className="writer-status-divider h-4 w-px shrink-0 bg-line" />
        <button
          type="button"
          onClick={onNewChapter}
          disabled={busy}
          aria-label="新章节"
          title="新章节"
          className="writer-new-chapter flex shrink-0 items-center gap-1.5 rounded-panel border border-line bg-panel px-3 py-1.5 text-caption font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-50"
        >
          <FilePlus2 className="size-4" aria-hidden />
          <span className="writer-new-chapter-label">新章节</span>
        </button>
      </div>
    </div>
  );
}

const CANVAS_VIEWS: ReadonlyArray<{ id: CanvasView; label: string; available: boolean }> = [
  { id: "manuscript", label: "稿件", available: true },
  { id: "chapters", label: "章节", available: true },
  { id: "review", label: "审校", available: true },
  { id: "tools", label: "工具", available: true },
];

/**
 * The mandated canvas view switcher (稿件 / 章节 / 审校 / 工具). Manuscript and
 * the chapters structure view are live; 审校 / 工具 stay honest-disabled until
 * their waves land. Selection is lifted to the workspace, which renders the
 * matching canvas panel.
 */
function ViewTabs({
  activeView,
  onSelect,
}: {
  activeView: CanvasView;
  onSelect: (view: CanvasView) => void;
}) {
  return (
    <nav aria-label="画布视图" className="writer-view-tabs flex shrink-0 items-center rounded-control bg-paper-deep p-0.5">
      {CANVAS_VIEWS.map((view) => {
        const active = view.id === activeView;
        return (
          <button
            key={view.id}
            type="button"
            disabled={!view.available}
            aria-current={active ? "page" : undefined}
            title={view.available ? undefined : "后续波次提供"}
            onClick={() => view.available && onSelect(view.id)}
            className={`rounded-control border px-3 py-1 text-caption transition-colors ${
              active
                ? "border-line-soft bg-panel font-medium text-ink"
                : "border-transparent text-muted hover:text-ink-soft disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:text-muted"
            }`}
          >
            {view.label}
          </button>
        );
      })}
    </nav>
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
    <div ref={rootRef} className="relative w-full min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`切换章节，${bookTitle}，${activeChapter?.title ?? "尚无章节"}`}
        title={`${bookTitle} / ${activeChapter?.title ?? "选择章节"}`}
        className="writer-chapter-trigger flex w-full min-w-0 items-center gap-1.5 rounded-panel px-2 py-1.5 text-left transition-colors hover:bg-panel"
      >
        <span className="writer-book-title min-w-0 max-w-[140px] truncate font-serif text-md font-semibold text-ink">
          {bookTitle}
        </span>
        <span aria-hidden className="writer-chapter-divider text-muted-soft">
          /
        </span>
        <span className="min-w-0 max-w-[180px] truncate text-sm text-ink">
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
          className="writer-chapter-list absolute left-0 top-full z-30 mt-1.5 w-[280px] overflow-hidden rounded-modal border border-line bg-panel shadow-lift"
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
    return (
      <span className="flex shrink-0 items-center gap-1.5 text-caption text-muted">
        <span aria-hidden className="size-1.5 rounded-full bg-candidate" />
        未保存
      </span>
    );
  }
  if (state.kind === "saving") {
    return (
      <span className="flex shrink-0 items-center gap-1.5 text-caption text-muted">
        <span aria-hidden className="size-1.5 animate-spin rounded-full border border-line border-t-muted" />
        正在保存
      </span>
    );
  }
  if (state.kind === "saved") {
    return (
      <span className="flex shrink-0 items-center gap-1.5 text-caption text-muted">
        <span aria-hidden className="size-1.5 rounded-full bg-success" />
        已保存
      </span>
    );
  }
  // conflict | error — honest, never a fake "saved".
  return (
    <span className="flex max-w-[300px] items-center gap-1.5 text-caption text-danger" role="alert">
      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-danger" />
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
