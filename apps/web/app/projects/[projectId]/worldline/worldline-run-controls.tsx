"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * The bottom 运行控制条 — the one vermilion primary action on the screen plus
 * the quiet secondary controls. With no session it is "启动世界线整备"; with a
 * live session it is "推进一步". The evolution mode (手动 / 首轮自动 / 持续自动)
 * is a calm segmented control that never competes with the primary action.
 */

export type EvolutionMode = "manual" | "first_auto" | "continuous_auto";

const MODES: { value: EvolutionMode; label: string }[] = [
  { value: "manual", label: "手动" },
  { value: "first_auto", label: "首轮自动" },
  { value: "continuous_auto", label: "持续自动" },
];

export function WorldlineRunControls({
  hasSession,
  busy = false,
  evolving = false,
  mode,
  onModeChange,
  onPrimary,
  onInjectVariable,
}: {
  hasSession: boolean;
  busy?: boolean;
  /** True while auto-evolution is streaming (primary becomes a breathing loader). */
  evolving?: boolean;
  mode: EvolutionMode;
  onModeChange: (mode: EvolutionMode) => void;
  /** Start preparation (no session) or push one step (live session). */
  onPrimary: () => void;
  onInjectVariable?: (input: { name: string; description: string }) => void;
}) {
  const [injectOpen, setInjectOpen] = useState(false);
  const [varName, setVarName] = useState("");
  const [varDesc, setVarDesc] = useState("");

  function submitVariable() {
    const name = varName.trim();
    if (!name) return;
    onInjectVariable?.({ name, description: varDesc.trim() });
    setVarName("");
    setVarDesc("");
    setInjectOpen(false);
  }

  return (
    <div className="shrink-0 border-t border-line bg-panel">
      {injectOpen && hasSession ? (
        <div className="flex items-end gap-2 border-b border-line-soft px-6 py-3">
          <label className="flex-1">
            <span className="mb-1 block text-[11px] text-muted">变量名</span>
            <input
              value={varName}
              onChange={(e) => setVarName(e.target.value)}
              placeholder="例如：顾临渊的记忆恢复"
              className="w-full rounded-[8px] border border-line bg-paper px-3 py-2 text-[13px] text-ink outline-none focus:border-accent/50"
            />
          </label>
          <label className="flex-[1.4]">
            <span className="mb-1 block text-[11px] text-muted">影响描述</span>
            <input
              value={varDesc}
              onChange={(e) => setVarDesc(e.target.value)}
              placeholder="它会怎样改变走向…"
              className="w-full rounded-[8px] border border-line bg-paper px-3 py-2 text-[13px] text-ink outline-none focus:border-accent/50"
            />
          </label>
          <button
            type="button"
            onClick={submitVariable}
            disabled={!varName.trim()}
            className="rounded-[8px] border border-accent/40 bg-accent-wash px-4 py-2 text-[12.5px] font-medium text-accent transition-colors hover:bg-accent/15 disabled:opacity-50"
          >
            注入
          </button>
          <button
            type="button"
            onClick={() => setInjectOpen(false)}
            className="rounded-[8px] px-3 py-2 text-[12.5px] text-muted transition-colors hover:text-ink"
          >
            收起
          </button>
        </div>
      ) : null}

      <div className="flex items-center gap-3 px-6 py-3.5">
        {/* primary action */}
        <button
          type="button"
          onClick={onPrimary}
          disabled={busy}
          className={cn(
            "rounded-[10px] bg-accent px-5 py-2.5 text-[13.5px] font-medium text-panel shadow-sm transition-colors hover:bg-accent-strong disabled:opacity-60",
            evolving && "animate-pulse",
          )}
        >
          {evolving ? "推演中…" : hasSession ? "推进一步" : "启动世界线整备"}
        </button>

        {hasSession ? (
          <>
            <button
              type="button"
              onClick={() => setInjectOpen((open) => !open)}
              disabled={busy}
              className="rounded-[10px] border border-line bg-panel px-4 py-2.5 text-[13px] font-medium text-ink transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50"
            >
              注入变量
            </button>

            {/* evolution mode segmented control */}
            <div
              role="tablist"
              aria-label="推演模式"
              className="ml-auto flex items-center rounded-[10px] border border-line bg-paper p-0.5"
            >
              {MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  role="tab"
                  aria-selected={mode === m.value}
                  onClick={() => onModeChange(m.value)}
                  className={cn(
                    "rounded-[8px] px-3.5 py-1.5 text-[12.5px] font-medium transition-colors",
                    mode === m.value ? "bg-panel text-accent shadow-sm" : "text-muted hover:text-ink",
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </>
        ) : (
          <p className="ml-auto text-[12.5px] text-muted">整备会自动选好演员，也可以稍后再调。</p>
        )}
      </div>
    </div>
  );
}
