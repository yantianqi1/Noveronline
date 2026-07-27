"use client";

import { Lock, LockOpen } from "lucide-react";

import { cn } from "@/lib/utils";
import { CharacterRoster, type RosterCharacter } from "@/components/character";
import type { WorldlineVariable } from "@/lib/api/worldline-types";

/**
 * The left 整备轨: preparation status, the cast roster (seals), and the
 * variable locks. Everything is quiet paper; the only vermilion here is the
 * section eyebrows. Variables can be locked — a locked variable carries into
 * the next round as a hard constraint, shown by the gold lock.
 */

export type PrepareStatus = {
  label: string;
  /** Author-facing line when preparation failed / is resumable. */
  detail?: string;
  tone: "ready" | "working" | "failed";
};

export function WorldlinePrepareRail({
  status,
  roster,
  variables,
  selectedAgentId,
  onSelectAgent,
  onToggleVariableLock,
  onResume,
}: {
  status: PrepareStatus;
  roster: RosterCharacter[];
  variables: WorldlineVariable[];
  selectedAgentId?: string | null;
  onSelectAgent?: (id: string) => void;
  onToggleVariableLock?: (variable: WorldlineVariable) => void;
  /** Resume a failed/resumable preparation. */
  onResume?: () => void;
}) {
  return (
    <aside className="hidden h-full w-rail-filter shrink-0 flex-col overflow-y-auto border-r border-line bg-paper/40 stack:flex">
      {/* preparation status */}
      <section className="border-b border-line-soft px-4 py-4">
        <RailEyebrow>整备状态</RailEyebrow>
        <div className="mt-2.5 flex items-center gap-2">
          <StatusDot tone={status.tone} />
          <span className="text-sm font-medium text-ink">{status.label}</span>
        </div>
        {status.detail ? (
          <p className="mt-2 text-caption leading-relaxed text-muted">{status.detail}</p>
        ) : null}
        {status.tone === "failed" && onResume ? (
          <button
            type="button"
            onClick={onResume}
            className="mt-3 w-full rounded-panel border border-accent/50 bg-accent-wash px-3 py-1.5 text-caption font-medium text-accent transition-colors hover:bg-accent/15"
          >
            续传整备
          </button>
        ) : null}
      </section>

      {/* cast roster */}
      <section className="border-b border-line-soft px-4 py-4">
        <RailEyebrow>演员名册</RailEyebrow>
        <div className="mt-2.5">
          <CharacterRoster
            characters={roster}
            mode="single"
            selectedIds={new Set(selectedAgentId ? [selectedAgentId] : [])}
            onToggle={(id) => onSelectAgent?.(id)}
            emptyHint="整备完成后，角色会列在这里"
          />
        </div>
      </section>

      {/* variable locks */}
      <section className="px-4 py-4">
        <RailEyebrow>变量锁</RailEyebrow>
        {variables.length === 0 ? (
          <p className="mt-2.5 rounded-panel border border-dashed border-line px-3 py-3 text-center text-caption text-muted">
            还没有注入变量
          </p>
        ) : (
          <ul className="mt-2.5 space-y-2">
            {variables.map((variable) => (
              <li key={variable.variable_id}>
                <button
                  type="button"
                  onClick={() => onToggleVariableLock?.(variable)}
                  title={variable.locked ? "解锁（不再约束下一轮）" : "锁定（约束传入下一轮）"}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-panel border px-3 py-2.5 text-left transition-colors",
                    variable.locked
                      ? "border-gold/50 bg-gold/[0.07]"
                      : "border-line bg-panel hover:border-accent/30",
                  )}
                >
                  <span aria-hidden className={cn("mt-0.5", variable.locked ? "text-candidate" : "text-muted")}>
                    {variable.locked ? <Lock className="size-3.5" /> : <LockOpen className="size-3.5" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">{variable.name}</span>
                    {variable.description ? (
                      <span className="mt-0.5 line-clamp-2 block text-caption leading-snug text-muted">
                        {variable.description}
                      </span>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}

function RailEyebrow({ children }: { children: React.ReactNode }) {
  return <h3 className="text-caption font-medium tracking-label text-muted">{children}</h3>;
}

function StatusDot({ tone }: { tone: PrepareStatus["tone"] }) {
  return (
    <span
      aria-hidden
      className={cn(
        "size-2 rounded-full",
        tone === "ready" && "bg-accent",
        tone === "working" && "animate-pulse bg-gold",
        tone === "failed" && "bg-ink/40",
      )}
    />
  );
}
