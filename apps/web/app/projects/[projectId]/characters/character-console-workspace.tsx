"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { MotionConfig } from "motion/react";

import { fetchCsrfToken } from "@/lib/api/session";
import {
  adoptCharacterProposal,
  appendCharacterTurn,
  CharacterConsoleError,
  convertInteractionToChapterDraft,
  createCharacterInteraction,
  fetchCharacterInteractions,
  fetchCharacterProposals,
  fetchCharacterTurns,
  readCharacterConsoleSelection,
  startCharacterDialogue,
  updateCharacterInteractionStatus,
} from "@/lib/api/character-console-client";
import type {
  CharacterInteraction,
  CharacterProposal,
  CharacterTurn,
  TurnKind,
} from "@/lib/api/character-console-types";
import { fetchWorldlinePreparedAgents, fetchWorldlinePreparations, fetchWorldlineSessions } from "@/lib/api/worldline-client";
import type { WorldlineSession } from "@/lib/api/worldline-types";
import { CharacterDossierPanel, type RosterCharacter } from "@/components/character";

import { CharacterComposer } from "./character-composer";
import { CharacterDescend, type DescendDraft } from "./character-descend";
import { CharacterSceneStream } from "./character-scene-stream";
import { CharacterSessionRail } from "./character-session-rail";
import { WorkbenchMasthead } from "@/components/workbench-masthead";

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

/**
 * The Character Console (角色控制) workbench — the 第一人称舞台. Two states on
 * one route: 降临态 (descend into a worldline session as one character) and
 * 舞台态 (the scene stream + composer + dossier). It reads and writes through
 * the character-interaction endpoints; proposals stay gold candidates until
 * the author adopts them, and 转写为章节草稿 shows "已排队", never a false
 * claim that the draft exists.
 */
