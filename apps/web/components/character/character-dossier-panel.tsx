"use client";

import { cn } from "@/lib/utils";
import { CharacterSeal } from "./character-seal";

/**
 * CharacterDossierPanel — the shared read-only 角色档案 right column. Used as
 * the Worldline inspector (when you click a roster seal) and as the default
 * right rail on the Character Console stage. One component, one data shape, so
 * both workbenches show the same character the same way.
 *
 * It renders ONLY the public dossier fields it is given — profile, memory
 * strips, relations, and an optional interaction outline. It never fabricates
 * memory: when a section has no data it shows an honest empty line, and when
 * the whole backend is missing the parent renders an error state instead of
 * mounting this panel.
 */

export type DossierProfile = {
  role?: string;
  status?: string;
  summary?: string;
};

export type DossierMemory = {
  id: string;
  /** Short strip of memory text. */
  text: string;
  /** Optional weight/salience 0–1 for the meter. */
  weight?: number;
};

export type DossierRelation = {
  id: string;
  /** The other party's name. */
  name: string;
  /** Nature of the tie (盟友 / 宿敌 / 血亲…). */
  kind: string;
  /** Strength 0–1 for the meter. */
  strength?: number;
};

export function CharacterDossierPanel({
  name,
  profile,
  memories = [],
  relations = [],
  outline,
  candidate = false,
  emptyMemoryHint = "还没有沉淀下记忆",
  emptyRelationHint = "还没有可辨认的关系",
  className,
}: {
  name: string;
  profile?: DossierProfile;
  memories?: DossierMemory[];
  relations?: DossierRelation[];
  /** Optional 互动大纲 (free-text lines describing the planned arc). */
  outline?: string[];
  /** Gold seal + tag when this character is itself a candidate. */
  candidate?: boolean;
  emptyMemoryHint?: string;
  emptyRelationHint?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex h-full min-h-0 flex-col overflow-y-auto", className)}>
      {/* header: large seal + name + status */}
      <header className="flex flex-col items-center border-b border-line-soft px-6 pb-6 pt-8 text-center">
        <CharacterSeal name={name} size="xl" tone={candidate ? "gold" : "vermilion"} />
        <h3 className="mt-4 font-serif text-xl font-semibold leading-tight text-ink">{name}</h3>
        <div className="mt-2 flex flex-wrap items-center justify-center gap-1.5">
          {profile?.role ? (
            <span className="rounded-control border border-line bg-panel px-2 py-0.5 text-caption text-ink-soft">
              {profile.role}
            </span>
          ) : null}
          {profile?.status ? (
            <span className="rounded-control border border-accent/30 bg-accent-wash px-2 py-0.5 text-caption text-accent">
              {profile.status}
            </span>
          ) : null}
          {candidate ? (
            <span className="rounded-control border border-gold/50 bg-gold/10 px-2 py-0.5 text-caption text-gold">
              候选
            </span>
          ) : null}
        </div>
        {profile?.summary ? (
          <p className="mt-3 max-w-[280px] font-serif text-sm text-muted">
            {profile.summary}
          </p>
        ) : null}
      </header>

      {/* memory strips */}
      <DossierSection title="记忆" count={memories.length}>
        {memories.length === 0 ? (
          <EmptyLine>{emptyMemoryHint}</EmptyLine>
        ) : (
          <ul className="space-y-2">
            {memories.map((memory) => (
              <li
                key={memory.id}
                className="rounded-panel border border-line-soft bg-paper px-3 py-2.5"
              >
                <p className="font-serif text-caption text-ink-soft">{memory.text}</p>
                {typeof memory.weight === "number" ? (
                  <Meter value={memory.weight} className="mt-2" />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </DossierSection>

      {/* relations */}
      <DossierSection title="关系" count={relations.length}>
        {relations.length === 0 ? (
          <EmptyLine>{emptyRelationHint}</EmptyLine>
        ) : (
          <ul className="space-y-2.5">
            {relations.map((relation) => (
              <li key={relation.id} className="flex items-center gap-3">
                <CharacterSeal name={relation.name} size="sm" tone="ink" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-serif text-sm font-medium text-ink">{relation.name}</span>
                    <span className="shrink-0 text-caption text-muted">{relation.kind}</span>
                  </div>
                  {typeof relation.strength === "number" ? (
                    <Meter value={relation.strength} className="mt-1.5" />
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </DossierSection>

      {/* interaction outline */}
      {outline && outline.length > 0 ? (
        <DossierSection title="互动大纲">
          <ol className="space-y-1.5">
            {outline.map((line, index) => (
              <li key={index} className="flex gap-2.5">
                <span className="mt-0.5 shrink-0 font-serif text-caption tabular-nums text-accent">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="font-serif text-caption text-ink-soft">{line}</span>
              </li>
            ))}
          </ol>
        </DossierSection>
      ) : null}
    </div>
  );
}

function DossierSection({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-line-soft px-6 py-5 last:border-b-0">
      <div className="mb-3 flex items-baseline justify-between">
        <h4 className="text-caption font-medium tracking-label text-muted">{title}</h4>
        {typeof count === "number" && count > 0 ? (
          <span className="text-caption tabular-nums text-muted">{count}</span>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function EmptyLine({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-panel border border-dashed border-line px-3 py-3 text-center text-caption text-muted">
      {children}
    </p>
  );
}

/** A quiet ink meter for memory salience / relation strength. */
function Meter({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className={cn("h-[3px] w-full overflow-hidden rounded-full bg-line-soft", className)}>
      <div className="h-full rounded-full bg-accent/60" style={{ width: `${pct}%` }} />
    </div>
  );
}
