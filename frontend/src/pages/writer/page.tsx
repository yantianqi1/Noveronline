/**
 * WriterPage — main orchestrator for the Writer Workbench.
 *
 * Three view modes via tabs: writing / outline / manuscript.
 * Left sidebar: controls + scene list (writing) or TOC (manuscript).
 * Main content: scene editor, outline editor, or prose view.
 * Right panel: agent trace & memory review (writing mode only).
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChevronRight, ChevronDown, Loader2 } from "lucide-react";

import { AgentTracePanel } from "@/components/agent-trace-panel";
import { AgentProgressPanel } from "@/components/agent-progress-panel";
import { useWriterState } from "./use-writer-state";
import type { ViewMode, ManuscriptBlockItem } from "./use-writer-state";
import { SceneEditor } from "./scene-editor";
import { SceneListPanel } from "./scene-list-panel";
import { ManuscriptTocPanel } from "./manuscript-toc-panel";
import { ManuscriptProseView } from "./manuscript-prose-view";
import type { ManuscriptProseViewRef } from "./manuscript-prose-view";
import { ContinuationContextPanel } from "./continuation-context-panel";
import { OutlineView } from "./outline-view";
import { ReviewerPanel } from "./reviewer-panel";
import { PresetEditor } from "./preset-editor";
import { BookPlanPanel } from "./book-plan-panel";
import { ForbiddenLexiconPanel } from "./forbidden-lexicon-panel";
import { createChapter, getChapters } from "@/api/writer-agent";
import {
  KeyboardShortcutProvider,
  useWriterShortcuts,
} from "./layout/keyboard-shortcut-provider";
import { BookPlanDrawer } from "./layout/book-plan-drawer";
import { CommandPalette } from "./layout/command-palette";
import { OneClickActionRow } from "./layout/one-click-action-row";
import { WriterStatusBarHost } from "./layout/writer-status-bar-host";
import { useWriterLayoutStore } from "@/stores/writer-layout-store";

/* ---------- Helpers ---------- */

function formatSelectionBecause(reasons: string[] = []): string {
  const labels: Record<string, string> = {
    pov: "POV 命中",
    scene_focus: "场景焦点命中",
    author_instruction: "创作指令命中",
    recency: "时间衰减保留",
  };
  return (Array.isArray(reasons) ? reasons : [])
    .map((item) => labels[item] || item)
    .join("、");
}

/* ---------- Component ---------- */

export default function WriterPage() {
  return (
    <KeyboardShortcutProvider>
      <WriterPageBody />
    </KeyboardShortcutProvider>
  );
}

