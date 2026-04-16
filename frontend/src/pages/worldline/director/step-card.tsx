import * as React from "react";
import { ChevronDown, ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { StatusRibbon } from "./status-ribbon";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface VariableEffect {
  name: string;
  description?: string;
}

interface ActionEffect {
  actor: string;
  action: string;
  intent?: string;
  target?: string;
}

interface RelationChange {
  source: string;
  target: string;
  label: string;
  note?: string;
}

interface ActorSummary {
  name: string;
  initial: string;
  actionCount?: number;
}

interface StepCardProps {
  step: number;
  stepLabel: string;
  title: string;
  summary: string;
  drivers: string[];
  variableEffects: VariableEffect[];
  actionEffects: ActionEffect[];
  relationChanges: RelationChange[];
  actorSummaries: ActorSummary[];
  status?: string;
  expanded: boolean;
  isLatest: boolean;
  onToggleExpand: () => void;
}

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function StepCard({
  stepLabel,
  title,
  summary,
  drivers,
  variableEffects,
  actionEffects,
  relationChanges,
  actorSummaries,
  status,
  expanded,
  isLatest,
  onToggleExpand,
}: StepCardProps) {
  const expandedActors = React.useMemo(() => {
    const map = new Map<string, { name: string; initial: string; action: string; target: string }>();
    for (const a of actionEffects) {
      if (!map.has(a.actor)) {
        map.set(a.actor, {
          name: a.actor,
          initial: a.actor.charAt(0),
          action: a.action,
          target: a.target || "",
        });
      }
    }
    for (const d of drivers) {
      if (!map.has(d)) {
        map.set(d, { name: d, initial: d.charAt(0), action: "", target: "" });
      }
    }
    return [...map.values()];
  }, [actionEffects, drivers]);

  return (
    <article
      className={cn(
        "border rounded-xl p-3.5 cursor-pointer transition-all",
        "border-amber-300/35 bg-white/70 hover:border-amber-600/50",
        isLatest && "border-amber-500/60 bg-gradient-to-br from-amber-50/95 to-orange-50/95",
        expanded && "bg-amber-50/90",
      )}
      onClick={onToggleExpand}
    >
      {/* Head */}
      <div className="flex justify-between items-start gap-3">
        <div className="min-w-0 flex-1">
          <span className="font-mono text-xs text-stone-500 tracking-wider uppercase">
            {stepLabel}
          </span>
          <h4 className="mt-0.5 text-[0.95rem] font-semibold text-stone-800 leading-tight">
            {title}
          </h4>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status && <StatusRibbon status={status} />}
          {isLatest && (
            <span className="px-2 py-0.5 rounded-full text-[0.7rem] font-bold bg-amber-500/20 text-amber-800 font-mono tracking-wide">
              最新
            </span>
          )}
          <ChevronDown
            className={cn(
              "w-3.5 h-3.5 text-stone-500 transition-transform",
              expanded && "rotate-180",
            )}
          />
        </div>
      </div>

      {/* Collapsed: actor chips + summary */}
      {!expanded && actorSummaries.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          {actorSummaries.map((actor) => (
            <span
              key={actor.name}
              className="w-6 h-6 rounded-full inline-flex items-center justify-center font-bold text-xs bg-amber-400/20 text-amber-900 shrink-0"
              title={actor.name}
            >
              {actor.initial}
            </span>
          ))}
          <span className="text-sm text-stone-500 flex-1 min-w-0 truncate">
            {summary}
          </span>
        </div>
      )}
      {!expanded && actorSummaries.length === 0 && (
        <p className="mt-2 text-sm text-stone-500 line-clamp-2">{summary}</p>
      )}

      {/* Expanded detail */}
      {expanded && (
        <div className="mt-3.5 pt-3 border-t border-amber-300/20">
          {/* Actor rows */}
          {expandedActors.length > 0 && (
            <div className="grid gap-2">
              {expandedActors.map((actor) => (
                <div
                  key={actor.name}
                  className="flex gap-2 items-center p-2 rounded-lg bg-amber-50/80 border border-amber-200/20 text-sm text-stone-600 flex-wrap"
                >
                  <span className="w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs bg-amber-400/20 text-amber-900 shrink-0">
                    {actor.initial}
                  </span>
                  <strong className="text-stone-800 text-sm">{actor.name}</strong>
                  {actor.action && (
                    <span className="text-stone-700">{actor.action}</span>
                  )}
                  {actor.target && (
                    <>
                      <ArrowRight className="w-3.5 h-3.5 text-amber-600" />
                      <span>{actor.target}</span>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Relation changes */}
          {relationChanges.length > 0 && (
            <div className="mt-2.5 grid gap-1">
              {relationChanges.map((r) => (
                <div
                  key={`${r.source}_${r.target}`}
                  className="pl-1.5 text-sm text-stone-600 flex gap-1.5 items-center"
                >
                  <span className="text-amber-700">&#10239;</span>
                  {r.source} &rarr; {r.target} &middot; {r.label}
                </div>
              ))}
            </div>
          )}

          {/* Variable footnote */}
          {variableEffects.length > 0 && (
            <div className="mt-2.5 flex gap-1.5 flex-wrap items-center">
              <span className="text-xs font-bold text-stone-500 tracking-wider uppercase">
                变量
              </span>
              {variableEffects.map((v) => (
                <span
                  key={v.name}
                  className="px-2 py-0.5 rounded-full text-xs bg-amber-200/70 text-amber-800"
                >
                  {v.name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
