"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchCsrfToken, fetchCurrentUser } from "@/lib/api/session";
import {
  adoptDraft,
  cancelWriterRun,
  createBlock,
  createChapter,
  ensureThread,
  fetchBlock,
  fetchBlocks,
  fetchChapters,
  fetchThreadMessages,
  fetchWriterDraft,
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
  WriterThread,
} from "@/lib/api/writer-types";

import { WriterCanvasTop } from "./writer-canvas-top";
import { WriterEmpty } from "./writer-empty";
import { ManuscriptPaper } from "./manuscript-paper";
import { ProjectTopbarSlot } from "../project-topbar-slot";
import { WriterRail, buildConversationTurns, type ConversationTurn, type SettledRunInfo } from "./writer-rail";
import { WriterComposer } from "./writer-composer";
import { ProposalRail } from "./proposal-rail";
import { ConversationReviewFlip } from "./composer-review-flip";

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
  const [activeChapterId, setActiveChapterId] = useState<string | null>(null);

  // The active chapter rendered as an ordered sequence of editable segments
  // (one manuscript block each). The canvas is a continuous document, not a
  // single card — adopted candidates land as new trailing segments.
  const [segments, setSegments] = useState<ManuscriptBlock[]>([]);
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
  const [actionError, setActionError] = useState<string | null>(null);
  // The canvas header used to print a fixed sample novel name. Read the real
  // one from the membership list so the author sees their own book.
  const [bookTitle, setBookTitle] = useState("");
  const [busy, setBusy] = useState(false);

  // ── W2: conversation + run + candidate ──────────────────────────────────
  const [thread, setThread] = useState<WriterThread | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  // Turn ids appended this session, so history (rebuilt on load) and live
  // appends never double-render the same message.
  const liveTurnIdsRef = useRef<Set<string>>(new Set());
  const [adoptingDraftId, setAdoptingDraftId] = useState<string | null>(null);
  // run_ids whose candidate the author has adopted into the manuscript.
  const [adoptedRunIds, setAdoptedRunIds] = useState<ReadonlySet<string>>(new Set());
  // run_id → where its adopted prose landed, so the settled card can reveal
  // the exact segment on the canvas (rebuilt from block metadata on load).
  const [settledRuns, setSettledRuns] = useState<ReadonlyMap<string, SettledRunInfo>>(new Map());
  // Segment flash target after 查看正文 (chapter switch + scroll + pulse).
  const [revealBlockId, setRevealBlockId] = useState<string | null>(null);
  // run_ids whose newest run is still streaming — only one at a time, tracked
  // so the composer disables while the agent is working.
  const [activeRunIds, setActiveRunIds] = useState<ReadonlySet<string>>(new Set());
  // Bumped after each draft adoption so the proposal rail re-fetches — the
  // adoption enqueues a distillation that lands new candidates a few seconds later.
  const [proposalRefreshKey, setProposalRefreshKey] = useState(0);
  const messageSeqRef = useRef(0);

  const saveTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const savePromisesRef = useRef<Map<string, Promise<boolean>>>(new Map());
  const segmentsRef = useRef<ManuscriptBlock[]>([]);
  segmentsRef.current = segments;
  const activeChapterIdRef = useRef<string | null>(null);
  activeChapterIdRef.current = activeChapterId;
  const selectionRef = useRef<WriterSelection | null>(null);
  selectionRef.current = selection;
  // A 查看正文 click whose target block lives in another chapter parks here
  // until that chapter's segments have loaded, then fires the flash.
  const pendingRevealBlockRef = useRef<string | null>(null);

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
    // Adopted runs settle from their manuscript blocks' provenance — this is
    // what lets a reload restore every settled turn without any local state.
    setAdoptedRunIds(
      new Set(
        blockList
          .map((b) => b.source_writer_run_id)
          .filter((id): id is string => typeof id === "string" && id.length > 0),
      ),
    );
    setSettledRuns(
      new Map(
        blockList
          .filter(
            (b): b is ManuscriptBlockMeta & { source_writer_run_id: string } =>
              typeof b.source_writer_run_id === "string" && b.source_writer_run_id.length > 0,
          )
          .map((b) => [
            b.source_writer_run_id,
            { blockId: b.block_id, chapterId: b.chapter_id ?? "" },
          ]),
      ),
    );
    return { chapterList, blockList };
  }, []);

  // Resolve the project's real display name for the canvas header. Failure is
  // non-fatal — the manuscript still loads, the header just falls back.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await fetchCurrentUser();
        const project = me.active_projects.find((p) => p.project_id === projectId);
        if (!cancelled && project) setBookTitle(project.name);
      } catch {
        // leave the fallback in place
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

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
                () => [],
              );
              if (cancelled) return;
              // Rebuild the whole rail from the persisted thread: user bubbles,
              // one task card per run (its steps/recall/candidate re-read from
              // the run's durable event stream), nothing lost across reloads.
              const historyTurns = buildConversationTurns(history);
              setTurns((current) => {
                const ids = new Set(historyTurns.map((turn) => turn.id));
                return [...historyTurns, ...current.filter((turn) => !ids.has(turn.id))];
              });
              liveTurnIdsRef.current = new Set([
                ...liveTurnIdsRef.current,
                ...historyTurns.map((turn) => turn.id),
              ]);
              setActiveRunIds(
                new Set(
                  historyTurns
                    .filter((turn): turn is Extract<ConversationTurn, { kind: "task" }> => turn.kind === "task")
                    .map((turn) => turn.runId),
                ),
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

  /**
   * Merge a fresh server read over the current canvas without clobbering the
   * author's in-flight edits: a block whose local text differs while its local
   * version is not behind the server keeps the local text (autosave will
   * persist it; a real version race surfaces through the conflict path).
   */
  function mergeSegments(fresh: ManuscriptBlock[], local: ManuscriptBlock[]): ManuscriptBlock[] {
    const localById = new Map(local.map((segment) => [segment.block_id, segment]));
    return fresh.map((incoming) => {
      const current = localById.get(incoming.block_id);
      if (current && current.content_text !== incoming.content_text && current.version >= incoming.version) {
        return { ...incoming, content_text: current.content_text, version: current.version };
      }
      return incoming;
    });
  }

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
        // A cross-chapter 查看正文 resolves once its chapter has loaded.
        if (pendingRevealBlockRef.current) {
          const target = pendingRevealBlockRef.current;
          pendingRevealBlockRef.current = null;
          setRevealBlockId(target);
        }
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
      if (!selection || !csrfToken) return false;
      const seg = segmentsRef.current.find((s) => s.block_id === blockId);
      if (!seg) return false;
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
        return true;
      } catch (error) {
        // The Go workspace store emits OPTIMISTIC_CONFLICT on a version race;
        // the older MANUSCRIPT_VERSION_CONFLICT is kept for compatibility.
        if (
          error instanceof WriterError &&
          (error.code === "OPTIMISTIC_CONFLICT" || error.code === "MANUSCRIPT_VERSION_CONFLICT")
        ) {
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
        return false;
      }
    },
    [selection, csrfToken],
  );

  const queueSegmentSave = useCallback(
    (blockId: string) => {
      const previous = savePromisesRef.current.get(blockId) ?? Promise.resolve(true);
      const queued = previous.then(() => persistSegment(blockId));
      savePromisesRef.current.set(blockId, queued);
      void queued.finally(() => {
        if (savePromisesRef.current.get(blockId) === queued) {
          savePromisesRef.current.delete(blockId);
        }
      });
      return queued;
    },
    [persistSegment],
  );

  const flushPendingSegmentSaves = useCallback(async () => {
    do {
      const blockIds = [...saveTimersRef.current.keys()];
      for (const timer of saveTimersRef.current.values()) clearTimeout(timer);
      saveTimersRef.current.clear();
      for (const blockId of blockIds) queueSegmentSave(blockId);

      const results = await Promise.all([...savePromisesRef.current.values()]);
      if (results.some((saved) => !saved)) return false;
    } while (saveTimersRef.current.size > 0 || savePromisesRef.current.size > 0);
    return true;
  }, [queueSegmentSave]);

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
        timers.delete(blockId);
        void queueSegmentSave(blockId);
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
      if (!(await flushPendingSegmentSaves())) {
        setActionError("当前章节尚未保存，新章节没有创建。请先处理保存错误。");
        return;
      }
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

  async function handleSelectChapter(chapterId: string) {
    if (chapterId === activeChapterId) return true;
    if (!(await flushPendingSegmentSaves())) {
      setActionError("当前章节尚未保存，已留在原章节。请先处理保存错误。");
      return false;
    }
    setActiveChapterId(chapterId);
    return true;
  }

  // ── W2: conversation actions ───────────────────────────────────────────

  // The composer only locks while the newest request is still running.
  const anyLive = activeRunIds.size > 0;

  async function handleSend(text: string) {
    if (!selection || !csrfToken || anyLive) return;
    setActionError(null);
    messageSeqRef.current += 1;
    const turnId = `u-${messageSeqRef.current}`;
    liveTurnIdsRef.current.add(turnId);
    setTurns((prev) => [...prev, { kind: "user", id: turnId, body: text }]);
    try {
      // The Go API persists the user message (with the run_id) inside the
      // start-run handler — one write, no double-append.
      const run = await startWriterRun(selection.project_id, selection.tenant_id, csrfToken, {
        mode: "draft",
        instruction: text,
        chapter_id: activeChapterId ?? undefined,
      });
      const taskTurnId = `task-${run.run_id}`;
      liveTurnIdsRef.current.add(taskTurnId);
      setTurns((prev) => [...prev, { kind: "task", id: taskTurnId, runId: run.run_id }]);
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

  /** A live turn discovered its draft is adopted — pin the settled state. */
  function handleTaskAdopted(runId: string) {
    setAdoptedRunIds((prev) => {
      if (prev.has(runId)) return prev;
      return new Set(prev).add(runId);
    });
  }

  /** Scroll the canvas to the prose this run contributed (switching chapter). */
  function handleRevealAdopted(runId: string) {
    const info = settledRuns.get(runId);
    if (!info) return;
    if (info.chapterId && info.chapterId !== activeChapterId) {
      pendingRevealBlockRef.current = info.blockId;
      void handleSelectChapter(info.chapterId).then((changed) => {
        if (!changed) pendingRevealBlockRef.current = null;
      });
      return;
    }
    setRevealBlockId(info.blockId);
  }

  async function handleAdopt(runId: string, draftId: string) {
    if (!selection || !csrfToken || !draftId || adoptingDraftId) return;
    setAdoptingDraftId(draftId);
    setActionError(null);
    try {
      if (!(await flushPendingSegmentSaves())) {
        setActionError("当前手稿尚未保存，候选稿没有采用。请先处理保存错误。");
        return;
      }
      // Adopt into the draft's OWN chapter — the run drafted for a specific
      // chapter, and the author may have switched views since. The active
      // chapter is only the fallback for target-less drafts.
      const draftDetail = await fetchWriterDraft(selection.project_id, selection.tenant_id, draftId).catch(() => null);
      const targetChapterId = draftDetail?.chapter_id || activeChapterId || undefined;
      const adoption = await adoptDraft(selection.project_id, selection.tenant_id, csrfToken, draftId, targetChapterId);
      setAdoptedRunIds((prev) => new Set(prev).add(runId));
      setSettledRuns((prev) => {
        const next = new Map(prev);
        next.set(runId, {
          blockId: adoption.block_id,
          chapterId: adoption.chapter_id ?? targetChapterId ?? "",
        });
        return next;
      });
      // Distillation runs async (outbox → ~5s dispatch → extraction), so refresh
      // the proposal rail now and once more shortly after to catch new candidates.
      setProposalRefreshKey((k) => k + 1);
      setTimeout(() => setProposalRefreshKey((k) => k + 1), 12_000);
      // The adopted prose is now a trailing manuscript block — reload the
      // chapter's segments so it appears on the canvas as the newest page,
      // merging so the author's unsaved edits are never clobbered.
      await loadStructure(selection);
      if (activeChapterId) {
        const segs = await loadChapterSegments(selection, activeChapterId);
        setSegments((prev) => mergeSegments(segs, prev));
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
        <h2 className="font-serif text-xl font-semibold text-ink">书房暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-sm text-muted">{state.message}</p>
      </div>
    );
  }

  const isEmpty = chapters.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* The writer's context lives in the single shared project top bar (via
          portal), not in a second stacked bar — one calm header for the whole
          workbench. */}
      <ProjectTopbarSlot>
        <WriterCanvasTop
          bookTitle={bookTitle || "未命名作品"}
          chapters={chapters}
          activeChapter={activeChapter}
          wordCount={segments.reduce((sum, s) => sum + countWords(s.content_text), 0)}
          saveState={saveState}
          onSelectChapter={handleSelectChapter}
          onNewChapter={handleNewChapter}
          busy={busy}
        />
      </ProjectTopbarSlot>

      {actionError ? (
        <div className="shrink-0 border-b border-line bg-accent-wash px-6 py-2.5 text-sm text-accent">
          {actionError}
        </div>
      ) : null}

      {isEmpty ? (
        <WriterEmpty onNewChapter={handleNewChapter} busy={busy} canAct={Boolean(csrfToken)} />
      ) : (
        /* Task state: conversation rail (entry) + manuscript canvas (protagonist) */
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* The whole co-writer dock is one two-sided card. Its front is the
              complete conversation UI; its back is the complete asset-review
              workbench. Individual composer/proposal cards never flip alone. */}
          <aside className="hidden h-full w-rail-inspector shrink-0 overflow-hidden border-r border-line bg-paper/40 wide:block">
            <ConversationReviewFlip
              projectId={projectId}
              tenantId={selection?.tenant_id ?? ""}
              refreshKey={proposalRefreshKey}
              conversation={
                <div className="flex h-full min-h-0 flex-col">
                  <div className="min-h-0 flex-1">
                    <WriterRail
                      turns={turns}
                      selection={selection}
                      csrfToken={csrfToken}
                      adoptedRunIds={adoptedRunIds}
                      settledRuns={settledRuns}
                      adoptingDraftId={adoptingDraftId}
                      onAdopt={handleAdopt}
                      onCancelRun={handleCancelRun}
                      onRunSettled={handleRunSettled}
                      onRevealAdopted={handleRevealAdopted}
                      onTaskAdopted={handleTaskAdopted}
                    />
                  </div>
                  <WriterComposer
                    onSend={handleSend}
                    disabled={!csrfToken || anyLive}
                    placeholder={anyLive ? "合著者起草中，完成后继续…" : undefined}
                  />
                </div>
              }
              review={(onCountChange) => (
                <ProposalRail
                  projectId={projectId}
                  tenantId={selection?.tenant_id ?? ""}
                  csrfToken={csrfToken}
                  refreshKey={proposalRefreshKey}
                  onCountChange={onCountChange}
                />
              )}
            />
          </aside>

          {/* Manuscript canvas — the dominant artifact */}
          <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
            <ManuscriptPaper
              chapter={activeChapter}
              segments={segments}
              onChangeSegment={handleEditSegment}
              readOnly={!csrfToken}
              revealBlockId={revealBlockId}
              onRevealConsumed={() => setRevealBlockId(null)}
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
      <h2 className="font-serif text-xl font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-sm text-muted">
        写作台需要知道你正在写哪部作品。回到书架，挑一部作品再进来。
      </p>
      <button
        type="button"
        onClick={onBack}
        className="mt-6 rounded-panel border border-line bg-panel px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent"
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
        <div className="h-6 w-48 animate-pulse rounded-control bg-line-soft" />
        <div className="ml-auto h-4 w-24 animate-pulse rounded-control bg-line-soft" />
      </div>
      <div className="mx-auto mt-10 w-full max-w-[680px] space-y-4 px-6">
        <div className="h-4 w-full animate-pulse rounded-control bg-line-soft" />
        <div className="h-4 w-full animate-pulse rounded-control bg-line-soft" />
        <div className="h-4 w-2/3 animate-pulse rounded-control bg-line-soft" />
      </div>
    </div>
  );
}