function WriterPageBody() {
  const state = useWriterState();
  const manuscriptProseRef = React.useRef<ManuscriptProseViewRef>(null);
  const traceScrollRef = React.useRef<HTMLDivElement>(null);

  /* ─── Drawer + layout version ─── */
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const layoutVersion = useWriterLayoutStore((s) => s.layoutVersion);
  const effectiveVersion = React.useMemo(() => {
    if (typeof window !== "undefined") {
      const qs = new URLSearchParams(window.location.search);
      const override = qs.get("layout");
      if (override === "v1" || override === "v2") return override;
    }
    return layoutVersion;
  }, [layoutVersion]);
  const v2Enabled = effectiveVersion === "v2";

  useWriterShortcuts([
    {
      key: "mod+b",
      handler: () => setDrawerOpen((prev) => !prev),
      enabled: v2Enabled,
    },
    {
      key: "mod+k",
      handler: () => setPaletteOpen((prev) => !prev),
      enabled: v2Enabled,
    },
  ]);

  /* ─── Create chapter dialog ─── */
  const [createChapterOpen, setCreateChapterOpen] = React.useState(false);
  const [newChapterName, setNewChapterName] = React.useState("");
  const [createChapterTarget, setCreateChapterTarget] = React.useState<
    "chapter" | "commit"
  >("chapter");

  async function handleCreateChapter() {
    const name = newChapterName.trim();
    if (!name || !state.projectId) return;
    try {
      const resp = await createChapter(state.projectId, { title: name });
      const newChapter = resp.data as Record<string, string>;
      // Refresh chapter options in state would happen via refreshProjectData
      void state.refreshProjectData();
      if (createChapterTarget === "chapter" && newChapter?.chapter_id) {
        state.handleChapterSelectUpdate(newChapter.chapter_id);
      } else if (createChapterTarget === "commit" && newChapter?.chapter_id) {
        state.handleCommitChapterSelectUpdate(newChapter.chapter_id);
      }
    } catch {
      /* handled by state */
    }
    setCreateChapterOpen(false);
    setNewChapterName("");
  }

  /* ─── Chapter select change (with "create new" interception) ─── */
  function onChapterSelectChange(val: string | null) {
    if (!val) return;
    if (val === "__create_new__") {
      setCreateChapterTarget("chapter");
      setCreateChapterOpen(true);
      return;
    }
    state.handleChapterSelectUpdate(val);
  }

  function onCommitChapterSelectChange(val: string | null) {
    if (!val) return;
    if (val === "__create_new__") {
      setCreateChapterTarget("commit");
      setCreateChapterOpen(true);
      return;
    }
    state.handleCommitChapterSelectUpdate(val);
  }

  /* ─── Auto-scroll trace ─── */
  React.useEffect(() => {
    if (traceScrollRef.current) {
      traceScrollRef.current.scrollTop = traceScrollRef.current.scrollHeight;
    }
  }, [
    state.agentTrace.orchestrator.rounds.length,
    state.agentTrace.writer.wordCount,
  ]);

  /* ─── Manuscript jump ─── */
  function handleManuscriptJump(chapterId: string | null) {
    state.setManuscriptSelectedChapterId(chapterId);
    if (chapterId && manuscriptProseRef.current) {
      manuscriptProseRef.current.scrollToChapter(chapterId);
    }
  }

  /* ─── Delete confirmation dialog ─── */
  const [deleteSceneId, setDeleteSceneId] = React.useState<string | null>(null);
  const [deleteBlockId, setDeleteBlockId] = React.useState<string | null>(null);
  const [deleteChapterId, setDeleteChapterId] = React.useState<string | null>(null);

  /* ─── Scope / task type options ─── */
  const scopeOptions = [
    { value: "project_chapter", label: "原著章节" },
    { value: "worldline_branch", label: "世界线分支" },
  ];

  const taskTypeOptions = [
    { value: "write_scene", label: "写场景" },
    { value: "continue", label: "续写" },
    { value: "outline", label: "大纲" },
  ];

  /* ─── Select options ─── */
  const chapterSelectOptions = React.useMemo(() => {
    const opts = state.chapterOptions.map((ch) => ({
      label: `第${ch.order}章 · ${ch.title}`,
      value: ch.chapter_id,
    }));
    if (state.projectId) {
      opts.push({ label: "+ 新建章节...", value: "__create_new__" });
    }
    return opts;
  }, [state.chapterOptions, state.projectId]);

  const commitChapterSelectOptions = React.useMemo(() => {
    const opts = state.chapterOptions.map((ch) => ({
      label: `第${ch.order}章 · ${ch.title}`,
      value: ch.chapter_id,
    }));
    opts.push({ label: "+ 新建章节...", value: "__create_new__" });
    return opts;
  }, [state.chapterOptions]);

  const isWriting = state.viewMode === "writing";
  const isManuscript = state.viewMode === "manuscript";
  const isOutline = state.viewMode === "outline";
  const isBookRun = state.viewMode === "book-run";

  const inputPlaceholder = React.useMemo(() => {
    if (state.taskType === "continue" && state.continuationContext) {
      return "描述接下来的走向、情节转折或角色行动...";
    }
    return '描述你的创作意图，如"续写第三章开场，主角在废塔中发现暗门"...';
  }, [state.taskType, state.continuationContext]);

  return (
    <>
      {v2Enabled && (
        <WriterStatusBarHost
          projectId={state.projectId}
          onOpenDrawer={() => setDrawerOpen(true)}
        />
      )}
      <div
        className={`grid ${v2Enabled ? "h-[calc(100vh-138px)]" : "h-[calc(100vh-100px)]"} gap-4 ${
          isManuscript || isOutline
            ? "grid-cols-[minmax(260px,300px)_minmax(0,1fr)]"
            : state.debugCollapsed
              ? "grid-cols-[minmax(280px,340px)_minmax(0,1fr)_44px]"
              : "grid-cols-[minmax(280px,340px)_minmax(0,1fr)_minmax(280px,360px)]"
        } transition-[grid-template-columns] duration-300`}
      >
        {/* ═══════════════════ LEFT SIDEBAR ═══════════════════ */}
        <aside className="overflow-y-auto rounded-lg border border-border/40 bg-card p-3">
          {isManuscript ? (
            <ManuscriptTocPanel
              chapters={state.manuscriptChapterList}
              blocks={state.manuscriptBlocks}
              selectedChapterId={state.manuscriptSelectedChapterId}
              totalWords={state.manuscriptTotalWords}
              totalBlocks={state.manuscriptBlocks.length}
              untaggedCount={state.manuscriptUntaggedCount}
              anchorBlockId={state.selectedAnchorBlockId}
              onSelectAnchor={state.setSelectedAnchorBlockId}
              onJump={handleManuscriptJump}
              onCreateChapter={state.handleCreateManuscriptChapter}
              onRenameChapter={state.handleRenameManuscriptChapter}
              onDeleteChapter={(id) => setDeleteChapterId(id)}
              onMoveBlock={state.handleMoveManuscriptBlock}
              onExport={state.handleManuscriptExport}
              onBack={() => state.switchViewMode("writing")}
            />
          ) : (
            <>
              <p
                className={`mb-2 text-xs ${state.error ? "text-destructive" : "text-muted-foreground"}`}
              >
                {state.error || state.message}
              </p>

              <div className="flex flex-col gap-2.5">
                {/* Project selector */}
                <div className="space-y-1">
                  <label className="text-xs font-medium">项目</label>
                  <Select
                    value={state.projectId || undefined}
                    onValueChange={(val) => val && state.handleProjectChange(val)}
                  >
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue placeholder="请选择项目" />
                    </SelectTrigger>
                    <SelectContent>
                      {state.projects.map((p) => {
                        const pid = p.id || (p as unknown as Record<string, string>).project_id || "";
                        return (
                          <SelectItem key={pid} value={pid}>
                            {p.name} · {pid.slice(0, 8)}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>

                {/* Scope toggle */}
                <Tabs
                  value={state.scopeType}
                  onValueChange={(v) => state.setScopeType(v)}
                >
                  <TabsList className="h-7 w-full">
                    {scopeOptions.map((opt) => (
                      <TabsTrigger
                        key={opt.value}
                        value={opt.value}
                        className="h-6 text-xs"
                      >
                        {opt.label}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>

                {/* Chapter / session selectors */}
                {state.scopeType === "project_chapter" ? (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium">章节</label>
                      <Select
                        value={state.chapterId || undefined}
                        onValueChange={onChapterSelectChange}
                      >
                        <SelectTrigger className="h-8 text-sm">
                          <SelectValue placeholder="请选择章节" />
                        </SelectTrigger>
                        <SelectContent>
                          {chapterSelectOptions.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium">POV</label>
                      <Select
                        value={state.povCharacter || undefined}
                        onValueChange={(v) => v && state.setPovCharacter(v)}
                      >
                        <SelectTrigger className="h-8 text-sm">
                          <SelectValue placeholder="请选择 POV" />
                        </SelectTrigger>
                        <SelectContent>
                          {state.povOptions.map((pov) => (
                            <SelectItem key={pov} value={pov}>
                              {pov}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium">世界线会话</label>
                      <Select
                        value={state.sessionId || undefined}
                        onValueChange={(v) => v && state.handleSessionChange(v)}
                      >
                        <SelectTrigger className="h-8 text-sm">
                          <SelectValue placeholder="请选择会话" />
                        </SelectTrigger>
                        <SelectContent>
                          {state.sessionOptions.map((s) => (
                            <SelectItem key={s.session_id} value={s.session_id}>
                              {s.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium">POV</label>
                      <Select
                        value={state.povCharacter || undefined}
                        onValueChange={(v) => v && state.setPovCharacter(v)}
                      >
                        <SelectTrigger className="h-8 text-sm">
                          <SelectValue placeholder="请选择 POV" />
                        </SelectTrigger>
                        <SelectContent>
                          {state.povOptions.map((pov) => (
                            <SelectItem key={pov} value={pov}>
                              {pov}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                )}

                {/* Scene focus */}
                <div className="space-y-1">
                  <label className="text-xs font-medium">
                    场景焦点{" "}
                    <span className="text-[11px] font-normal text-muted-foreground">
                      (可选)
                    </span>
                  </label>
                  <Input
                    className="h-8 text-sm"
                    value={state.sceneFocus}
                    onChange={(e) => state.setSceneFocus(e.target.value)}
                    placeholder="例如：废塔残响、顾行舟现身"
                  />
                </div>

                {/* Task type */}
                <div className="space-y-1">
                  <label className="text-xs font-medium">任务类型</label>
                  <Tabs
                    value={state.taskType}
                    onValueChange={(v) =>
                      v && state.setTaskType(v as "write_scene" | "continue" | "outline")
                    }
                  >
                    <TabsList className="h-7 w-full">
                      {taskTypeOptions.map((opt) => (
                        <TabsTrigger
                          key={opt.value}
                          value={opt.value}
                          className="h-6 text-xs"
                        >
                          {opt.label}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </Tabs>
                </div>

                {/* Preset selector */}
                <div className="space-y-1">
                  <label className="text-xs font-medium">写作风格预设</label>
                  <div className="flex items-center gap-1.5">
                    <Select
                      value={state.selectedPresetId || undefined}
                      onValueChange={(v) => v && state.setSelectedPresetId(v)}
                    >
                      <SelectTrigger className="h-8 flex-1 text-sm">
                        <SelectValue placeholder="选择预设" />
                      </SelectTrigger>
                      <SelectContent>
                        {state.presets.map((p) => (
                          <SelectItem key={p.preset_id} value={p.preset_id}>
                            {p.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8"
                      onClick={() =>
                        state.openPresetEditor(
                          state.presets.find(
                            (p) => p.preset_id === state.selectedPresetId,
                          ) ?? null,
                        )
                      }
                    >
                      编辑
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8"
                      onClick={() => state.openPresetEditor(null)}
                    >
                      新建
                    </Button>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={state.busy || !state.projectId}
                    onClick={() => state.refreshProjectData()}
                  >
                    {state.busy && (
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    )}
                    刷新项目数据
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={state.busy || !state.projectId}
                    onClick={state.handleMigrate}
                  >
                    迁移数据
                  </Button>
                </div>
              </div>

              {/* Scene list */}
              {state.chapterId && (
                <SceneListPanel
                  scenes={state.scenes}
                  selectedSceneId={state.selectedSceneId}
                  onSelect={state.handleSceneSelect}
                  onAdd={state.handleAddScene}
                  onDelete={(id) => setDeleteSceneId(id)}
                />
              )}

              {/* Reviewer rules */}
              {state.projectId && (
                <div className="mt-2.5 rounded-lg border border-border/40">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between px-3.5 py-2.5"
                    onClick={() =>
                      state.setReviewerRulesCollapsed(
                        !state.reviewerRulesCollapsed,
                      )
                    }
                  >
                    <span className="text-sm font-semibold">审校规则</span>
                    <div className="flex items-center gap-1.5">
                      {state.reviewerRulesIsCustom && (
                        <Badge variant="secondary" className="text-[10px]">
                          自定义
                        </Badge>
                      )}
                      {state.reviewerRulesCollapsed ? (
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                    </div>
                  </button>
                  {!state.reviewerRulesCollapsed && (
                    <div className="px-3.5 pb-3.5">
                      <Textarea
                        className="min-h-[160px]"
                        value={state.reviewerRulesText}
                        onChange={(e) =>
                          state.setReviewerRulesText(e.target.value)
                        }
                        placeholder="输入审校规则提示词..."
                      />
                      <div className="mt-2 flex gap-2">
                        <Button
                          size="sm"
                          disabled={state.reviewerRulesSaving}
                          onClick={state.handleSaveReviewerRules}
                        >
                          {state.reviewerRulesSaving && (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          )}
                          保存
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={
                            state.reviewerRulesSaving ||
                            !state.reviewerRulesIsCustom
                          }
                          onClick={state.handleResetReviewerRules}
                        >
                          恢复默认
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </aside>

        {/* ═══════════════════ MAIN CONTENT ═══════════════════ */}
        <main className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border/40 bg-card">
          {/* Header bar */}
          <div className="flex items-center justify-between border-b border-border/40 px-3 py-2">
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/50">
                WRITER
              </span>
              <h2 className="text-base font-bold">工作台</h2>
              {!state.projectId && (
                <span className="text-xs text-muted-foreground/50">
                  请选择项目
                </span>
              )}
            </div>
            {v2Enabled && state.chapterId && (
              <OneClickActionRow
                projectId={state.projectId}
                chapterId={state.chapterId}
                chapterOrder={state.chapterOrder}
                onEvent={state.handleTraceEvent}
                className="mx-2"
              />
            )}
            <Tabs
              value={state.viewMode}
              onValueChange={(v) => v && state.switchViewMode(v as ViewMode)}
            >
              <TabsList className="h-7">
                <TabsTrigger value="writing" className="h-6 text-xs">
                  写作
                </TabsTrigger>
                <TabsTrigger value="outline" className="h-6 text-xs">
                  大纲
                </TabsTrigger>
                <TabsTrigger value="manuscript" className="h-6 text-xs">
                  稿件
                </TabsTrigger>
                <TabsTrigger value="book-run" className="h-6 text-xs">
                  成书
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* ─── Book-run view ─── */}
          {isBookRun && (
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <BookPlanPanel projectId={state.projectId} />
              <ForbiddenLexiconPanel projectId={state.projectId} />
            </div>
          )}

          {/* ─── Manuscript prose view ─── */}
          {isManuscript && (
            <ManuscriptProseView
              ref={manuscriptProseRef}
              blocks={state.manuscriptBlocks}
              chapters={state.manuscriptChapterList}
              onEditSave={state.handleManuscriptBlockSave}
              onDelete={(id) => setDeleteBlockId(id)}
              onMoveBlock={state.handleMoveManuscriptBlock}
            />
          )}

          {/* ─── Outline view ─── */}
          {isOutline && (
            <div className="flex-1 overflow-y-auto">
              {state.chapterOutlineData && state.chapterOutlineData.length > 0 ? (
                <OutlineView
                  outline={state.chapterOutlineData}
                  chapterId={state.chapterId}
                  projectId={state.projectId}
                  versions={state.outlineVersions}
                  previewOutline={state.outlinePreview}
                  onSave={state.handleOutlineSave}
                  onLoadVersions={state.handleLoadVersions}
                  onRestore={state.handleOutlineRestore}
                  onCancelPreview={() => {
                    state.setOutlinePreview(null);
                    state.setOutlinePreviewVersionId("");
                  }}
                />
              ) : (
                <p className="py-20 text-center text-sm text-muted-foreground">
                  当前章节暂无大纲。请在"写作"页签中选择"大纲"任务类型生成。
                </p>
              )}
            </div>
          )}

          {/* ─── Writing mode ─── */}
          {isWriting && (
            <ScrollArea className="min-h-0 flex-1">
              <div className="p-3">
                {/* Data health banner (Task 4): warn when narrative / graph /
                    worldline data is missing so the author can act before the
                    agent finishes writing with poor context. */}
                {state.dataHealthIssues.length > 0 && !state.dataHealthDismissed && (
                  <div className="mb-3 rounded-lg border border-amber-500/40 bg-amber-50 p-2.5 dark:border-amber-500/60 dark:bg-amber-950/40">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-bold text-amber-900 dark:text-amber-200">
                        本项目数据不完整（{state.dataHealthIssues.length}）
                      </h3>
                      <button
                        type="button"
                        className="rounded px-1 text-[11px] text-amber-700 hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-900/60"
                        onClick={state.dismissDataHealth}
                      >
                        隐藏
                      </button>
                    </div>
                    <ul className="mt-2 space-y-1.5 text-[12px] leading-5 text-amber-900 dark:text-amber-100">
                      {state.dataHealthIssues.map((issue) => (
                        <li key={issue.code}>
                          <span
                            className={
                              issue.severity === "warning"
                                ? "mr-1 inline-block rounded bg-amber-200 px-1 text-[10px] font-bold text-amber-900 dark:bg-amber-800 dark:text-amber-100"
                                : "mr-1 inline-block rounded bg-slate-200 px-1 text-[10px] font-bold text-slate-700 dark:bg-slate-700 dark:text-slate-200"
                            }
                          >
                            {issue.severity === "warning" ? "WARN" : "INFO"}
                          </span>
                          <strong>{issue.title}</strong>：{issue.hint}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {/* Context pack */}
                {state.contextPack && (
                  <div className="mb-3 rounded-lg border border-border/40 p-2.5">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between"
                      onClick={() =>
                        state.setContextCollapsed(!state.contextCollapsed)
                      }
                    >
                      <h3 className="text-sm font-bold">上下文包</h3>
                      <div className="flex items-center gap-1.5">
                        <Badge variant="secondary" className="text-[10px]">
                          必知 {state.contextPack.must_know.length}
                        </Badge>
                        <Badge
                          variant="destructive"
                          className="text-[10px]"
                        >
                          风险 {state.contextPack.warnings.length}
                        </Badge>
                        {state.contextCollapsed ? (
                          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                      </div>
                    </button>
                    {!state.contextCollapsed && (
                      <div className="mt-2 flex flex-col gap-2.5">
                        {state.contextPack.must_know.slice(0, 4).map((item) => (
                          <div
                            key={item.item_id}
                            className="flex items-baseline gap-2 border-b border-border/20 py-1.5 text-sm"
                          >
                            <Badge
                              variant="outline"
                              className="text-[10px]"
                            >
                              {item.category}
                            </Badge>
                            <span>{item.summary}</span>
                          </div>
                        ))}
                        {state.contextPack.must_know.length > 4 && (
                          <div className="text-[13px] text-muted-foreground">
                            +{state.contextPack.must_know.length - 4} 更多必知条目
                          </div>
                        )}

                        {/* History recent anchors */}
                        {state.historyRecentAnchors.length > 0 && (
                          <div className="flex flex-col gap-2.5">
                            <div className="text-[11px] uppercase tracking-wider text-primary">
                              近章承接
                            </div>
                            {state.historyRecentAnchors.map((item) => (
                              <div
                                key={
                                  item.chapter_id ||
                                  String(item.chapter_order)
                                }
                                className="rounded-lg border border-border/40 bg-muted/30 p-2.5"
                              >
                                <Badge variant="secondary" className="text-[10px]">
                                  第{item.chapter_order}章
                                </Badge>
                                <div className="mt-1 text-sm font-semibold">
                                  {item.title || `第${item.chapter_order}章`}
                                </div>
                                <div className="mt-0.5 text-xs text-muted-foreground">
                                  {item.summary_text}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* History selection trace */}
                        {state.historySelectionTrace.length > 0 && (
                          <div className="flex flex-col gap-2.5">
                            <div className="text-[11px] uppercase tracking-wider text-primary">
                              长线回调来源
                            </div>
                            {state.historySelectionTrace
                              .slice(0, 6)
                              .map((item, index) => (
                                <div
                                  key={`${item.source_ref || item.chapter_order}_${index}`}
                                  className="rounded-lg border border-border/40 bg-muted/30 p-2.5"
                                >
                                  <div className="flex items-center gap-1.5">
                                    <Badge
                                      variant="outline"
                                      className="text-[10px]"
                                    >
                                      {item.item_type || "history"}
                                    </Badge>
                                    <Badge variant="secondary" className="text-[10px]">
                                      第{item.chapter_order}章
                                    </Badge>
                                  </div>
                                  <div className="mt-1 text-xs text-muted-foreground">
                                    {item.summary_text}
                                  </div>
                                  <div className="mt-0.5 text-[11px] text-muted-foreground">
                                    命中原因：
                                    {formatSelectionBecause(
                                      item.selected_because,
                                    )}
                                  </div>
                                </div>
                              ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Manuscript toolbar */}
                {state.projectId && (
                  <div className="mb-2 flex flex-wrap items-center gap-1.5">
                    {state.agentSceneContent &&
                      state.draftPhase === "done" &&
                      !state.outlineData && (
                        <>
                          <Select
                            value={state.commitTargetChapterId || undefined}
                            onValueChange={onCommitChapterSelectChange}
                          >
                            <SelectTrigger className="h-7 w-[200px] text-xs">
                              <SelectValue placeholder="不归类" />
                            </SelectTrigger>
                            <SelectContent>
                              {commitChapterSelectOptions.map((opt) => (
                                <SelectItem
                                  key={opt.value}
                                  value={opt.value}
                                >
                                  {opt.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Button
                            size="sm"
                            className="h-7"
                            disabled={state.commitBusy}
                            onClick={() => state.handleCommitToManuscript()}
                          >
                            {state.commitBusy && (
                              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                            )}
                            提交到稿件
                          </Button>
                        </>
                      )}
                    {state.showContinueButton && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7"
                        onClick={state.handleContinueNext}
                      >
                        继续写下一段
                      </Button>
                    )}
                    {state.commitDone &&
                      !state.worldUpdateBusy &&
                      !state.worldUpdateDone && (
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7"
                          onClick={state.handleWorldUpdate}
                        >
                          更新世界数据
                        </Button>
                      )}
                    {state.worldUpdateBusy && (
                      <Button
                        size="sm"
                        variant="secondary"
                        className="h-7"
                        disabled
                      >
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        世界数据更新中...
                      </Button>
                    )}
                    {state.worldUpdateDone && (
                      <span className="text-xs text-green-500">
                        {state.worldUpdateSummary}
                      </span>
                    )}
                  </div>
                )}

                {/* Continuation context panel */}
                {state.continuationContext && (
                  <ContinuationContextPanel
                    context={state.continuationContext}
                    anchorBlockId={state.selectedAnchorBlockId}
                    onClearAnchor={() => state.setSelectedAnchorBlockId(null)}
                  />
                )}

                {/* Continuation banner */}
                {state.taskType === "continue" &&
                  state.continuationContext?.tail_text && (
                    <div className="mt-2 flex items-center gap-2 rounded-r-md border-l-[3px] border-l-primary bg-muted/50 px-3 py-1.5 text-xs">
                      <span className="shrink-0 text-[11px] font-bold uppercase tracking-wider text-primary">
                        续写模式
                      </span>
                      <span className="truncate text-muted-foreground">
                        ...{state.continuationContext.tail_text.slice(-80)}
                      </span>
                    </div>
                  )}

                {/* Draft output: outline or scene editor */}
                <div className="my-3 flex h-[60vh] min-h-[400px] flex-col overflow-hidden rounded-lg border border-border/40 bg-gradient-to-b from-card to-muted/20">
                  {state.outlineData ? (
                    <OutlineView
                      outline={state.outlineData}
                      chapterId={state.chapterId}
                      projectId={state.projectId}
                      versions={state.outlineVersions}
                      previewOutline={state.outlinePreview}
                      onSave={state.handleOutlineSave}
                      onLoadVersions={state.handleLoadVersions}
                      onRestore={state.handleOutlineRestore}
                      onCancelPreview={() => {
                        state.setOutlinePreview(null);
                        state.setOutlinePreviewVersionId("");
                      }}
                    />
                  ) : (
                    <SceneEditor
                      content={state.agentSceneContent}
                      streaming={state.agentStreaming}
                      readonly={state.agentStreaming}
                      onUpdate={state.handleSceneContentUpdate}
                      onCommitSelection={(text) =>
                        state.handleCommitToManuscript(text)
                      }
                    />
                  )}
                </div>

                {/* Idle hint */}
                {state.draftPhase === "idle" && !state.continuationContext && (
                  <p className="py-4 text-center text-sm text-muted-foreground">
                    在下方输入框中描述你的创作意图，系统会自动收集上下文、角色记忆和文风，然后生成小说正文。
                  </p>
                )}

                {/* Author input area */}
                <div className="mt-3 overflow-hidden rounded-lg border border-border/40 bg-card transition-colors focus-within:border-primary/30 focus-within:ring-2 focus-within:ring-primary/10">
                  <Textarea
                    className="min-h-[60px] resize-y border-0 text-[15px] leading-relaxed focus-visible:ring-0"
                    value={state.authorInstruction}
                    onChange={(e) =>
                      state.setAuthorInstruction(e.target.value)
                    }
                    placeholder={inputPlaceholder}
                    disabled={
                      state.draftPhase === "writing" ||
                      state.draftPhase === "collecting"
                    }
                    onKeyDown={(e) => {
                      if (
                        (e.ctrlKey || e.metaKey) &&
                        e.key === "Enter"
                      ) {
                        e.preventDefault();
                        state.handleAgentGenerate();
                      }
                    }}
                  />
                  <div className="flex items-center gap-2.5 border-t border-border/20 bg-muted/20 px-3 py-2">
                    <span className="flex-1 font-mono text-[11px] text-muted-foreground">
                      Ctrl+Enter 发送
                    </span>
                    <Button
                      disabled={!state.canGenerate}
                      onClick={state.handleAgentGenerate}
                    >
                      {(state.draftPhase === "collecting" ||
                        state.draftPhase === "writing") && (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                      )}
                      {state.generateButtonLabel}
                    </Button>
                    {/* Task 6: cancel in-flight generation. Visible only while
                        the stream is active so the button doesn't distract
                        during setup. */}
                    {(state.draftPhase === "collecting" ||
                      state.draftPhase === "writing") && (
                      <Button
                        variant="outline"
                        onClick={state.cancelDraft}
                        title="中断当前生成流"
                      >
                        取消
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </ScrollArea>
          )}
        </main>

        {/* ═══════════════════ RIGHT PANEL (debug) ═══════════════════ */}
        {isWriting && (
          <aside
            className={`relative overflow-hidden rounded-lg border border-border/40 bg-card transition-all duration-300 ${
              state.debugCollapsed
                ? "w-[44px] min-w-[44px] px-1 py-2"
                : "p-3"
            }`}
          >
            {/* Collapse toggle */}
            <button
              type="button"
              className="absolute left-2 top-3.5 z-10 flex flex-col items-center gap-2 rounded-lg border border-border/40 bg-card px-0 py-2 transition-colors hover:bg-muted"
              style={{ width: 28 }}
              onClick={() => state.setDebugCollapsed(!state.debugCollapsed)}
              title={state.debugCollapsed ? "展开日志面板" : "收起日志面板"}
            >
              <span
                className={`inline-block h-[7px] w-[7px] border-b-2 border-r-2 border-current text-muted-foreground transition-transform duration-300 ${
                  state.debugCollapsed ? "rotate-[135deg]" : "-rotate-45"
                }`}
              />
              {state.debugCollapsed && (
                <span
                  className="text-[11px] font-medium text-muted-foreground"
                  style={{
                    writingMode: "vertical-rl",
                    letterSpacing: "3px",
                  }}
                >
                  日志
                </span>
              )}
            </button>

            {!state.debugCollapsed && (
              <div className="ml-8 flex h-full flex-col gap-2.5 overflow-y-auto pr-1">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground/50">
                  TRACE &amp; LOG
                </p>
                <h2 className="text-base font-bold">来源与日志</h2>

                {/* Agent progress overview */}
                <AgentProgressPanel
                  traceState={state.agentTrace}
                  draftPhase={state.draftPhase}
                />

                {/* Agent timeline */}
                <div className="rounded-lg border border-border/40 p-2.5">
                  <h3 className="mb-1.5 text-sm font-bold">
                    Agent 时间线
                  </h3>
                  {state.agentTrace.orchestrator.status === "idle" &&
                  !state.agentTrace.error ? (
                    <div className="text-xs text-muted-foreground">
                      生成正文后，这里会显示 Agent 的实时工作流程。
                    </div>
                  ) : (
                    <div
                      ref={traceScrollRef}
                      className="max-h-[400px] overflow-y-auto py-2"
                    >
                      <AgentTracePanel
                        state={state.agentTrace}
                        renderContext={{
                          projectId: state.projectId,
                          chapterId: state.chapterId,
                          sceneId: state.selectedSceneId,
                          onPrependToInput: (text) =>
                            state.setAuthorInstruction(
                              state.authorInstruction
                                ? `${text}\n\n${state.authorInstruction}`
                                : text,
                            ),
                        }}
                      />
                    </div>
                  )}
                </div>

                {/* Writer reviewer panel — shown after a draft commits and the
                    reviewer has produced feedback. One-shot UI: apply rewrites
                    or dismiss to keep the original draft. */}
                {state.agentTrace.reviewer?.feedback && (
                  <ReviewerPanel
                    feedback={state.agentTrace.reviewer.feedback}
                    streaming={state.agentStreaming}
                    onApply={state.handleApplyReviewer}
                    onDismiss={() => state.dismissReviewerFeedback()}
                  />
                )}

                {/* Memory review */}
                <div className="rounded-lg border border-border/40 p-2.5">
                  <h3 className="mb-1.5 text-sm font-bold">记忆审校</h3>
                  {!state.selectedItem ? (
                    <div className="text-xs text-muted-foreground">
                      点选上下文包中的条目后，可在这里查看记忆时间线。
                    </div>
                  ) : (
                    <>
                      <div className="rounded-lg border border-border/40 p-2.5">
                        <div className="flex items-center gap-1.5">
                          <Badge variant="outline" className="text-[10px]">
                            {state.selectedItem.category}
                          </Badge>
                          <Badge
                            variant={
                              state.selectedItem.memory_layer ===
                              "candidate"
                                ? "secondary"
                                : "default"
                            }
                            className="text-[10px]"
                          >
                            {state.selectedItem.memory_layer}
                          </Badge>
                        </div>
                        <div className="mt-1 text-sm font-semibold">
                          {state.selectedItem.summary}
                        </div>
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {state.selectedItem.why_it_matters}
                        </div>
                      </div>
                      <div className="mt-2.5 flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={
                            state.reviewBusy || !state.canLoadTimeline
                          }
                          onClick={state.loadSelectedTimeline}
                        >
                          {state.reviewBusy && (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          )}
                          查看记忆时间线
                        </Button>
                        <Button
                          size="sm"
                          disabled={
                            state.reviewBusy ||
                            !state.activeCandidateMemoryId
                          }
                          onClick={state.adoptSelectedMemory}
                        >
                          采纳为 Canon
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={
                            state.reviewBusy ||
                            !state.activeCandidateMemoryId
                          }
                          onClick={state.rejectSelectedMemory}
                        >
                          驳回 Candidate
                        </Button>
                      </div>
                      {state.timelineError && (
                        <div className="mt-1 text-xs text-muted-foreground">
                          {state.timelineError}
                        </div>
                      )}
                      {state.memoryTimeline && (
                        <div className="mt-2.5 flex flex-col gap-2">
                          <div className="rounded-lg border border-border/40 p-2.5">
                            <div className="text-sm font-semibold">
                              Subject &middot;{" "}
                              {
                                (
                                  state.memoryTimeline as Record<
                                    string,
                                    string
                                  >
                                ).subject
                              }
                            </div>
                            <div className="text-xs text-muted-foreground">
                              版本数：
                              {
                                (
                                  (
                                    state.memoryTimeline as Record<
                                      string,
                                      unknown[]
                                    >
                                  ).memories || []
                                ).length
                              }{" "}
                              &middot; 事件数：
                              {
                                (
                                  (
                                    state.memoryTimeline as Record<
                                      string,
                                      unknown[]
                                    >
                                  ).events || []
                                ).length
                              }
                            </div>
                          </div>
                          {(
                            (
                              state.memoryTimeline as Record<
                                string,
                                Array<Record<string, string>>
                              >
                            ).memories || []
                          ).map(
                            (
                              item: Record<string, string>,
                            ) => (
                              <div
                                key={item.memory_id}
                                className="rounded-lg border border-border/40 p-2.5"
                              >
                                <div className="flex items-center gap-1.5">
                                  <Badge
                                    variant={
                                      item.memory_layer === "candidate"
                                        ? "secondary"
                                        : "default"
                                    }
                                    className="text-[10px]"
                                  >
                                    {item.memory_layer}
                                  </Badge>
                                  <Badge
                                    variant="outline"
                                    className="text-[10px]"
                                  >
                                    {item.status}
                                  </Badge>
                                </div>
                                <div className="mt-1 text-sm font-semibold">
                                  {item.summary}
                                </div>
                                <div className="mt-0.5 text-[11px] text-muted-foreground">
                                  v{item.version} &middot;{" "}
                                  {item.updated_at || item.created_at}
                                </div>
                              </div>
                            ),
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            )}
          </aside>
        )}
      </div>

      {/* ═══ Preset editor dialog ═══ */}
      <PresetEditor
        visible={state.presetEditorVisible}
        preset={state.editingPreset}
        onSave={state.handlePresetSave}
        onClose={() => state.setPresetEditorVisible(false)}
      />

      {/* ═══ Create chapter dialog ═══ */}
      <Dialog
        open={createChapterOpen}
        onOpenChange={(open) => !open && setCreateChapterOpen(false)}
      >
        <DialogContent className="max-w-[400px]">
          <DialogHeader>
            <DialogTitle>新建章节</DialogTitle>
          </DialogHeader>
          <Input
            value={newChapterName}
            onChange={(e) => setNewChapterName(e.target.value)}
            placeholder="输入章节名称..."
            autoFocus
            onKeyDown={(e) => e.key === "Enter" && handleCreateChapter()}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateChapterOpen(false)}>
              取消
            </Button>
            <Button onClick={handleCreateChapter}>创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ Delete scene confirmation ═══ */}
      <Dialog
        open={!!deleteSceneId}
        onOpenChange={(open) => !open && setDeleteSceneId(null)}
      >
        <DialogContent className="max-w-[400px]">
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">确定删除此场景？</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteSceneId(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteSceneId) state.handleDeleteScene(deleteSceneId);
                setDeleteSceneId(null);
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ Delete manuscript block confirmation ═══ */}
      <Dialog
        open={!!deleteBlockId}
        onOpenChange={(open) => !open && setDeleteBlockId(null)}
      >
        <DialogContent className="max-w-[400px]">
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            确定要删除这段稿件内容吗？此操作不可撤销。
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteBlockId(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteBlockId) state.handleManuscriptBlockDelete(deleteBlockId);
                setDeleteBlockId(null);
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ Delete manuscript chapter confirmation ═══ */}
      <Dialog
        open={!!deleteChapterId}
        onOpenChange={(open) => !open && setDeleteChapterId(null)}
      >
        <DialogContent className="max-w-[400px]">
          <DialogHeader>
            <DialogTitle>确认删除章节</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            确定要删除此章节吗？章节内的段落将移至未归类。
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteChapterId(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteChapterId)
                  state.handleDeleteManuscriptChapter(deleteChapterId);
                setDeleteChapterId(null);
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <BookPlanDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        projectId={state.projectId}
      />
      {v2Enabled && (
        <CommandPalette
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          chapters={state.manuscriptChapterList.map((c) => ({
            chapter_id: c.chapter_id,
            title: c.title,
            order: c.order,
          }))}
          currentChapterId={state.chapterId}
          onSwitchView={(v) => state.switchViewMode(v as ViewMode)}
          onJumpToChapter={(chapterId) => {
            state.switchViewMode("manuscript" as ViewMode);
            state.setManuscriptSelectedChapterId?.(chapterId);
          }}
          onOpenBookPlan={() => setDrawerOpen(true)}
        />
      )}
    </>
  );
}
