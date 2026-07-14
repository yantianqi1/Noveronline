"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";

export type WriterMode = "draft" | "continue" | "outline" | "revise";

const MODES: WriterMode[] = ["draft", "continue", "outline", "revise"];

type WriterModePickerProps = {
  locale: Locale;
  /** Compact chip inside the input row (phone + dense desktop). */
  variant?: "chip" | "segmented";
};

export function writerModeLabel(locale: Locale, mode: string) {
  if (mode === "continue") return tx(locale, "续写", "Continue");
  if (mode === "outline") return tx(locale, "大纲", "Outline");
  if (mode === "revise") return tx(locale, "修订", "Revise");
  return tx(locale, "起草", "Draft");
}

/**
 * Writing mode control. Chip variant: one small button + popover menu.
 * Segmented variant: classic 4-tab radios (desktop default).
 * Always submits `name="mode"` for the server action form.
 */
export function WriterModePicker({ locale, variant = "chip" }: WriterModePickerProps) {
  const [mode, setMode] = useState<WriterMode>("draft");
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointer(event: MouseEvent | TouchEvent) {
      const root = rootRef.current;
      if (!root) {
        return;
      }
      if (event.target instanceof Node && !root.contains(event.target)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (variant === "segmented") {
    return (
      <fieldset className="writer-mode-segmented">
        <legend className="sr-only">
          <Bi zh="写作模式" en="Writing mode" />
        </legend>
        {MODES.map((entry, index) => (
          <label key={entry}>
            <input
              defaultChecked={index === 0}
              name="mode"
              type="radio"
              value={entry}
              onChange={() => setMode(entry)}
            />
            <span>{writerModeLabel(locale, entry)}</span>
          </label>
        ))}
      </fieldset>
    );
  }

  return (
    <div className="writer-mode-picker" ref={rootRef} data-open={open ? "true" : "false"}>
      <input name="mode" type="hidden" value={mode} />
      <button
        type="button"
        className="writer-mode-chip"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{writerModeLabel(locale, mode)}</span>
        <ChevronDown aria-hidden="true" size={14} />
      </button>
      {open ? (
        <div
          className="writer-mode-menu"
          id={listId}
          role="listbox"
          aria-label={tx(locale, "写作模式", "Writing mode")}
        >
          {MODES.map((entry) => (
            <button
              key={entry}
              type="button"
              role="option"
              aria-selected={mode === entry}
              className="writer-mode-menu-item"
              data-active={mode === entry ? "true" : "false"}
              onClick={() => {
                setMode(entry);
                setOpen(false);
              }}
            >
              {writerModeLabel(locale, entry)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
