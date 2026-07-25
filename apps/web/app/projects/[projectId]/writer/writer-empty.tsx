"use client";

import { Feather, FilePlus2 } from "lucide-react";

/**
 * The zero-start canvas: no chapters yet. A single quiet invitation to open
 * the first chapter — the LLM gate stays downstream (the author can hand-write
 * before ever invoking the agent). One primary action.
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
      <span className="grid size-14 place-items-center rounded-full border border-line bg-panel text-accent">
        <Feather className="size-6" aria-hidden />
      </span>
      <h2 className="mt-5 font-serif text-[24px] font-semibold leading-snug text-ink">
        从第一张稿纸开始
      </h2>
      <p className="mt-2.5 max-w-[420px] text-[13.5px] leading-relaxed text-muted">
        这里还没有任何章节。立下第一章，就可以直接落笔；想让人工智能合著者起草、续写或审校时，它随时在。
      </p>
      <button
        type="button"
        onClick={onNewChapter}
        disabled={busy || !canAct}
        className="mt-7 flex items-center gap-2 rounded-[10px] bg-accent px-6 py-3 text-[14px] font-medium text-white shadow-[0_8px_20px_-8px_rgba(143,33,27,0.6)] transition-all hover:bg-accent-strong disabled:opacity-50"
      >
        <FilePlus2 className="size-4" aria-hidden />
        {busy ? "正在立下…" : "立下第一章"}
      </button>
    </div>
  );
}
