import { Loader2, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { LLMChannel, LLMModel } from "@/lib/api/llm-types";

import { ModelPicker, type ModelChoice } from "./model-picker";

/**
 * The batch "set every module at once" control.
 *
 * The primary, friendly path: choose a channel + model once, apply it to all
 * 31 modules in a single action. Per-module rows below remain for fine-tuning.
 * This is what unblocks Seed analysis in one gesture.
 */
export function BatchApplyBar({
  channels,
  models,
  choice,
  onChoiceChange,
  onApply,
  applying,
  disabled,
  boundCount,
  totalCount,
}: {
  channels: LLMChannel[];
  models: LLMModel[];
  choice: ModelChoice;
  onChoiceChange: (next: ModelChoice) => void;
  onApply: () => void;
  applying: boolean;
  disabled?: boolean;
  boundCount: number;
  totalCount: number;
}) {
  const ready = Boolean(choice.channelId && choice.modelId);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-modal border border-line bg-gradient-to-br from-panel to-paper-deep/40 px-5 py-4 shadow-hairline">
      <div className="flex items-center gap-2.5">
        <span className="grid size-9 place-items-center rounded-panel bg-accent-wash text-accent">
          <Wand2 className="size-4.5" aria-hidden />
        </span>
        <div>
          <p className="text-sm font-semibold text-ink">一键套用全部功能</p>
          <p className="text-caption text-muted">
            已绑定 <span className="font-medium text-ink">{boundCount}</span>/{totalCount} 个功能
          </p>
        </div>
      </div>

      <div className="h-8 w-px bg-line-soft" aria-hidden />

      <ModelPicker
        channels={channels}
        models={models}
        value={choice}
        onChange={onChoiceChange}
        disabled={disabled || applying}
        ariaLabel="批量套用"
      />

      <Button
        size="sm"
        onClick={onApply}
        disabled={!ready || disabled || applying}
        loading={applying}
        className="ml-auto"
      >
        {applying ? "正在套用…" : "套用到全部"}
      </Button>
    </div>
  );
}

export function BatchProgress({ done, total }: { done: number; total: number }) {
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div className="mt-2 flex items-center gap-3">
      <div className="h-[5px] flex-1 overflow-hidden rounded-full bg-paper-deep">
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="flex items-center gap-1.5 text-caption text-muted">
        <Loader2 className="size-3 animate-spin" aria-hidden />
        {done}/{total}
      </span>
    </div>
  );
}
