import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import type { LLMChannel, LLMModel } from "@/lib/api/llm-types";

/**
 * Compact two-step channel → model picker.
 *
 * Two tight selects share one control. Two modes:
 *  - Controlled (batch bar): the parent owns the value via value + onChange.
 *  - Auto-save (per-module row): pass onSave; the row keeps a local "pending"
 *    channel selection so the user can browse a channel's models, and only
 *    commits once both a channel AND a model are chosen (a real, complete
 *    binding) — at which point onSave fires once.
 */
export type ModelChoice = { channelId: string; modelId: string };

export function ModelPicker({
  channels,
  models,
  value,
  onChange,
  onSave,
  disabled,
  compact = false,
  ariaLabel,
}: {
  channels: LLMChannel[];
  /** Models for the currently-selected channel. */
  models: LLMModel[];
  value: ModelChoice;
  onChange?: (next: ModelChoice) => void;
  /** Auto-save mode: fired once when a complete channel+model pair is chosen. */
  onSave?: (next: ModelChoice) => void;
  disabled?: boolean;
  compact?: boolean;
  ariaLabel?: string;
}) {
  // Local browsing state, only used in auto-save mode. Holds the channel the
  // user is currently inspecting (and the model within it) until both are set.
  const [pending, setPending] = useState<ModelChoice | null>(null);

  const shown = onSave ? (pending ?? value) : value;
  const channel = channels.find((c) => c.channel_id === shown.channelId) ?? null;

  function pickChannel(channelId: string) {
    if (onSave) {
      // Browse the channel's models without committing; reset the model.
      setPending({ channelId, modelId: "" });
    } else {
      onChange?.({ channelId, modelId: "" });
    }
  }

  function pickModel(modelId: string) {
    if (onSave) {
      const complete = { channelId: shown.channelId, modelId };
      setPending(null);
      if (modelId && modelId !== value.modelId) {
        onSave(complete);
      }
    } else {
      onChange?.({ channelId: shown.channelId, modelId });
    }
  }

  return (
    <div className={cn("flex items-center gap-1.5", compact && "gap-1")}>
      <SelectShell compact={compact} ariaLabel={ariaLabel ? `${ariaLabel}·渠道` : "选择渠道"}>
        <select
          value={shown.channelId}
          disabled={disabled}
          onChange={(e) => pickChannel(e.target.value)}
          className={selectClass(compact, !channel)}
        >
          <option value="" disabled>
            渠道
          </option>
          {channels.map((c) => (
            <option key={c.channel_id} value={c.channel_id}>
              {c.name}
            </option>
          ))}
        </select>
      </SelectShell>

      <SelectShell compact={compact} ariaLabel={ariaLabel ? `${ariaLabel}·模型` : "选择模型"}>
        <select
          value={shown.modelId}
          disabled={disabled || !channel}
          onChange={(e) => pickModel(e.target.value)}
          className={selectClass(compact, !shown.modelId)}
        >
          <option value="" disabled>
            {channel ? "模型" : "先选渠道"}
          </option>
          {models.map((m) => (
            <option key={m.model_id} value={m.model_id}>
              {m.model_id}
            </option>
          ))}
        </select>
      </SelectShell>
    </div>
  );
}

function SelectShell({
  children,
  compact,
  ariaLabel,
}: {
  children: React.ReactNode;
  compact: boolean;
  ariaLabel: string;
}) {
  return (
    <span
      className={cn(
        "relative inline-flex items-center rounded-[9px] border border-line bg-panel shadow-[0_1px_2px_rgba(23,26,27,0.04)] transition-colors focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20",
        compact ? "h-8" : "h-9",
      )}
      aria-label={ariaLabel}
    >
      {children}
      <ChevronDown
        className={cn("pointer-events-none absolute right-2 text-muted/70", compact ? "size-3" : "size-3.5")}
        aria-hidden
      />
    </span>
  );
}

function selectClass(compact: boolean, placeholder: boolean): string {
  return cn(
    "w-full appearance-none bg-transparent pl-2.5 pr-7 text-ink outline-none disabled:cursor-not-allowed disabled:opacity-50",
    compact ? "h-8 max-w-[150px] text-[12.5px]" : "h-9 max-w-[170px] text-[13px]",
    placeholder && "text-muted/70",
  );
}
