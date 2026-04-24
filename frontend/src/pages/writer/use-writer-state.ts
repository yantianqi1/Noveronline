/**
 * Central state hook for the writer workbench.
 * Manages project selection, chapter/scene state, SSE streaming,
 * manuscript and outline data, and all CRUD mutations.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getChapterContextOptions,
  getReviewerRules,
  saveReviewerRules,
} from "@/api/novel";
import {
  listWorldlineSessions,
  getWorldlineAgents,
} from "@/api/worldline";
import {
  getArchiveMemoryTimeline,
  adoptArchiveMemory,
  rejectArchiveMemory,
} from "@/api/assets";
import {
  runWriterAgent,
  getScenes,
  updateScene as updateSceneApi,
  deleteScene as deleteSceneApi,
  getPresets,
  createPreset,
  updatePreset,
  deletePreset,
  getChapters,
  migrateProject,
  commitToManuscript,
  getContinuationContext,
  updateChapter,
  createChapter,
  getManuscript,
  updateManuscriptBlock,
  deleteManuscriptBlock,
  moveManuscriptBlock,
  exportManuscript,
  getOutlineVersions,
  getOutlineVersion,
  restoreOutlineVersion,
  updateWorldData,
  applyReviewer,
} from "@/api/writer-agent";
import { useProjectCatalog } from "@/hooks/use-project-catalog";
import { useNotification } from "@/hooks/use-notification";
import type { SSEEvent } from "@/api/sse";

import {
  deriveWriterDefaults,
  resolveWriterPovOptions,
} from "./writer-workbench-state";
import type {
  ChapterOption,
  ContextPack,
  ContextItem,
  WorldlineAgent,
} from "./writer-workbench-state";
import type { AgentTraceState, AgentRound, AgentToolCall } from "@/components/agent-trace-panel";

/* ================================================================
   Types
   ================================================================ */

export type ViewMode = "writing" | "outline" | "manuscript" | "book-run";
export type DraftPhase = "idle" | "collecting" | "writing" | "done";
export type TaskType = "write_scene" | "continue" | "outline";

export interface SceneItem {
  scene_id: string;
  scene_order: number;
  title: string;
  word_count: number;
  status: string;
  content: string;
}

export interface PresetItem {
  preset_id: string;
  name: string;
  description?: string;
  system_prompt?: string;
  is_default?: boolean;
}

export interface ManuscriptBlockItem {
  block_id: string;
  block_order: number;
  chapter_id: string | null;
  chapter_tag?: string;
  content: string;
  word_count: number;
  summary?: string;
  pov_entity_id?: string;
}

export interface ManuscriptChapter {
  chapter_id: string;
  title: string;
  order: number;
  blockCount: number;
  wordCount: number;
}

export interface OutlineScene {
  scene_order: number;
  title: string;
  summary: string;
  pov: string;
  key_events: string[];
}

export interface OutlineVersionItem {
  version_id: string;
  label?: string;
  created_at: string;
  outline_json?: string;
}

// One entry from the orchestrator's ``data_health_warning`` SSE event. Matches
// the backend payload in ``_collect_data_health_issues``.
export interface DataHealthIssue {
  code: string;
  severity: "info" | "warning";
  title: string;
  hint: string;
}

export interface ContinuationCtx {
  tail_text?: string;
  last_pov?: string;
  last_location?: string;
  narrative_note?: string;
  last_chapter_tag?: string;
  last_block_order?: number;
  recent_summaries?: Array<{
    block_order: number;
    chapter_tag?: string;
    summary: string;
  }>;
  active_threads?: string[];
  total_words?: number;
  total_blocks?: number;
}

interface SessionOption {
  session_id: string;
  label: string;
}

/* ================================================================
   Hook
   ================================================================ */

