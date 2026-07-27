"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";

import { fetchCsrfToken } from "@/lib/api/session";
import {
  adoptWorldlineEvent,
  fetchWorldlineEvents,
  fetchWorldlineGoalStart,
  fetchWorldlineGoalStarts,
  fetchWorldlinePreparedAgents,
  fetchWorldlinePreparations,
  fetchWorldlineSession,
  fetchWorldlineSessions,
  fetchWorldlineTimeline,
  fetchWorldlineVariables,
  injectWorldlineVariable,
  readWorldlineSelection,
  setWorldlineVariableLocked,
  startWorldlineGoalStart,
  startWorldlineStep,
  updateWorldlineEvent,
  WorldlineError,
} from "@/lib/api/worldline-client";
import type {
  WorldlineEvent,
  WorldlineGoalStart,
  WorldlineSession,
  WorldlineTimelineEvent,
  WorldlineVariable,
} from "@/lib/api/worldline-types";
import { WORLDLINE_CANDIDATE, WORLDLINE_CANON } from "@/lib/api/worldline-types";
import type { RosterCharacter } from "@/components/character";
import { Button } from "@/components/ui/button";

import { WorldlineCandidateRail } from "./worldline-candidate-rail";
import { WorldlinePrepareRail, type PrepareStatus } from "./worldline-prepare-rail";
import { WorldlineRunControls, type EvolutionMode } from "./worldline-run-controls";
import { WorldlineStateBanner } from "./worldline-state-banner";
import { WorldlineTimeline } from "./worldline-timeline";
import { DUR, EASE, useFadeUp, useSlideIn } from "@/lib/motion";
import { WorkbenchMasthead } from "@/components/workbench-masthead";
import { PanelRight } from "lucide-react";

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

/**
 * The Worldline (世界线) workbench — the 导演监视器. Three states on one route:
 * 起点态 (a goal prompt), 整备态 (the Pi cast planner decomposes the goal,
 * pulls assets from the 资产库, and prepares the cast), and 推演态 (a
 * three-column monitor: prepare rail / evolution timeline / candidate rail).
 * The timeline only ever shows confirmed canon; candidates wait in gold until
 * the author adopts them. Nothing here fabricates events — the backend drives
 * every card, and a missing backend renders an honest error.
 */
