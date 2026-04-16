/**
 * Worldline auto-evolution hook — SSE-based streaming state management.
 *
 * Ported from:
 * - src-vue/views/worldline/useWorldlineAutoEvolution.js
 * - src-vue/views/worldline/worldlineAutoEvolutionSSE.js
 * - src-vue/views/worldline/worldlineAutoEvolutionState.js
 */

import { useCallback, useRef, useState } from "react";

/* ================================================================
 * Constants from worldlineAutoEvolutionState.js
 * ================================================================ */

const MANUAL_MODE = "manual";
const FIRST_ROUND_MODE = "first_round";
const DEFAULT_MAX_STEPS = 6;
const MIN_STEPS = 1;
export const MAIN_WORLD_BRANCH_ID = "main";

function normalizeMaxSteps(maxSteps: number): number {
  const numeric = Number(maxSteps);
  if (!Number.isFinite(numeric)) return DEFAULT_MAX_STEPS;
  return Math.max(MIN_STEPS, Math.round(numeric));
}

interface AutoEvolvePayload {
  mode: string;
  goal_text: string;
  max_steps: number;
  constraints?: string[];
}

function buildAutoEvolvePayload(opts: {
  createMode?: string;
  goalText?: string;
  maxSteps?: number;
}): AutoEvolvePayload | null {
  const { createMode = MANUAL_MODE, goalText = "", maxSteps = DEFAULT_MAX_STEPS } = opts;
  if (createMode === MANUAL_MODE) return null;
  if (createMode === FIRST_ROUND_MODE) {
    return { mode: FIRST_ROUND_MODE, goal_text: "", max_steps: 1 };
  }
  return {
    mode: createMode,
    goal_text: goalText.trim(),
    max_steps: normalizeMaxSteps(maxSteps),
  };
}

/* ================================================================
 * SSE helper from worldlineAutoEvolutionSSE.js
 * ================================================================ */

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

interface SSEConnection {
  abort: () => void;
}

interface SSEEvent {
  type: string;
  [key: string]: unknown;
}

