"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";
import { CharacterRoster, CharacterSeal, type RosterCharacter } from "@/components/character";
import type { WorldlineSession } from "@/lib/api/worldline-types";
import { DUR, EASE, useFadeUp } from "./character-motion";

/**
 * The 降临态 — a three-step in-page descent (not a wizard modal). Pick the
 * worldline session to stand in, pick the character to become, then confirm the
 * descend node. The character seal follows you onto the stage so "I am this
 * person" stays visually anchored.
 */

export type DescendDraft = {
  sessionId: string | null;
  agentId: string | null;
};

export function CharacterDescend({
  sessions,
  roster,
  draft,
  busy = false,
  onChange,
  onConfirm,
}: {
  sessions: WorldlineSession[];
  roster: RosterCharacter[];
  draft: DescendDraft;
  busy?: boolean;
  onChange: (draft: DescendDraft) => void;
  onConfirm: () => void;
}) {
  const fadeUp = useFadeUp();
  const step = draft.sessionId ? (draft.agentId ? 3 : 2) : 1;
  const chosen = roster.find((r) => r.id === draft.agentId) ?? null;

  if (sessions.length === 0) {
    return (
      <motion.div
        initial={fadeUp.initial}
        animate={fadeUp.animate}
        transition={{ duration: DUR.med, ease: EASE }}
        className="flex h-full flex-col items-center justify-center px-8 py-16 text-center"
      >
        <p className="font-serif text-[20px] font-semibold text-ink">还没有可降临的世界</p>
        <p className="mt-2 max-w-[360px] text-[13.5px] leading-relaxed text-muted">
          角色控制建立在世界线之上。先去「世界线」跑一段推演，再回来代入角色。
        </p>
      </motion.div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[680px] px-8 py-10">
      {/* step indicator */}
      <ol className="mb-8 flex items-center justify-center gap-2 text-[12px] text-muted">
        {["选世界", "选角色", "确认降临"].map((label, i) => (
          <li key={label} className="flex items-center gap-2">
            <span
              className={cn(
                "grid size-5 place-items-center rounded-full text-[10.5px] font-medium",
                step > i ? "bg-accent text-panel" : "border border-line text-muted",
              )}
            >
              {i + 1}
            </span>
            <span className={step > i ? "text-ink" : ""}>{label}</span>
            {i < 2 ? <span className="text-line">—</span> : null}
          </li>
        ))}
      </ol>

      {/* step 1: session */}
      <DescendSection number={1} title="站在哪个世界里" done={Boolean(draft.sessionId)}>
        <ul className="space-y-2">
          {sessions.map((session) => (
            <li key={session.session_id}>
              <button
                type="button"
                onClick={() => onChange({ sessionId: session.session_id, agentId: draft.agentId })}
                className={cn(
                  "w-full rounded-[12px] border px-4 py-3 text-left transition-colors",
                  draft.sessionId === session.session_id
                    ? "border-accent/50 bg-accent-wash"
                    : "border-line bg-panel hover:border-accent/30",
                )}
              >
                <p className="font-serif text-[14px] font-medium text-ink">
                  {session.goal_summary || `会话 ${session.session_id.slice(0, 8)}`}
                </p>
                <p className="mt-0.5 text-[11.5px] text-muted">{session.status}</p>
              </button>
            </li>
          ))}
        </ul>
      </DescendSection>

      {/* step 2: character */}
      {draft.sessionId ? (
        <DescendSection number={2} title="成为谁" done={Boolean(draft.agentId)}>
          <CharacterRoster
            characters={roster}
            mode="single"
            selectedIds={new Set(draft.agentId ? [draft.agentId] : [])}
            onToggle={(id) => onChange({ ...draft, agentId: id === draft.agentId ? null : id })}
            emptyHint="这个世界还没有可扮演的角色"
          />
        </DescendSection>
      ) : null}

      {/* step 3: confirm */}
      {draft.sessionId && chosen ? (
        <motion.div
          initial={fadeUp.initial}
          animate={fadeUp.animate}
          transition={{ duration: DUR.med, ease: EASE }}
          className="mt-8 rounded-[14px] border border-line bg-panel p-6 text-center shadow-lift"
        >
          <div className="flex justify-center">
            <CharacterSeal name={chosen.name} size="xl" />
          </div>
          <h3 className="mt-4 font-serif text-[20px] font-semibold text-ink">我，{chosen.name}</h3>
          <p className="mt-1.5 text-[13px] text-muted">即将降临到当前世界节点，以第一人称开始互动。</p>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="mt-5 rounded-[12px] bg-accent px-8 py-3 text-[14px] font-medium text-panel shadow-sm transition-colors hover:bg-accent-strong disabled:opacity-60"
          >
            {busy ? "降临中…" : "确认降临"}
          </button>
        </motion.div>
      ) : null}
    </div>
  );
}

function DescendSection({
  number,
  title,
  done,
  children,
}: {
  number: number;
  title: string;
  done: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <div className="mb-3 flex items-baseline gap-2.5">
        <span className="font-brush text-[18px] leading-none text-accent">{["一", "二", "三"][number - 1]}</span>
        <h3 className="font-serif text-[16px] font-semibold text-ink">{title}</h3>
        {done ? <span className="text-[11px] text-accent">已选</span> : null}
      </div>
      {children}
    </section>
  );
}
