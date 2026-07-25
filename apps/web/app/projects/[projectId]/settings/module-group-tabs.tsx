import { LayoutGroup, motion } from "motion/react";

import { cn } from "@/lib/utils";
import { bindingFor, type ModuleGroup } from "@/lib/api/llm";
import type { LLMModuleBinding } from "@/lib/api/llm-types";

/**
 * The module-family tab bar. Each capability family (解析与图谱 / 档案与资产 /
 * 角色控制 / 世界线 / 写作台) is a tab showing its bound coverage; selecting one
 * swaps the module list below so a single family gets the full width and its
 * rows stay readable instead of being crammed into a cramped multi-column grid.
 */
export function ModuleGroupTabs({
  groups,
  bindings,
  active,
  onChange,
}: {
  groups: ModuleGroup[];
  bindings: LLMModuleBinding[];
  active: string;
  onChange: (groupKey: string) => void;
}) {
  return (
    <LayoutGroup id="module-group-tabs">
      <div
        role="tablist"
        aria-label="功能分组"
        className="flex flex-wrap items-center gap-1 rounded-[12px] border border-line bg-paper/60 p-1"
      >
        {groups.map((group) => {
          const bound = group.modules.filter(
            (m) => bindingFor(m.module_key, bindings).kind !== "unbound",
          ).length;
          const total = group.modules.length;
          const complete = bound === total;
          const selected = group.key === active;
          return (
            <button
              key={group.key}
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(group.key)}
              className={cn(
                "relative flex items-center gap-2 rounded-[9px] px-3.5 py-2 text-[13px] font-medium transition-colors",
                selected ? "text-accent-strong" : "text-muted hover:text-ink",
              )}
            >
              {selected && (
                <motion.span
                  layoutId="tab-active-pill"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  className="absolute inset-0 rounded-[9px] border border-accent/25 bg-panel shadow-[0_1px_2px_rgba(23,26,27,0.06)]"
                />
              )}
              <span className="relative z-10">{group.label}</span>
              <span
                className={cn(
                  "relative z-10 rounded-full px-1.5 py-px text-[10.5px] tabular-nums",
                  complete
                    ? "bg-accent-wash text-accent-strong"
                    : selected
                      ? "bg-paper-deep text-ink-soft"
                      : "bg-paper-deep/70 text-muted/80",
                )}
              >
                {bound}/{total}
              </span>
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
