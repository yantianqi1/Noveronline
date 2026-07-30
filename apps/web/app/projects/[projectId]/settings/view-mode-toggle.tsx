import { LayoutGroup, motion } from "motion/react";

import { cn } from "@/lib/utils";

export type SettingsViewMode = "function" | "tier";

const MODES: { key: SettingsViewMode; label: string }[] = [
  { key: "function", label: "按功能模块" },
  { key: "tier", label: "按能力强度" },
];

/**
 * The two-way classification switch for the module list: group by workbench
 * family (功能模块) or by capability tier (能力强度). Mirrors the tab bar's
 * sliding selection pill so the two controls read as one system.
 */
export function ViewModeToggle({
  value,
  onChange,
}: {
  value: SettingsViewMode;
  onChange: (mode: SettingsViewMode) => void;
}) {
  return (
    <LayoutGroup id="settings-view-mode">
      <div
        role="tablist"
        aria-label="分类方式"
        className="inline-flex items-center gap-1 rounded-modal border border-line bg-paper/60 p-1"
      >
        {MODES.map((mode) => {
          const selected = mode.key === value;
          return (
            <button
              key={mode.key}
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(mode.key)}
              className={cn(
                "relative rounded-panel px-3.5 py-1.5 text-caption font-medium transition-colors",
                selected ? "text-accent-strong" : "text-muted hover:text-ink",
              )}
            >
              {selected && (
                <motion.span
                  layoutId="view-mode-active-pill"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  className="absolute inset-0 rounded-panel border border-accent/30 bg-panel shadow-hairline"
                />
              )}
              <span className="relative z-10">{mode.label}</span>
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
