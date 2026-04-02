import { computed, ref, shallowRef } from "vue";

import { connectAutoEvolveSSE } from "./worldlineAutoEvolutionSSE.js";
import {
  MAIN_WORLD_BRANCH_ID,
  buildAutoEvolvePayload,
} from "./worldlineAutoEvolutionState.js";

/**
 * Composable: SSE-based auto-evolution streaming.
 *
 * Replaces the old polling approach with real-time SSE.
 * The backend sends evolve_start → evolve_thinking → evolve_candidate → evolve_done → done.
 * Candidate events are accumulated here and exposed to the UI for adopt / reject / edit.
 *
 * Backward-compatible: `currentTask` computed still exposes a task-like object
 * so WorldlineAutoTaskPanel and WorldlineControlPanel keep working.
 */
export function useWorldlineAutoEvolution({
  refreshWorldline,
  setFeedback,
  setError,
} = {}) {
  /* ── config state (user settings) ─────────────────────────── */
  const createMode = ref("manual");
  const goalText = ref("");
  const maxSteps = ref(6);
  const constraints = ref([]);

  /* ── SSE stream state ─────────────────────────────────────── */
  const streamPhase = ref("idle"); // idle | connecting | thinking | streaming | done | error
  const candidateEvents = ref([]);
  const thinkingInfo = shallowRef(null);
  const streamProgress = ref({ completedSteps: 0, maxSteps: 0, candidateCount: 0 });
  const streamResult = shallowRef(null);
  const streamError = ref("");

  let activeStream = null;
  let sseTaskId = "";

  /* ── backward-compatible task snapshot for legacy consumers ── */
  const currentTask = computed(() => {
    if (streamPhase.value === "idle") return null;

    const phase = streamPhase.value;
    const progress = streamProgress.value;
    const statusMap = {
      connecting: "pending",
      thinking: "processing",
      streaming: "processing",
      done: "completed",
      error: "failed",
    };
    const messageMap = {
      connecting: "正在连接自动演化流…",
      thinking: thinkingInfo.value?.question || "正在评估角色决策…",
      streaming: `已生成 ${progress.candidateCount} 个候选事件`,
      done: streamResult.value?.stopReason
        ? `演化完成 (${streamResult.value.stopReason})`
        : "演化完成",
      error: streamError.value,
    };
    const progressPct = progress.maxSteps
      ? Math.round((progress.completedSteps / progress.maxSteps) * 100)
      : 0;

    return {
      branch_id: MAIN_WORLD_BRANCH_ID,
      branch_title: "当前世界",
      task_id: sseTaskId,
      status: statusMap[phase] || "processing",
      progress: phase === "done" ? 100 : progressPct,
      message: messageMap[phase] || "",
      stop_reason: streamResult.value?.stopReason || "",
      goal_verdict: streamResult.value?.goalVerdict || null,
      latest_event: candidateEvents.value.length
        ? candidateEvents.value[candidateEvents.value.length - 1]
        : null,
      error: streamError.value,
    };
  });

  /* ── internal helpers ─────────────────────────────────────── */
  function resetStream() {
    streamPhase.value = "idle";
    candidateEvents.value = [];
    thinkingInfo.value = null;
    streamProgress.value = { completedSteps: 0, maxSteps: 0, candidateCount: 0 };
    streamResult.value = null;
    streamError.value = "";
  }

  function handleSSEEvent(event) {
    const type = event.type;
    if (type === "evolve_start") {
      streamPhase.value = "thinking";
      streamProgress.value = {
        ...streamProgress.value,
        maxSteps: event.max_steps || 0,
      };
    } else if (type === "evolve_thinking") {
      streamPhase.value = "thinking";
      thinkingInfo.value = {
        agent: event.agent || "system",
        question: event.question || "",
        factors: event.factors || [],
        candidates: event.candidates || [],
      };
    } else if (type === "evolve_candidate") {
      streamPhase.value = "streaming";
      const candidate = {
        event_id: event.event_id,
        step: event.step,
        title: event.action || "",
        summary: event.consequence || "",
        driving_entities: event.actor ? [event.actor] : [],
        confidence: event.confidence || "medium",
        confidence_reason: event.confidence_reason || "",
        event_source: event.event_source || "archive_based",
        status: "candidate",
      };
      candidateEvents.value = [...candidateEvents.value, candidate];
      streamProgress.value = {
        ...streamProgress.value,
        completedSteps: streamProgress.value.completedSteps + 1,
        candidateCount: candidateEvents.value.length,
      };
      void refreshWorldline?.();
    } else if (type === "evolve_done") {
      streamResult.value = {
        candidateCount: event.candidate_count || 0,
        completedSteps: event.completed_steps || 0,
        stopReason: event.stop_reason || "max_steps",
        goalVerdict: event.goal_verdict || null,
      };
    } else if (type === "done") {
      streamPhase.value = "done";
      void refreshWorldline?.();
      setFeedback?.(`自动演化完成，生成 ${candidateEvents.value.length} 个候选事件待审核`);
    } else if (type === "error") {
      streamPhase.value = "error";
      streamError.value = event.message || "未知错误";
      setError?.(streamError.value);
    }
  }

  /* ── public API ────────────────────────────────────────────── */

  function stopStream() {
    if (activeStream) {
      activeStream.abort();
      activeStream = null;
    }
  }

  function syncWorld() {
    // No-op for SSE mode; kept for API compatibility with WorkbenchView.
  }

  function prepareAfterSessionCreate() {
    if (createMode.value === "manual") {
      resetStream();
      return false;
    }
    resetStream();
    return true;
  }

  async function startForSession(sessionId) {
    const payload = buildAutoEvolvePayload({
      createMode: createMode.value,
      goalText: goalText.value,
      maxSteps: maxSteps.value,
    });
    if (!payload) return [];

    stopStream();
    resetStream();
    streamPhase.value = "connecting";
    sseTaskId = `sse-${Date.now()}`;

    payload.constraints = constraints.value.length ? constraints.value : [];

    activeStream = connectAutoEvolveSSE({
      sessionId,
      payload,
      onEvent: handleSSEEvent,
      onError: (err) => {
        streamPhase.value = "error";
        streamError.value = err.message || "SSE 连接失败";
        setError?.(streamError.value);
        activeStream = null;
      },
      onDone: () => {
        if (streamPhase.value !== "error") {
          streamPhase.value = "done";
        }
        activeStream = null;
      },
    });

    // Return immediately so the caller's `await` resolves fast.
    // The SSE stream continues in the background.
    return [{ branch_id: MAIN_WORLD_BRANCH_ID, status: "streaming" }];
  }

  function removeCandidateEvent(eventId) {
    candidateEvents.value = candidateEvents.value.filter((e) => e.event_id !== eventId);
  }

  function removeCandidateEvents(eventIds) {
    const idSet = new Set(eventIds);
    candidateEvents.value = candidateEvents.value.filter((e) => !idSet.has(e.event_id));
  }

  function updateCandidateEvent(eventId, updates) {
    candidateEvents.value = candidateEvents.value.map((e) =>
      e.event_id === eventId ? { ...e, ...updates } : e,
    );
  }

  return {
    // Config
    createMode,
    goalText,
    maxSteps,
    constraints,
    // SSE stream state
    streamPhase,
    candidateEvents,
    thinkingInfo,
    streamProgress,
    streamResult,
    streamError,
    // Backward-compatible
    currentTask,
    // Methods
    syncWorld,
    prepareAfterSessionCreate,
    startForSession,
    stopStream,
    removeCandidateEvent,
    removeCandidateEvents,
    updateCandidateEvent,
  };
}
