/**
 * ManuscriptTocSidebar — compact sidebar TOC for the manuscript drawer.
 */

import * as React from "react";

interface ChapterEntry {
  tag: string;
  blockCount: number;
  wordCount: number;
}

interface ManuscriptTocSidebarProps {
  chapters: ChapterEntry[];
  selectedTag: string | null;
  totalWords: number;
  totalBlocks: number;
  untaggedCount: number;
  onSelect: (tag: string | null) => void;
}

export function ManuscriptTocSidebar({
  chapters,
  selectedTag,
  totalWords,
  totalBlocks,
  untaggedCount,
  onSelect,
}: ManuscriptTocSidebarProps) {
  return (
    <div className="flex min-h-0 flex-col overflow-hidden border-r border-border/40">
      <div className="border-b border-border/40 px-3 pb-2 pt-2.5">
        <div className="text-sm font-bold">目录</div>
        <div className="mt-1 text-[11px] text-muted-foreground">
          {totalWords} 字 &middot; {totalBlocks} 段
        </div>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        <button
          type="button"
          className={`flex w-full items-center justify-between border-l-[3px] px-4 py-2.5 text-[13px] transition-colors ${
            selectedTag === null
              ? "border-l-primary bg-muted"
              : "border-l-transparent hover:bg-muted/50"
          }`}
          onClick={() => onSelect(null)}
        >
          <span className="font-medium">全部</span>
          <span className="text-[11px] text-muted-foreground">{totalBlocks} 段</span>
        </button>

        {chapters.map((ch) => (
          <button
            key={ch.tag}
            type="button"
            className={`flex w-full items-center justify-between border-l-[3px] px-4 py-2.5 text-[13px] transition-colors ${
              selectedTag === ch.tag
                ? "border-l-primary bg-muted"
                : "border-l-transparent hover:bg-muted/50"
            }`}
            onClick={() => onSelect(ch.tag)}
          >
            <span className="font-medium">{ch.tag}</span>
            <span className="ml-2 whitespace-nowrap text-[11px] text-muted-foreground">
              {ch.blockCount} 段 &middot; {ch.wordCount} 字
            </span>
          </button>
        ))}

        {untaggedCount > 0 && (
          <button
            type="button"
            className={`flex w-full items-center justify-between border-l-[3px] px-4 py-2.5 text-[13px] transition-colors ${
              selectedTag === "__untagged__"
                ? "border-l-primary bg-muted"
                : "border-l-transparent hover:bg-muted/50"
            }`}
            onClick={() => onSelect("__untagged__")}
          >
            <span className="font-medium italic text-muted-foreground">
              未归类
            </span>
            <span className="text-[11px] text-muted-foreground">
              {untaggedCount} 段
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