export function useWriterState() {
  const { projects, refreshProjects } = useProjectCatalog();
  const { notifySuccess, notifyError } = useNotification();

  /* ─── Core selection ─── */
  const [projectId, setProjectId] = useState("");
  const [scopeType, setScopeType] = useState("project_chapter");
  const [chapterId, setChapterId] = useState("");
  const [chapterOrder, setChapterOrder] = useState(0);
  const [povCharacter, setPovCharacter] = useState("");
  const [sceneFocus, setSceneFocus] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [authorInstruction, setAuthorInstruction] = useState("");
  const [taskType, setTaskType] = useState<TaskType>("write_scene");
  const [viewMode, setViewMode] = useState<ViewMode>("writing");

  /* ─── Data lists ─── */
  const [chapterOptions, setChapterOptions] = useState<ChapterOption[]>([]);
  const [projectPovs, setProjectPovs] = useState<string[]>([]);
  const [sessionOptions, setSessionOptions] = useState<SessionOption[]>([]);
  const [worldlineAgents, setWorldlineAgents] = useState<WorldlineAgent[]>([]);
  const [scenes, setScenes] = useState<SceneItem[]>([]);
  const [selectedSceneId, setSelectedSceneId] = useState("");
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState("");

  /* ─── UI state ─── */
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("请选择项目，然后在输入框中开始创作");
  const [error, setError] = useState("");
  const [debugCollapsed, setDebugCollapsed] = useState(false);

  /* ─── Reviewer rules ─── */
  const [reviewerRulesCollapsed, setReviewerRulesCollapsed] = useState(true);
  const [reviewerRulesText, setReviewerRulesText] = useState("");
  const [reviewerRulesDefault, setReviewerRulesDefault] = useState("");
  const [reviewerRulesSaving, setReviewerRulesSaving] = useState(false);
  const [reviewerRulesIsCustom, setReviewerRulesIsCustom] = useState(false);

  /* ─── Context pack & memory review ─── */
  const [contextPack, setContextPack] = useState<ContextPack | null>(null);
  const [contextCollapsed, setContextCollapsed] = useState(true);
  const [selectedItem, setSelectedItem] = useState<ContextItem | null>(null);
  const [memoryTimeline, setMemoryTimeline] = useState<Record<string, unknown> | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [timelineError, setTimelineError] = useState("");

  /* ─── Draft generation ─── */
  const [draftPhase, setDraftPhase] = useState<DraftPhase>("idle");
  const [agentSceneContent, setAgentSceneContent] = useState("");
  const [agentStreaming, setAgentStreaming] = useState(false);
  const [involvedEntityIds] = useState<string[]>([]);
  const draftAbortControllerRef = useRef<AbortController | null>(null);

  /* ─── Data health self-check (Task 4) ─── */
  // Populated from the ``data_health_warning`` SSE event that the orchestrator
  // emits before the retrieval planner runs. Each issue is
  // ``{code, severity, title, hint}``. Reset on every run so stale warnings
  // don't linger after the user fixes the underlying data.
  const [dataHealthIssues, setDataHealthIssues] = useState<DataHealthIssue[]>([]);
  const [dataHealthDismissed, setDataHealthDismissed] = useState(false);

  /* ─── Agent trace ─── */
  const [agentTrace, setAgentTrace] = useState<AgentTraceState>({
    orchestrator: { status: "idle", model: "", rounds: [], summary: undefined },
    writer: { status: "idle", model: "", wordCount: 0, elapsedMs: 0 },
    error: "",
  });

  /* ─── Outline ─── */
  const [outlineData, setOutlineData] = useState<OutlineScene[] | null>(null);
  const [chapterOutlineData, setChapterOutlineData] = useState<OutlineScene[] | null>(null);
  const [outlineVersions, setOutlineVersions] = useState<OutlineVersionItem[]>([]);
  const [outlinePreview, setOutlinePreview] = useState<OutlineScene[] | null>(null);
  const [outlinePreviewVersionId, setOutlinePreviewVersionId] = useState("");

  /* ─── Manuscript ─── */
  const [manuscriptBlocks, setManuscriptBlocks] = useState<ManuscriptBlockItem[]>([]);
  const [manuscriptTotalWords, setManuscriptTotalWords] = useState(0);
  const [manuscriptSelectedChapterId, setManuscriptSelectedChapterId] = useState<string | null>(null);
  const [continuationContext, setContinuationContext] = useState<ContinuationCtx | null>(null);
  const [showContinueButton, setShowContinueButton] = useState(false);
  const [lastCommittedBlockId, setLastCommittedBlockId] = useState("");
  // Task 5: optional user-picked continuation anchor. When empty, falls back
  // to lastCommittedBlockId (the latest committed block). Lets authors pick
  // any block in the TOC as the "continue from here" point.
  const [selectedAnchorBlockId, setSelectedAnchorBlockId] = useState<string | null>(null);
  const [commitBusy, setCommitBusy] = useState(false);
  const [commitDone, setCommitDone] = useState(false);
  const [commitTargetChapterId, setCommitTargetChapterId] = useState("");
  const [worldUpdateBusy, setWorldUpdateBusy] = useState(false);
  const [worldUpdateDone, setWorldUpdateDone] = useState(false);
  const [worldUpdateSummary, setWorldUpdateSummary] = useState("");
  const worldUpdateAbortRef = useRef<AbortController | null>(null);

  /* ─── Preset editor ─── */
  const [presetEditorVisible, setPresetEditorVisible] = useState(false);
  const [editingPreset, setEditingPreset] = useState<PresetItem | null>(null);

  /* ─── Mutable ref for streaming content (avoids stale closure) ─── */
  const contentRef = useRef("");

  /* ================================================================
     Derived values
     ================================================================ */

  const povOptions = useMemo(
    () => resolveWriterPovOptions(scopeType, projectPovs, worldlineAgents),
    [scopeType, projectPovs, worldlineAgents],
  );

  const canSubmit = useMemo(() => {
    if (!projectId || !povCharacter) return false;
    return scopeType === "worldline_branch"
      ? !!sessionId
      : !!(chapterId || chapterOrder);
  }, [projectId, povCharacter, scopeType, sessionId, chapterId, chapterOrder]);

  const canGenerate = useMemo(() => {
    if (!canSubmit || !authorInstruction.trim()) return false;
    return draftPhase === "idle" || draftPhase === "done";
  }, [canSubmit, authorInstruction, draftPhase]);

  const generateButtonLabel = useMemo(() => {
    if (draftPhase === "collecting") return "收集中...";
    if (draftPhase === "writing") return "创作中...";
    return "开始创作";
  }, [draftPhase]);

  const manuscriptChapterList = useMemo<ManuscriptChapter[]>(() => {
    const map = new Map<string, ManuscriptChapter>();
    for (const ch of chapterOptions) {
      map.set(ch.chapter_id, {
        chapter_id: ch.chapter_id,
        title: ch.title,
        order: ch.order,
        blockCount: 0,
        wordCount: 0,
      });
    }
    for (const b of manuscriptBlocks) {
      if (b.chapter_id && map.has(b.chapter_id)) {
        const ch = map.get(b.chapter_id)!;
        ch.blockCount++;
        ch.wordCount += b.word_count || 0;
      }
    }
    return [...map.values()].sort((a, b) => a.order - b.order);
  }, [chapterOptions, manuscriptBlocks]);

  const manuscriptUntaggedCount = useMemo(
    () => manuscriptBlocks.filter((b) => !b.chapter_id).length,
    [manuscriptBlocks],
  );

  const historyRecentAnchors = contextPack?.history_recall?.recent_anchors ?? [];
  const historySelectionTrace = contextPack?.history_recall?.selection_trace ?? [];

  const canLoadTimeline = Boolean(
    selectedItem?.archive_id &&
      (selectedItem?.normalized_subject || selectedItem?.source_ref),
  );

  const activeCandidateMemoryId = useMemo(() => {
    if (!memoryTimeline) return "";
    const memories = (memoryTimeline as { memories?: Array<Record<string, unknown>> }).memories;
    if (!Array.isArray(memories)) return "";
    const item = memories.find(
      (entry) =>
        entry.memory_layer === "candidate" && entry.status === "active",
    );
    return (item as Record<string, string> | undefined)?.memory_id ?? "";
  }, [memoryTimeline]);

  /* ================================================================
     Agent trace helpers
     ================================================================ */

  const resetAgentTrace = useCallback(() => {
    setAgentTrace({
      orchestrator: { status: "idle", model: "", rounds: [], summary: undefined },
      writer: { status: "idle", model: "", wordCount: 0, elapsedMs: 0 },
      reviewer: { status: "idle" },
      error: "",
    });
  }, []);

  const ensureRound = useCallback(
    (roundNum: number, current: AgentTraceState): AgentRound[] => {
      const rounds = [...current.orchestrator.rounds];
      while (rounds.length <= roundNum) {
        rounds.push({
          roundNum: rounds.length,
          status: "running",
          toolCalls: [],
        });
      }
      return rounds;
    },
    [],
  );

  /* ================================================================
     SSE event handler
     ================================================================ */

  const handleTraceEvent = useCallback(
    (event: SSEEvent) => {
      // React 19 StrictMode intentionally double-invokes state updaters to surface
      // impure reducers. Side effects (ref mutations, setState on other atoms,
      // appending tokens) MUST happen outside the setAgentTrace updater — otherwise
      // each writer_token gets appended twice, which is the root cause of the
      // observed prose duplication.
      if (event.type === "writer_token") {
        const token = (event.token as string) || "";
        contentRef.current += token;
        const wordCount = contentRef.current.length;
        setAgentSceneContent(contentRef.current);
        setDraftPhase("writing");
        setAgentTrace((prev) => ({
          ...prev,
          writer: { ...prev.writer, status: "running", wordCount },
        }));
        return;
      }

      if (event.type === "orchestrator_status") {
        setDraftPhase(event.phase === "writing" ? "writing" : "collecting");
        setMessage((event.message as string) || "编排中...");
      } else if (event.type === "data_health_warning") {
        // Fired once per run, right after orchestrator_status starting. Reset
        // the dismissed flag so fresh issues show a banner even if the user
        // closed the previous one.
        const issues = Array.isArray(event.issues)
          ? (event.issues as DataHealthIssue[])
          : [];
        setDataHealthIssues(issues);
        setDataHealthDismissed(false);
      } else if (event.type === "outline_ready") {
        setDraftPhase("done");
        setOutlineData(event.outline as OutlineScene[]);
      } else if (event.type === "error") {
        setError((event.message as string) || "生成失败");
        setAgentStreaming(false);
        setDraftPhase(contentRef.current ? "done" : "idle");
      }

      setAgentTrace((prev) => {
        const next = { ...prev };

        if (event.type === "orchestrator_status") {
          const orchStatus = { ...prev.orchestrator, status: "running" as const };
          if (event.model) {
            if (event.phase === "writing") {
              next.writer = { ...prev.writer, model: event.model as string, status: "running" };
            } else {
              orchStatus.model = event.model as string;
            }
          }
          next.orchestrator = orchStatus;
        } else if (event.type === "thinking") {
          const rn = (event.round as number) ?? Math.max(0, prev.orchestrator.rounds.length - 1);
          const rounds = ensureRound(rn, prev);
          const r = rounds[rn]!;
          rounds[rn] = { roundNum: r.roundNum, status: r.status, toolCalls: r.toolCalls, elapsedMs: r.elapsedMs, promptSnapshot: r.promptSnapshot, thinking: event.content as string };
          next.orchestrator = { ...prev.orchestrator, rounds };
        } else if (event.type === "tool_call") {
          const rn = (event.round as number) ?? Math.max(0, prev.orchestrator.rounds.length - 1);
          const rounds = ensureRound(rn, prev);
          const r = rounds[rn]!;
          rounds[rn] = {
            roundNum: r.roundNum,
            status: r.status,
            thinking: r.thinking,
            elapsedMs: r.elapsedMs,
            promptSnapshot: r.promptSnapshot,
            toolCalls: [
              ...r.toolCalls,
              {
                name: event.name as string,
                display: (event.display as string) || (event.name as string),
                status: "pending",
                toolElapsedMs: 0,
              },
            ],
          };
          next.orchestrator = { ...prev.orchestrator, rounds };
        } else if (event.type === "tool_result") {
          const rn = (event.round as number) ?? Math.max(0, prev.orchestrator.rounds.length - 1);
          const rounds = ensureRound(rn, prev);
          const r = rounds[rn]!;
          const updated = r.toolCalls.map((tc) =>
            tc.name === event.name && tc.status === "pending"
              ? {
                  ...tc,
                  fullResult: (event.full_result as string) || (event.summary as string),
                  status: (event.status === "error" ? "error" : "done") as "done" | "error",
                  toolElapsedMs: (event.tool_elapsed_ms as number) || 0,
                  render: (event.render as AgentToolCall["render"]) ?? null,
                }
              : tc,
          );
          rounds[rn] = { roundNum: r.roundNum, status: r.status, thinking: r.thinking, elapsedMs: r.elapsedMs, promptSnapshot: r.promptSnapshot, toolCalls: updated };
          next.orchestrator = { ...prev.orchestrator, rounds };
        } else if (event.type === "prompt_snapshot") {
          const rn = (event.round as number) ?? 0;
          const rounds = ensureRound(rn, prev);
          const r = rounds[rn]!;
          const messages = (event.messages as Array<{ content?: string }>) || [];
          const charCount = messages.reduce((sum, m) => sum + (m.content?.length || 0), 0);
          rounds[rn] = {
            roundNum: r.roundNum,
            status: r.status,
            thinking: r.thinking,
            toolCalls: r.toolCalls,
            promptSnapshot: { messages: messages as Array<{ role: string; content: string }>, charCount },
            elapsedMs: (event.elapsed_ms as number) || 0,
          };
          next.orchestrator = { ...prev.orchestrator, rounds };
        } else if (event.type === "phase_summary") {
          const rounds = prev.orchestrator.rounds.map((r) => ({ ...r, status: "done" as const }));
          next.orchestrator = {
            ...prev.orchestrator,
            rounds,
            status: "done",
            summary: {
              toolCount: (event.tool_count as number) || 0,
              roundCount: rounds.length,
              elapsedMs: (event.elapsed_ms as number) || 0,
              tokenUsage: (event.token_usage as { total_tokens?: number }) ?? undefined,
            },
          };
        } else if (event.type === "reviewer_status") {
          next.reviewer = {
            ...(prev.reviewer || { status: "idle" }),
            status: (event.status as "running" | "done" | "error") || "running",
          };
        } else if (event.type === "reviewer_feedback") {
          next.reviewer = {
            ...(prev.reviewer || { status: "running" }),
            status: "done",
            feedback: event.feedback as NonNullable<AgentTraceState["reviewer"]>["feedback"],
            sceneId: event.scene_id as string | undefined,
            chapterId: event.chapter_id as string | undefined,
            chapterOrder: event.chapter_order as number | undefined,
            sceneOrder: event.scene_order as number | undefined,
          };
        } else if (event.type === "reviewer_complete") {
          next.reviewer = {
            ...(prev.reviewer || { status: "done" }),
            status: "done",
            elapsedMs: (event.elapsed_ms as number) || 0,
          };
        } else if (event.type === "error") {
          next.error = (event.message as string) || "生成失败";
        }
        return next;
      });
    },
    [ensureRound],
  );

  const handleTraceDone = useCallback(
    (event: SSEEvent) => {
      setAgentStreaming(false);
      setDraftPhase("done");
      setAgentTrace((prev) => ({
        ...prev,
        writer: {
          ...prev.writer,
          status: "done",
          elapsedMs: (event.elapsed_ms as number) || 0,
        },
      }));
      if (event.outline_saved) {
        setMessage(`大纲已保存：${event.scene_count} 个场景`);
        return;
      }
      const wc = (event.word_count as number) || contentRef.current.length;
      setMessage(`创作完成：${wc} 字`);
      setCommitTargetChapterId(chapterId || "");
      void loadScenes();
    },
    [chapterId], // eslint-disable-line react-hooks/exhaustive-deps
  );

  /* ================================================================
     Data loading
     ================================================================ */

  const loadScenes = useCallback(async () => {
    if (!projectId || !chapterId) {
      setScenes([]);
      return;
    }
    try {
      const response = await getScenes(chapterId, projectId);
      setScenes((response.data as SceneItem[]) || []);
    } catch {
      setScenes([]);
    }
  }, [projectId, chapterId]);

  const loadPresets = useCallback(async () => {
    if (!projectId) return;
    try {
      const response = await getPresets(projectId);
      const list = (response.data as PresetItem[]) || [];
      setPresets(list);
      if (!selectedPresetId && list.length) {
        const def = list.find((p) => p.is_default);
        setSelectedPresetId((def ?? list[0])!.preset_id);
      }
    } catch {
      setPresets([]);
    }
  }, [projectId, selectedPresetId]);

  const loadReviewerRules = useCallback(async () => {
    if (!projectId) return;
    try {
      const response = await getReviewerRules(projectId);
      const data = (response.data as Record<string, unknown>) || {};
      setReviewerRulesDefault((data.default_prompt as string) || "");
      setReviewerRulesIsCustom(Boolean(data.is_custom));
      setReviewerRulesText(
        data.is_custom ? (data.custom_prompt as string) : (data.default_prompt as string) || "",
      );
    } catch {
      /* silent */
    }
  }, [projectId]);

  const loadManuscriptBlocks = useCallback(async () => {
    if (!projectId) {
      setManuscriptBlocks([]);
      setManuscriptTotalWords(0);
      return;
    }
    try {
      const res = await getManuscript(projectId);
      const payload = (res.data as Record<string, unknown>) || {};
      setManuscriptBlocks((payload.blocks as ManuscriptBlockItem[]) || []);
      setManuscriptTotalWords((payload.total_words as number) || 0);
    } catch (e) {
      console.error("Failed to load manuscript", e);
    }
  }, [projectId]);

  const loadChapterOutline = useCallback(async () => {
    if (!projectId || !chapterId) {
      setChapterOutlineData(null);
      return;
    }
    try {
      const chapters = await getChapters(projectId);
      const rawData = chapters.data as Record<string, unknown> | ChapterOption[] | undefined;
      const list: Array<Record<string, unknown>> = Array.isArray(rawData) ? rawData as unknown as Array<Record<string, unknown>> : ((rawData as Record<string, unknown>)?.chapters as Array<Record<string, unknown>>) || [];
      const ch = (list as unknown as Array<Record<string, unknown>>).find((c) => c.chapter_id === chapterId);
      if (ch?.outline_json) {
        const parsed =
          typeof ch.outline_json === "string"
            ? JSON.parse(ch.outline_json as string)
            : ch.outline_json;
        setChapterOutlineData(Array.isArray(parsed) ? parsed : null);
      } else {
        setChapterOutlineData(null);
      }
    } catch {
      setChapterOutlineData(null);
    }
  }, [projectId, chapterId]);

  /* ================================================================
     Project / chapter change handlers
     ================================================================ */

  const refreshProjectData = useCallback(async () => {
    if (!projectId) return;
    try {
      const [optionsResponse, sessionsResponse] = await Promise.all([
        getChapterContextOptions(projectId),
        listWorldlineSessions({ projectId }),
      ]);
      const optData = (optionsResponse.data as Record<string, unknown>) || {};
      setChapterOptions((optData.chapters as ChapterOption[]) || []);
      setProjectPovs((optData.pov_characters as string[]) || []);
      const defaults = deriveWriterDefaults(optData as { chapters?: ChapterOption[]; pov_characters?: string[] });
      setChapterId((prev) => (!prev && defaults.chapterId ? defaults.chapterId : prev));
      setChapterOrder((prev) => (!prev && defaults.chapterOrder ? defaults.chapterOrder : prev));
      setPovCharacter((prev) => (!prev && defaults.povCharacter ? defaults.povCharacter : prev));

      const sessData = (sessionsResponse.data as Record<string, unknown>) || {};
      const sessArr = (sessData.sessions as Array<Record<string, unknown>>) || [];
      setSessionOptions(
        sessArr.map((item) => ({
          session_id: item.session_id as string,
          label:
            (item.label as string) ||
            `${item.session_scope === "global" ? "全局" : "项目"} · ${(item.session_id as string).slice(0, 8)}`,
        })),
      );
      setMessage("项目数据已刷新");
      await loadReviewerRules();
      await loadPresets();
    } catch (err: unknown) {
      setError((err as Error).message || "读取项目上下文失败");
    }
  }, [projectId, loadReviewerRules, loadPresets]);

  const handleProjectChange = useCallback(
    async (newProjectId: string) => {
      setProjectId(newProjectId);
      setContextPack(null);
      setSelectedItem(null);
      setMemoryTimeline(null);
      setTimelineError("");
      setDraftPhase("idle");
      resetAgentTrace();
      if (!newProjectId) {
        setChapterOptions([]);
        setProjectPovs([]);
        setSessionOptions([]);
        setWorldlineAgents([]);
        setReviewerRulesText("");
        setReviewerRulesDefault("");
        setReviewerRulesIsCustom(false);
        return;
      }
    },
    [resetAgentTrace],
  );

  // Load project data whenever projectId changes
  useEffect(() => {
    if (projectId) {
      void refreshProjectData();
    }
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load scenes when chapter changes
  useEffect(() => {
    if (chapterId) {
      const ch = chapterOptions.find((c) => c.chapter_id === chapterId);
      setChapterOrder(ch?.order ?? 0);
      void loadScenes();
      setSelectedSceneId("");
      setAgentSceneContent("");
    }
  }, [chapterId]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ================================================================
     Session change
     ================================================================ */

  const handleSessionChange = useCallback(
    async (newSessionId: string) => {
      setSessionId(newSessionId);
      setWorldlineAgents([]);
      if (!newSessionId) return;
      try {
        const response = await getWorldlineAgents(newSessionId, "main");
        setWorldlineAgents(
          ((response.data as Record<string, unknown>)?.agents as WorldlineAgent[]) || [],
        );
      } catch (err: unknown) {
        setError((err as Error).message || "读取世界线角色失败");
      }
    },
    [],
  );

  /* ================================================================
     Scene management
     ================================================================ */

  const handleSceneSelect = useCallback(
    (sceneId: string) => {
      setSelectedSceneId(sceneId);
      const scene = scenes.find((s) => s.scene_id === sceneId);
      if (scene) setAgentSceneContent(scene.content || "");
    },
    [scenes],
  );

  const handleAddScene = useCallback(() => {
    if (!chapterId) return;
    const nextOrder =
      scenes.length > 0 ? Math.max(...scenes.map((s) => s.scene_order)) + 1 : 1;
    const newSceneId = `sc_${Date.now().toString(36)}`;
    setScenes((prev) => [
      ...prev,
      {
        scene_id: newSceneId,
        scene_order: nextOrder,
        title: `场景 ${nextOrder}`,
        word_count: 0,
        status: "draft",
        content: "",
      },
    ]);
    setSelectedSceneId(newSceneId);
    setAgentSceneContent("");
  }, [chapterId, scenes]);

  const handleDeleteScene = useCallback(
    async (sceneId: string) => {
      try {
        await deleteSceneApi(sceneId, projectId);
        setScenes((prev) => prev.filter((s) => s.scene_id !== sceneId));
        if (selectedSceneId === sceneId) {
          setSelectedSceneId("");
          setAgentSceneContent("");
        }
      } catch (err: unknown) {
        setError((err as Error).message || "删除场景失败");
      }
    },
    [projectId, selectedSceneId],
  );

  const handleSceneContentUpdate = useCallback(
    async (newContent: string) => {
      setAgentSceneContent(newContent);
      if (selectedSceneId && projectId) {
        try {
          await updateSceneApi(selectedSceneId, {
            project_id: projectId,
            content: newContent,
          });
          setScenes((prev) =>
            prev.map((s) =>
              s.scene_id === selectedSceneId
                ? { ...s, word_count: newContent.length }
                : s,
            ),
          );
        } catch {
          /* silent save failure */
        }
      }
    },
    [selectedSceneId, projectId],
  );

  /* ================================================================
     Preset management
     ================================================================ */

  const openPresetEditor = useCallback(
    (preset: PresetItem | null) => {
      setEditingPreset(preset);
      setPresetEditorVisible(true);
    },
    [],
  );

  const handlePresetSave = useCallback(
    async (data: Record<string, unknown>) => {
      try {
        if (data.preset_id) {
          await updatePreset(data.preset_id as string, {
            ...data,
            project_id: projectId,
          });
        } else {
          const result = await createPreset({ ...data, project_id: projectId });
          const rd = result.data as Record<string, string> | undefined;
          if (rd?.preset_id) setSelectedPresetId(rd.preset_id);
        }
        setPresetEditorVisible(false);
        await loadPresets();
      } catch (err: unknown) {
        setError((err as Error).message || "保存预设失败");
      }
    },
    [projectId, loadPresets],
  );

  /* ================================================================
     Agent generation
     ================================================================ */

  const handleAgentGenerate = useCallback(async () => {
    if (!projectId) return;
    setError("");
    setAgentStreaming(true);
    setAgentSceneContent("");
    contentRef.current = "";
    setOutlineData(null);
    setDraftPhase("collecting");
    resetAgentTrace();
    setDataHealthIssues([]);
    setDataHealthDismissed(false);
    setCommitDone(false);
    if (worldUpdateAbortRef.current) {
      worldUpdateAbortRef.current.abort();
      worldUpdateAbortRef.current = null;
    }
    setWorldUpdateBusy(false);
    setWorldUpdateDone(false);
    setWorldUpdateSummary("");

    const chapter = chapterOptions.find((c) => c.chapter_id === chapterId);
    const currentSceneOrder =
      scenes.find((s) => s.scene_id === selectedSceneId)?.scene_order || 1;

    const payload = {
      project_id: projectId,
      task_type: taskType,
      chapter_id: chapterId,
      chapter_order: chapter?.order || chapterOrder,
      scene_order: currentSceneOrder,
      pov_entity_id: povCharacter,
      involved_entity_ids: involvedEntityIds,
      scene_focus: sceneFocus,
      user_instruction: authorInstruction,
      preset_id: selectedPresetId,
      session_id: sessionId,
      selected_text: "",
      scene_id: selectedSceneId,
      last_block_id:
        taskType === "continue"
          ? (selectedAnchorBlockId || lastCommittedBlockId)
          : "",
    };

    if (draftAbortControllerRef.current) {
      draftAbortControllerRef.current.abort();
    }
    draftAbortControllerRef.current = new AbortController();

    await runWriterAgent(
      payload,
      {
        onEvent: handleTraceEvent,
        onDone: handleTraceDone,
        onError(event) {
          setAgentStreaming(false);
          // When the stream fails mid-generation, prose collected so far is
          // almost always truncated and useless. Keeping it on-screen only
          // invites the user to hit "generate" again and see the broken head
          // prepended to the new output, so we drop it and reset the editor.
          contentRef.current = "";
          setAgentSceneContent("");
          setDraftPhase("idle");
          const msg =
            (event as SSEEvent)?.message ??
            (event as Error)?.toString?.() ??
            "生成失败";
          setError(msg as string);
        },
      },
      draftAbortControllerRef.current.signal,
    );
  }, [
    projectId,
    chapterId,
    chapterOptions,
    chapterOrder,
    taskType,
    scenes,
    selectedSceneId,
    povCharacter,
    involvedEntityIds,
    sceneFocus,
    authorInstruction,
    selectedPresetId,
    sessionId,
    lastCommittedBlockId,
    selectedAnchorBlockId,
    resetAgentTrace,
    handleTraceEvent,
    handleTraceDone,
  ]);

  /* ================================================================
     Reviewer rules
     ================================================================ */

  const handleSaveReviewerRules = useCallback(async () => {
    if (!projectId || reviewerRulesSaving) return;
    try {
      setReviewerRulesSaving(true);
      await saveReviewerRules(projectId, reviewerRulesText);
      setReviewerRulesIsCustom(true);
      setMessage("审校规则已保存");
    } catch (err: unknown) {
      setError((err as Error).message || "保存审校规则失败");
    } finally {
      setReviewerRulesSaving(false);
    }
  }, [projectId, reviewerRulesSaving, reviewerRulesText]);

  const handleResetReviewerRules = useCallback(async () => {
    if (!projectId || reviewerRulesSaving) return;
    try {
      setReviewerRulesSaving(true);
      await saveReviewerRules(projectId, "");
      setReviewerRulesText(reviewerRulesDefault);
      setReviewerRulesIsCustom(false);
      setMessage("已恢复默认审校规则");
    } catch (err: unknown) {
      setError((err as Error).message || "恢复默认规则失败");
    } finally {
      setReviewerRulesSaving(false);
    }
  }, [projectId, reviewerRulesSaving, reviewerRulesDefault]);

  /* ================================================================
     Memory review
     ================================================================ */

  const loadSelectedTimeline = useCallback(async () => {
    if (!canLoadTimeline || !selectedItem?.archive_id) return;
    try {
      setReviewBusy(true);
      setTimelineError("");
      const response = await getArchiveMemoryTimeline(selectedItem.archive_id, {
        normalizedSubject: selectedItem.normalized_subject,
        memoryId:
          selectedItem.source_kind === "agent_memory" ? selectedItem.source_ref : "",
      });
      setMemoryTimeline(response.data as Record<string, unknown>);
    } catch (err: unknown) {
      setTimelineError((err as Error).message || "读取时间线失败");
    } finally {
      setReviewBusy(false);
    }
  }, [canLoadTimeline, selectedItem]);

  const adoptSelectedMemory = useCallback(async () => {
    if (!activeCandidateMemoryId || !selectedItem?.archive_id) return;
    try {
      setReviewBusy(true);
      setTimelineError("");
      await adoptArchiveMemory(selectedItem.archive_id, activeCandidateMemoryId);
      await loadSelectedTimeline();
    } catch (err: unknown) {
      setTimelineError((err as Error).message || "采纳失败");
    } finally {
      setReviewBusy(false);
    }
  }, [activeCandidateMemoryId, selectedItem, loadSelectedTimeline]);

  const rejectSelectedMemory = useCallback(async () => {
    if (!activeCandidateMemoryId || !selectedItem?.archive_id) return;
    try {
      setReviewBusy(true);
      setTimelineError("");
      await rejectArchiveMemory(selectedItem.archive_id, activeCandidateMemoryId);
      await loadSelectedTimeline();
    } catch (err: unknown) {
      setTimelineError((err as Error).message || "驳回失败");
    } finally {
      setReviewBusy(false);
    }
  }, [activeCandidateMemoryId, selectedItem, loadSelectedTimeline]);

  /* ================================================================
     Outline
     ================================================================ */

  const handleOutlineSave = useCallback(
    async (outline: OutlineScene[], label = "") => {
      if (!projectId || !chapterId) {
        setError("请先选择项目和章节");
        return;
      }
      try {
        await updateChapter(chapterId, {
          project_id: projectId,
          outline_json: JSON.stringify(outline),
          outline_label: label,
        });
        if (viewMode === "outline") {
          setChapterOutlineData(outline);
        } else {
          setOutlineData(outline);
        }
        setMessage("大纲已保存");
        setError("");
      } catch (err: unknown) {
        setError((err as Error).message || "保存大纲失败");
      }
    },
    [projectId, chapterId, viewMode],
  );

  const handleLoadVersions = useCallback(
    async (versionId?: string) => {
      if (!projectId || !chapterId) return;
      try {
        if (!versionId) {
          const resp = await getOutlineVersions(chapterId, projectId);
          setOutlineVersions((resp.data as OutlineVersionItem[]) || []);
          return;
        }
        const resp = await getOutlineVersion(chapterId, versionId, projectId);
        const ver = resp.data as Record<string, unknown>;
        if (ver?.outline_json) {
          const parsed =
            typeof ver.outline_json === "string"
              ? JSON.parse(ver.outline_json as string)
              : ver.outline_json;
          setOutlinePreview(Array.isArray(parsed) ? parsed : null);
          setOutlinePreviewVersionId(versionId);
        }
        setError("");
      } catch (err: unknown) {
        setError((err as Error).message || "加载版本失败");
      }
    },
    [projectId, chapterId],
  );

  const handleOutlineRestore = useCallback(async () => {
    if (!outlinePreviewVersionId || !projectId || !chapterId) return;
    try {
      await restoreOutlineVersion(chapterId, outlinePreviewVersionId, projectId);
      setOutlinePreview(null);
      setOutlinePreviewVersionId("");
      if (viewMode === "outline") {
        await loadChapterOutline();
      }
      const resp = await getOutlineVersions(chapterId, projectId);
      setOutlineVersions((resp.data as OutlineVersionItem[]) || []);
      setMessage("已回退到历史版本");
      setError("");
    } catch (err: unknown) {
      setError((err as Error).message || "回退失败");
    }
  }, [outlinePreviewVersionId, projectId, chapterId, viewMode, loadChapterOutline]);

  /* ================================================================
     Manuscript operations
     ================================================================ */

  const handleCommitToManuscript = useCallback(
    async (content?: string) => {
      if (!projectId) return;
      const text = content || agentSceneContent;
      if (!text.trim()) return;
      const targetId = commitTargetChapterId || chapterId;
      const chapter = targetId
        ? chapterOptions.find((c) => c.chapter_id === targetId)
        : null;
      const chapterLabel = chapter
        ? `第${chapter.order}章 · ${chapter.title}`
        : undefined;
      try {
        setCommitBusy(true);
        const commitResult = await commitToManuscript(projectId, {
          content: text,
          source_scene_id: selectedSceneId || undefined,
          chapter_id: targetId || undefined,
          pov_entity_id: povCharacter || undefined,
          involved_entities_json: involvedEntityIds.length
            ? JSON.stringify(involvedEntityIds)
            : undefined,
        });
        const blockData = (commitResult?.data ?? commitResult) as Record<string, string>;
        if (blockData?.block_id) {
          setLastCommittedBlockId(blockData.block_id);
        }
        setMessage(
          chapterLabel ? `已提交到稿件 [${chapterLabel}]` : "已提交到稿件",
        );
        setShowContinueButton(true);
        setCommitDone(true);
      } catch (err: unknown) {
        setError((err as Error).message || "提交到稿件失败");
      } finally {
        setCommitBusy(false);
      }
    },
    [
      projectId,
      agentSceneContent,
      commitTargetChapterId,
      chapterId,
      chapterOptions,
      selectedSceneId,
      povCharacter,
      involvedEntityIds,
    ],
  );

  const handleContinueNext = useCallback(async () => {
    setAgentSceneContent("");
    contentRef.current = "";
    setDraftPhase("idle");
    setShowContinueButton(false);
    setTaskType("continue");
    try {
      const res = await getContinuationContext(projectId, {
        lastBlockId: selectedAnchorBlockId || lastCommittedBlockId,
      });
      setContinuationContext(
        ((res.data as ContinuationCtx) || res) as ContinuationCtx,
      );
    } catch (err: unknown) {
      setError((err as Error).message || "加载续写上下文失败");
    }
  }, [projectId, lastCommittedBlockId, selectedAnchorBlockId]);

  const dismissReviewerFeedback = useCallback(() => {
    setAgentTrace((prev) => ({
      ...prev,
      reviewer: { ...(prev.reviewer || { status: "idle" }), feedback: undefined },
    }));
  }, []);

  /** Re-run the writer composer with reviewer-selected rewrites, in place. */
  const handleApplyReviewer = useCallback(
    async (acceptedIssueIds: string[]) => {
      if (!projectId) return;
      const reviewer = agentTrace.reviewer;
      const feedback = reviewer?.feedback;
      if (!feedback || !reviewer?.sceneId) {
        setError("没有可应用的审校建议");
        return;
      }
      const accepted = (feedback.issues || []).filter((i) =>
        acceptedIssueIds.includes(i.id),
      );
      if (!accepted.length) {
        setError("请至少选择一条改写建议");
        return;
      }
      const draft = contentRef.current || agentSceneContent;
      if (!draft.trim()) {
        setError("初稿内容为空，无法改写");
        return;
      }

      setError("");
      setAgentStreaming(true);
      setDraftPhase("writing");
      // Hold the original draft in contentRef so we can restore on error.
      const originalDraft = draft;
      contentRef.current = "";
      setAgentSceneContent("");

      const payload = {
        project_id: projectId,
        scene_id: reviewer.sceneId,
        chapter_id: reviewer.chapterId || chapterId || "",
        chapter_order:
          reviewer.chapterOrder ??
          chapterOptions.find((c) => c.chapter_id === chapterId)?.order ??
          chapterOrder,
        scene_order: reviewer.sceneOrder ?? 1,
        preset_id: selectedPresetId,
        pov_entity_id: povCharacter,
        involved_entity_ids: involvedEntityIds,
        writing_brief: {}, // server falls back to its stored brief via scene repo (not yet wired)
        accepted_issues: accepted,
        draft: originalDraft,
      };

      try {
        await applyReviewer(payload, {
          onEvent: handleTraceEvent,
          onDone: handleTraceDone,
          onError(event) {
            setAgentStreaming(false);
            // Restore original draft so the user can still see it and retry.
            contentRef.current = originalDraft;
            setAgentSceneContent(originalDraft);
            setDraftPhase("done");
            const msg =
              (event as SSEEvent)?.message ??
              (event as Error)?.toString?.() ??
              "改写失败";
            setError(msg as string);
          },
        });
      } catch (err: unknown) {
        setAgentStreaming(false);
        contentRef.current = originalDraft;
        setAgentSceneContent(originalDraft);
        setDraftPhase("done");
        setError((err as Error)?.message || "改写失败");
      }
    },
    [
      projectId,
      agentTrace.reviewer,
      agentSceneContent,
      chapterId,
      chapterOptions,
      chapterOrder,
      selectedPresetId,
      povCharacter,
      involvedEntityIds,
      handleTraceEvent,
      handleTraceDone,
    ],
  );

  const handleWorldUpdate = useCallback(async () => {
    if (!projectId || !agentSceneContent) return;
    if (worldUpdateAbortRef.current) {
      worldUpdateAbortRef.current.abort();
    }
    worldUpdateAbortRef.current = new AbortController();
    resetAgentTrace();
    setWorldUpdateBusy(true);
    setWorldUpdateDone(false);
    setWorldUpdateSummary("");
    try {
      await updateWorldData(
        {
          project_id: projectId,
          content: agentSceneContent,
          chapter_order: chapterOrder || 0,
        },
        {
          onEvent: handleTraceEvent,
          onDone() {
            setWorldUpdateBusy(false);
            setWorldUpdateDone(true);
            setWorldUpdateSummary("世界数据已更新");
            setAgentTrace((prev) => ({
              ...prev,
              orchestrator: { ...prev.orchestrator, status: "done" },
            }));
          },
          onError(event) {
            setWorldUpdateBusy(false);
            setError(
              ((event as SSEEvent)?.message as string) || "世界数据更新失败",
            );
          },
        },
        worldUpdateAbortRef.current.signal,
      );
    } catch (err: unknown) {
      setWorldUpdateBusy(false);
      setError((err as Error).message || "世界数据更新失败");
    }
  }, [projectId, agentSceneContent, chapterOrder, resetAgentTrace, handleTraceEvent]);

  const handleManuscriptBlockSave = useCallback(
    async (block: ManuscriptBlockItem, newContent: string) => {
      try {
        await updateManuscriptBlock(block.block_id, {
          project_id: projectId,
          content: newContent,
        });
      } catch (e) {
        console.error("Manuscript block save failed", e);
      }
    },
    [projectId],
  );

  const handleManuscriptBlockDelete = useCallback(
    async (blockId: string) => {
      try {
        await deleteManuscriptBlock(blockId, projectId);
        await loadManuscriptBlocks();
        setMessage("稿件段落已删除");
      } catch (e: unknown) {
        setError((e as Error).message || "删除稿件失败");
      }
    },
    [projectId, loadManuscriptBlocks],
  );

  const handleMoveManuscriptBlock = useCallback(
    async (blockId: string, targetChapterId: string | null) => {
      if (!projectId || !blockId) return;
      try {
        await moveManuscriptBlock(blockId, {
          project_id: projectId,
          chapter_id: targetChapterId || null,
        });
        await loadManuscriptBlocks();
        setMessage(targetChapterId ? "已移动到目标章节" : "已移出章节");
      } catch (e: unknown) {
        setError((e as Error).message || "移动稿件段落失败");
      }
    },
    [projectId, loadManuscriptBlocks],
  );

  const handleCreateManuscriptChapter = useCallback(
    async (name: string) => {
      if (!projectId || !name.trim()) return;
      try {
        await createChapter(projectId, { title: name.trim() });
        const optionsResponse = await getChapters(projectId);
        const optData = (optionsResponse.data as Record<string, unknown>) || {};
        setChapterOptions((optData.chapters as ChapterOption[]) || []);
        setMessage(`章节「${name}」已创建`);
      } catch (err: unknown) {
        setError((err as Error).message || "创建章节失败");
      }
    },
    [projectId],
  );

  const handleRenameManuscriptChapter = useCallback(
    async (chapterIdToRename: string, newTitle: string) => {
      if (!projectId || !chapterIdToRename || !newTitle.trim()) return;
      try {
        await updateChapter(chapterIdToRename, {
          title: newTitle.trim(),
          project_id: projectId,
        });
        const optionsResponse = await getChapters(projectId);
        const optData = (optionsResponse.data as Record<string, unknown>) || {};
        setChapterOptions((optData.chapters as ChapterOption[]) || []);
        await loadManuscriptBlocks();
        setMessage(`章节已重命名为「${newTitle}」`);
      } catch (e: unknown) {
        setError((e as Error).message || "重命名章节失败");
      }
    },
    [projectId, loadManuscriptBlocks],
  );

  const handleDeleteManuscriptChapter = useCallback(
    async (chapterIdToDelete: string) => {
      if (!projectId || !chapterIdToDelete) return;
      const blocksInChapter = manuscriptBlocks.filter(
        (b) => b.chapter_id === chapterIdToDelete,
      );
      try {
        for (const b of blocksInChapter) {
          await moveManuscriptBlock(b.block_id, {
            project_id: projectId,
            chapter_id: null,
          });
        }
        const { deleteChapter: delCh } = await import("@/api/writer-agent");
        await delCh(chapterIdToDelete, projectId);
        const optionsResponse = await getChapters(projectId);
        const optData = (optionsResponse.data as Record<string, unknown>) || {};
        setChapterOptions((optData.chapters as ChapterOption[]) || []);
        await loadManuscriptBlocks();
        setMessage("章节已删除，段落已移至未归类");
      } catch (e: unknown) {
        setError((e as Error).message || "删除章节失败");
      }
    },
    [projectId, manuscriptBlocks, loadManuscriptBlocks],
  );

  const handleManuscriptExport = useCallback(
    async (fmt: string) => {
      try {
        const blob = await exportManuscript(projectId, fmt);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `manuscript.${fmt}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (e: unknown) {
        setError((e as Error).message || "导出失败");
      }
    },
    [projectId],
  );

  const switchViewMode = useCallback(
    (mode: ViewMode) => {
      setViewMode(mode);
      if (mode === "manuscript") void loadManuscriptBlocks();
      else if (mode === "outline") void loadChapterOutline();
    },
    [loadManuscriptBlocks, loadChapterOutline],
  );

  const handleChapterSelectUpdate = useCallback(
    async (val: string) => {
      if (val === "__create_new__") {
        return "__create_new__";
      }
      setChapterId(val);
      return val;
    },
    [],
  );

  const handleCommitChapterSelectUpdate = useCallback(
    async (val: string) => {
      if (val === "__create_new__") {
        return "__create_new__";
      }
      setCommitTargetChapterId(val);
      return val;
    },
    [],
  );

  /* ─── Migration ─── */
  const handleMigrate = useCallback(async () => {
    if (!projectId) return;
    try {
      setBusy(true);
      setMessage("正在迁移数据到 novel.sqlite3...");
      await migrateProject(projectId);
      setMessage("数据迁移完成");
      await loadScenes();
      await loadPresets();
    } catch (err: unknown) {
      setError((err as Error).message || "迁移失败");
    } finally {
      setBusy(false);
    }
  }, [projectId, loadScenes, loadPresets]);

  /* ─── Cleanup ─── */
  useEffect(() => {
    return () => {
      if (draftAbortControllerRef.current) draftAbortControllerRef.current.abort();
      if (worldUpdateAbortRef.current) worldUpdateAbortRef.current.abort();
    };
  }, []);

  /* ─── Load projects on mount ─── */
  useEffect(() => {
    void refreshProjects();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    /* selection */
    projects,
    projectId,
    scopeType,
    setScopeType,
    chapterId,
    chapterOrder,
    povCharacter,
    setPovCharacter,
    sceneFocus,
    setSceneFocus,
    sessionId,
    authorInstruction,
    setAuthorInstruction,
    taskType,
    setTaskType,
    viewMode,

    /* options */
    chapterOptions,
    povOptions,
    sessionOptions,

    /* ui */
    busy,
    message,
    error,
    debugCollapsed,
    setDebugCollapsed,

    /* reviewer rules */
    reviewerRulesCollapsed,
    setReviewerRulesCollapsed,
    reviewerRulesText,
    setReviewerRulesText,
    reviewerRulesIsCustom,
    reviewerRulesSaving,

    /* context & memory */
    contextPack,
    contextCollapsed,
    setContextCollapsed,
    selectedItem,
    setSelectedItem,
    memoryTimeline,
    reviewBusy,
    timelineError,
    canLoadTimeline,
    activeCandidateMemoryId,
    historyRecentAnchors,
    historySelectionTrace,

    /* draft */
    draftPhase,
    agentSceneContent,
    agentStreaming,
    agentTrace,
    handleTraceEvent,
    outlineData,
    canSubmit,
    canGenerate,
    generateButtonLabel,

    /* data health (Task 4) */
    dataHealthIssues,
    dataHealthDismissed,
    dismissDataHealth: () => setDataHealthDismissed(true),

    /* scenes */
    scenes,
    selectedSceneId,

    /* presets */
    presets,
    selectedPresetId,
    setSelectedPresetId,
    presetEditorVisible,
    editingPreset,

    /* manuscript */
    manuscriptBlocks,
    manuscriptTotalWords,
    manuscriptChapterList,
    manuscriptUntaggedCount,
    manuscriptSelectedChapterId,
    setManuscriptSelectedChapterId,
    continuationContext,
    showContinueButton,
    // Task 5: continuation anchor override
    selectedAnchorBlockId,
    setSelectedAnchorBlockId,
    commitBusy,
    commitDone,
    commitTargetChapterId,
    worldUpdateBusy,
    worldUpdateDone,
    worldUpdateSummary,

    /* outline tab */
    chapterOutlineData,
    outlineVersions,
    outlinePreview,

    /* handlers */
    handleProjectChange,
    refreshProjectData,
    handleSessionChange,
    handleSceneSelect,
    handleAddScene,
    handleDeleteScene,
    handleSceneContentUpdate,
    openPresetEditor,
    handlePresetSave,
    handleAgentGenerate,
    // Task 6: cancel the in-flight draft stream. Triggers AbortController →
    // sse.ts onError → which already clears contentRef + resets draftPhase.
    cancelDraft: () => {
      if (draftAbortControllerRef.current) {
        draftAbortControllerRef.current.abort();
        draftAbortControllerRef.current = null;
      }
    },
    handleSaveReviewerRules,
    handleResetReviewerRules,
    loadSelectedTimeline,
    adoptSelectedMemory,
    rejectSelectedMemory,
    handleOutlineSave,
    handleLoadVersions,
    handleOutlineRestore,
    handleCommitToManuscript,
    handleContinueNext,
    handleWorldUpdate,
    handleApplyReviewer,
    dismissReviewerFeedback,
    handleManuscriptBlockSave,
    handleManuscriptBlockDelete,
    handleMoveManuscriptBlock,
    handleCreateManuscriptChapter,
    handleRenameManuscriptChapter,
    handleDeleteManuscriptChapter,
    handleManuscriptExport,
    handleMigrate,
    handleChapterSelectUpdate,
    handleCommitChapterSelectUpdate,
    switchViewMode,
    setOutlinePreview,
    setOutlinePreviewVersionId: setOutlinePreviewVersionId,
    setPresetEditorVisible,
    loadManuscriptBlocks,
  };
}
