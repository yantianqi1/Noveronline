"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";
import { CharacterSeal } from "./character-seal";

/**
 * CharacterRoster — the vertical list of character seals used as the Worldline
 * 演员名册 (multi-select for preparation) and the Character Console 降临选角
 * (single-select). One component, two selection modes, so both workbenches read
 * from the same visual vocabulary.
 *
 * Each row is seal + name + a small role/status line. Selection is purely
 * presentational — the parent owns the id set and the confirm action. No data
 * is fetched here; rows come from prepared agents or asset characters.
 */

export type RosterCharacter = {
  id: string;
  name: string;
  /** Small line under the name — role, archetype, or status. */
  role?: string;
  /** Right-aligned hint, e.g. a status chip or a memory count. */
  hint?: string;
  /** Gold seal marks a proposed/candidate character. */
  candidate?: boolean;
};

export function CharacterRoster({
  characters,
  mode,
  selectedIds,
  onToggle,
  emptyHint = "还没有可选角色",
  className,
}: {
  characters: RosterCharacter[];
  mode: "single" | "multi";
  /** Currently selected id set (single mode uses at most one). */
  selectedIds: ReadonlySet<string>;
  onToggle: (id: string) => void;
  emptyHint?: string;
  className?: string;
}) {
  if (characters.length === 0) {
    return (
      <div className={cn("rounded-modal border border-dashed border-line px-4 py-6 text-center", className)}>
        <p className="text-caption text-muted">{emptyHint}</p>
      </div>
    );
  }

  return (
    <ul className={cn("flex flex-col gap-1", className)} role="listbox" aria-label="角色名册">
      {characters.map((character) => {
        const selected = selectedIds.has(character.id);
        return (
          <li key={character.id}>
            <button
              type="button"
              role="option"
              aria-selected={selected}
              onClick={() => onToggle(character.id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-panel border px-3 py-2.5 text-left transition-colors",
                selected
                  ? "border-accent/50 bg-accent-wash"
                  : "border-transparent hover:border-line hover:bg-panel",
              )}
            >
              <CharacterSeal
                name={character.name}
                size="md"
                tone={character.candidate ? "gold" : selected ? "vermilion" : "ink"}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-serif text-base font-medium leading-tight text-ink">
                  {character.name}
                </span>
                {character.role ? (
                  <span className="mt-0.5 block truncate text-caption leading-tight text-muted">
                    {character.role}
                  </span>
                ) : null}
              </span>
              {character.hint ? (
                <span className="shrink-0 text-caption tabular-nums text-muted">{character.hint}</span>
              ) : null}
              {mode === "multi" ? (
                <span
                  aria-hidden
                  className={cn(
                    "grid size-4 shrink-0 place-items-center rounded-control border text-caption transition-colors",
                    selected ? "border-accent bg-accent text-panel" : "border-line bg-transparent text-transparent",
                  )}
                >
                  <Check className="size-3" />
                </span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
