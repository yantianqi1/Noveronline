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
  pendingCount = 0,
  mode,
  onModeChange,
  onPrimary,
  onInjectVariable,
}: {
  hasSession: boolean;
  busy?: boolean;
  /** True while auto-evolution is streaming (primary becomes a breathing loader). */
  evolving?: boolean;
  /** Candidates awaiting 定夺 — the world cannot move on until they are settled. */
  pendingCount?: number;
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
        <div className="flex flex-wrap items-end gap-2 border-b border-line-soft px-6 py-3">
          <label className="flex-1">
            <span className="mb-1 block text-caption text-muted">变量名</span>
            <input
              value={varName}
              onChange={(e) => setVarName(e.target.value)}
              placeholder="例如：顾临渊的记忆恢复"
              className="w-full rounded-panel border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent/50"
            />
          </label>
          <label className="flex-[1.4]">
            <span className="mb-1 block text-caption text-muted">影响描述</span>
            <input
              value={varDesc}
              onChange={(e) => setVarDesc(e.target.value)}
              placeholder="它会怎样改变走向…"
              className="w-full rounded-panel border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent/50"
            />
          </label>
          <button
            type="button"
            onClick={submitVariable}
            disabled={!varName.trim()}
            className="shrink-0 whitespace-nowrap rounded-control border border-line bg-panel px-4 py-2 text-caption font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-50"
          >
            注入
          </button>
          <button
            type="button"
            onClick={() => setInjectOpen(false)}
            className="rounded-panel px-3 py-2 text-caption text-muted transition-colors hover:text-ink"
          >
            收起
          </button>
          <p className="w-full text-caption text-muted-soft">
            注入的变量默认未锁定，可在右栏「锁定变量」里锁为硬约束。
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 px-6 py-3.5">
        {/* primary action */}
        <button
          type="button"
          onClick={onPrimary}
          disabled={busy || pendingCount > 0}
          title={pendingCount > 0 ? "先定夺完这一步的候选" : undefined}
          className={cn(
            "shrink-0 whitespace-nowrap rounded-control bg-accent px-5 py-2.5 text-sm font-medium text-panel shadow-accent transition-colors hover:bg-accent-strong disabled:opacity-60",
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
              className="shrink-0 whitespace-nowrap rounded-control border border-line bg-panel px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-50"
            >
              注入变量
            </button>

            {/* evolution mode segmented control */}
            <div
              role="tablist"
              aria-label="推演模式"
              className="ml-auto flex shrink-0 items-center rounded-control border border-line bg-paper p-0.5"
            >
              {MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  role="tab"
                  aria-selected={mode === m.value}
                  onClick={() => onModeChange(m.value)}
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-control px-3.5 py-1.5 text-caption font-medium transition-colors",
                    mode === m.value ? "bg-panel text-accent shadow-hairline" : "text-muted hover:text-ink",
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </>
        ) : (
          <p className="ml-auto text-caption text-muted">选角导演会自动选好演员，也可以稍后再调。</p>
        )}
      </div>
    </div>
  );
}
