/**
 * CommandPalette — ⌘K quick-nav + quick-action panel using cmdk.
 *
 * Groups:
 * - 视图：switch between writing / outline / manuscript view modes
 * - 章节：jump to a chapter (switches to manuscript view, selects it)
 * - 一键：trigger a one-click runner for the current chapter
 * - 布局：toggle book-plan drawer, v1/v2 layout, etc.
 *
 * Keeping the palette dumb — it only emits intent callbacks; the caller owns
 * state. This keeps the component reusable and testable in isolation.
 */

import * as React from "react";
import { Command } from "cmdk";
import {
  BookOpen,
  Feather,
  FileText,
  LayoutPanelLeft,
  Ruler,
  ScanLine,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";

export interface PaletteChapter {
  chapter_id: string;
  title: string;
  order: number;
}

export type PaletteViewMode = "writing" | "outline" | "manuscript";

export type PaletteOneClickKind =
  | "outline"
  | "continue"
  | "words"
  | "lexicon"
  | "relations";

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chapters: PaletteChapter[];
  currentChapterId?: string;
  onSwitchView: (view: PaletteViewMode) => void;
  onJumpToChapter: (chapterId: string) => void;
  onOneClick?: (kind: PaletteOneClickKind) => void;
  onOpenBookPlan?: () => void;
  /** Disable one-click group when target prerequisites aren't met. */
  oneClickReady?: boolean;
}

const ONE_CLICK_ITEMS: Array<{
  kind: PaletteOneClickKind;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { kind: "outline", label: "一键补全大纲", icon: Sparkles },
  { kind: "continue", label: "一键续写本章", icon: Feather },
  { kind: "words", label: "一键对齐字数", icon: Ruler },
  { kind: "lexicon", label: "一键扫禁词", icon: ScanLine },
  { kind: "relations", label: "一键补关系", icon: Users },
];

export function CommandPalette({
  open,
  onOpenChange,
  chapters,
  currentChapterId,
  onSwitchView,
  onJumpToChapter,
  onOneClick,
  onOpenBookPlan,
  oneClickReady = true,
}: CommandPaletteProps) {
  const [query, setQuery] = React.useState("");

  React.useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [open, onOpenChange]);

  if (!open) return null;

  const run = (fn: () => void) => {
    onOpenChange(false);
    // defer so dialog closes before state mutation (prevents flash)
    setTimeout(fn, 0);
  };

  return (
    <div
      role="dialog"
      aria-label="命令面板"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[15vh]"
      onClick={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
    >
      <Command
        label="命令面板"
        className={cn(
          "w-[560px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-popover shadow-lg",
        )}
      >
        <div className="border-b border-border/40 px-3 py-2">
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder="输入命令或搜索章节 …"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            autoFocus
          />
        </div>
        <Command.List className="max-h-[420px] overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-center text-xs text-muted-foreground">
            未匹配到命令
          </Command.Empty>

          <Command.Group heading="视图切换" className="pb-1">
            <PaletteItem
              value="view:writing"
              label="切换到写作视图"
              icon={FileText}
              onSelect={() => run(() => onSwitchView("writing"))}
            />
            <PaletteItem
              value="view:outline"
              label="切换到大纲视图"
              icon={Target}
              onSelect={() => run(() => onSwitchView("outline"))}
            />
            <PaletteItem
              value="view:manuscript"
              label="切换到稿件视图"
              icon={BookOpen}
              onSelect={() => run(() => onSwitchView("manuscript"))}
            />
          </Command.Group>

          {chapters.length > 0 && (
            <Command.Group heading="章节" className="pb-1">
              {chapters.slice(0, 80).map((ch) => (
                <PaletteItem
                  key={ch.chapter_id}
                  value={`chapter:${ch.chapter_id} 第${ch.order}章 ${ch.title}`}
                  label={`第 ${ch.order} 章${ch.title ? ` · ${ch.title}` : ""}`}
                  icon={BookOpen}
                  badge={ch.chapter_id === currentChapterId ? "当前" : undefined}
                  onSelect={() => run(() => onJumpToChapter(ch.chapter_id))}
                />
              ))}
            </Command.Group>
          )}

          {onOneClick && currentChapterId && (
            <Command.Group heading="一键操作（当前章节）" className="pb-1">
              {ONE_CLICK_ITEMS.map((item) => (
                <PaletteItem
                  key={item.kind}
                  value={`oneclick:${item.kind} ${item.label}`}
                  label={item.label}
                  icon={item.icon}
                  disabled={!oneClickReady}
                  onSelect={() => run(() => onOneClick(item.kind))}
                />
              ))}
            </Command.Group>
          )}

          {onOpenBookPlan && (
            <Command.Group heading="布局" className="pb-1">
              <PaletteItem
                value="layout:book-plan"
                label="打开成书抽屉"
                icon={LayoutPanelLeft}
                onSelect={() => run(onOpenBookPlan)}
              />
            </Command.Group>
          )}
        </Command.List>
        <div className="flex items-center justify-between border-t border-border/40 bg-muted/30 px-3 py-1.5 text-[10px] text-muted-foreground">
          <span>↑↓ 选择 · ↵ 执行 · Esc 关闭</span>
          <span>⌘K</span>
        </div>
      </Command>
    </div>
  );
}

interface PaletteItemProps {
  value: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onSelect: () => void;
  badge?: string;
  disabled?: boolean;
}

function PaletteItem({ value, label, icon: Icon, onSelect, badge, disabled }: PaletteItemProps) {
  return (
    <Command.Item
      value={value}
      onSelect={disabled ? undefined : onSelect}
      disabled={disabled}
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
        "data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground",
        disabled && "opacity-50",
      )}
    >
      <Icon className="size-3.5 text-muted-foreground" />
      <span className="flex-1 truncate">{label}</span>
      {badge && (
        <span className="shrink-0 rounded-sm bg-muted px-1 text-[10px] text-muted-foreground">
          {badge}
        </span>
      )}
    </Command.Item>
  );
}
