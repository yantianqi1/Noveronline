"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";

import { fetchCsrfToken } from "@/lib/api/session";
import {
  adoptWorldlineEvent,
  fetchWorldlineEvents,
  fetchWorldlinePreparedAgents,
  fetchWorldlinePreparations,
  fetchWorldlineSession,
  fetchWorldlineSessions,
  fetchWorldlineTimeline,
  injectWorldlineVariable,
  readWorldlineSelection,
  startWorldlineSession,
  startWorldlineStep,
  updateWorldlineEvent,
  WorldlineError,
} from "@/lib/api/worldline-client";
import type {
  WorldlineEvent,
  WorldlineSession,
  WorldlineTimelineEvent,
  WorldlineVariable,
} from "@/lib/api/worldline-types";
import { WORLDLINE_CANDIDATE } from "@/lib/api/worldline-types";
import type { RosterCharacter } from "@/components/character";

import { WorldlineCandidateRail } from "./worldline-candidate-rail";
import { WorldlinePrepareRail, type PrepareStatus } from "./worldline-prepare-rail";
import { WorldlineRunControls, type EvolutionMode } from "./worldline-run-controls";
import { WorldlineStateBanner } from "./worldline-state-banner";
import { WorldlineTimeline } from "./worldline-timeline";
import { DUR, EASE, useFadeUp, useSlideIn } from "./worldline-motion";
import { WorkbenchMasthead } from "@/components/workbench-masthead";

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

/**
 * The Worldline (世界线) workbench — the 导演监视器. Two states on one route:
 * 起点态 (a goal-driven prompt to launch the simulation) and 推演态 (a
 * three-column monitor: prepare rail / evolution timeline / candidate rail).
 * The timeline only ever shows confirmed canon; candidates wait in gold until
 * the author adopts them. Nothing here fabricates events — the backend drives
 * every card, and a missing backend renders an honest error.
 */
