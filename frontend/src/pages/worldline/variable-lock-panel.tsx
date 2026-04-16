import * as React from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Lock, Unlock } from "lucide-react";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface WorldVariable {
  variable_id: string;
  name: string;
  description: string;
  impact_axis?: string;
  source?: string;
}

interface VariableLockPanelProps {
  sectionIndex?: string;
  worldVariables: WorldVariable[];
  lockedVariableIds: Set<string>;
  onToggleLock: (variableId: string) => void;
  onLockAll: () => void;
  onUnlockAll: () => void;
}

/* ================================================================ */
/*  Constants                                                        */
/* ================================================================ */

const SOURCE_LABELS: Record<string, string> = {
  user: "用户注入",
  system: "系统生成",
  llm: "LLM 推导",
};

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function VariableLockPanel({
  sectionIndex = "03 / 变量锁定",
  worldVariables,
  lockedVariableIds,
  onToggleLock,
  onLockAll,
  onUnlockAll,
}: VariableLockPanelProps) {
  if (!worldVariables.length) return null;

  const lockedCount = worldVariables.filter((v) =>
    lockedVariableIds.has(v.variable_id),
  ).length;

  return (
    <section className="flex flex-col gap-2 p-3 border border-amber-300/20 rounded-lg bg-gradient-to-b from-amber-50/85 to-white/95">
      {/* Header */}
      <div className="flex justify-between items-start gap-2">
        <div>
          <p className="font-mono text-xs text-amber-700 tracking-widest">
            {sectionIndex}
          </p>
          <h3 className="text-[0.95rem] font-semibold text-stone-800 mt-0.5">
            变量锁定
          </h3>
        </div>
        <p className="text-xs text-stone-500 max-w-xs">
          锁定的变量将作为约束条件传入下一轮自动演化，LLM 在生成候选事件时会遵守这些不变量。
        </p>
      </div>

      {/* Summary + batch actions */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm text-stone-500 tracking-wide">
          {lockedCount} / {worldVariables.length} 已锁定
        </span>
        <div className="flex gap-1.5">
          <Button
            size="sm"
            variant="outline"
            disabled={lockedCount === worldVariables.length}
            onClick={onLockAll}
          >
            全部锁定
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={lockedCount === 0}
            onClick={onUnlockAll}
          >
            全部解锁
          </Button>
        </div>
      </div>

      {/* Variable list */}
      <div className="flex flex-col gap-2">
        {worldVariables.map((variable) => {
          const locked = lockedVariableIds.has(variable.variable_id);
          return (
            <article
              key={variable.variable_id}
              className={cn(
                "flex gap-2 p-2 px-2.5 rounded-lg border transition-all",
                locked
                  ? "border-amber-500/40 bg-amber-50/95 shadow-sm"
                  : "border-stone-200 bg-white/95",
              )}
            >
              <button
                className={cn(
                  "shrink-0 w-7 h-7 flex items-center justify-center border rounded cursor-pointer transition-all",
                  locked
                    ? "border-amber-500/40 bg-amber-100/90"
                    : "border-stone-200 bg-white/80 hover:bg-amber-50",
                )}
                title={locked ? "解锁此变量" : "锁定此变量"}
                onClick={() => onToggleLock(variable.variable_id)}
              >
                {locked ? (
                  <Lock className="w-3.5 h-3.5 text-amber-700" />
                ) : (
                  <Unlock className="w-3.5 h-3.5 text-stone-400" />
                )}
              </button>
              <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                <strong className="text-sm font-semibold text-stone-800">
                  {variable.name}
                </strong>
                <p className="text-xs text-stone-500 leading-relaxed m-0">
                  {variable.description}
                </p>
                <div className="flex gap-2 mt-0.5">
                  {variable.impact_axis && (
                    <span className="font-mono text-[0.68rem] text-stone-400 tracking-wide px-1.5 py-px rounded bg-blue-500/8">
                      {variable.impact_axis}
                    </span>
                  )}
                  <span className="font-mono text-[0.68rem] text-stone-400 tracking-wide">
                    {SOURCE_LABELS[variable.source || ""] || variable.source || "未知"}
                  </span>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
