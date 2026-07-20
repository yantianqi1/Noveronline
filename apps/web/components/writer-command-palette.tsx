"use client";

import { BookOpenText, ListTree, MessageSquare, Search, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { type Locale, tx } from "../lib/locale";
import { useWriterWorkbench, type WriterArtifactTab } from "./writer-workbench-context";

type PaletteCommand = {
  id: string;
  label: string;
  group: string;
  keywords: string;
  icon: typeof BookOpenText;
  run: () => void;
};

const AGENT_COMPOSER_ID = "writer-instruction";

export function WriterCommandPaletteTrigger({ locale }: { locale: Locale }) {
  const workbench = useWriterWorkbench();
  return (
    <button
      aria-label={tx(locale, "命令面板（⌘K / Ctrl+K）", "Command palette (⌘K / Ctrl+K)")}
      className="writer-command-palette-trigger"
      onClick={() => workbench?.openPalette()}
      title={tx(locale, "命令面板（⌘K / Ctrl+K）", "Command palette (⌘K / Ctrl+K)")}
      type="button"
    >
      <Search aria-hidden="true" size={15} />
      <span className="writer-canvas-tool-label">{tx(locale, "命令", "Commands")}</span>
      <kbd className="writer-command-palette-kbd">⌘K</kbd>
    </button>
  );
}

export function WriterCommandPalette({ locale }: { locale: Locale }) {
  const workbench = useWriterWorkbench();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const open = workbench?.paletteOpen ?? false;
  const close = workbench?.closePalette ?? (() => {});
  const setActiveTab = workbench?.setActiveTab ?? (() => {});

  const commands = useMemo<PaletteCommand[]>(() => {
    const gotoTab = (tab: WriterArtifactTab) => () => {
      setActiveTab(tab);
      close();
    };
    const focusComposer = () => {
      close();
      const el = document.getElementById(AGENT_COMPOSER_ID);
      if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
        el.focus();
        el.scrollIntoView({ block: "nearest" });
      }
    };
    const nav = tx(locale, "跳转", "Navigate");
    const agent = tx(locale, "Agent", "Agent");
    return [
      { id: "tab-manuscript", label: tx(locale, "打开稿件正文", "Open manuscript"), group: nav, keywords: "manuscript prose 稿件 正文", icon: BookOpenText, run: gotoTab("manuscript") },
      { id: "tab-structure", label: tx(locale, "章节管理", "Chapter management"), group: nav, keywords: "structure chapters scenes 章节 场景 结构 管理", icon: ListTree, run: gotoTab("structure") },
      { id: "tab-review", label: tx(locale, "打开审校", "Open review"), group: nav, keywords: "review reviewer proposals 审校 候选", icon: ShieldCheck, run: gotoTab("review") },
      { id: "tab-studio", label: tx(locale, "打开工具", "Open tools"), group: nav, keywords: "studio tools planning commands dedup export 工作室 工具 规划 命令 去重 导出", icon: SlidersHorizontal, run: gotoTab("studio") },
      { id: "focus-agent", label: tx(locale, "聚焦对话输入", "Focus conversation composer"), group: agent, keywords: "agent chat composer write 对话 写作 输入", icon: MessageSquare, run: focusComposer },
    ];
  }, [close, locale, setActiveTab]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((command) => `${command.label} ${command.keywords}`.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    setActiveIndex((index) => Math.min(index, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  if (!open) return null;

  const runActive = () => {
    const command = filtered[activeIndex];
    if (command) command.run();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (filtered.length ? (index + 1) % filtered.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (filtered.length ? (index - 1 + filtered.length) % filtered.length : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      runActive();
    }
  };

  return (
    <div className="writer-command-palette-backdrop" onClick={close} role="presentation">
      <div
        aria-label={tx(locale, "命令面板", "Command palette")}
        aria-modal="true"
        className="writer-command-palette"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
        role="dialog"
      >
        <div className="writer-command-palette-search">
          <Search aria-hidden="true" size={16} />
          <input
            aria-label={tx(locale, "搜索命令", "Search commands")}
            className="writer-command-palette-input"
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tx(locale, "搜索命令，例如「审校」「聚焦对话」…", "Search commands, e.g. “review”, “focus composer”…")}
            ref={inputRef}
            type="text"
            value={query}
          />
          <kbd className="writer-command-palette-kbd">Esc</kbd>
        </div>
        {filtered.length === 0 ? (
          <p className="writer-command-palette-empty">{tx(locale, "没有匹配的命令。", "No matching commands.")}</p>
        ) : (
          <ul className="writer-command-palette-list" role="listbox">
            {filtered.map((command, index) => {
              const Icon = command.icon;
              const active = index === activeIndex;
              return (
                <li key={command.id} role="option" aria-selected={active}>
                  <button
                    className={`writer-command-palette-item ${active ? "is-active" : ""}`}
                    onClick={command.run}
                    onMouseEnter={() => setActiveIndex(index)}
                    type="button"
                  >
                    <Icon aria-hidden="true" size={16} strokeWidth={1.8} />
                    <span className="writer-command-palette-item-label">{command.label}</span>
                    <span className="writer-command-palette-item-group">{command.group}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
