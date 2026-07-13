"use client";

import { Minimize2, PenLine, Sparkles, SpellCheck, StretchHorizontal } from "lucide-react";
import { useState } from "react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";

export type SelectionAction = "rewrite" | "expand" | "condense" | "polish" | "correct" | "custom";

type WriterSelectionToolbarProps = {
  locale: Locale;
  selectionText: string;
  onAction: (action: SelectionAction, freeInstruction?: string) => void;
};

const PRESETS: { action: Exclude<SelectionAction, "custom">; zh: string; en: string; icon: typeof PenLine }[] = [
  { action: "rewrite", zh: "改写", en: "Rewrite", icon: PenLine },
  { action: "expand", zh: "扩写", en: "Expand", icon: StretchHorizontal },
  { action: "condense", zh: "精简", en: "Condense", icon: Minimize2 },
  { action: "polish", zh: "润色", en: "Polish", icon: Sparkles },
  { action: "correct", zh: "校正", en: "Correct", icon: SpellCheck },
];

/**
 * Floating selection toolbar for manuscript prose.
 * ≤5 presets + free instruction; seal-red primary actions.
 */
export function WriterSelectionToolbar({ locale, selectionText, onAction }: WriterSelectionToolbarProps) {
  const [openCustom, setOpenCustom] = useState(false);
  const [custom, setCustom] = useState("");
  const preview = selectionText.trim().slice(0, 48);

  return (
    <div className="writer-selection-toolbar" role="toolbar" aria-label={tx(locale, "选区修订", "Selection revise")}>
      <span className="writer-selection-preview" title={selectionText}>
        “{preview}{selectionText.trim().length > 48 ? "…" : ""}”
      </span>
      <div className="writer-selection-actions">
        {PRESETS.map(({ action, zh, en, icon: Icon }) => (
          <button
            key={action}
            type="button"
            className="writer-selection-action"
            data-action={action}
            onClick={() => onAction(action)}
          >
            <Icon aria-hidden="true" size={14} />
            <Bi zh={zh} en={en} />
          </button>
        ))}
        <button
          type="button"
          className="writer-selection-action writer-selection-action-custom"
          aria-expanded={openCustom}
          onClick={() => setOpenCustom((value) => !value)}
        >
          <Bi zh="指令" en="Prompt" />
        </button>
      </div>
      {openCustom ? (
        <form
          className="writer-selection-custom"
          onSubmit={(event) => {
            event.preventDefault();
            if (!custom.trim()) return;
            onAction("custom", custom.trim());
            setCustom("");
            setOpenCustom(false);
          }}
        >
          <label className="sr-only" htmlFor="writer-selection-free">
            <Bi zh="自由指令" en="Free instruction" />
          </label>
          <input
            id="writer-selection-free"
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            placeholder={tx(locale, "告诉 Agent 如何改这段……", "Tell the agent how to revise…")}
          />
          <button type="submit" data-tone="primary">
            <Bi zh="执行" en="Run" />
          </button>
        </form>
      ) : null}
    </div>
  );
}
