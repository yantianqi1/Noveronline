"use client";

import { useState, type ReactNode } from "react";

export type WorkspaceModeOption<T extends string> = {
  id: T;
  label: ReactNode;
};

type WorkspaceModeSwitcherProps<T extends string> = {
  "aria-label": string;
  defaultMode: T;
  modes: WorkspaceModeOption<T>[];
  panels: Record<T, ReactNode>;
};

/**
 * Mutually exclusive workspace modes: only one panel mounts/renders at a time.
 */
export function WorkspaceModeSwitcher<T extends string>({
  "aria-label": ariaLabel,
  defaultMode,
  modes,
  panels,
}: WorkspaceModeSwitcherProps<T>) {
  const [mode, setMode] = useState<T>(defaultMode);

  return (
    <div className="workspace-mode-root" data-mode={mode}>
      <div className="workspace-mode-switcher" role="tablist" aria-label={ariaLabel}>
        {modes.map((item) => (
          <button
            aria-selected={mode === item.id}
            key={item.id}
            onClick={() => setMode(item.id)}
            role="tab"
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="workspace-mode-panel" role="tabpanel">
        {panels[mode]}
      </div>
    </div>
  );
}
