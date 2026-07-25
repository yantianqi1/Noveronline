"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchCsrfToken } from "@/lib/api/session";
import {
  adoptDraft,
  appendThreadMessage,
  cancelWriterRun,
  createBlock,
  createChapter,
  ensureThread,
  fetchBlock,
  fetchBlocks,
  fetchChapters,
  fetchThreadMessages,
  readSelectionFor,
  startWriterRun,
  updateBlockText,
  WriterError,
  type WriterSelection,
} from "@/lib/api/writer-client";
import type {
  Chapter,
  ManuscriptBlock,
  ManuscriptBlockMeta,
  WriterMessage,
  WriterThread,
} from "@/lib/api/writer-types";

import { WriterCanvasTop } from "./writer-canvas-top";
import { WriterEmpty } from "./writer-empty";
import { ManuscriptPaper } from "./manuscript-paper";
import { WriterRail, type ConversationTurn } from "./writer-rail";
import { WriterComposer } from "./writer-composer";

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

type SaveState =
  | { kind: "idle" }
  | { kind: "dirty" }
  | { kind: "saving" }
  | { kind: "saved"; at: number }
  | { kind: "conflict"; message: string }
  | { kind: "error"; message: string };

const AUTOSAVE_DEBOUNCE_MS = 1400;

/**
 * The Writer workbench ("纸墨书房") — W1: the manuscript canvas.
 *
 * A single dominant artifact surface: a chapter switcher in the top bar, the
 * manuscript paper for in-place reading/editing, word count, and an honest
 * save state (dirty → saving → saved, or a real conflict/error). The
 * conversation rail that drives the PI Writer Agent lands in W2; this wave
 * proves the canvas can read, edit, and persist real manuscript blocks.
 */
