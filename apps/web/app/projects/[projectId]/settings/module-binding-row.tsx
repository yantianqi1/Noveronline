import { Check, Loader2, RotateCcw } from "lucide-react";

import { cn } from "@/lib/utils";
import type { BindingState } from "@/lib/api/llm";
import type { LLMChannel, LLMModel, LLMModule } from "@/lib/api/llm-types";

import { ModelPicker, type ModelChoice } from "./model-picker";

export type RowSaveState = "idle" | "saving" | "saved" | "error";

/**
 * One module's binding row: its current model (or an honest "unbound" state)
 * with a compact inline picker. Choosing a different channel+model saves the
 * project override immediately — there is no separate save step. Resetting
 * removes the override so the module falls back to the inherited default.
 */
export function ModuleBindingRow({
  module,
  state,
  channels,
  models,
  onSave,
  onReset,
  saveState,
  disabled,
}: {
  module: LLMModule;
  state: BindingState;
  channels: LLMChannel[];
  /** Models for the row's currently-shown channel. */
  models: LLMModel[];
  onSave: (moduleKey: string, choice: ModelChoice) => void;
  onReset: (moduleKey: string) => void;
  saveState: RowSaveState;
  disabled?: boolean;
}) {
  const bound = state.kind !== "unbound";
  const overridden = state.kind === "project";
  const value = currentChoice(state);
  const busy = saveState === "saving";

  return (
    <div
      className={cn(
        "group flex items-center justify-between gap-4 rounded-panel border px-4 py-3 transition-colors",
        saveState === "error"
          ? "border-accent/50 bg-accent-wash/40"
          : bound
            ? "border-line-soft bg-panel hover:border-line"
            : "border-dashed border-line bg-paper/50",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <StatusDot bound={bound} overridden={overridden} />
          <span className="text-sm font-medium text-ink" title={module.description}>
            {module.label}
          </span>
          {overridden && (
            <span className="shrink-0 rounded-full bg-accent-wash px-1.5 py-px text-caption font-medium text-accent-strong">
              自定义
            </span>
          )}
        </div>
        <p className="mt-1 truncate pl-[15px] text-caption text-muted">
          {saveState === "error" ? (
            <span className="text-accent">保存失败，请重试</span>
          ) : bound ? (
            <>
              <span className="text-ink-soft">{state.binding.model_id}</span>
              <span className="text-muted-soft"> · {state.binding.channel_name}</span>
            </>
          ) : (
            <span className="text-muted">未绑定 — 选一个模型即可启用</span>
          )}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <RowFeedback saveState={saveState} />
        {overridden && (
          <button
            type="button"
            onClick={() => onReset(module.module_key)}
            disabled={busy || disabled}
            title="清除自定义，恢复默认"
            className="grid size-7 place-items-center rounded-control text-muted-soft opacity-0 transition-all hover:bg-accent-wash hover:text-accent focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-40"
          >
            <RotateCcw className="size-3.5" aria-hidden />
          </button>
        )}
        <ModelPicker
          compact
          channels={channels}
          models={models}
          value={value}
          onSave={(next) => onSave(module.module_key, next)}
          disabled={busy || disabled}
          ariaLabel={module.label}
        />
      </div>
    </div>
  );
}

function RowFeedback({ saveState }: { saveState: RowSaveState }) {
  if (saveState === "saving") {
    return <Loader2 className="size-3.5 animate-spin text-accent" aria-label="保存中" />;
  }
  if (saveState === "saved") {
    return <Check className="size-3.5 text-accent-strong" aria-label="已保存" />;
  }
  return null;
}

function currentChoice(state: BindingState): ModelChoice {
  if (state.kind === "unbound") return { channelId: "", modelId: "" };
  return { channelId: state.binding.channel_id, modelId: state.binding.model_id };
}

function StatusDot({ bound, overridden }: { bound: boolean; overridden: boolean }) {
  if (!bound) {
    return <span className="size-[7px] shrink-0 rounded-full border border-dashed border-muted/60" aria-hidden />;
  }
  return (
    <span
      className={cn("size-[7px] shrink-0 rounded-full", overridden ? "bg-accent" : "bg-ink-soft/70")}
      aria-hidden
    />
  );
}