export function WorldlineWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const fadeUp = useFadeUp();
  const slideIn = useSlideIn();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<{ tenant_id: string; project_id: string } | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  const [session, setSession] = useState<WorldlineSession | null>(null);
  const [timeline, setTimeline] = useState<WorldlineTimelineEvent[]>([]);
  const [candidates, setCandidates] = useState<WorldlineEvent[]>([]);
  const [roster, setRoster] = useState<RosterCharacter[]>([]);
  const [variables, setVariables] = useState<WorldlineVariable[]>([]);

  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<EvolutionMode>("manual");
  const [busy, setBusy] = useState(false);
  const [evolving, setEvolving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [inspectEvent, setInspectEvent] = useState<WorldlineEvent | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  const agentNames = useMemo(() => new Map(roster.map((r) => [r.id, r.name])), [roster]);
  const currentStep = useMemo(
    () => (timeline.length > 0 ? Math.max(...timeline.map((e) => e.sequence)) : 0),
    [timeline],
  );

  // ── Load the most recent session (if any) ────────────────────────────────

  const loadSessionData = useCallback(
    async (sel: { tenant_id: string; project_id: string }, sessionId: string) => {
      const [sess, tl, evs] = await Promise.all([
        fetchWorldlineSession(sel.project_id, sel.tenant_id, sessionId),
        fetchWorldlineTimeline(sel.project_id, sel.tenant_id, sessionId).catch(() => []),
        fetchWorldlineEvents(sel.project_id, sel.tenant_id, sessionId, WORLDLINE_CANDIDATE).catch(() => []),
      ]);
      setSession(sess);
      setTimeline(tl);
      setCandidates(evs);
      return sess;
    },
    [],
  );

  useEffect(() => {
    const sel = readWorldlineSelection(projectId);
    if (!sel) {
      setState({ status: "no-selection" });
      return;
    }
    setSelection(sel);
    let cancelled = false;
    (async () => {
      try {
        const token = await fetchCsrfToken().catch(() => null);
        const sessions = await fetchWorldlineSessions(sel.project_id, sel.tenant_id).catch(() => []);
        if (cancelled) return;
        setCsrfToken(token);
        // Resume the most recent session if one exists, else stay in 起点态.
        const latest = sessions[0];
        if (latest) {
          await loadSessionData(sel, latest.session_id);
          // Pull the cast for the roster (from the session's preparation).
          void fetchWorldlinePreparations(sel.project_id, sel.tenant_id)
            .then(async (preps) => {
              if (cancelled || preps.length === 0) return;
              const agents = await fetchWorldlinePreparedAgents(sel.project_id, sel.tenant_id, preps[0].prepare_id).catch(
                () => [],
              );
              if (cancelled) return;
              setRoster(
                agents.map((a) => ({
                  id: a.agent_id,
                  name: a.display_name,
                  role: a.role || a.status,
                  candidate: a.status === "candidate",
                })),
              );
            })
            .catch(() => {});
        }
        if (!cancelled) setState({ status: "ready" });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof WorldlineError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "世界线暂时读不出来，请重试。",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, loadSessionData, router]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleStart = useCallback(async () => {
    if (!selection || !csrfToken) return;
    const goalText = goal.trim();
    if (!goalText) {
      setActionError("先写一个推演目标，再启动整备。");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      const run = await startWorldlineSession(selection.project_id, selection.tenant_id, csrfToken, {
        goal: goalText,
      });
      // The run prepares the cast asynchronously; load whatever session landed.
      const sessions = await fetchWorldlineSessions(selection.project_id, selection.tenant_id).catch(() => []);
      const sess = sessions.find((s) => s.run_id === run.run_id) ?? sessions[0];
      if (sess) await loadSessionData(selection, sess.session_id);
      setGoal("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "启动整备失败，请重试。");
    } finally {
      setBusy(false);
    }
  }, [selection, csrfToken, goal, loadSessionData]);

  const handleStep = useCallback(async () => {
    if (!selection || !csrfToken || !session) return;
    setBusy(true);
    setEvolving(true);
    setActionError(null);
    try {
      await startWorldlineStep(selection.project_id, selection.tenant_id, csrfToken, session.session_id, {
        mode: mode === "manual" ? "manual" : "director",
      });
      await loadSessionData(selection, session.session_id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "推进失败，请重试。");
    } finally {
      setBusy(false);
      setEvolving(false);
    }
  }, [selection, csrfToken, session, mode, loadSessionData]);

  const handlePrimary = useCallback(() => {
    if (session) void handleStep();
    else void handleStart();
  }, [session, handleStep, handleStart]);

  const handleInjectVariable = useCallback(
    async (input: { name: string; description: string }) => {
      if (!selection || !csrfToken || !session) return;
      setActionError(null);
      try {
        const variable = await injectWorldlineVariable(
          selection.project_id,
          selection.tenant_id,
          csrfToken,
          session.session_id,
          { name: input.name, description: input.description, locked: false },
        );
        setVariables((prev) => [...prev, variable]);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "注入变量失败，请重试。");
      }
    },
    [selection, csrfToken, session],
  );

  const handleToggleVariableLock = useCallback((variable: { variable_id: string }) => {
    setVariables((prev) =>
      prev.map((v) => (v.variable_id === variable.variable_id ? { ...v, locked: !v.locked } : v)),
    );
  }, []);

  const handleAdoptCandidate = useCallback(
    async (event: WorldlineEvent) => {
      if (!selection || !csrfToken || !session) return;
      setBusy(true);
      setActionError(null);
      try {
        await adoptWorldlineEvent(selection.project_id, selection.tenant_id, csrfToken, event.event_id);
        await loadSessionData(selection, session.session_id);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "采纳失败，请重试。");
      } finally {
        setBusy(false);
      }
    },
    [selection, csrfToken, session, loadSessionData],
  );

  const handleEditCandidate = useCallback(
    async (event: WorldlineEvent, draft: string) => {
      if (!selection || !csrfToken) return;
      setActionError(null);
      try {
        await updateWorldlineEvent(selection.project_id, selection.tenant_id, csrfToken, event.event_id, {
          summary: draft,
        });
        setCandidates((prev) =>
          prev.map((c) => (c.event_id === event.event_id ? { ...c, summary: draft } : c)),
        );
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "保存修改失败，请重试。");
      }
    },
    [selection, csrfToken],
  );

  const handleRejectCandidate = useCallback((event: WorldlineEvent) => {
    // A rejected candidate simply leaves the queue; it never touches the timeline.
    setCandidates((prev) => prev.filter((c) => c.event_id !== event.event_id));
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────

  if (state.status === "loading") return <WorldlineSkeleton />;
  if (state.status === "no-selection") return <NoSelection onBack={() => router.push("/workspace")} />;
  if (state.status === "error") {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
        <h2 className="font-serif text-[22px] font-semibold text-ink">世界线暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">{state.message}</p>
      </div>
    );
  }

  const prepareStatus: PrepareStatus = session
    ? { label: "整备就绪", tone: "ready", detail: `会话 ${session.session_id.slice(0, 8)} · ${session.status}` }
    : { label: "待整备", tone: "working", detail: "填一个推演目标，启动第一次整备。" };

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        {/* 栏目眉 — compact栏目条 */}
        <WorkbenchMasthead
          eyebrow="世 界 线"
          title="演化时间线"
          tagline="单世界剧情推演：启动、变量注入与事件流。推演只产候选，采纳后才进正史。"
          aside={
            session ? (
              <span className="text-[12.5px] tabular-nums text-muted">
                {timeline.length} 段正史 · {candidates.length} 条候选
              </span>
            ) : undefined
          }
        />

        {actionError ? (
          <div className="shrink-0 border-b border-line bg-accent-wash px-6 py-2.5 text-[13px] text-accent">
            {actionError}
          </div>
        ) : null}

        {!session ? (
          /* 起点态 — a single goal prompt, centred like the Writer's empty state */
          <div className="flex flex-1 items-center justify-center px-8 py-16">
            <motion.div
              initial={fadeUp.initial}
              animate={fadeUp.animate}
              transition={{ duration: DUR.med, ease: EASE }}
              className="w-full max-w-[600px]"
            >
              <h2 className="text-center font-serif text-[24px] font-semibold text-ink">这一回，世界往哪走？</h2>
              <p className="mt-2 text-center text-[13.5px] text-muted">
                写下一个推演目标。整备会自动选好演员，你也可以稍后再调整。
              </p>
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                rows={3}
                placeholder="例如：如果顾临渊在第七步恢复记忆，他和谢无衍的关系会走向何方？"
                className="mt-6 w-full resize-none rounded-[14px] border border-line bg-panel px-5 py-4 font-serif text-[15px] leading-relaxed text-ink shadow-sm outline-none focus:border-accent/50"
              />
              <div className="mt-4 flex justify-center">
                <button
                  type="button"
                  onClick={handlePrimary}
                  disabled={busy || !csrfToken}
                  className="rounded-[12px] bg-accent px-8 py-3 text-[14.5px] font-medium text-panel shadow-lift transition-colors hover:bg-accent-strong disabled:opacity-60"
                >
                  {busy ? "整备中…" : "启动世界线整备"}
                </button>
              </div>
            </motion.div>
          </div>
        ) : (
          /* 推演态 — three columns + bottom run controls */
          <>
            <div className="flex min-h-0 flex-1 overflow-hidden">
              <WorldlinePrepareRail
                status={prepareStatus}
                roster={roster}
                variables={variables}
                selectedAgentId={selectedAgentId}
                onSelectAgent={(id) => setSelectedAgentId(id === selectedAgentId ? null : id)}
                onToggleVariableLock={handleToggleVariableLock}
              />

              {/* center: state banner + timeline */}
              <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
                <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
                  <div className="mx-auto max-w-[720px]">
                    <WorldlineStateBanner
                      session={session}
                      currentStep={currentStep}
                      variableNames={variables.filter((v) => v.locked).map((v) => v.name)}
                    />
                    <div className="mt-6">
                      <WorldlineTimeline
                        events={timelineEventsToWorldlineEvents(timeline, session.project_id)}
                        agents={agentNames}
                        onInspect={setInspectEvent}
                      />
                    </div>
                  </div>
                </div>
                <WorldlineRunControls
                  hasSession
                  busy={busy}
                  evolving={evolving}
                  mode={mode}
                  onModeChange={setMode}
                  onPrimary={handlePrimary}
                  onInjectVariable={handleInjectVariable}
                />
              </div>

              {/* right: candidate rail (or inspector overlay) */}
              <AnimatePresence mode="wait">
                {inspectEvent ? (
                  <motion.aside
                    key={inspectEvent.event_id}
                    initial={slideIn.initial}
                    animate={slideIn.animate}
                    exit={slideIn.exit}
                    transition={{ duration: DUR.med, ease: EASE }}
                    className="flex h-full w-[380px] shrink-0 flex-col overflow-y-auto border-l border-line bg-panel px-6 py-6 max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:z-40 max-lg:w-full max-lg:max-w-[420px] max-lg:shadow-panel"
                  >
                    <EventInspector event={inspectEvent} onClose={() => setInspectEvent(null)} />
                  </motion.aside>
                ) : (
                  <WorldlineCandidateRail
                    candidates={candidates}
                    busyId={busy ? undefined : null}
                    onAdopt={handleAdoptCandidate}
                    onEdit={handleEditCandidate}
                    onReject={handleRejectCandidate}
                  />
                )}
              </AnimatePresence>
            </div>
          </>
        )}
      </div>
    </MotionConfig>
  );
}

// ── helpers ─────────────────────────────────────────────────────────────────

/** Timeline records carry step as `sequence`; map them onto event cards. */
function timelineEventsToWorldlineEvents(timeline: WorldlineTimelineEvent[], projectId: string): WorldlineEvent[] {
  return timeline.map((t) => ({
    event_id: t.event_id,
    session_id: t.session_id,
    project_id: projectId,
    step: t.sequence,
    title: t.title,
    summary: t.summary,
    kind: t.kind,
    status: t.status,
    lifecycle: t.lifecycle,
    confidence: "",
    involved_agent_ids: [],
    state_changes: {},
    source_run_id: t.run_id,
    created_by: "",
    created_at: t.created_at,
    updated_at: t.created_at,
  }));
}

function EventInspector({ event, onClose }: { event: WorldlineEvent; onClose: () => void }) {
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-serif text-[18px] font-semibold leading-snug text-ink">{event.title}</h3>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-[6px] px-2 py-1 text-[12px] text-muted transition-colors hover:bg-paper hover:text-ink"
        >
          关闭
        </button>
      </div>
      <p className="mt-1 text-[11.5px] tracking-wide text-muted">
        第 {event.step} 步{event.kind ? ` · ${event.kind}` : ""} · {event.lifecycle === "canon" ? "正史" : "候选"}
      </p>
      <p className="mt-4 font-serif text-[13.5px] leading-[1.9] text-ink-soft">{event.summary}</p>
      {Object.keys(event.state_changes ?? {}).length > 0 ? (
        <div className="mt-5 border-t border-line-soft pt-4">
          <h4 className="text-[11.5px] font-medium tracking-[0.2em] text-accent">状态变化</h4>
          <dl className="mt-2.5 space-y-1.5">
            {Object.entries(event.state_changes).map(([key, value]) => (
              <div key={key} className="flex items-baseline justify-between gap-3 text-[12.5px]">
                <dt className="text-muted">{key}</dt>
                <dd className="min-w-0 truncate text-right text-ink-soft">{String(value)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </div>
  );
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
      <h2 className="font-serif text-[22px] font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">
        世界线需要知道你正在推演哪部作品。回到书架，挑一部作品再进来。
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

function WorldlineSkeleton() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-line-soft px-8 pb-5 pt-7">
        <div className="h-3 w-16 animate-pulse rounded bg-line-soft" />
        <div className="mt-3 h-7 w-44 animate-pulse rounded bg-line-soft" />
        <div className="mt-2 h-4 w-80 animate-pulse rounded bg-line-soft" />
      </div>
      <div className="flex flex-1 items-center justify-center">
        <div className="w-full max-w-[600px] space-y-4 px-8">
          <div className="h-6 w-2/3 animate-pulse rounded bg-line-soft" />
          <div className="h-24 w-full animate-pulse rounded bg-line-soft" />
          <div className="mx-auto h-11 w-40 animate-pulse rounded bg-line-soft" />
        </div>
      </div>
    </div>
  );
}