export function WriterWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<WriterSelection | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [blocks, setBlocks] = useState<ManuscriptBlockMeta[]>([]);
  const [activeChapterId, setActiveChapterId] = useState<string | null>(null);

  // The active chapter rendered as an ordered sequence of editable segments
  // (one manuscript block each). The canvas is a continuous document, not a
  // single card — adopted candidates land as new trailing segments.
  const [segments, setSegments] = useState<ManuscriptBlock[]>([]);
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // ── W2: conversation + run + candidate ──────────────────────────────────
  const [thread, setThread] = useState<WriterThread | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [adoptingDraftId, setAdoptingDraftId] = useState<string | null>(null);
  // run_ids whose candidate the author has adopted into the manuscript.
  const [adoptedRunIds, setAdoptedRunIds] = useState<ReadonlySet<string>>(new Set());
  // run_ids whose newest run is still streaming — only one at a time, tracked
  // so the composer disables while the agent is working.
  const [activeRunIds, setActiveRunIds] = useState<ReadonlySet<string>>(new Set());
  const messageSeqRef = useRef(0);

  const saveTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const segmentsRef = useRef<ManuscriptBlock[]>([]);
  segmentsRef.current = segments;

  const activeChapter = useMemo(
    () => chapters.find((c) => c.chapter_id === activeChapterId) ?? null,
    [chapters, activeChapterId],
  );

  // ── Loading ────────────────────────────────────────────────────────────

  const loadStructure = useCallback(async (sel: WriterSelection) => {
    const [chapterList, blockList] = await Promise.all([
      fetchChapters(sel.project_id, sel.tenant_id),
      fetchBlocks(sel.project_id, sel.tenant_id),
    ]);
    setChapters(chapterList);
    setBlocks(blockList);
    return { chapterList, blockList };
  }, []);

  useEffect(() => {
    const sel = readSelectionFor(projectId);
    if (!sel) {
      setState({ status: "no-selection" });
      return;
    }
    setSelection(sel);
    let cancelled = false;
    (async () => {
      try {
        const { chapterList } = await loadStructure(sel);
        const token = await fetchCsrfToken().catch(() => null);
        if (cancelled) return;
        setCsrfToken(token);
        // Default to the first chapter that has content, else the first chapter.
        setActiveChapterId((prev) => prev ?? chapterList[0]?.chapter_id ?? null);
        setState({ status: "ready" });
        // Ensure the conversation thread + load its history (non-blocking).
        if (token) {
          void ensureThread(sel.project_id, sel.tenant_id, token)
            .then(async (t) => {
              if (cancelled) return;
              setThread(t);
              const history = await fetchThreadMessages(sel.project_id, sel.tenant_id, t.thread_id).catch(
                () => [] as WriterMessage[],
              );
              if (cancelled) return;
              setTurns(
                history
                  .filter((m) => m.role === "user")
                  .map((m) => ({ kind: "user", id: m.message_id, body: m.body }) as ConversationTurn),
              );
              messageSeqRef.current = history.length;
            })
            .catch(() => {
              // The composer stays usable; history just won't render.
            });
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof WriterError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "加载失败，请重试。",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, loadStructure, router]);

  // ── Load the active chapter's segments (each block's body) ─────────────

  const loadChapterSegments = useCallback(
    async (sel: WriterSelection, chapterId: string): Promise<ManuscriptBlock[]> => {
      const metas = (await fetchBlocks(sel.project_id, sel.tenant_id))
        .filter((b) => b.chapter_id === chapterId)
        .sort((a, b) => a.block_order - b.block_order);
      const bodies = await Promise.all(
        metas.map((m) => fetchBlock(sel.project_id, sel.tenant_id, m.block_id).catch(() => null)),
      );
      return bodies.filter((b): b is ManuscriptBlock => b !== null);
    },
    [],
  );

  useEffect(() => {
    if (state.status !== "ready" || !selection || !activeChapterId) {
      setSegments([]);
      setSaveState({ kind: "idle" });
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const segs = await loadChapterSegments(selection, activeChapterId);
        if (cancelled) return;
        setSegments(segs);
        setSaveState({ kind: "idle" });
      } catch {
        if (!cancelled) setActionError("这一章的正文暂时读不出来，请重试。");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [state.status, selection, activeChapterId, loadChapterSegments]);

  // ── Autosave (per segment) ─────────────────────────────────────────────

  const persistSegment = useCallback(
    async (blockId: string) => {
      if (!selection || !csrfToken) return;
      const seg = segmentsRef.current.find((s) => s.block_id === blockId);
      if (!seg) return;
      setSaveState({ kind: "saving" });
      try {
        const updated = await updateBlockText(
          selection.project_id,
          selection.tenant_id,
          csrfToken,
          seg.block_id,
          seg.version,
          seg.content_text,
        );
        // Sync the saved version/word_count back without clobbering newer edits.
        setSegments((prev) =>
          prev.map((s) =>
            s.block_id === updated.block_id
              ? { ...s, version: updated.version, word_count: updated.word_count, content_text: s.content_text }
              : s,
          ),
        );
        setSaveState({ kind: "saved", at: Date.now() });
      } catch (error) {
        if (error instanceof WriterError && error.code === "MANUSCRIPT_VERSION_CONFLICT") {
          setSaveState({
            kind: "conflict",
            message: "这份稿子在别处被改过了。刷新后重试，别覆盖掉新内容。",
          });
        } else {
          setSaveState({
            kind: "error",
            message: error instanceof Error ? error.message : "保存失败，请重试。",
          });
        }
      }
    },
    [selection, csrfToken],
  );

  function handleEditSegment(blockId: string, next: string) {
    setSegments((prev) =>
      prev.map((s) => (s.block_id === blockId ? { ...s, content_text: next } : s)),
    );
    setSaveState({ kind: "dirty" });
    const timers = saveTimersRef.current;
    if (timers.has(blockId)) clearTimeout(timers.get(blockId)!);
    timers.set(
      blockId,
      setTimeout(() => {
        void persistSegment(blockId);
      }, AUTOSAVE_DEBOUNCE_MS),
    );
  }

  useEffect(
    () => () => {
      for (const timer of saveTimersRef.current.values()) clearTimeout(timer);
      saveTimersRef.current.clear();
    },
    [],
  );

  // ── Structure actions ─────────────────────────────────────────────────

  async function handleNewChapter() {
    if (!selection || !csrfToken) return;
    setBusy(true);
    setActionError(null);
    try {
      const order = chapters.length + 1;
      const chapter = await createChapter(selection.project_id, selection.tenant_id, csrfToken, {
        title: `第${order}章`,
        order,
      });
      // Open a blank block so the author can start typing immediately.
      await createBlock(selection.project_id, selection.tenant_id, csrfToken, {
        chapter_id: chapter.chapter_id,
        content_text: "",
      });
      await loadStructure(selection);
      setActiveChapterId(chapter.chapter_id);
      setSaveState({ kind: "idle" });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "新建章节失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  function handleSelectChapter(chapterId: string) {
    if (chapterId === activeChapterId) return;
    // Flush any pending edits before switching away.
    for (const [blockId, timer] of saveTimersRef.current) {
      clearTimeout(timer);
      void persistSegment(blockId);
    }
    saveTimersRef.current.clear();
    setActiveChapterId(chapterId);
  }

  // ── W2: conversation actions ───────────────────────────────────────────

  // The composer only locks while the newest request is still running.
  const anyLive = activeRunIds.size > 0;

  async function handleSend(text: string) {
    if (!selection || !csrfToken || anyLive) return;
    setActionError(null);
    messageSeqRef.current += 1;
    const turnId = `u-${messageSeqRef.current}`;
    setTurns((prev) => [...prev, { kind: "user", id: turnId, body: text }]);
    try {
      // Persist the author message, then start the run (idempotent via X-Request-Id).
      if (thread) {
        void appendThreadMessage(selection.project_id, selection.tenant_id, csrfToken, thread.thread_id, {
          role: "user",
          body: text,
        }).catch(() => {});
      }
      const run = await startWriterRun(selection.project_id, selection.tenant_id, csrfToken, {
        mode: "draft",
        instruction: text,
        chapter_id: activeChapterId ?? undefined,
      });
      setTurns((prev) => [...prev, { kind: "task", id: `t-${run.run_id}`, runId: run.run_id }]);
      setActiveRunIds((prev) => new Set(prev).add(run.run_id));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "没能开始起草，请重试。");
    }
  }

  /** A task turn reports its terminal state so the composer can unlock. */
  function handleRunSettled(runId: string) {
    setActiveRunIds((prev) => {
      if (!prev.has(runId)) return prev;
      const next = new Set(prev);
      next.delete(runId);
      return next;
    });
  }

  async function handleAdopt(runId: string, draftId: string) {
    if (!selection || !csrfToken || !draftId || adoptingDraftId) return;
    setAdoptingDraftId(draftId);
    setActionError(null);
    try {
      await adoptDraft(selection.project_id, selection.tenant_id, csrfToken, draftId, activeChapterId ?? undefined);
      setAdoptedRunIds((prev) => new Set(prev).add(runId));
      // The adopted prose is now a trailing manuscript block — reload the
      // chapter's segments so it appears on the canvas as the newest page.
      await loadStructure(selection);
      if (activeChapterId) {
        const segs = await loadChapterSegments(selection, activeChapterId);
        setSegments(segs);
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "采用失败，请重试。");
    } finally {
      setAdoptingDraftId(null);
    }
  }

  async function handleCancelRun(runId: string) {
    if (!selection || !csrfToken) return;
    try {
      await cancelWriterRun(selection.project_id, selection.tenant_id, csrfToken, runId);
      // The terminal event reconciles the turn's state through its own polling.
    } catch {
      // surfaced via the run's eventual terminal state
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────

  if (state.status === "loading") {
    return <WriterSkeleton />;
  }
  if (state.status === "no-selection") {
    return <NoSelection onBack={() => router.push("/workspace")} />;
  }
  if (state.status === "error") {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
        <h2 className="font-serif text-[22px] font-semibold text-ink">书房暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">{state.message}</p>
      </div>
    );
  }

  const isEmpty = chapters.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <WriterCanvasTop
        bookTitle="苍兰诀外传"
        chapters={chapters}
        activeChapter={activeChapter}
        wordCount={segments.reduce((sum, s) => sum + countWords(s.content_text), 0)}
        saveState={saveState}
        onSelectChapter={handleSelectChapter}
        onNewChapter={handleNewChapter}
        busy={busy}
      />

      {actionError ? (
        <div className="shrink-0 border-b border-line bg-accent-wash px-6 py-2.5 text-[13px] text-accent">
          {actionError}
        </div>
      ) : null}

      {isEmpty ? (
        <WriterEmpty onNewChapter={handleNewChapter} busy={busy} canAct={Boolean(csrfToken)} />
      ) : (
        /* Task state: conversation rail (entry) + manuscript canvas (protagonist) */
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Conversation rail — the single entry to the agent */}
          <aside className="flex h-full w-[360px] shrink-0 flex-col overflow-hidden border-r border-line bg-paper/40">
            <WriterRail
              turns={turns}
              selection={selection}
              csrfToken={csrfToken}
              adoptedRunIds={adoptedRunIds}
              adoptingDraftId={adoptingDraftId}
              onAdopt={handleAdopt}
              onCancelRun={handleCancelRun}
              onRunSettled={handleRunSettled}
            />
            <WriterComposer
              onSend={handleSend}
              disabled={!csrfToken || anyLive}
            />
          </aside>

          {/* Manuscript canvas — the dominant artifact */}
          <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
            <ManuscriptPaper
              chapter={activeChapter}
              segments={segments}
              onChangeSegment={handleEditSegment}
              readOnly={!csrfToken}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function countWords(text: string): number {
  // Chinese prose counts characters, not whitespace-separated tokens.
  return text.replace(/\s/g, "").length;
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
      <h2 className="font-serif text-[22px] font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">
        写作台需要知道你正在写哪部作品。回到书架，挑一部作品再进来。
      </p>
      <button
        type="button"
        onClick={onBack}
        className="mt-6 rounded-[10px] border border-line bg-panel px-5 py-2.5 text-[13.5px] font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent"
      >
        返回书架
      </button>
    </div>
  );
}

function WriterSkeleton() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex h-14 items-center gap-3 border-b border-line px-6">
        <div className="h-6 w-48 animate-pulse rounded bg-line-soft" />
        <div className="ml-auto h-4 w-24 animate-pulse rounded bg-line-soft" />
      </div>
      <div className="mx-auto mt-10 w-full max-w-[680px] space-y-4 px-6">
        <div className="h-4 w-full animate-pulse rounded bg-line-soft" />
        <div className="h-4 w-full animate-pulse rounded bg-line-soft" />
        <div className="h-4 w-2/3 animate-pulse rounded bg-line-soft" />
      </div>
    </div>
  );
}