function connectAutoEvolveSSE(opts: {
  sessionId: string;
  payload: AutoEvolvePayload;
  onEvent: (event: SSEEvent) => void;
  onError: (err: Error) => void;
  onDone: () => void;
}): SSEConnection {
  const { sessionId, payload, onEvent, onError, onDone } = opts;
  const controller = new AbortController();
  let retryCount = 0;

  function attempt(): void {
    fetch(`/api/worldline/session/${sessionId}/auto-evolve/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text().catch(() => "");
          throw new Error(`SSE 连接失败 (${response.status}): ${text.slice(0, 200)}`);
        }
        retryCount = 0;
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6)) as SSEEvent;
                onEvent(data);
              } catch {
                // skip malformed SSE data lines
              }
            }
          }
        }
        // flush remaining buffer
        if (buffer.startsWith("data: ")) {
          try {
            const data = JSON.parse(buffer.slice(6)) as SSEEvent;
            onEvent(data);
          } catch {
            // skip
          }
        }
        onDone();
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        if (retryCount < MAX_RETRIES) {
          retryCount++;
          setTimeout(attempt, RETRY_DELAY_MS);
        } else {
          onError(err);
        }
      });
  }

  attempt();
  return { abort: () => controller.abort() };
}

/* ================================================================
 * Types
 * ================================================================ */

export type StreamPhase = "idle" | "connecting" | "thinking" | "streaming" | "done" | "error";

export interface CandidateEvent {
  event_id: string;
  step: number;
  title: string;
  summary: string;
  driving_entities: string[];
  confidence: string;
  confidence_reason: string;
  event_source: string;
  status: string;
}

export interface ThinkingInfo {
  agent: string;
  question: string;
  factors: unknown[];
  candidates: unknown[];
}

export interface StreamProgress {
  completedSteps: number;
  maxSteps: number;
  candidateCount: number;
}

export interface StreamResult {
  candidateCount: number;
  completedSteps: number;
  stopReason: string;
  goalVerdict: unknown | null;
}

export interface CurrentTask {
  branch_id: string;
  branch_title: string;
  task_id: string;
  status: string;
  progress: number;
  message: string;
  stop_reason: string;
  goal_verdict: unknown | null;
  latest_event: CandidateEvent | null;
  error: string;
}

export interface AutoEvolutionConfig {
  createMode?: string;
  goalText?: string;
  maxSteps?: number;
  constraints?: string[];
}

export interface UseWorldlineAutoEvolutionOptions {
  refreshWorldline?: () => void;
  setFeedback?: (msg: string) => void;
  setError?: (msg: string) => void;
}

/* ================================================================
 * Hook
 * ================================================================ */

export function useWorldlineAutoEvolution(
  options: UseWorldlineAutoEvolutionOptions = {},
) {
  const { refreshWorldline, setFeedback, setError } = options;

  /* ---- config state ---- */
  const [createMode, setCreateMode] = useState("manual");
  const [goalText, setGoalText] = useState("");
  const [maxSteps, setMaxSteps] = useState(6);
  const [constraints, setConstraints] = useState<string[]>([]);

  /* ---- SSE stream state ---- */
  const [streamPhase, setStreamPhase] = useState<StreamPhase>("idle");
  const [candidateEvents, setCandidateEvents] = useState<CandidateEvent[]>([]);
  const [thinkingInfo, setThinkingInfo] = useState<ThinkingInfo | null>(null);
  const [streamProgress, setStreamProgress] = useState<StreamProgress>({
    completedSteps: 0,
    maxSteps: 0,
    candidateCount: 0,
  });
  const [streamResult, setStreamResult] = useState<StreamResult | null>(null);
  const [streamError, setStreamError] = useState("");

  const activeStreamRef = useRef<SSEConnection | null>(null);
  const sseTaskIdRef = useRef("");

  /* ---- derived: backward-compatible task snapshot ---- */
  function getCurrentTask(): CurrentTask | null {
    if (streamPhase === "idle") return null;

    const statusMap: Record<string, string> = {
      connecting: "pending",
      thinking: "processing",
      streaming: "processing",
      done: "completed",
      error: "failed",
    };

    const messageMap: Record<string, string> = {
      connecting: "正在连接自动演化流...",
      thinking: thinkingInfo?.question || "正在评估角色决策...",
      streaming: `已生成 ${streamProgress.candidateCount} 个候选事件`,
      done: streamResult?.stopReason
        ? `演化完成 (${streamResult.stopReason})`
        : "演化完成",
      error: streamError,
    };

    const progressPct = streamProgress.maxSteps
      ? Math.round((streamProgress.completedSteps / streamProgress.maxSteps) * 100)
      : 0;

    return {
      branch_id: MAIN_WORLD_BRANCH_ID,
      branch_title: "当前世界",
      task_id: sseTaskIdRef.current,
      status: statusMap[streamPhase] || "processing",
      progress: streamPhase === "done" ? 100 : progressPct,
      message: messageMap[streamPhase] || "",
      stop_reason: streamResult?.stopReason || "",
      goal_verdict: streamResult?.goalVerdict || null,
      latest_event: candidateEvents.length
        ? candidateEvents[candidateEvents.length - 1]!
        : null,
      error: streamError,
    };
  }

  /* ---- internal helpers ---- */
  function resetStream(): void {
    setStreamPhase("idle");
    setCandidateEvents([]);
    setThinkingInfo(null);
    setStreamProgress({ completedSteps: 0, maxSteps: 0, candidateCount: 0 });
    setStreamResult(null);
    setStreamError("");
  }

  function handleSSEEvent(event: SSEEvent): void {
    const type = event.type as string;

    if (type === "evolve_start") {
      setStreamPhase("thinking");
      setStreamProgress((prev) => ({
        ...prev,
        maxSteps: (event.max_steps as number) || 0,
      }));
    } else if (type === "evolve_thinking") {
      setStreamPhase("thinking");
      setThinkingInfo({
        agent: (event.agent as string) || "system",
        question: (event.question as string) || "",
        factors: (event.factors as unknown[]) || [],
        candidates: (event.candidates as unknown[]) || [],
      });
    } else if (type === "evolve_candidate") {
      setStreamPhase("streaming");
      const candidate: CandidateEvent = {
        event_id: event.event_id as string,
        step: event.step as number,
        title: (event.action as string) || "",
        summary: (event.consequence as string) || "",
        driving_entities: event.actor ? [event.actor as string] : [],
        confidence: (event.confidence as string) || "medium",
        confidence_reason: (event.confidence_reason as string) || "",
        event_source: (event.event_source as string) || "archive_based",
        status: "candidate",
      };
      setCandidateEvents((prev) => {
        const next = [...prev, candidate];
        setStreamProgress((p) => ({
          ...p,
          completedSteps: p.completedSteps + 1,
          candidateCount: next.length,
        }));
        return next;
      });
      refreshWorldline?.();
    } else if (type === "evolve_done") {
      setStreamResult({
        candidateCount: (event.candidate_count as number) || 0,
        completedSteps: (event.completed_steps as number) || 0,
        stopReason: (event.stop_reason as string) || "max_steps",
        goalVerdict: event.goal_verdict || null,
      });
    } else if (type === "done") {
      setStreamPhase("done");
      refreshWorldline?.();
      // Use a callback to read the latest candidateEvents length
      setCandidateEvents((prev) => {
        setFeedback?.(`自动演化完成，生成 ${prev.length} 个候选事件待审核`);
        return prev;
      });
    } else if (type === "error") {
      setStreamPhase("error");
      const msg = (event.message as string) || "未知错误";
      setStreamError(msg);
      setError?.(msg);
    }
  }

  /* ---- public API ---- */

  const stopStream = useCallback(() => {
    if (activeStreamRef.current) {
      activeStreamRef.current.abort();
      activeStreamRef.current = null;
    }
  }, []);

  const prepareAfterSessionCreate = useCallback((): boolean => {
    if (createMode === "manual") {
      resetStream();
      return false;
    }
    resetStream();
    return true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createMode]);

  const startForSession = useCallback(
    async (sessionId: string): Promise<Array<{ branch_id: string; status: string }>> => {
      const payload = buildAutoEvolvePayload({
        createMode,
        goalText,
        maxSteps,
      });
      if (!payload) return [];

      stopStream();
      resetStream();
      setStreamPhase("connecting");
      sseTaskIdRef.current = `sse-${Date.now()}`;

      payload.constraints = constraints.length ? constraints : [];

      activeStreamRef.current = connectAutoEvolveSSE({
        sessionId,
        payload,
        onEvent: handleSSEEvent,
        onError: (err) => {
          setStreamPhase("error");
          const msg = err.message || "SSE 连接失败";
          setStreamError(msg);
          setError?.(msg);
          activeStreamRef.current = null;
        },
        onDone: () => {
          setStreamPhase((prev) => (prev !== "error" ? "done" : prev));
          activeStreamRef.current = null;
        },
      });

      return [{ branch_id: MAIN_WORLD_BRANCH_ID, status: "streaming" }];
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [createMode, goalText, maxSteps, constraints, stopStream],
  );

  const removeCandidateEvent = useCallback((eventId: string) => {
    setCandidateEvents((prev) => prev.filter((e) => e.event_id !== eventId));
  }, []);

  const removeCandidateEvents = useCallback((eventIds: string[]) => {
    const idSet = new Set(eventIds);
    setCandidateEvents((prev) => prev.filter((e) => !idSet.has(e.event_id)));
  }, []);

  const updateCandidateEvent = useCallback(
    (eventId: string, updates: Partial<CandidateEvent>) => {
      setCandidateEvents((prev) =>
        prev.map((e) => (e.event_id === eventId ? { ...e, ...updates } : e)),
      );
    },
    [],
  );

  return {
    /* Config */
    createMode,
    setCreateMode,
    goalText,
    setGoalText,
    maxSteps,
    setMaxSteps,
    constraints,
    setConstraints,
    /* SSE stream state */
    streamPhase,
    candidateEvents,
    thinkingInfo,
    streamProgress,
    streamResult,
    streamError,
    /* Derived */
    currentTask: getCurrentTask(),
    /* Methods */
    prepareAfterSessionCreate,
    startForSession,
    stopStream,
    removeCandidateEvent,
    removeCandidateEvents,
    updateCandidateEvent,
  } as const;
}
