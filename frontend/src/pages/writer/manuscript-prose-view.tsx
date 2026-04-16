/**
 * ManuscriptProseView — prose block editor with chapter grouping.
 * Exposes `scrollToChapter(chapterId)` via forwardRef + useImperativeHandle.
 */

import * as React from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import type { ManuscriptBlockItem, ManuscriptChapter } from "./use-writer-state";

/* ---------- Types ---------- */

export interface ManuscriptProseViewRef {
  scrollToChapter: (chapterId: string) => void;
}

interface ManuscriptProseViewProps {
  blocks: ManuscriptBlockItem[];
  chapters: ManuscriptChapter[];
  onEditSave: (block: ManuscriptBlockItem, newContent: string) => void;
  onDelete: (blockId: string) => void;
  onMoveBlock: (blockId: string, targetChapterId: string | null) => void;
}

interface GroupedChapter {
  chapter_id: string;
  title: string;
  order: number;
  wordCount: number;
  blocks: ManuscriptBlockItem[];
}

/* ---------- Component ---------- */

export const ManuscriptProseView = React.forwardRef<
  ManuscriptProseViewRef,
  ManuscriptProseViewProps
>(function ManuscriptProseView(
  { blocks, chapters, onEditSave, onDelete, onMoveBlock },
  ref,
) {
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const chapterRefsMap = React.useRef<Record<string, HTMLDivElement | null>>({});
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [hoveredId, setHoveredId] = React.useState<string | null>(null);
  const editorRef = React.useRef<HTMLTextAreaElement>(null);
  const saveTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSaveRef = React.useRef<{
    block: ManuscriptBlockItem;
    value: string;
  } | null>(null);

  /* ─── Expose scrollToChapter ─── */
  React.useImperativeHandle(ref, () => ({
    scrollToChapter(chapterId: string) {
      const el = chapterRefsMap.current[chapterId];
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    },
  }));

  /* ─── Group blocks by chapter ─── */
  const groupedChapters = React.useMemo<GroupedChapter[]>(() => {
    const map = new Map<string, GroupedChapter>();
    for (const ch of chapters) {
      map.set(ch.chapter_id, {
        chapter_id: ch.chapter_id,
        title: ch.title || `第${ch.order}章`,
        order: ch.order,
        wordCount: 0,
        blocks: [],
      });
    }
    for (const b of blocks) {
      const cid = b.chapter_id || "__untagged__";
      if (!map.has(cid)) {
        map.set(cid, {
          chapter_id: cid,
          title: cid === "__untagged__" ? "未归类" : "未归类",
          order: Infinity,
          wordCount: 0,
          blocks: [],
        });
      }
      const ch = map.get(cid)!;
      ch.blocks.push(b);
      ch.wordCount += b.word_count || 0;
    }
    return [...map.values()].sort((a, b) => a.order - b.order);
  }, [blocks, chapters]);

  /* ─── Move target options ─── */
  const moveTargetOptions = React.useMemo(
    () => [
      ...chapters.map((c) => ({ label: c.title || "未命名", value: c.chapter_id })),
      { label: "未归类", value: "__unassign__" },
    ],
    [chapters],
  );

  /* ─── Editing ─── */
  function flushSave() {
    if (pendingSaveRef.current) {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      onEditSave(pendingSaveRef.current.block, pendingSaveRef.current.value);
      pendingSaveRef.current = null;
    }
  }

  function handleBlockClick(blockId: string) {
    if (editingId === blockId) return;
    flushSave();
    setEditingId(blockId);
  }

  function onInput(block: ManuscriptBlockItem, value: string) {
    // Mutate local content for display
    block.content = value;
    block.word_count = value.length;
    // Auto-resize
    if (editorRef.current) {
      editorRef.current.style.height = "auto";
      editorRef.current.style.height = editorRef.current.scrollHeight + "px";
    }
    // Debounced save
    pendingSaveRef.current = { block, value };
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      if (pendingSaveRef.current) {
        onEditSave(pendingSaveRef.current.block, pendingSaveRef.current.value);
        pendingSaveRef.current = null;
      }
    }, 800);
  }

  function finishEdit() {
    flushSave();
    setEditingId(null);
  }

  /* ─── Auto-resize on edit start ─── */
  React.useLayoutEffect(() => {
    if (editingId && editorRef.current) {
      editorRef.current.focus();
      editorRef.current.style.height = "auto";
      editorRef.current.style.height = editorRef.current.scrollHeight + "px";
    }
  }, [editingId]);

  /* ─── Click outside to close editor ─── */
  React.useEffect(() => {
    if (!editingId) return;
    function handleOutsideClick(e: MouseEvent) {
      const el = scrollRef.current?.querySelector(".prose-editing");
      if (el && !el.contains(e.target as Node)) {
        finishEdit();
      }
    }
    document.addEventListener("click", handleOutsideClick, true);
    return () => document.removeEventListener("click", handleOutsideClick, true);
  }, [editingId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div
        ref={scrollRef}
        className="flex flex-1 flex-col items-center overflow-y-auto px-8 pb-20 pt-10"
      >
        {groupedChapters.length > 0 ? (
          groupedChapters.map((chapter) => (
            <div
              key={chapter.chapter_id}
              ref={(el) => {
                chapterRefsMap.current[chapter.chapter_id] = el;
              }}
              className="mb-12 w-full max-w-[720px]"
            >
              <div
                className={`mb-7 flex items-baseline gap-3 border-b border-border/40 pb-3 ${
                  chapter.chapter_id === "__untagged__" ? "italic text-muted-foreground" : ""
                }`}
              >
                <h2 className="m-0 font-serif text-[22px] font-bold">
                  {chapter.title}
                </h2>
                <span className="text-xs text-muted-foreground">
                  {chapter.wordCount} 字
                </span>
              </div>

              {chapter.blocks.map((block) => (
                <div
                  key={block.block_id}
                  className={`group relative mb-1 cursor-text rounded px-2 py-1 transition-colors ${
                    editingId === block.block_id
                      ? "prose-editing rounded-lg bg-primary/5 px-2 py-2"
                      : "hover:bg-primary/[0.03]"
                  }`}
                  onMouseEnter={() => setHoveredId(block.block_id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => handleBlockClick(block.block_id)}
                >
                  {/* Hover action bar */}
                  {hoveredId === block.block_id && editingId !== block.block_id && (
                    <div
                      className="absolute right-1 top-1 z-10 flex items-center gap-1 rounded border border-border/40 bg-card px-1 py-0.5 shadow-sm"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {chapters.length > 0 && (
                        <Select
                          value={block.chapter_id || "__unassign__"}
                          onValueChange={(val) =>
                            onMoveBlock(
                              block.block_id,
                              val === "__unassign__" ? null : val,
                            )
                          }
                        >
                          <SelectTrigger className="h-6 w-[100px] text-[11px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {moveTargetOptions.map((opt) => (
                              <SelectItem key={opt.value} value={opt.value}>
                                {opt.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs text-destructive hover:text-destructive"
                        onClick={() => onDelete(block.block_id)}
                      >
                        删除
                      </Button>
                    </div>
                  )}

                  {editingId === block.block_id ? (
                    <>
                      <textarea
                        ref={editorRef}
                        className="w-full resize-none overflow-hidden rounded-md border border-primary bg-card p-3 font-serif text-base leading-relaxed outline-none"
                        defaultValue={block.content}
                        onChange={(e) => onInput(block, e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <div className="mt-1.5 flex items-center justify-between">
                        <span className="text-[11px] text-muted-foreground">
                          {block.word_count} 字
                        </span>
                        <Button
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            finishEdit();
                          }}
                        >
                          完成
                        </Button>
                      </div>
                    </>
                  ) : (
                    <p className="m-0 whitespace-pre-wrap font-serif text-base leading-relaxed">
                      {block.content}
                    </p>
                  )}
                </div>
              ))}

              {chapter.blocks.length === 0 &&
                chapter.chapter_id !== "__untagged__" && (
                  <div className="py-6 text-center text-[13px] italic text-muted-foreground">
                    暂无段落，在写作模式中创作并提交到此章节。
                  </div>
                )}
            </div>
          ))
        ) : (
          <div className="max-w-[720px] py-28 text-center text-[15px] text-muted-foreground">
            尚无稿件内容，在写作模式中创作并提交到稿件。
          </div>
        )}
      </div>
    </div>
  );
});
