"use client";

import { Lock, LockOpen, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { RosterCharacter } from "@/components/character";
import { IconButton } from "@/components/ui/icon-button";
import type { WorldlineEvent, WorldlineVariable } from "@/lib/api/worldline-types";

import { WorldlineCandidateCard } from "./worldline-candidate-card";

/**
 * The right 待定夺 rail (方案A): the gold queue of candidate events the
 * simulation offered but the author has not confirmed, above the常驻 推演上下文
 * (锁定变量 + 演员名册). Adopting a card here is what moves an event onto the
 * timeline as canon; 暂不采纳 persists a rejection and the card leaves for
 * good. Locked variables are hard constraints the director must honor on the
 * next step — each row toggles its lock in place.
 *
 * Inline at the wide band; an overlay drawer below it, because pinning three
 * fixed columns used to crush the timeline between them.
 */
export function WorldlineCandidateRail({
  candidates,
  pendingStep,
  busyId,
  variables,
  roster,
  open = false,
  onClose,
  onAdopt,
  onEdit,
  onReject,
  onToggleVariableLock,
  involvedNames,
}: {
  candidates: WorldlineEvent[];
  /** The step these candidates draft (session.current_step + 1). */
  pendingStep: number;
  /** event_id currently being adopted/edited/rejected (disables its card). */
  busyId?: string | null;
  variables: WorldlineVariable[];
  roster: RosterCharacter[];
  /** Drawer visibility below the wide band. Always inline at wide. */
  open?: boolean;
  onClose?: () => void;
  onAdopt?: (event: WorldlineEvent) => void;
  onEdit?: (event: WorldlineEvent, draft: string) => void;
  onReject?: (event: WorldlineEvent) => void;
  onToggleVariableLock?: (variable: WorldlineVariable) => void;
  involvedNames?: (event: WorldlineEvent) => string[];
}) {
  return (
    <>
      {open ? (
        <div aria-hidden onClick={onClose} className="fixed inset-0 z-30 bg-ink/45 wide:hidden" />
      ) : null}
      <aside
        aria-label="待定夺候选队列"
        className={cn(
          "h-full w-rail-inspector shrink-0 flex-col overflow-hidden border-l border-line bg-panel",
          "max-wide:fixed max-wide:inset-y-0 max-wide:right-0 max-wide:z-40 max-wide:w-full max-wide:max-w-[420px] max-wide:shadow-panel",
          open ? "flex" : "hidden wide:flex",
        )}
      >
        <header className="flex shrink-0 items-center gap-2.5 border-b border-line-soft px-5 py-4">
          <h3 className="font-serif text-base font-semibold text-ink">待定夺 · 第 {pendingStep} 步</h3>
          <span className="grid min-w-6 place-items-center rounded-full bg-candidate-wash px-1.5 py-0.5 text-caption font-semibold text-candidate">
            {candidates.length}
          </span>
          <IconButton label="收起队列" size="sm" onClick={onClose} className="ml-auto wide:hidden">
            <X className="size-4" aria-hidden />
          </IconButton>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {candidates.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <span aria-hidden className="font-brush text-3xl text-line">
                待
              </span>
              <p className="mt-2 max-w-[240px] font-serif text-sm leading-relaxed text-muted-soft">
                尚无待定夺的候选。点击底栏「推进一步」，导演会给出第 {pendingStep} 步的候选走向。
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {candidates.map((event) => (
                <WorldlineCandidateCard
                  key={event.event_id}
                  event={event}
                  busy={busyId === event.event_id}
                  involvedNames={involvedNames?.(event) ?? []}
                  onAdopt={onAdopt}
                  onEdit={onEdit}
                  onReject={onReject}
                />
              ))}
            </div>
          )}
        </div>

        {/* 推演上下文 — 锁定变量 + 演员名册, always on hand while judging */}
        <div className="max-h-[44%] shrink-0 overflow-y-auto border-t border-line-soft px-4 py-3.5">
          <section>
            <h4 className="flex items-baseline gap-2 text-caption font-medium tracking-label text-muted">
              锁定变量
              <span className="text-caption font-normal tracking-normal text-muted-soft">作为硬约束注入下一轮推演</span>
            </h4>
            {variables.length === 0 ? (
              <p className="mt-2 rounded-panel border border-dashed border-line px-3 py-2.5 text-center text-caption text-muted">
                还没有注入变量
              </p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {variables.map((variable) => (
                  <li key={variable.variable_id} className="flex items-start gap-2">
                    <button
                      type="button"
                      aria-pressed={variable.locked}
                      title={variable.locked ? "解锁（不再约束下一轮）" : "锁定为硬约束"}
                      onClick={() => onToggleVariableLock?.(variable)}
                      className={cn(
                        "mt-0.5 grid size-5 shrink-0 place-items-center rounded-control border transition-colors",
                        variable.locked
                          ? "border-gold/60 bg-candidate-wash text-candidate"
                          : "border-line bg-panel text-muted-soft hover:border-muted hover:text-ink",
                      )}
                    >
                      {variable.locked ? (
                        <Lock className="size-3" aria-hidden />
                      ) : (
                        <LockOpen className="size-3" aria-hidden />
                      )}
                    </button>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-serif text-sm text-ink-soft">{variable.name}</span>
                      {variable.description ? (
                        <span className="mt-0.5 line-clamp-1 block text-caption text-muted">
                          {variable.description}
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-4">
            <h4 className="text-caption font-medium tracking-label text-muted">演员名册</h4>
            {roster.length === 0 ? (
              <p className="mt-2 rounded-panel border border-dashed border-line px-3 py-2.5 text-center text-caption text-muted">
                整备完成后，角色会列在这里
              </p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {roster.map((member) => (
                  <li key={member.id} className="flex items-baseline gap-2.5">
                    <span className="shrink-0 font-serif text-sm text-ink-soft">{member.name}</span>
                    {member.role ? (
                      <span className="min-w-0 truncate text-caption text-muted">{member.role}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </aside>
    </>
  );
}