export function CharacterConsoleWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<{ tenant_id: string; project_id: string } | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  const [sessions, setSessions] = useState<WorldlineSession[]>([]);
  const [roster, setRoster] = useState<RosterCharacter[]>([]);
  const [interactions, setInteractions] = useState<CharacterInteraction[]>([]);
  const [active, setActive] = useState<CharacterInteraction | null>(null);
  const [turns, setTurns] = useState<CharacterTurn[]>([]);
  const [proposals, setProposals] = useState<CharacterProposal[]>([]);

  const [descendDraft, setDescendDraft] = useState<DescendDraft>({ sessionId: null, agentId: null });
  const [descending, setDescending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const agentNames = useMemo(() => new Map(roster.map((r) => [r.id, r.name])), [roster]);
  const activeAgent = active ? roster.find((r) => r.id === active.pov_agent_id) ?? null : null;

  // ── Load sessions, roster, interactions ───────────────────────────────────

  useEffect(() => {
    const sel = readCharacterConsoleSelection(projectId);
    if (!sel) {
      setState({ status: "no-selection" });
      return;
    }
    setSelection(sel);
    let cancelled = false;
    (async () => {
      try {
        const token = await fetchCsrfToken().catch(() => null);
        const [sess, ints] = await Promise.all([
          fetchWorldlineSessions(sel.project_id, sel.tenant_id).catch(() => []),
          fetchCharacterInteractions(sel.project_id, sel.tenant_id).catch(() => []),
        ]);
        if (cancelled) return;
        setCsrfToken(token);
        setSessions(sess);
        setInteractions(ints);
        // Pull the cast once for the descend roster + dossier names.
        if (sess.length > 0) {
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
        if (error instanceof CharacterConsoleError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "角色控制暂时读不出来，请重试。",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, router]);

  // ── Load an interaction's turns + proposals ───────────────────────────────

  const openInteraction = useCallback(
    async (interaction: CharacterInteraction) => {
      if (!selection) return;
      setActive(interaction);
      setTurns([]);
      setProposals([]);
      setActionError(null);
      try {
        const [t, p] = await Promise.all([
          fetchCharacterTurns(selection.project_id, selection.tenant_id, interaction.interaction_id).catch(() => []),
          fetchCharacterProposals(selection.project_id, selection.tenant_id, interaction.interaction_id).catch(() => []),
        ]);
        setTurns(t);
        setProposals(p.filter((prop) => prop.lifecycle !== "canon"));
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "这段互动暂时读不出来，请重试。");
      }
    },
    [selection],
  );

  // ── Descend ───────────────────────────────────────────────────────────────

  const handleDescend = useCallback(async () => {
    if (!selection || !csrfToken || !descendDraft.sessionId || !descendDraft.agentId) return;
    const agent = roster.find((r) => r.id === descendDraft.agentId);
    setDescending(true);
    setActionError(null);
    try {
      const interaction = await createCharacterInteraction(selection.project_id, selection.tenant_id, csrfToken, {
        worldline_session_id: descendDraft.sessionId,
        anchor_type: "current",
        anchor_id: descendDraft.sessionId,
        pov_agent_id: descendDraft.agentId,
        mode: "first_person",
        title: agent ? `我，${agent.name}` : "第一人称互动",
      });
      setInteractions((prev) => [interaction, ...prev]);
      setDescendDraft({ sessionId: null, agentId: null });
      await openInteraction(interaction);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "降临失败，请重试。");
    } finally {
      setDescending(false);
    }
  }, [selection, csrfToken, descendDraft, roster, openInteraction]);

  // ── Send a turn + get the reaction ────────────────────────────────────────

  const handleSend = useCallback(
    async (kind: TurnKind, text: string) => {
      if (!selection || !csrfToken || !active || sending) return;
      setSending(true);
      setActionError(null);
      try {
        const myTurn = await appendCharacterTurn(selection.project_id, selection.tenant_id, csrfToken, active.interaction_id, {
          actor_type: "user",
          actor_id: active.pov_agent_id,
          turn_kind: kind,
          summary: text,
        });
        setTurns((prev) => [...prev, myTurn]);
        // Ask the world for its reaction, then fold it into the stream.
        const reaction = await startCharacterDialogue(selection.project_id, selection.tenant_id, csrfToken, active.interaction_id, {
          in_response_to: myTurn.turn_id,
        }).catch(() => null);
        if (reaction) setTurns((prev) => [...prev, reaction]);
        // New proposals may have arrived with the reaction.
        const next = await fetchCharacterProposals(selection.project_id, selection.tenant_id, active.interaction_id).catch(
          () => [],
        );
        setProposals(next.filter((prop) => prop.lifecycle !== "canon"));
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "没能送出，请重试。");
      } finally {
        setSending(false);
      }
    },
    [selection, csrfToken, active, sending],
  );

  // ── Proposal adoption ─────────────────────────────────────────────────────

  const handleAdoptProposal = useCallback(
    async (proposal: CharacterProposal) => {
      if (!selection || !csrfToken || !active) return;
      setActionError(null);
      try {
        await adoptCharacterProposal(
          selection.project_id,
          selection.tenant_id,
          csrfToken,
          active.interaction_id,
          proposal.asset_id,
        );
        setProposals((prev) => prev.filter((p) => p.asset_id !== proposal.asset_id));
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "采纳失败，请重试。");
      }
    },
    [selection, csrfToken, active],
  );

  const handleRejectProposal = useCallback((proposal: CharacterProposal) => {
    setProposals((prev) => prev.filter((p) => p.asset_id !== proposal.asset_id));
  }, []);

  // ── Save / handoff ────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    if (!selection || !csrfToken || !active) return;
    setBusy(true);
    setActionError(null);
    try {
      const updated = await updateCharacterInteractionStatus(
        selection.project_id,
        selection.tenant_id,
        csrfToken,
        active.interaction_id,
        "saved",
      );
      setActive(updated);
      setInteractions((prev) => prev.map((i) => (i.interaction_id === updated.interaction_id ? updated : i)));
      setNotice("互动已保存。");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  }, [selection, csrfToken, active]);

  const handleResume = useCallback(async () => {
    if (!selection || !csrfToken || !active) return;
    setBusy(true);
    setActionError(null);
    try {
      const updated = await updateCharacterInteractionStatus(
        selection.project_id,
        selection.tenant_id,
        csrfToken,
        active.interaction_id,
        "active",
      );
      setActive(updated);
      setInteractions((prev) => prev.map((i) => (i.interaction_id === updated.interaction_id ? updated : i)));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "恢复互动失败，请重试。");
    } finally {
      setBusy(false);
    }
  }, [selection, csrfToken, active]);

  const handleConvertToDraft = useCallback(async () => {
    if (!selection || !csrfToken || !active) return;
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      await convertInteractionToChapterDraft(selection.project_id, selection.tenant_id, csrfToken, active.interaction_id);
      // Honest handoff: the run is queued, the draft is not yet written.
      setNotice("已排队交给写作台转写。草稿写好后会出现在写作台里。");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "转写排队失败，请重试。");
    } finally {
      setBusy(false);
    }
  }, [selection, csrfToken, active]);

  // ── Render ────────────────────────────────────────────────────────────────

  if (state.status === "loading") return <ConsoleSkeleton />;
  if (state.status === "no-selection") return <NoSelection onBack={() => router.push("/workspace")} />;
  if (state.status === "error") {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
        <h2 className="font-serif text-[22px] font-semibold text-ink">角色控制暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">{state.message}</p>
      </div>
    );
  }

  const inStage = active !== null;
  // Replay （回放）: a saved or archived interaction is read-only — the composer
  // hides and the stage becomes a script you read, until you resume it.
  const isReplay = inStage && active.status !== "active";

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        {/* 栏目眉 — compact栏目条 */}
        <WorkbenchMasthead
          eyebrow="角 色 控 制"
          title="互动舞台"
          tagline="以第一人称进入角色，在当前世界节点互动写作。互动只产候选，采纳后才沉淀。"
          aside={
            inStage && activeAgent ? (
              <span className="font-serif text-[13px] text-ink-soft">我，{activeAgent.name}</span>
            ) : undefined
          }
        />

        {actionError ? (
          <div className="shrink-0 border-b border-line bg-accent-wash px-6 py-2.5 text-[13px] text-accent">
            {actionError}
          </div>
        ) : null}
        {notice ? (
          <div className="shrink-0 border-b border-line-soft bg-panel px-6 py-2.5 text-[13px] text-ink-soft">
            {notice}
          </div>
        ) : null}

        {!inStage ? (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <CharacterDescend
              sessions={sessions}
              roster={roster}
              draft={descendDraft}
              busy={descending}
              onChange={setDescendDraft}
              onConfirm={handleDescend}
            />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="flex min-h-0 flex-1 overflow-hidden">
              <CharacterSessionRail
                interactions={interactions}
                activeId={active.interaction_id}
                agentNames={agentNames}
                onSelect={(i) => void openInteraction(i)}
                onNewDescend={() => setActive(null)}
              />

              {/* center: scene stream + composer (hidden in 回放) */}
              <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
                {isReplay ? (
                  <div className="shrink-0 border-b border-line-soft bg-paper/60 px-6 py-2 text-center text-[12px] tracking-wide text-muted">
                    回放 · 这段互动已{active.status === "saved" ? "保存" : "归档"}，只能阅读
                  </div>
                ) : null}
                <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
                  <div className="mx-auto max-w-[720px]">
                    <CharacterSceneStream
                      turns={turns}
                      proposals={isReplay ? [] : proposals}
                      onAdoptProposal={handleAdoptProposal}
                      onRejectProposal={handleRejectProposal}
                    />
                  </div>
                </div>
                {!isReplay ? (
                  <CharacterComposer disabled={!csrfToken} busy={sending} onSend={handleSend} />
                ) : null}
              </div>

              {/* right: dossier */}
              <aside className="hidden h-full w-[360px] shrink-0 overflow-hidden border-l border-line bg-panel lg:block">
                <CharacterDossierPanel
                  name={activeAgent?.name ?? "角色"}
                  profile={{ role: activeAgent?.role, status: active.status === "active" ? "进行中" : active.status }}
                  candidate={activeAgent?.candidate}
                />
              </aside>
            </div>

            {/* bottom: save + handoff (or resume in 回放) */}
            <div className="flex shrink-0 items-center gap-3 border-t border-line bg-panel px-6 py-3">
              {isReplay ? (
                <>
                  <span className="text-[12.5px] text-muted">想接着写？恢复这段互动就能继续。</span>
                  <button
                    type="button"
                    onClick={handleResume}
                    disabled={busy}
                    className="rounded-[10px] border border-line bg-panel px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50"
                  >
                    继续互动
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={busy}
                  className="rounded-[10px] border border-line bg-panel px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50"
                >
                  保存互动
                </button>
              )}
              <button
                type="button"
                onClick={handleConvertToDraft}
                disabled={busy || turns.length === 0}
                className="ml-auto rounded-[10px] bg-accent px-5 py-2 text-[13px] font-medium text-panel shadow-sm transition-colors hover:bg-accent-strong disabled:opacity-50"
              >
                转写为章节草稿 → 写作台
              </button>
            </div>
          </div>
        )}
      </div>
    </MotionConfig>
  );
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
      <h2 className="font-serif text-[22px] font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">
        角色控制需要知道你正在写哪部作品。回到书架，挑一部作品再进来。
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

function ConsoleSkeleton() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-line-soft px-8 pb-5 pt-7">
        <div className="h-3 w-20 animate-pulse rounded bg-line-soft" />
        <div className="mt-3 h-7 w-40 animate-pulse rounded bg-line-soft" />
        <div className="mt-2 h-4 w-80 animate-pulse rounded bg-line-soft" />
      </div>
      <div className="flex flex-1 items-center justify-center">
        <div className="w-full max-w-[680px] space-y-4 px-8">
          <div className="h-4 w-1/3 animate-pulse rounded bg-line-soft" />
          <div className="h-16 w-full animate-pulse rounded bg-line-soft" />
          <div className="h-16 w-full animate-pulse rounded bg-line-soft" />
        </div>
      </div>
    </div>
  );
}
