"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type {
  ManuscriptBlock,
  PrivateManuscriptBlock,
  Scene,
} from "../lib/writer-workspace-api";
import type { Locale } from "../lib/locale";
import { tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { useWriterWorkbench } from "./writer-workbench-context";
import { fetchBlocks, fetchPrivateBlock, fetchScenes } from "./writer-workspace-client";

/**
 * Client-side selection + content state for the writer paper.
 *
 * Chapter / scene / block selection lives here instead of in the URL query,
 * so switching where you write swaps the paper's content in place with no
 * full-page navigation — the source of the previous "click flashes". The
 * server still seeds the initial chapter; after that the client owns reads.
 */

type SelectionState = {
  tenantSlug: string;
  projectId: string;
  chapterId: string;
  sceneId: string;
  blockId: string;
  /** Blocks (metadata + private content merged) for the current chapter. */
  blocks: PrivateManuscriptBlock[];
  scenes: Scene[];
  loadingChapter: boolean;
  /** Set selection without a navigation. */
  selectChapter: (chapterId: string) => void;
  selectScene: (chapterId: string, sceneId: string) => void;
  selectBlock: (blockId: string) => void;
  /** Refetch current chapter's blocks (after a mutation that stayed client-side). */
  refreshBlocks: () => void;
};

const WriterSelectionContext = createContext<SelectionState | null>(null);

const CONTENT_LIMIT = 20;

export function WriterSelectionProvider({
  tenantSlug,
  projectId,
  initialChapterId,
  initialSceneId,
  initialBlockId,
  initialBlocks,
  initialScenes,
  children,
}: {
  tenantSlug: string;
  projectId: string;
  initialChapterId: string;
  initialSceneId: string;
  initialBlockId: string;
  initialBlocks: PrivateManuscriptBlock[];
  initialScenes: Scene[];
  children: ReactNode;
}) {
  const [chapterId, setChapterId] = useState(initialChapterId);
  const [sceneId, setSceneId] = useState(initialSceneId);
  const [blockId, setBlockId] = useState(initialBlockId);
  const [blocks, setBlocks] = useState<PrivateManuscriptBlock[]>(initialBlocks);
  const [scenes, setScenes] = useState<Scene[]>(initialScenes);
  const [loadingChapter, setLoadingChapter] = useState(false);
  const requestRef = useRef(0);
  const workbench = useWriterWorkbench();

  const loadChapter = useCallback(
    async (nextChapterId: string, nextSceneId: string) => {
      const requestId = ++requestRef.current;
      setLoadingChapter(true);
      try {
        const [allBlocks, nextScenes] = await Promise.all([
          fetchBlocks(tenantSlug, projectId),
          nextChapterId ? fetchScenes(tenantSlug, projectId, nextChapterId) : Promise.resolve([]),
        ]);
        if (requestRef.current !== requestId) return; // a newer navigation superseded
        const chapterBlocks = pickChapterBlocks(allBlocks, nextChapterId);
        const privates = await Promise.all(
          chapterBlocks.map((block) => fetchPrivateBlock(tenantSlug, projectId, block.block_id).catch(() => null)),
        );
        if (requestRef.current !== requestId) return;
        const merged = chapterBlocks.map((meta, index) => privates[index] ?? { ...meta, content_text: "" });
        setBlocks(merged);
        setScenes(nextScenes);
        // Keep a requested scene when it still exists; otherwise clear.
        if (nextSceneId && !nextScenes.some((scene) => scene.scene_id === nextSceneId)) {
          setSceneId("");
        }
        // Default the open section to the first of the new chapter.
        setBlockId(merged[0]?.block_id ?? "");
      } catch {
        if (requestRef.current === requestId) {
          // Roll focus back to a coherent empty chapter view — never leave
          // the previous chapter's scenes sitting under the new highlight.
          setBlocks([]);
          setScenes([]);
          setSceneId("");
          setBlockId("");
        }
      } finally {
        if (requestRef.current === requestId) {
          setLoadingChapter(false);
        }
      }
    },
    [tenantSlug, projectId],
  );

  // Mirror paper focus into the shell-level workbench so the agent composer
  // admits against the chapter the author is actually reading.
  const setFocus = workbench?.setFocus;
  useEffect(() => {
    setFocus?.({ chapterId, sceneId, blockId });
  }, [setFocus, chapterId, sceneId, blockId]);

  const selectChapter = useCallback(
    (nextChapterId: string) => {
      if (nextChapterId === chapterId) return;
      setChapterId(nextChapterId);
      setSceneId("");
      void loadChapter(nextChapterId, "");
    },
    [chapterId, loadChapter],
  );

  const selectScene = useCallback(
    (nextChapterId: string, nextSceneId: string) => {
      if (nextChapterId !== chapterId) {
        setChapterId(nextChapterId);
        setSceneId(nextSceneId);
        void loadChapter(nextChapterId, nextSceneId);
        return;
      }
      setSceneId(nextSceneId);
    },
    [chapterId, loadChapter],
  );

  const selectBlock = useCallback((nextBlockId: string) => {
    setBlockId(nextBlockId);
  }, []);

  const refreshBlocks = useCallback(() => {
    void loadChapter(chapterId, sceneId);
  }, [chapterId, sceneId, loadChapter]);

  // Keep internal state in sync if the server hands us a different initial chapter
  // (e.g. deep link with a chapterId query param on first load).
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    setChapterId(initialChapterId);
    setSceneId(initialSceneId);
    setBlockId(initialBlockId);
    setBlocks(initialBlocks);
    setScenes(initialScenes);
  }, [initialChapterId, initialSceneId, initialBlockId, initialBlocks, initialScenes]);

  const value = useMemo<SelectionState>(
    () => ({
      tenantSlug,
      projectId,
      chapterId,
      sceneId,
      blockId,
      blocks,
      scenes,
      loadingChapter,
      selectChapter,
      selectScene,
      selectBlock,
      refreshBlocks,
    }),
    [
      tenantSlug,
      projectId,
      chapterId,
      sceneId,
      blockId,
      blocks,
      scenes,
      loadingChapter,
      selectChapter,
      selectScene,
      selectBlock,
      refreshBlocks,
    ],
  );

  return <WriterSelectionContext.Provider value={value}>{children}</WriterSelectionContext.Provider>;
}