const GOAL_START_POLL_MS = 2000;
const GOAL_START_TIMEOUT_MS = 30 * 60 * 1000;
const STEP_POLL_MS = 2500;
const STEP_TIMEOUT_MS = 10 * 60 * 1000;
/** Terminal session statuses — a step has finished writing when the session settles here. */
const STEP_SETTLED_STATUSES = new Set(["paused", "ready", "failed", "completed", "cancelled"]);

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
  const [canonEvents, setCanonEvents] = useState<WorldlineEvent[]>([]);
  const [roster, setRoster] = useState<RosterCharacter[]>([]);
  const [variables, setVariables] = useState<WorldlineVariable[]>([]);

  const [goal, setGoal] = useState("");
  const [goalStart, setGoalStart] = useState<WorldlineGoalStart | null>(null);
  const [preparingAgents, setPreparingAgents] = useState<RosterCharacter[]>([]);
  const [mode, setMode] = useState<EvolutionMode>("manual");
  const [busy, setBusy] = useState(false);
  const [busyCandidateId, setBusyCandidateId] = useState<string | null>(null);
  const [evolving, setEvolving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [inspectEvent, setInspectEvent] = useState<WorldlineEvent | null>(null);
  // Candidate rail is inline at the wide band and a drawer below it.
  const [candidateRailOpen, setCandidateRailOpen] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const pendingVariableLocksRef = useRef<Set<string>>(new Set());

  // Resolve an involved_agent_ids entry (UUID, slug, or display name) to a
  // display name. The director writes slugs like "xu_qi_an"; the roster keys
  // agents by UUID — so we match by the roster's display names, which are unique.
  const agentNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of roster) {
      map.set(r.id, r.name);
      map.set(r.name, r.name);
    }
    return map;
  }, [roster]);
  const resolveAgentName = useCallback(
    (raw: string): string => {
      const key = raw.trim();
      if (!key) return "";
      const direct = agentNames.get(key);
      if (direct) return direct;
      // slug form (xu_qi_an / wang-bu-tou): match against roster display names by
      // shared CJK characters — reliable since prepared agents carry Chinese names.
      const latin = key.replace(/[_-]+/g, " ").trim().toLowerCase();
      for (const r of roster) {
        const name = r.name;
        if (!name) continue;
        if (name.toLowerCase() === latin) return name;
      }
      return "";
    },
    [agentNames, roster],
  );
  // The one public "第 X 步" is the domain step the backend reports on the
  // session (MAX(worldline_events.step)) — never the orchestration sequence,
  // which adoptions inflate without stepping the world.
  const currentStep = session?.current_step ?? 0;
  const preparing = !session && goalStart !== null && goalStart.status !== "failed";

  // ── Load the most recent session (if any) ────────────────────────────────

  const loadSessionData = useCallback(
    async (sel: { tenant_id: string; project_id: string }, sessionId: string) => {
      const [sess, tl, evs, canon, vars] = await Promise.all([
        fetchWorldlineSession(sel.project_id, sel.tenant_id, sessionId),
        fetchWorldlineTimeline(sel.project_id, sel.tenant_id, sessionId).catch(() => []),
        fetchWorldlineEvents(sel.project_id, sel.tenant_id, sessionId, WORLDLINE_CANDIDATE).catch(() => []),
        fetchWorldlineEvents(sel.project_id, sel.tenant_id, sessionId, WORLDLINE_CANON).catch(() => []),
        fetchWorldlineVariables(sel.project_id, sel.tenant_id, sessionId).catch(() => []),
      ]);
      setSession(sess);
      setTimeline(tl);
      setCandidates(evs);
      setCanonEvents(canon);
      setVariables((current) => {
        const local = new Map(current.map((variable) => [variable.variable_id, variable]));
        return vars.map((variable) =>
          pendingVariableLocksRef.current.has(variable.variable_id)
            ? local.get(variable.variable_id) ?? variable
            : variable,
        );
      });
      return sess;
    },
    [],
  );

  /** Pull the prepared cast for a session's preparation into the roster rail. */
  const loadRoster = useCallback(
    async (sel: { tenant_id: string; project_id: string }, prepareId?: string) => {
      let id = prepareId?.trim() ?? "";
      if (!id) {
        const preps = await fetchWorldlinePreparations(sel.project_id, sel.tenant_id).catch(() => []);
        id = preps[0]?.prepare_id ?? "";
      }
      if (!id) {
        setRoster([]);
        return;
      }
      const agents = await fetchWorldlinePreparedAgents(sel.project_id, sel.tenant_id, id).catch(() => []);
      setRoster(
        agents.map((a) => ({
          id: a.agent_id,
          name: a.display_name,
          role: a.role || a.status,
          candidate: a.status === "candidate",
        })),
      );
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
        const [sessions, goalStarts] = await Promise.all([
          fetchWorldlineSessions(sel.project_id, sel.tenant_id).catch(() => []),
          fetchWorldlineGoalStarts(sel.project_id, sel.tenant_id).catch(() => []),
        ]);
        if (cancelled) return;
        setCsrfToken(token);
        // Resume the most recent session if one exists, else stay in 起点态.
        const latest = sessions[0];
        if (latest) {
          await loadSessionData(sel, latest.session_id);
          void loadRoster(sel).catch(() => {});
        }
        if (!latest) {
          const resumable = goalStarts.find((item) => item.status !== "ready") ?? null;
          if (resumable) {
            setGoalStart(resumable);
            setGoal(resumable.goal ?? "");
          }
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
  }, [projectId, loadSessionData, loadRoster, router]);

  // ── Poll the goal-start run until the cast is ready (or it fails) ─────────
  //
  // The Pi orchestration walks queued → casting → preparing → starting →
  // ready. While it runs we surface the stage and the agents as they land in
  // the preparation, so the author watches the cast assemble from the 资产库.

  useEffect(() => {
    if (!selection || session || !goalStart || goalStart.status === "failed") return;
    const runId = goalStart.run_id;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const deadline = Date.now() + GOAL_START_TIMEOUT_MS;

    const tick = async () => {
      if (cancelled) return;
      try {
        const gs = await fetchWorldlineGoalStart(selection.project_id, selection.tenant_id, runId);
        if (cancelled) return;
        setGoalStart(gs);
        if (gs.status === "ready" && gs.session_id) {
          await loadSessionData(selection, gs.session_id);
          await loadRoster(selection, gs.prepare_id);
          return; // session landed — the poll loop ends
        }
        if (gs.status === "failed") {
          setActionError(gs.error_message || "整备失败了，请重试。");
          return;
        }
        if (gs.prepare_id) {
          const agents = await fetchWorldlinePreparedAgents(selection.project_id, selection.tenant_id, gs.prepare_id).catch(
            () => [],
          );
          if (!cancelled) {
            setPreparingAgents(
              agents.map((a) => ({
                id: a.agent_id,
                name: a.display_name,
                role: a.role || a.status,
                candidate: a.status === "candidate",
              })),
            );
          }
        }
      } catch {
        // transient read errors keep polling until the deadline
      }
      if (!cancelled && Date.now() < deadline) {
        timer = setTimeout(() => void tick(), GOAL_START_POLL_MS);
      } else if (!cancelled) {
        setGoalStart((prev) =>
          prev
            ? { ...prev, status: "failed", error_message: "整备超时了——选角或整备耗时过长，请重试。" }
            : prev,
        );
        setActionError("整备超时了——选角或整备耗时过长，请重试。");
      }
    };
    timer = setTimeout(() => void tick(), GOAL_START_POLL_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [selection, session, goalStart?.run_id, goalStart?.status, loadSessionData, loadRoster]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleStart = useCallback(
    async (resumeRunId?: string) => {
      if (!selection || !csrfToken) return;
      const goalText = resumeRunId ? (goalStart?.goal ?? goal).trim() : goal.trim();
      if (!goalText) {
        setActionError("先写一个推演目标，再启动整备。");
        return;
      }
      setBusy(true);
      setActionError(null);
      try {
        const run = await startWorldlineGoalStart(selection.project_id, selection.tenant_id, csrfToken, {
          goal: goalText,
          // 续传: re-admit the failed run under its own idempotency key so the
          // backend replays the same goal-start instead of admitting a new one.
          options: resumeRunId ? { resume_of: resumeRunId } : undefined,
        });
        setPreparingAgents([]);
        setGoalStart(run.status === "ready" && run.session_id ? null : run);
        if (run.status === "ready" && run.session_id) {
          await loadSessionData(selection, run.session_id);
          await loadRoster(selection, run.prepare_id);
        } else if (run.status === "failed") {
          setActionError(run.error_message || "启动整备失败，请重试。");
        } else {
          setGoal("");
        }
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "启动整备失败，请重试。");
      } finally {
        setBusy(false);
      }
    },
    [selection, csrfToken, goal, goalStart, loadSessionData, loadRoster],
  );

  const handleStep = useCallback(async () => {
    if (!selection || !csrfToken || !session) return;
    const sessionId = session.session_id;
    setBusy(true);
    setEvolving(true);
    setActionError(null);
    try {
      await startWorldlineStep(selection.project_id, selection.tenant_id, csrfToken, sessionId, {
        mode: mode === "manual" ? "manual" : "director",
      });
      // The step runs asynchronously (LLM director): poll the session until it
      // settles off running/queued, then load whatever candidates landed.
      const deadline = Date.now() + STEP_TIMEOUT_MS;
      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, STEP_POLL_MS));
        const current = await fetchWorldlineSession(selection.project_id, selection.tenant_id, sessionId);
        if (STEP_SETTLED_STATUSES.has(current.status)) {
          if (current.status === "failed") {
            setActionError("这一步推演失败了，请重试。");
          }
          break;
        }
        if (Date.now() >= deadline) {
          setActionError("推演耗时较长——结果出来后可刷新查看。");
          break;
        }
      }
      await loadSessionData(selection, sessionId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "推进失败，请重试。");
      await loadSessionData(selection, sessionId).catch(() => {});
    } finally {
      setBusy(false);
      setEvolving(false);
    }
  }, [selection, csrfToken, session, mode, loadSessionData]);

  const handlePrimary = useCallback(() => {
    if (session) void handleStep();
    else void handleStart();
  }, [session, handleStep, handleStart]);

  /** Inspect a timeline card: resolve an adoption card to the canon domain
   * event it adopted (agents/confidence/state changes) instead of showing the
   * orchestration placeholder. Clicking the open card again closes the panel. */
  const handleInspect = useCallback(
    (event: WorldlineEvent) => {
      setInspectEvent((current) =>
        current && current.event_id === event.event_id ? null : resolveInspectEvent(event, timeline, canonEvents),
      );
    },
    [timeline, canonEvents],
  );

  /** Names the event actually involves: resolved agent ids first, else roster
   * characters whose display name appears in the event text (the director's
   * involved_agent_ids are slugs that don't map back, so we fall back to what
   * the event itself says). */
  const involvedNamesFor = useCallback(
    (event: WorldlineEvent): string[] => {
      const resolved = (event.involved_agent_ids ?? []).map((id) => resolveAgentName(id)).filter(Boolean);
      if (resolved.length > 0) return [...new Set(resolved)];
      const text = `${event.title} ${event.summary}`;
      return roster.filter((r) => r.name && text.includes(r.name)).map((r) => r.name);
    },
    [resolveAgentName, roster],
  );

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

  /** Persist the lock (locked variables are hard constraints for the next
   * step). Optimistic flip; a failed PATCH rolls the flag back. */
  const handleToggleVariableLock = useCallback(
    async (variable: WorldlineVariable) => {
      if (!selection || !csrfToken || !session) return;
      const nextLocked = !variable.locked;
      pendingVariableLocksRef.current.add(variable.variable_id);
      setVariables((prev) =>
        prev.map((v) => (v.variable_id === variable.variable_id ? { ...v, locked: nextLocked } : v)),
      );
      try {
        const saved = await setWorldlineVariableLocked(
          selection.project_id,
          selection.tenant_id,
          csrfToken,
          session.session_id,
          variable.variable_id,
          nextLocked,
        );
        setVariables((prev) => prev.map((v) => (v.variable_id === saved.variable_id ? saved : v)));
      } catch (error) {
        setVariables((prev) =>
          prev.map((v) => (v.variable_id === variable.variable_id ? { ...v, locked: variable.locked } : v)),
        );
        setActionError(error instanceof Error ? error.message : "锁定变量失败，请重试。");
      } finally {
        pendingVariableLocksRef.current.delete(variable.variable_id);
      }
    },
    [selection, csrfToken, session],
  );

  const handleAdoptCandidate = useCallback(
    async (event: WorldlineEvent) => {
      if (!selection || !csrfToken || !session) return;
      setBusy(true);
      setBusyCandidateId(event.event_id);
      setActionError(null);
      try {
        await adoptWorldlineEvent(selection.project_id, selection.tenant_id, csrfToken, event.event_id);
        await loadSessionData(selection, session.session_id);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "采纳失败，请重试。");
      } finally {
        setBusy(false);
        setBusyCandidateId(null);
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
        <h2 className="font-serif text-xl font-semibold text-ink">世界线暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-sm text-muted">{state.message}</p>
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
          eyebrow="世界线"
          title="演化时间线"
          tagline="单世界剧情推演：启动、变量注入与事件流。推演只产候选，采纳后才进正史。"
          aside={
            session ? (
              <>
                <span className="text-caption tabular-nums text-muted">
                  {timeline.length} 段正史 · {candidates.length} 条候选
                </span>
                {/* Below the wide band the candidate rail is a drawer, so it
                    needs a way in. Hidden at wide, where it is already inline. */}
                <Button
                  variant="outline"
                  size="xs"
                  className="wide:hidden"
                  onClick={() => setCandidateRailOpen(true)}
                >
                  <PanelRight className="size-3.5" aria-hidden />
                  候选
                </Button>
              </>
            ) : undefined
          }
        />

        {actionError ? (
          <div className="shrink-0 border-b border-line bg-accent-wash px-6 py-2.5 text-sm text-accent">
            {actionError}
          </div>
        ) : null}

        {preparing && goalStart ? (
          /* 整备态 — the Pi cast planner is assembling the cast from the 资产库 */
          <GoalStartProgress
            goalStart={goalStart}
            agents={preparingAgents}
            busy={busy}
            onResume={() => void handleStart(goalStart.run_id)}
            onReset={() => {
              setGoalStart(null);
              setPreparingAgents([]);
              setActionError(null);
            }}
          />
        ) : !session ? (
          /* 起点态 — a single goal prompt, centred like the Writer's empty state */
          <div className="flex flex-1 items-center justify-center px-8 py-16">
            <motion.div
              initial={fadeUp.initial}
              animate={fadeUp.animate}
              transition={{ duration: DUR.med, ease: EASE }}
              className="w-full max-w-[600px]"
            >
              <h2 className="text-center font-serif text-xl font-semibold text-ink">这一回，世界往哪走？</h2>
              <p className="mt-2 text-center text-sm text-muted">
                写下一个推演目标。选角导演会拆解它，从资产库里选好演员并完成整备，你也可以稍后再调整。
              </p>
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                rows={3}
                placeholder="例如：如果顾临渊在第七步恢复记忆，他和谢无衍的关系会走向何方？"
                className="mt-6 w-full resize-none rounded-modal border border-line bg-panel px-5 py-4 font-serif text-md leading-relaxed text-ink shadow-hairline outline-none focus:border-accent/50"
              />
              <div className="mt-4 flex justify-center">
                <button
                  type="button"
                  onClick={handlePrimary}
                  disabled={busy || !csrfToken}
                  className="rounded-modal bg-accent px-8 py-3 text-base font-medium text-panel shadow-lift transition-colors hover:bg-accent-strong disabled:opacity-60"
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
                        events={timelineEventsToWorldlineEvents(timeline, session.project_id, canonEvents)}
                        agents={agentNames}
                        onInspect={handleInspect}
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
                    className="flex h-full w-rail-inspector shrink-0 flex-col overflow-y-auto border-l border-line bg-panel px-6 py-6 max-wide:fixed max-wide:inset-y-0 max-wide:right-0 max-wide:z-40 max-wide:w-full max-wide:max-w-[420px] max-wide:shadow-panel"
                  >
                    <EventInspector
                      event={inspectEvent}
                      involvedNames={involvedNamesFor(inspectEvent)}
                      onClose={() => setInspectEvent(null)}
                    />
                  </motion.aside>
                ) : (
                  <WorldlineCandidateRail
                    candidates={candidates}
                    busyId={busyCandidateId}
                    open={candidateRailOpen}
                    onClose={() => setCandidateRailOpen(false)}
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

const GOAL_START_STAGES: { key: string; label: string; hint: string }[] = [
  { key: "casting", label: "选角", hint: "拆解目标，从资产库挑选演员与素材" },
  { key: "preparing", label: "整备演员", hint: "为每位演员生成档案与就位状态" },
  { key: "starting", label: "建立会话", hint: "把整备好的世界线装订成一次推演" },
];

/** The 整备态 panel — stage ladder + assembling roster + rationale, or failure. */
function GoalStartProgress({
  goalStart,
  agents,
  busy,
  onResume,
  onReset,
}: {
  goalStart: WorldlineGoalStart;
  agents: RosterCharacter[];
  busy: boolean;
  onResume: () => void;
  onReset: () => void;
}) {
  const failed = goalStart.status === "failed";
  const stageIndex = goalStartStageIndex(goalStart.status);
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto px-8 py-12">
      <div className="w-full max-w-[560px]">
        <h2 className="text-center font-serif text-xl font-semibold text-ink">
          {failed ? "整备中断了" : "选角导演正在整备这条世界线"}
        </h2>
        {goalStart.goal ? (
          <p className="mt-2 text-center font-serif text-sm leading-relaxed text-muted">
            「{goalStart.goal}」
          </p>
        ) : null}

        {/* stage ladder */}
        <ol className="mt-8 space-y-1">
          {GOAL_START_STAGES.map((stage, index) => {
            const done = !failed && index < stageIndex;
            const active = !failed && index === stageIndex;
            return (
              <li key={stage.key} className="flex items-start gap-3 rounded-panel px-3 py-2.5">
                <span
                  aria-hidden
                  className={`mt-1.5 size-2 shrink-0 rounded-full ${
 done ? "bg-accent" : active ? "animate-pulse bg-gold" : "bg-line"
                  }`}
                />
                <div className="min-w-0">
                  <p className={`text-sm font-medium ${done || active ? "text-ink" : "text-muted"}`}>
                    {stage.label}
                    {done ? <span className="ml-2 text-caption font-normal text-accent">已完成</span> : null}
                    {active ? <span className="ml-2 text-caption font-normal text-gold">进行中…</span> : null}
                  </p>
                  <p className="mt-0.5 text-caption text-muted">{stage.hint}</p>
                </div>
              </li>
            );
          })}
        </ol>

        {/* agents as they land in the preparation */}
        {agents.length > 0 ? (
          <div className="mt-4 rounded-modal border border-line bg-panel px-4 py-3.5">
            <p className="text-caption font-medium tracking-label text-muted">已就位演员</p>
            <ul className="mt-2 space-y-1.5">
              {agents.map((agent) => (
                <li key={agent.id} className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate font-serif text-ink">{agent.name}</span>
                  {agent.role ? <span className="shrink-0 text-caption text-muted">{agent.role}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* the cast planner's rationale, once committed */}
        {goalStart.rationale ? (
          <p className="mt-4 rounded-modal border border-line-soft bg-paper/60 px-4 py-3 font-serif text-caption text-ink-soft">
            <span className="text-muted">选角思路 · </span>
            {goalStart.rationale}
          </p>
        ) : null}

        {failed ? (
          <div className="mt-8 text-center">
            <p className="text-sm text-accent">{goalStart.error_message || "整备失败了，请重试。"}</p>
            <div className="mt-4 flex justify-center gap-3">
              <button
                type="button"
                onClick={onResume}
                disabled={busy}
                className="rounded-panel bg-accent px-6 py-2.5 text-sm font-medium text-panel shadow-hairline transition-colors hover:bg-accent-strong disabled:opacity-60"
              >
                {busy ? "续传中…" : "续传整备"}
              </button>
              <button
                type="button"
                onClick={onReset}
                disabled={busy}
                className="rounded-panel border border-line bg-panel px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-60"
              >
                换个目标
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** queued → casting → preparing → starting → ready, mapped onto the 3-stage ladder. */
function goalStartStageIndex(status: string): number {
  switch (status) {
    case "casting":
      return 0;
    case "preparing":
      return 1;
    case "starting":
      return 2;
    case "ready":
      return GOAL_START_STAGES.length;
    default:
      return 0; // queued — the cast stage is about to start
  }
}

/** Map one timeline row onto an event card. Adoption rows surface the adopted
 * domain event's title/summary (via the backend's event_ref_id join) instead of
 * the orchestration bookkeeping text. The card's step is the DOMAIN step of the
 * referenced event — the timeline's own `sequence` counts orchestration rows
 * (an adoption bumps it without stepping the world), so it never feeds "第 N 步". */
function timelineEventToWorldlineEvent(
  t: WorldlineTimelineEvent,
  projectId: string,
  canonById: ReadonlyMap<string, WorldlineEvent>,
): WorldlineEvent {
  const isAdoption = t.kind === "event_adoption" || Boolean(t.event_ref_id);
  const adopted = isAdoption && t.event_ref_id?.trim() ? canonById.get(t.event_ref_id) : undefined;
  return {
    event_id: t.event_ref_id?.trim() ? t.event_ref_id : t.event_id,
    session_id: t.session_id,
    project_id: projectId,
    step: adopted?.step ?? 0,
    title: adopted?.title ?? (isAdoption && t.adopted_title?.trim() ? t.adopted_title : t.title),
    summary: adopted?.summary ?? (isAdoption && t.adopted_summary?.trim() ? t.adopted_summary : t.summary),
    kind: t.kind,
    status: t.status,
    lifecycle: t.lifecycle,
    event_type: t.event_type,
    confidence: "",
    involved_agent_ids: [],
    state_changes: {},
    source_run_id: t.run_id,
    created_by: "",
    created_at: t.created_at,
    updated_at: t.created_at,
  };
}

function timelineEventsToWorldlineEvents(
  timeline: WorldlineTimelineEvent[],
  projectId: string,
  canonEvents: WorldlineEvent[],
): WorldlineEvent[] {
  const canonById = new Map(canonEvents.map((e) => [e.event_id, e] as const));
  return timeline.map((t) => timelineEventToWorldlineEvent(t, projectId, canonById));
}

/** Resolve the full domain event for the inspector: an adoption card looks up
 * the canon event it adopted (so the inspector shows agents/confidence/state
 * changes); anything else is shown as-is. */
function resolveInspectEvent(
  event: WorldlineEvent,
  timeline: WorldlineTimelineEvent[],
  canonEvents: WorldlineEvent[],
): WorldlineEvent {
  const row = timeline.find((t) => t.event_ref_id?.trim() && t.event_ref_id === event.event_id);
  const canonById = canonEvents.find((e) => e.event_id === event.event_id);
  if (canonById) return { ...canonById, event_type: row?.event_type ?? event.event_type };
  return event;
}

function EventInspector({
  event,
  involvedNames,
  onClose,
}: {
  event: WorldlineEvent;
  involvedNames: string[];
  onClose: () => void;
}) {
  const canon = event.lifecycle === "canon" || event.lifecycle === "canon_reference" || event.status === "canon";
  const stateChanges = event.state_changes ?? {};
  const stateSummary = typeof stateChanges.summary === "string" ? stateChanges.summary.trim() : "";
  const stateEntries = Object.entries(stateChanges).filter(
    ([key]) => !["summary", "model_id", "mode", "source_step_index", "source_workflow_type"].includes(key),
  );
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-serif text-lg font-semibold leading-snug text-ink">{event.title || "未命名事件"}</h3>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-control px-2 py-1 text-caption text-muted transition-colors hover:bg-paper hover:text-ink"
        >
          关闭
        </button>
      </div>
      <p className="mt-1 text-caption tracking-wide text-muted">
        {event.step > 0 ? `第 ${event.step} 步` : "整备"}
        {event.kind ? ` · ${event.kind}` : ""} · {canon ? "正史" : "候选"}
      </p>
      {event.summary ? (
        <p className="mt-4 font-serif text-sm text-ink-soft">{event.summary}</p>
      ) : null}

      {involvedNames.length > 0 || event.confidence ? (
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line-soft pt-4">
          {involvedNames.length > 0 ? (
            <div>
              <h4 className="text-caption font-medium tracking-label text-muted">涉及角色</h4>
              <p className="mt-1.5 font-serif text-sm text-ink-soft">{involvedNames.join("、")}</p>
            </div>
          ) : null}
          {event.confidence ? (
            <div>
              <h4 className="text-caption font-medium tracking-label text-muted">置信度</h4>
              <p className="mt-1.5 text-sm tabular-nums text-ink-soft">{event.confidence}</p>
            </div>
          ) : null}
        </div>
      ) : null}

      {stateSummary || stateEntries.length > 0 ? (
        <div className="mt-5 border-t border-line-soft pt-4">
          <h4 className="text-caption font-medium tracking-label text-muted">状态变化</h4>
          {stateSummary ? (
            <p className="mt-2 font-serif text-sm text-ink-soft">{stateSummary}</p>
          ) : null}
          {stateEntries.length > 0 ? (
            <dl className="mt-2.5 space-y-1.5">
              {stateEntries.map(([key, value]) => (
                <div key={key} className="flex items-baseline justify-between gap-3 text-caption">
                  <dt className="text-muted">{key}</dt>
                  <dd className="min-w-0 truncate text-right text-ink-soft">{String(value)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
      <h2 className="font-serif text-xl font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-sm text-muted">
        世界线需要知道你正在推演哪部作品。回到书架，挑一部作品再进来。
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

function WorldlineSkeleton() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-line-soft px-8 pb-5 pt-7">
        <div className="h-3 w-16 animate-pulse rounded-control bg-line-soft" />
        <div className="mt-3 h-7 w-44 animate-pulse rounded-control bg-line-soft" />
        <div className="mt-2 h-4 w-80 animate-pulse rounded-control bg-line-soft" />
      </div>
      <div className="flex flex-1 items-center justify-center">
        <div className="w-full max-w-[600px] space-y-4 px-8">
          <div className="h-6 w-2/3 animate-pulse rounded-control bg-line-soft" />
          <div className="h-24 w-full animate-pulse rounded-control bg-line-soft" />
          <div className="mx-auto h-11 w-40 animate-pulse rounded-control bg-line-soft" />
        </div>
      </div>
    </div>
  );
}
