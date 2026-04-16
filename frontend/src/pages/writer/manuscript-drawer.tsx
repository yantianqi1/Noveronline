/**
 * ManuscriptDrawer — right-side sheet with manuscript reading view.
 */

import * as React from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ManuscriptTocSidebar } from "./manuscript-toc-sidebar";
import { ManuscriptReadingPane } from "./manuscript-reading-pane";
import {
  getManuscript,
  updateManuscriptBlock,
  deleteManuscriptBlock,
  tagManuscriptBlocks,
  exportManuscript,
} from "@/api/writer-agent";
import type { ManuscriptBlockItem } from "./use-writer-state";

interface ManuscriptDrawerProps {
  visible: boolean;
  projectId: string;
  onClose: () => void;
  onUpdated?: () => void;
}

export function ManuscriptDrawer({
  visible,
  projectId,
  onClose,
  onUpdated,
}: ManuscriptDrawerProps) {
  const [blocks, setBlocks] = React.useState<ManuscriptBlockItem[]>([]);
  const [totalWords, setTotalWords] = React.useState(0);
  const [selectedTag, setSelectedTag] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (visible && projectId) {
      setSelectedTag(null);
      void loadBlocks();
    }
  }, [visible, projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadBlocks() {
    try {
      const res = await getManuscript(projectId);
      const payload = (res.data as Record<string, unknown>) || {};
      setBlocks((payload.blocks as ManuscriptBlockItem[]) || []);
      setTotalWords((payload.total_words as number) || 0);
    } catch (e) {
      console.error("Failed to load manuscript", e);
    }
  }

  const chapterList = React.useMemo(() => {
    const map = new Map<string, { tag: string; blockCount: number; wordCount: number }>();
    for (const b of blocks) {
      const tag = b.chapter_tag;
      if (!tag) continue;
      if (!map.has(tag)) map.set(tag, { tag, blockCount: 0, wordCount: 0 });
      const entry = map.get(tag)!;
      entry.blockCount++;
      entry.wordCount += b.word_count || 0;
    }
    return Array.from(map.values());
  }, [blocks]);

  const untaggedCount = React.useMemo(
    () => blocks.filter((b) => !b.chapter_tag).length,
    [blocks],
  );

  const filteredBlocks = React.useMemo(() => {
    if (selectedTag === null) return blocks;
    if (selectedTag === "__untagged__")
      return blocks.filter((b) => !b.chapter_tag);
    return blocks.filter((b) => b.chapter_tag === selectedTag);
  }, [blocks, selectedTag]);

  const currentChapterTitle = React.useMemo(() => {
    if (selectedTag === null) return "全部稿件";
    if (selectedTag === "__untagged__") return "未归类";
    return selectedTag;
  }, [selectedTag]);

  const currentChapterWords = React.useMemo(
    () => filteredBlocks.reduce((sum, b) => sum + (b.word_count || 0), 0),
    [filteredBlocks],
  );

  let editTimer: ReturnType<typeof setTimeout>;
  function handleEditInput(block: ManuscriptBlockItem, value: string) {
    block.content = value;
    block.word_count = value.length;
    clearTimeout(editTimer);
    editTimer = setTimeout(async () => {
      try {
        await updateManuscriptBlock(block.block_id, {
          project_id: projectId,
          content: value,
        });
        onUpdated?.();
      } catch (e) {
        console.error("Save failed", e);
      }
    }, 800);
  }

  async function handleDelete(blockId: string) {
    try {
      await deleteManuscriptBlock(blockId, projectId);
      await loadBlocks();
      onUpdated?.();
    } catch (e) {
      console.error("Delete failed", e);
    }
  }

  async function handleExport(fmt: string) {
    try {
      const blob = await exportManuscript(projectId, fmt);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `manuscript.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Export failed", e);
    }
  }

  return (
    <Sheet open={visible} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-[90vw] max-w-[1400px] p-0 sm:max-w-[1400px]">
        <SheetHeader className="flex-row items-center gap-3 border-b border-border/40 px-5 py-3">
          <SheetTitle>稿件阅读器</SheetTitle>
          <span className="text-xs text-muted-foreground">
            {totalWords} 字 &middot; {blocks.length} 段
          </span>
          <div className="ml-auto flex gap-1.5">
            <Button size="sm" variant="ghost" onClick={() => handleExport("txt")}>
              导出 TXT
            </Button>
            <Button size="sm" variant="ghost" onClick={() => handleExport("md")}>
              导出 MD
            </Button>
          </div>
        </SheetHeader>
        <div className="grid h-[calc(100vh-56px)] grid-cols-[260px_1fr]">
          <ManuscriptTocSidebar
            chapters={chapterList}
            selectedTag={selectedTag}
            totalWords={totalWords}
            totalBlocks={blocks.length}
            untaggedCount={untaggedCount}
            onSelect={setSelectedTag}
          />
          <ManuscriptReadingPane
            blocks={filteredBlocks}
            chapterTitle={currentChapterTitle}
            totalWords={currentChapterWords}
            onDelete={handleDelete}
            onEditInput={handleEditInput}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