export function useWriterSelection(): SelectionState | null {
  return useContext(WriterSelectionContext);
}

/** Header word/section counts that track the live chapter, not the SSR seed. */
export function WriterCanvasStats({
  locale,
  fallbackWordCount,
  fallbackSectionCount,
}: {
  locale: Locale;
  fallbackWordCount: number;
  fallbackSectionCount: number;
}) {
  const selection = useWriterSelection();
  const blocks = selection?.blocks;
  const wordCount = blocks
    ? blocks.reduce((sum, block) => sum + (block.word_count ?? 0), 0)
    : fallbackWordCount;
  const sectionCount = blocks ? blocks.length : fallbackSectionCount;
  return (
    <p className="writer-canvas-meta" aria-label={tx(locale, "稿件统计", "Manuscript stats")}>
      <span>
        {wordCount} <Bi zh="字" en="words" />
      </span>
      <span aria-hidden="true">·</span>
      <span>
        {sectionCount} <Bi zh="片段" en="sections" />
      </span>
    </p>
  );
}

function pickChapterBlocks(blocks: ManuscriptBlock[], chapterId: string): ManuscriptBlock[] {
  return blocks
    .filter((block) => block.status !== "deleted")
    .filter((block) => (chapterId ? (block.chapter_id ?? "") === chapterId : !block.chapter_id))
    .slice()
    .sort((a, b) => a.block_order - b.block_order)
    .slice(0, CONTENT_LIMIT);
}
