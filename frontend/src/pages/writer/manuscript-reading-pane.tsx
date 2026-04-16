/**
 * ManuscriptReadingPane — read-only manuscript view for the drawer.
 */

import * as React from "react";
import type { ManuscriptBlockItem } from "./use-writer-state";

interface ManuscriptReadingPaneProps {
  blocks: ManuscriptBlockItem[];
  chapterTitle: string;
  totalWords: number;
  onDelete: (blockId: string) => void;
  onEditInput: (block: ManuscriptBlockItem, value: string) => void;
}

export function ManuscriptReadingPane({
  blocks,
  chapterTitle,
  totalWords,
  onDelete,
  onEditInput,
}: ManuscriptReadingPaneProps) {
  const [hoveredId, setHoveredId] = React.useState<string | null>(null);
  const [editingId, setEditingId] = React.useState<string | null>(null);

  return (
    <div className="flex min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/40 px-5 pb-2.5 pt-3.5">
        <h2 className="m-0 text-base font-bold">{chapterTitle}</h2>
        <div className="mt-1 text-xs text-muted-foreground">
          {totalWords} 字 &middot; {blocks.length} 段
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-5 pb-6 pt-4">
        {blocks.length > 0 ? (
          blocks.map((block) => (
            <div
              key={block.block_id}
              className={`relative border-b border-dashed border-transparent pb-3 pt-0.5 transition-colors hover:border-border/40 ${
                editingId === block.block_id ? "border-primary/30" : ""
              }`}
              onMouseEnter={() => setHoveredId(block.block_id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              {hoveredId === block.block_id && editingId !== block.block_id && (
                <div className="absolute right-0 top-0 z-10 flex items-center gap-1.5 rounded border border-border/40 bg-card px-1.5 py-0.5 text-xs">
                  <span className="text-[10px] text-muted-foreground">
                    #{block.block_order}
                  </span>
                  <button
                    type="button"
                    className="rounded px-1.5 py-0.5 text-muted-foreground transition-colors hover:bg-muted"
                    onClick={() => setEditingId(block.block_id)}
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    className="rounded px-1.5 py-0.5 text-destructive transition-colors hover:bg-destructive/10"
                    onClick={() => onDelete(block.block_id)}
                  >
                    删除
                  </button>
                </div>
              )}

              {editingId === block.block_id ? (
                <>
                  <textarea
                    className="w-full min-h-[160px] resize-y rounded-md border border-primary bg-muted/30 p-3 font-serif text-[15px] leading-relaxed outline-none"
                    defaultValue={block.content}
                    onChange={(e) => onEditInput(block, e.target.value)}
                  />
                  <div className="mt-1.5 flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground">
                      {block.word_count} 字
                    </span>
                    <button
                      type="button"
                      className="rounded px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
                      onClick={() => setEditingId(null)}
                    >
                      完成
                    </button>
                  </div>
                </>
              ) : (
                <div className="whitespace-pre-wrap font-serif text-[15px] leading-relaxed">
                  {block.content}
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="py-20 text-center text-sm text-muted-foreground">
            尚无稿件内容
          </div>
        )}
      </div>
    </div>
  );
}
