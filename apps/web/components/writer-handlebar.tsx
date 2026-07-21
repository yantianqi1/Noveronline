"use client";

import { Layers, Library, ListTree } from "lucide-react";

import { type Locale, tx } from "../lib/locale";
import { useWriterWorkbench, type WriterDrawer } from "./writer-workbench-context";

type Handle = {
  id: Exclude<WriterDrawer, null>;
  icon: typeof ListTree;
  zh: string;
  en: string;
};

const HANDLES: Handle[] = [
  { id: "structure", icon: ListTree, zh: "结构", en: "Structure" },
  { id: "tools", icon: Layers, zh: "工具", en: "Tools" },
  { id: "library", icon: Library, zh: "资料", en: "Library" },
];

/**
 * Bottom handlebar: the three drawer handles. Always visible, one-line each —
 * the author's on-demand lids over the paper.
 */
export function WriterHandlebar({ locale }: { locale: Locale }) {
  const workbench = useWriterWorkbench();
  const drawer = workbench?.drawer ?? null;

  return (
    <nav aria-label={tx(locale, "写作面板", "Writer panels")} className="writer-handlebar">
      {HANDLES.map((handle) => {
        const Icon = handle.icon;
        const active = drawer === handle.id;
        return (
          <button
            aria-expanded={active}
            className={`writer-handle ${active ? "is-active" : ""}`}
            key={handle.id}
            onClick={() => workbench?.toggleDrawer(handle.id)}
            type="button"
          >
            <Icon aria-hidden="true" size={15} />
            {tx(locale, handle.zh, handle.en)}
          </button>
        );
      })}
    </nav>
  );
}
