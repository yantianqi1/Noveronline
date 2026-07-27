"use client";

import { motion } from "motion/react";
import { CandidateReviewCard } from "@/components/character";
import type { CharacterProposal, CharacterTurn } from "@/lib/api/character-console-types";
import { DUR, EASE, useFadeUp } from "@/lib/motion";

/**
 * The scene stream — the soul of the Character Console. A first-person script
 * that reads like a page being written, not a chat log:
 *   · system / descend notes  — centred, muted stage directions
 *   · my turns (我说/我做/…)   — vermilion-tinted bubbles, right-aligned
 *   · world / agent reactions — serif novel paragraphs, left-aligned, no bubble
 *   · proposals               — gold candidate cards floated into the flow
 * Three voices, one glance tells them apart.
 */

const MY_TURN_LABELS: Record<string, string> = {
  say: "我说",
  do: "我做",
  think: "我内心",
  influence: "我想影响",
};

function isMyTurn(turn: CharacterTurn): boolean {
  return turn.actor_type === "user" || turn.actor_type === "author";
}

function isSystemTurn(turn: CharacterTurn): boolean {
  return turn.actor_type === "system" || turn.turn_kind === "system";
}

export function CharacterSceneStream({
  turns,
  proposals = [],
  streamingBody,
  onAdoptProposal,
  onRejectProposal,
  proposalBusyId,
}: {
  turns: CharacterTurn[];
  proposals?: CharacterProposal[];
  /** Live streaming reaction text (typewriter), shown before it settles. */
  streamingBody?: string;
  onAdoptProposal?: (proposal: CharacterProposal) => void;
  onRejectProposal?: (proposal: CharacterProposal) => void;
  proposalBusyId?: string | null;
}) {
  const fadeUp = useFadeUp();

  if (turns.length === 0 && !streamingBody) {
    return (
      <motion.div
        initial={fadeUp.initial}
        animate={fadeUp.animate}
        transition={{ duration: DUR.med, ease: EASE }}
        className="flex h-full flex-col items-center justify-center px-8 py-16 text-center"
      >
        <p className="font-serif text-lg font-medium text-ink">舞台还空着</p>
        <p className="mt-1.5 max-w-[300px] text-sm leading-relaxed text-muted">
          此刻，你想让 TA 做什么？说一句、做一件事，世界会回应你。
        </p>
      </motion.div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {turns.map((turn, index) => (
        <SceneTurn key={turn.turn_id} turn={turn} index={index} />
      ))}

      {/* live streaming reaction */}
      {streamingBody ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
          <div className="max-w-[680px]">
            <p className="font-serif text-md text-ink-soft">
              {streamingBody}
              <span className="ml-0.5 inline-block h-[1.1em] w-[2px] animate-pulse bg-accent align-middle" />
            </p>
          </div>
        </motion.div>
      ) : null}

      {/* proposals floated into the flow as gold candidate cards */}
      {proposals.length > 0 ? (
        <div className="flex flex-col gap-3 border-t border-line-soft pt-5">
          {proposals.map((proposal) => (
            <CandidateReviewCard
              key={proposal.asset_id}
              title={proposal.title}
              summary={proposal.summary}
              sourceLabel={proposal.category ? `提案 · ${proposal.category}` : "提案"}
              busy={proposalBusyId === proposal.asset_id}
              onAdopt={onAdoptProposal ? () => onAdoptProposal(proposal) : undefined}
              onReject={onRejectProposal ? () => onRejectProposal(proposal) : undefined}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SceneTurn({ turn, index }: { turn: CharacterTurn; index: number }) {
  const fadeUp = useFadeUp();

  if (isSystemTurn(turn)) {
    return (
      <motion.div
        initial={fadeUp.initial}
        animate={fadeUp.animate}
        transition={{ duration: DUR.med, ease: EASE }}
        className="flex justify-center"
      >
        <p className="max-w-[560px] text-center font-serif text-caption leading-relaxed tracking-wide text-muted">
          {turn.summary}
        </p>
      </motion.div>
    );
  }

  if (isMyTurn(turn)) {
    const label = MY_TURN_LABELS[turn.turn_kind] ?? "我说";
    return (
      <motion.div
        initial={fadeUp.initial}
        animate={fadeUp.animate}
        transition={{ delay: Math.min(index * 0.03, 0.2), duration: DUR.med, ease: EASE }}
        className="flex justify-end"
      >
        <div className="max-w-[560px]">
          <p className="mb-1 text-right text-caption font-medium tracking-label text-muted">{label}</p>
          <div className="rounded-modal rounded-tr-control border border-accent/30 bg-accent-wash px-4 py-3">
            <p className="font-serif text-base text-ink">{turn.summary}</p>
          </div>
        </div>
      </motion.div>
    );
  }

  // world / agent reaction — a serif novel paragraph, no bubble.
  return (
    <motion.div
      initial={fadeUp.initial}
      animate={fadeUp.animate}
      transition={{ delay: Math.min(index * 0.03, 0.2), duration: DUR.med, ease: EASE }}
      className="flex justify-start"
    >
      <div className="max-w-[680px]">
        <p className="font-serif text-md text-ink-soft">{turn.summary}</p>
      </div>
    </motion.div>
  );
}

/** Small helper so the composer can label the four turn kinds consistently. */
export function turnKindLabel(kind: string): string {
  return MY_TURN_LABELS[kind] ?? "我说";
}
