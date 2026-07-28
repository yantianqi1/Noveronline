"use client";

import { FilePlus2 } from "lucide-react";

/**
 * The zero-start canvas: no chapters yet. A book-page invitation — folio-level
 * eyebrow, serif display title with a single vermilion caret, and one primary
 * action. The LLM gate stays downstream (the author can hand-write before
 * ever invoking the agent).
 */
export function WriterEmpty({
  onNewChapter,
  busy,
  canAct,
}: {
  onNewChapter: () => void;
  busy: boolean;
  canAct: boolean;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
      <p className="text-micro tracking-label text-muted">写作台</p>
      <h2 className="mt-3 font-serif text-display font-bold text-ink">
        从第一张稿纸开始
        <span
          className="mb-1 ml-2 inline-block h-[0.85em] w-0.5 animate-pulse bg-accent"
          aria-hidden
        />
      </h2>
      <p className="mt-4 max-w-[420px] text-sm leading-relaxed text-muted">
        这里还没有任何章节。立下第一章，就可以直接落笔；想让人工智能合著者起草、续写或审校时，它随时在。
      </p>
      <button
        type="button"
        onClick={onNewChapter}
        disabled={busy || !canAct}
        className="mt-7 flex items-center gap-2 rounded-panel bg-accent px-6 py-3 text-base font-medium text-panel shadow-accent transition-all hover:bg-accent-strong disabled:opacity-50"
      >
        <FilePlus2 className="size-4" aria-hidden />
        {busy ? "正在立下…" : "立下第一章"}
      </button>
    </div>
  );
}
