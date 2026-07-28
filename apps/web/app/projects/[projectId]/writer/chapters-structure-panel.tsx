"use client";

import {
  ArrowDown,
  ArrowUp,
  BookOpenText,
  Check,
  FilePlus2,
  GripVertical,
  Loader2,
  Pencil,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  WriterError,
  createScene,
  deleteScene,
  fetchScene,
  fetchScenes,
  reorderChapters,
  reorderScenes,
  updateScene,
} from "@/lib/api/writer-client";
import type { Chapter, ManuscriptBlockMeta, Scene, SceneDetail } from "@/lib/api/writer-types";

/**
 * The chapters structure view (章节) — the canvas's second live view alongside
 * the manuscript. Three calm columns: the chapter list, the selected chapter's
 * scenes, and the selected scene's planning detail (brief/outline). Prose stays
 * on the manuscript (CONN-001); this panel edits structure and planning only.
 * Reorder uses the existing reorder endpoints — arrow-key reorder rather than
 * drag, so the wave ships without a DnD dependency.
 */
export function ChaptersStructurePanel({
  projectId,
  tenantId,
  csrfToken,
  chapters,
  blocks,
  activeChapterId,
  onChaptersChanged,
  onOpenInManuscript,
  onNewChapter,
  busy,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
  chapters: Chapter[];
  blocks: ManuscriptBlockMeta[];
  activeChapterId: string | null;
  onChaptersChanged: () => void | Promise<unknown>;
  onOpenInManuscript: (chapterId: string) => void;
  onNewChapter: () => void;
  busy: boolean;
}) {
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(activeChapterId);
  useEffect(() => {
    setSelectedChapterId((prev) => prev ?? activeChapterId ?? chapters[0]?.chapter_id ?? null);
  }, [activeChapterId, chapters]);

  const selectedChapter = useMemo(
    () => chapters.find((c) => c.chapter_id === selectedChapterId) ?? null,
    [chapters, selectedChapterId],
  );

  // Word count per chapter, summed from block metadata (no body reads).
  const wordCountByChapter = useMemo(() => {
    const map = new Map<string, number>();
    for (const block of blocks) {
      if (!block.chapter_id) continue;
      map.set(block.chapter_id, (map.get(block.chapter_id) ?? 0) + (block.word_count ?? 0));
    }
    return map;
  }, [blocks]);

  const [scenes, setScenes] = useState<Scene[]>([]);
  const [scenesLoading, setScenesLoading] = useState(false);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reordering, setReordering] = useState(false);

  const loadScenes = useCallback(
    async (chapterId: string) => {
      setScenesLoading(true);
      try {
        const list = await fetchScenes(projectId, tenantId, chapterId);
        setScenes(list);
        setSelectedSceneId((prev) => (list.some((s) => s.scene_id === prev) ? prev : (list[0]?.scene_id ?? null)));
      } catch {
        setScenes([]);
        setSelectedSceneId(null);
        setActionError("这一章的场景暂时读不出来,请重试。");
      } finally {
        setScenesLoading(false);
      }
    },
    [projectId, tenantId],
  );

  useEffect(() => {
    if (!selectedChapterId) {
      setScenes([]);
      setSelectedSceneId(null);
      return;
    }
    void loadScenes(selectedChapterId);
  }, [selectedChapterId, loadScenes]);

  async function handleMoveChapter(chapterId: string, direction: -1 | 1) {
    if (!csrfToken || reordering) return;
    const index = chapters.findIndex((c) => c.chapter_id === chapterId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= chapters.length) return;
    const ordered = chapters.map((c) => c.chapter_id);
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    setReordering(true);
    setActionError(null);
    try {
      await reorderChapters(projectId, tenantId, csrfToken, ordered);
      await onChaptersChanged();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "调整章节顺序失败,请重试。");
    } finally {
      setReordering(false);
    }
  }

  async function handleMoveScene(sceneId: string, direction: -1 | 1) {
    if (!csrfToken || !selectedChapterId || reordering) return;
    const index = scenes.findIndex((s) => s.scene_id === sceneId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= scenes.length) return;
    const ordered = scenes.map((s) => s.scene_id);
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    setReordering(true);
    setActionError(null);
    try {
      await reorderScenes(projectId, tenantId, csrfToken, selectedChapterId, ordered);
      await loadScenes(selectedChapterId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "调整场景顺序失败,请重试。");
    } finally {
      setReordering(false);
    }
  }

  async function handleNewScene() {
    if (!csrfToken || !selectedChapterId) return;
    setActionError(null);
    try {
      const scene = await createScene(projectId, tenantId, csrfToken, selectedChapterId, {
        title: `场景 ${scenes.length + 1}`,
        order: scenes.length + 1,
      });
      await loadScenes(selectedChapterId);
      setSelectedSceneId(scene.scene_id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "新建场景失败,请重试。");
    }
  }

  async function handleDeleteScene(scene: Scene) {
    if (!csrfToken || !selectedChapterId || reordering) return;
    setReordering(true);
    setActionError(null);
    try {
      await deleteScene(projectId, tenantId, csrfToken, scene.scene_id, scene.optimistic_version);
      await loadScenes(selectedChapterId);
    } catch (error) {
      if (error instanceof WriterError && (error.code === "WRITER_WORKSPACE_VERSION_CONFLICT" || error.code === "OPTIMISTIC_CONFLICT")) {
        setActionError("这个场景在别处被改过了。已刷新列表,请再删一次。");
        await loadScenes(selectedChapterId);
      } else {
        setActionError(error instanceof Error ? error.message : "删除场景失败,请重试。");
      }
    } finally {
      setReordering(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1040px] px-6 pb-16 pt-7">
      <div className="flex items-baseline gap-3">
        <h2 className="font-serif text-lg font-semibold text-ink">章节结构</h2>
        <span className="text-sm text-muted">
          {chapters.length} 章{selectedChapter ? ` · ${scenes.length} 场景` : ""}
        </span>
      </div>
      <p className="mt-1 text-caption text-muted-soft">
        用上下键调整顺序;点选场景查看与编辑摘要、大纲。正文仍在「稿件」里写,这里只组织结构。
      </p>

      {actionError ? (
        <div className="mt-4 rounded-panel border border-line bg-accent-wash px-4 py-2.5 text-sm text-accent" role="alert">
          {actionError}
        </div>
      ) : null}

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        {/* Chapter list */}
        <StructureColumn
          title="章节目录"
          action={
            <button
              type="button"
              onClick={onNewChapter}
              disabled={!csrfToken || busy}
              className="flex items-center gap-1 text-caption text-accent hover:text-accent-strong disabled:opacity-50"
            >
              <FilePlus2 className="size-3.5" aria-hidden /> 新章节
            </button>
          }
        >
          {chapters.map((chapter, index) => (
            <StructureRow
              key={chapter.chapter_id}
              selected={chapter.chapter_id === selectedChapterId}
              title={chapter.title}
              meta={`${(wordCountByChapter.get(chapter.chapter_id) ?? 0).toLocaleString("en-US")} 字`}
              badge={<StatusBadge status={chapter.status} />}
              onSelect={() => setSelectedChapterId(chapter.chapter_id)}
              onOpen={() => onOpenInManuscript(chapter.chapter_id)}
              moveUp={index > 0 ? () => handleMoveChapter(chapter.chapter_id, -1) : undefined}
              moveDown={index < chapters.length - 1 ? () => handleMoveChapter(chapter.chapter_id, 1) : undefined}
              reorderDisabled={!csrfToken || reordering}
            />
          ))}
          {chapters.length === 0 ? <ColumnEmpty text="还没有章节。先新第一章。" /> : null}
        </StructureColumn>

        {/* Scenes + detail */}
        <div className="flex min-w-0 flex-col gap-5">
          <StructureColumn
            title={selectedChapter ? `${selectedChapter.title} · 场景` : "场景"}
            action={
              <button
                type="button"
                onClick={handleNewScene}
                disabled={!csrfToken || !selectedChapterId}
                className="flex items-center gap-1 text-caption text-accent hover:text-accent-strong disabled:opacity-50"
              >
                <FilePlus2 className="size-3.5" aria-hidden /> 新场景
              </button>
            }
          >
            {scenesLoading ? (
              <ColumnEmpty text="读取场景中…" loading />
            ) : scenes.length === 0 ? (
              <ColumnEmpty text="这一章还没有场景。" />
            ) : (
              scenes.map((scene, index) => (
                <StructureRow
                  key={scene.scene_id}
                  selected={scene.scene_id === selectedSceneId}
                  title={scene.title}
                  meta=""
                  badge={<StatusBadge status={scene.status} />}
                  onSelect={() => setSelectedSceneId(scene.scene_id)}
                  onDelete={() => void handleDeleteScene(scene)}
                  moveUp={index > 0 ? () => handleMoveScene(scene.scene_id, -1) : undefined}
                  moveDown={index < scenes.length - 1 ? () => handleMoveScene(scene.scene_id, 1) : undefined}
                  reorderDisabled={!csrfToken || reordering}
                />
              ))
            )}
          </StructureColumn>

          <SceneDetailCard
            key={selectedSceneId ?? "none"}
            projectId={projectId}
            tenantId={tenantId}
            csrfToken={csrfToken}
            sceneId={selectedSceneId}
            chapterTitle={selectedChapter?.title ?? ""}
            onSaved={() => {
              if (selectedChapterId) void loadScenes(selectedChapterId);
            }}
          />
        </div>
      </div>
    </div>
  );
}

