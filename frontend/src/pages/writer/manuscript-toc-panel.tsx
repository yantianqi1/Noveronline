/**
 * ManuscriptTocPanel — table of contents sidebar for manuscript view.
 * Supports chapter CRUD, block reordering, and export.
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ManuscriptChapter, ManuscriptBlockItem } from "./use-writer-state";

interface ManuscriptTocPanelProps {
  chapters: ManuscriptChapter[];
  blocks: ManuscriptBlockItem[];
  selectedChapterId: string | null;
  totalWords: number;
  totalBlocks: number;
  untaggedCount: number;
  onJump: (chapterId: string | null) => void;
  onCreateChapter: (name: string) => void;
  onRenameChapter: (chapterId: string, newTitle: string) => void;
  onDeleteChapter: (chapterId: string) => void;
  onMoveBlock: (blockId: string, targetChapterId: string | null) => void;
  onExport: (format: string) => void;
  onBack: () => void;
}

export function ManuscriptTocPanel({
  chapters,
  blocks,
  selectedChapterId,
  totalWords,
  totalBlocks,
  untaggedCount,
  onJump,
  onCreateChapter,
  onRenameChapter,
  onDeleteChapter,
  onMoveBlock,
  onExport,
  onBack,
}: ManuscriptTocPanelProps) {
  const [newChapterName, setNewChapterName] = React.useState("");
  const [renamingId, setRenamingId] = React.useState<string | null>(null);
  const [renameValue, setRenameValue] = React.useState("");
  const [expandedChapters, setExpandedChapters] = React.useState<Set<string>>(
    new Set(),
  );
  const renameInputRef = React.useRef<HTMLInputElement>(null);

  const untaggedBlocks = React.useMemo(
    () => blocks.filter((b) => !b.chapter_id),
    [blocks],
  );

  const moveTargetOptions = React.useMemo(
    () => [
      ...chapters.map((c) => ({ label: c.title || "未命名", value: c.chapter_id })),
      { label: "未归类", value: "__unassign__" },
    ],
    [chapters],
  );

  function getBlocksForChapter(chapterId: string) {
    return blocks.filter((b) => b.chapter_id === chapterId);
  }

  function blockLabel(block: ManuscriptBlockItem): string {
    if (block.summary)
      return block.summary.slice(0, 40) + (block.summary.length > 40 ? "..." : "");
    if (block.content)
      return block.content.slice(0, 40) + (block.content.length > 40 ? "..." : "");
    return `段落 #${block.block_order}`;
  }

  function toggleExpand(id: string) {
    setExpandedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function startRename(ch: ManuscriptChapter) {
    setRenamingId(ch.chapter_id);
    setRenameValue(ch.title || "");
    setTimeout(() => renameInputRef.current?.focus(), 50);
  }

  function commitRename(chapterId: string) {
    const newTitle = renameValue.trim();
    if (newTitle) onRenameChapter(chapterId, newTitle);
    setRenamingId(null);
  }

  function handleCreate() {
    const name = newChapterName.trim();
    if (!name) return;
    onCreateChapter(name);
    setNewChapterName("");
  }

  function handleMoveBlock(
    blockId: string,
    targetValue: string | null,
    _currentValue: string,
  ) {
    if (!targetValue || targetValue === _currentValue) return;
    onMoveBlock(blockId, targetValue === "__unassign__" ? null : targetValue);
  }

  return (
    <div className="flex h-full flex-col gap-2 overflow-hidden p-3">
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border/40 text-muted-foreground transition-colors hover:bg-muted"
          onClick={onBack}
          title="返回写作模式"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">
            MANUSCRIPT
          </p>
          <h2 className="text-base font-bold">稿件目录</h2>
        </div>
      </div>

      {/* List */}
      <div className="flex flex-1 flex-col gap-px overflow-y-auto">
        {/* All entry */}
        <button
          type="button"
          className={`flex items-center gap-1.5 rounded-md border-l-[3px] px-2.5 py-1.5 text-sm transition-colors ${
            !selectedChapterId
              ? "border-l-primary bg-primary/5"
              : "border-l-transparent hover:bg-muted/50"
          }`}
          onClick={() => onJump(null)}
        >
          <span className="flex-1 text-left font-medium">全部</span>
          <span className="text-[11px] text-muted-foreground">{totalBlocks} 段</span>
        </button>

        {/* Chapters */}
        {chapters.map((ch) => (
          <div key={ch.chapter_id}>
            <div
              className={`group flex items-center gap-1.5 rounded-md border-l-[3px] px-2.5 py-1.5 text-sm transition-colors ${
                selectedChapterId === ch.chapter_id
                  ? "border-l-primary bg-primary/5"
                  : "border-l-transparent hover:bg-muted/50"
              }`}
            >
              <button
                type="button"
                className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleExpand(ch.chapter_id);
                }}
              >
                {expandedChapters.has(ch.chapter_id) ? (
                  <ChevronRight className="h-2.5 w-2.5 rotate-90 transition-transform" />
                ) : (
                  <ChevronRight className="h-2.5 w-2.5 transition-transform" />
                )}
              </button>

              {renamingId === ch.chapter_id ? (
                <Input
                  ref={renameInputRef}
                  className="h-6 flex-1 text-sm"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename(ch.chapter_id);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                  onBlur={() => commitRename(ch.chapter_id)}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left font-semibold"
                    onClick={() => onJump(ch.chapter_id)}
                  >
                    {ch.title || "未命名章节"}
                  </button>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {ch.blockCount} 段 &middot; {ch.wordCount} 字
                  </span>
                  <div className="flex shrink-0 gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      className="rounded px-1 text-xs text-muted-foreground hover:bg-muted hover:text-primary"
                      onClick={(e) => {
                        e.stopPropagation();
                        startRename(ch);
                      }}
                      title="重命名"
                    >
                      &#9998;
                    </button>
                    <button
                      type="button"
                      className="rounded px-1 text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteChapter(ch.chapter_id);
                      }}
                      title="删除章节"
                    >
                      &#10005;
                    </button>
                  </div>
                </>
              )}
            </div>

            {/* Expanded blocks */}
            {expandedChapters.has(ch.chapter_id) && (
              <div className="ml-2 border-l border-border/40">
                {getBlocksForChapter(ch.chapter_id).map((block) => (
                  <div
                    key={block.block_id}
                    className="group/block flex items-center gap-1.5 border-l-0 py-1 pl-8 pr-2 text-xs text-muted-foreground"
                    onClick={() => onJump(ch.chapter_id)}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {blockLabel(block)}
                    </span>
                    <div
                      className="shrink-0 opacity-0 transition-opacity group-hover/block:opacity-100"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Select
                        value={ch.chapter_id}
                        onValueChange={(val) =>
                          handleMoveBlock(block.block_id, val, ch.chapter_id)
                        }
                      >
                        <SelectTrigger className="h-5 w-[90px] text-[10px]">
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
                    </div>
                  </div>
                ))}
                {getBlocksForChapter(ch.chapter_id).length === 0 && (
                  <div className="py-1 pl-8 text-[11px] italic text-muted-foreground">
                    暂无段落
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Untagged */}
        {untaggedCount > 0 && (
          <div>
            <button
              type="button"
              className={`flex w-full items-center gap-1.5 rounded-md border-l-[3px] px-2.5 py-1.5 text-sm italic transition-colors ${
                selectedChapterId === "__untagged__"
                  ? "border-l-primary bg-primary/5"
                  : "border-l-transparent hover:bg-muted/50"
              }`}
              onClick={() => onJump("__untagged__")}
            >
              <button
                type="button"
                className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleExpand("__untagged__");
                }}
              >
                {expandedChapters.has("__untagged__") ? (
                  <ChevronRight className="h-2.5 w-2.5 rotate-90" />
                ) : (
                  <ChevronRight className="h-2.5 w-2.5" />
                )}
              </button>
              <span className="flex-1 text-left text-muted-foreground">
                未归类
              </span>
              <span className="text-[11px] text-muted-foreground">
                {untaggedCount} 段
              </span>
            </button>

            {expandedChapters.has("__untagged__") && (
              <div className="ml-2 border-l border-border/40">
                {untaggedBlocks.map((block) => (
                  <div
                    key={block.block_id}
                    className="group/block flex items-center gap-1.5 py-1 pl-8 pr-2 text-xs text-muted-foreground"
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {blockLabel(block)}
                    </span>
                    <div
                      className="shrink-0 opacity-0 transition-opacity group-hover/block:opacity-100"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Select
                        value="__unassign__"
                        onValueChange={(val) =>
                          handleMoveBlock(block.block_id, val, "__unassign__")
                        }
                      >
                        <SelectTrigger className="h-5 w-[90px] text-[10px]">
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
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* New chapter input */}
      <div className="border-t border-border/40 pt-2">
        <div className="flex gap-1.5">
          <Input
            className="h-8 flex-1 text-sm"
            placeholder="新章节名称..."
            value={newChapterName}
            onChange={(e) => setNewChapterName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <Button
            size="sm"
            variant="ghost"
            disabled={!newChapterName.trim()}
            onClick={handleCreate}
          >
            添加
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="flex gap-3 border-t border-border/40 pt-2">
        <span className="rounded-xl bg-primary/5 px-2.5 py-0.5 text-xs font-medium text-primary">
          {totalWords} <small className="font-normal opacity-70">字</small>
        </span>
        <span className="rounded-xl bg-primary/5 px-2.5 py-0.5 text-xs font-medium text-primary">
          {chapters.length} <small className="font-normal opacity-70">章</small>
        </span>
        <span className="rounded-xl bg-primary/5 px-2.5 py-0.5 text-xs font-medium text-primary">
          {totalBlocks} <small className="font-normal opacity-70">段</small>
        </span>
      </div>

      {/* Export */}
      <div className="flex gap-1.5">
        <Button size="sm" variant="outline" onClick={() => onExport("txt")}>
          导出 TXT
        </Button>
        <Button size="sm" variant="outline" onClick={() => onExport("md")}>
          导出 MD
        </Button>
      </div>
    </div>
  );
}
