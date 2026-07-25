"use client";

import { cn } from "@/lib/utils";
import { CharacterSeal } from "@/components/character";
import type { CharacterInteraction } from "@/lib/api/character-console-types";

/**
 * The left 会话轨: the list of interactions (active / saved / archived) the
 * author can step back into. The current one carries a vermilion dot. Selecting
 * a row re-descends into that stage; 回放 entries open read-only.
 */

export function CharacterSessionRail({
  interactions,
  activeId,
  agentNames,
  onSelect,
  onNewDescend,
}: {
  interactions: CharacterInteraction[];
  activeId?: string | null;
  /** Resolve pov_agent_id → display name for the seal. */
  agentNames?: ReadonlyMap<string, string>;
  onSelect?: (interaction: CharacterInteraction) => void;
  onNewDescend?: () => void;
}) {
  return (
    <aside className="flex h-full w-[260px] shrink-0 flex-col overflow-hidden border-r border-line bg-paper/40">
      <header className="shrink-0 border-b border-line-soft px-4 py-4">
        <h3 className="text-[11px] font-medium tracking-[0.24em] text-accent">互 动 会 话</h3>
        <button
          type="button"
          onClick={onNewDescend}
          className="mt-3 w-full rounded-[8px] border border-accent/40 bg-accent-wash px-3 py-2 text-[12.5px] font-medium text-accent transition-colors hover:bg-accent/15"
        >
          新的降临
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        {interactions.length === 0 ? (
          <p className="px-3 py-6 text-center text-[12px] leading-relaxed text-muted">
            还没有互动。先去世界线跑一段推演，再来代入角色。
          </p>
        ) : (
          <ul className="space-y-0.5">
            {interactions.map((interaction) => {
              const active = interaction.interaction_id === activeId;
              const name = agentNames?.get(interaction.pov_agent_id) ?? "";
              return (
                <li key={interaction.interaction_id}>
                  <button
                    type="button"
                    onClick={() => onSelect?.(interaction)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2.5 text-left transition-colors",
                      active ? "bg-accent-wash" : "hover:bg-panel",
                    )}
                  >
                    {name ? <CharacterSeal name={name} size="sm" tone={active ? "vermilion" : "ink"} /> : null}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-serif text-[13.5px] font-medium text-ink">
                        {interaction.title || name || "未命名互动"}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-muted">{statusLabel(interaction.status)}</span>
                    </span>
                    {active ? <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-accent" /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

function statusLabel(status: string): string {
  switch (status) {
    case "active":
      return "进行中";
    case "saved":
      return "已保存";
    case "archived":
      return "已归档";
    default:
      return status || "进行中";
  }
}