function StructureColumn({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-panel border border-line bg-panel">
      <header className="flex items-center gap-2 border-b border-line-soft px-4 py-2.5">
        <span className="text-caption text-muted">{title}</span>
        <span className="ml-auto">{action}</span>
      </header>
      <div className="max-h-[420px] overflow-y-auto">{children}</div>
    </section>
  );
}

function StructureRow({
  selected,
  title,
  meta,
  badge,
  onSelect,
  onOpen,
  onDelete,
  moveUp,
  moveDown,
  reorderDisabled,
}: {
  selected: boolean;
  title: string;
  meta: string;
  badge?: React.ReactNode;
  onSelect: () => void;
  onOpen?: () => void;
  onDelete?: () => void;
  moveUp?: () => void;
  moveDown?: () => void;
  reorderDisabled: boolean;
}) {
  return (
    <div
      className={`group flex items-center gap-1 border-b border-line-soft border-l-2 px-2 py-2 transition-colors ${
        selected ? "border-l-accent bg-accent-wash" : "border-l-transparent hover:bg-paper"
      }`}
    >
      <GripVertical className="size-4 shrink-0 text-muted-soft" aria-hidden />
      <button type="button" onClick={onSelect} className="min-w-0 flex-1 px-1 text-left">
        <div className="truncate text-sm text-ink">{title}</div>
        {meta ? <div className="font-mono text-micro text-muted-soft">{meta}</div> : null}
      </button>
      {badge}
      <span className="flex shrink-0 flex-col opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={moveUp}
          disabled={!moveUp || reorderDisabled}
          aria-label="上移"
          className="rounded p-0.5 text-muted hover:text-accent disabled:opacity-30"
        >
          <ArrowUp className="size-3.5" aria-hidden />
        </button>
        <button
          type="button"
          onClick={moveDown}
          disabled={!moveDown || reorderDisabled}
          aria-label="下移"
          className="rounded p-0.5 text-muted hover:text-accent disabled:opacity-30"
        >
          <ArrowDown className="size-3.5" aria-hidden />
        </button>
      </span>
      {onDelete ? (
        <button
          type="button"
          onClick={onDelete}
          disabled={reorderDisabled}
          aria-label="删除场景"
          title="删除场景"
          className="shrink-0 rounded p-1 text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 disabled:opacity-30"
        >
          <Trash2 className="size-4" aria-hidden />
        </button>
      ) : null}
      {onOpen ? (
        <button
          type="button"
          onClick={onOpen}
          aria-label="在稿件中打开"
          title="在稿件中打开"
          className="shrink-0 rounded p-1 text-muted opacity-0 transition-opacity hover:text-accent group-hover:opacity-100"
        >
          <BookOpenText className="size-4" aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

function ColumnEmpty({ text, loading }: { text: string; loading?: boolean }) {
  return (
    <div className="flex items-center justify-center gap-2 px-4 py-10 text-sm text-muted-soft">
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
      {text}
    </div>
  );
}

function SceneDetailCard({
  projectId,
  tenantId,
  csrfToken,
  sceneId,
  chapterTitle,
  onSaved,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
  sceneId: string | null;
  chapterTitle: string;
  onSaved: () => void | Promise<void>;
}) {
  const [scene, setScene] = useState<SceneDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [outline, setOutline] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sceneId) {
      setScene(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const detail = await fetchScene(projectId, tenantId, sceneId);
        if (cancelled) return;
        setScene(detail);
        setTitle(detail.title);
        setBrief(detail.private?.brief ?? "");
        setOutline(detail.private?.outline ?? "");
        setEditing(false);
      } catch {
        if (!cancelled) setError("这个场景的详情暂时读不出来。");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, tenantId, sceneId]);

  async function handleSave() {
    if (!csrfToken || !scene) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateScene(projectId, tenantId, csrfToken, scene.scene_id, {
        expectedVersion: scene.optimistic_version,
        title,
        brief,
        outline,
      });
      setScene({ ...updated, private: { brief, outline, content_text: "" } });
      setEditing(false);
      await onSaved();
    } catch (err) {
      if (err instanceof WriterError && (err.code === "WRITER_WORKSPACE_VERSION_CONFLICT" || err.code === "OPTIMISTIC_CONFLICT")) {
        setError("这个场景在别处被改过了。刷新后重试,别覆盖掉新内容。");
      } else {
        setError(err instanceof Error ? err.message : "保存失败,请重试。");
      }
    } finally {
      setSaving(false);
    }
  }

  if (!sceneId) {
    return (
      <section className="rounded-panel border border-line bg-panel px-6 py-12 text-center text-sm text-muted-soft">
        选一个场景,查看与编辑它的摘要和大纲。
      </section>
    );
  }
  if (loading) {
    return (
      <section className="rounded-panel border border-line bg-panel">
        <ColumnEmpty text="读取场景详情…" loading />
      </section>
    );
  }
  if (!scene) {
    return (
      <section className="rounded-panel border border-line bg-panel px-6 py-12 text-center text-sm text-muted-soft">
        {error ?? "场景详情不可用。"}
      </section>
    );
  }

  return (
    <section className="rounded-panel border border-line bg-panel px-6 py-5">
      <div className="text-caption text-muted">{chapterTitle}</div>

      {editing ? (
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="mt-1 w-full rounded-control border border-line bg-paper px-2.5 py-1.5 font-serif text-lg font-semibold text-ink focus:outline-none"
        />
      ) : (
        <h3 className="mt-1 font-serif text-lg font-semibold text-ink">{scene.title}</h3>
      )}

      <FieldLabel>场景摘要</FieldLabel>
      {editing ? (
        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          rows={3}
          className="w-full resize-y rounded-control border border-line bg-paper px-3 py-2 text-sm leading-relaxed text-ink-soft focus:outline-none"
        />
      ) : (
        <p className="text-sm leading-relaxed text-ink-soft">{brief || <span className="text-muted-soft">还没有摘要。</span>}</p>
      )}

      <FieldLabel>场景大纲</FieldLabel>
      {editing ? (
        <textarea
          value={outline}
          onChange={(e) => setOutline(e.target.value)}
          rows={6}
          className="w-full resize-y rounded-control border border-line bg-paper px-3 py-2 text-sm leading-relaxed text-ink-soft focus:outline-none"
        />
      ) : outline ? (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">{outline}</p>
      ) : (
        <p className="text-sm text-muted-soft">还没有大纲。</p>
      )}

      {error ? (
        <div className="mt-4 rounded-control border border-line bg-accent-wash px-3 py-2 text-sm text-accent" role="alert">
          {error}
        </div>
      ) : null}

      <div className="mt-5 flex gap-2.5">
        {editing ? (
          <>
            <Button variant="primary" size="sm" onClick={handleSave} loading={saving}>
              <Check className="size-4" aria-hidden /> 保存
            </Button>
            <Button variant="outline" size="sm" onClick={() => setEditing(false)} disabled={saving}>
              <X className="size-4" aria-hidden /> 取消
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)} disabled={!csrfToken}>
            <Pencil className="size-4" aria-hidden /> 编辑
          </Button>
        )}
      </div>
    </section>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 mt-4 text-micro uppercase tracking-label text-muted">{children}</div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const { label, className } = statusBadge(status);
  if (!label) return null;
  return (
    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-micro ${className}`}>{label}</span>
  );
}

function statusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case "completed":
      return { label: "已完成", className: "border-transparent bg-success-wash text-success" };
    case "drafting":
      return { label: "写作中", className: "border-transparent bg-candidate-wash text-candidate" };
    case "planned":
      return { label: "规划中", className: "border-line-soft text-muted" };
    default:
      return { label: "", className: "" };
  }
}
