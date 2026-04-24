/**
 * OneClickActionRow — 4 buttons that trigger backend /one-click/* runners
 * and surface emitted render cards in the agent trace panel.
 *
 * Design (W-3 §4.4): each button is an icon + short label. Disabled while
 * another one-click run is in flight (global mutex across buttons — the
 * backend is single-threaded per session so queueing would just stall).
 *
 * All cards surface through the normal SSE tool_result.render pipeline, so
 * users see them in the agent-trace panel alongside other tool results.
 */

import * as React from "react";
import {
  CheckCircle2,
  Feather,
  Loader2,
  Ruler,
  ScanLine,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";

import {
  oneClickAlignWords,
  oneClickCompleteOutline,
  oneClickContinueChapter,
  oneClickFillRelationships,
  oneClickScanLexicon,
} from "@/api/writer-agent";
import { Button } from "@/components/ui/button";
import { useNotification } from "@/hooks/use-notification";
import { cn } from "@/lib/utils";

import type { ToolRenderPayload, WriterEvent } from "@/types/writer";

type ButtonKind = "outline" | "continue" | "words" | "lexicon" | "relations";

interface OneClickSummary {
  runner: string;
  verdict?: string;
  cards: ToolRenderPayload[];
  error?: string | null;
}

export interface OneClickActionRowProps {
  projectId: string;
  chapterId: string;
  chapterOrder: number;
  /** Target word count pulled from book_plan (align-words gated on this). */
  targetWordCount?: number;
  /** Current lexicon asset selection from ForbiddenLexiconPanel. */
  lexiconAssetIds?: string[];
  /** Called for every SSE event so the caller can stream them into the
   * trace panel. Cards arrive as `tool_result` events with `render` set. */
  onEvent?: (event: WriterEvent) => void;
  /** Called when a one-click run settles — final summary contains cards[]. */
  onSettled?: (summary: OneClickSummary) => void;
  className?: string;
}

interface ActionConfig {
  kind: ButtonKind;
  icon: LucideIcon;
  label: string;
  tooltip: string;
  disabled?: string;
}

export function OneClickActionRow({
  projectId,
  chapterId,
  chapterOrder,
  targetWordCount,
  lexiconAssetIds,
  onEvent,
  onSettled,
  className,
}: OneClickActionRowProps) {
  const [activeKind, setActiveKind] = React.useState<ButtonKind | null>(null);
  const { notifySuccess, notifyError } = useNotification();
  const abortRef = React.useRef<AbortController | null>(null);

  const ready = Boolean(projectId && chapterId);
  const targetReady = typeof targetWordCount === "number" && targetWordCount > 0;

  const actions: ActionConfig[] = React.useMemo(
    () => [
      {
        kind: "outline",
        icon: Sparkles,
        label: "补全大纲",
        tooltip: "🪄 扫描当前章节大纲缺口，生成场景提案（不落库）",
      },
      {
        kind: "continue",
        icon: Feather,
        label: "续写本章",
        tooltip: "✍️ 检索设定 + WriterComposer 流式生成 400-800 字续写草稿",
      },
      {
        kind: "words",
        icon: Ruler,
        label: "对齐字数",
        tooltip: targetReady
          ? "📐 扫描字数偏差，生成扩写/精简提案"
          : "需先在成书抽屉设置目标字数",
        disabled: targetReady ? undefined : "未设定章节目标字数",
      },
      {
        kind: "lexicon",
        icon: ScanLine,
        label: "扫禁词",
        tooltip: "🚫 扫描正文禁词，生成改写提案",
      },
      {
        kind: "relations",
        icon: Users,
        label: "补关系",
        tooltip: "🔗 识别章内共现但未建档的角色对，生成关系提案",
      },
    ],
    [targetReady],
  );

  const runOneClick = React.useCallback(
    async (kind: ButtonKind) => {
      if (!ready || activeKind) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setActiveKind(kind);

      const cards: ToolRenderPayload[] = [];
      const settledRef: { current: OneClickSummary | null } = { current: null };

      const handlers = {
        onEvent: (evt: unknown) => {
          if (evt && typeof evt === "object") {
            const event = evt as WriterEvent;
            onEvent?.(event);
            if (event.type === "tool_result") {
              const render = (event as { render?: ToolRenderPayload }).render;
              if (render && typeof render === "object") cards.push(render);
            }
            if (event.type === "summary") {
              settledRef.current = {
                runner: (event.runner as string) ?? kind,
                verdict: (event.verdict as string) ?? "",
                cards,
                error: (event.error as string | null) ?? null,
              };
            }
          }
        },
        onError: (err: unknown) => {
          notifyError(
            "一键任务失败",
            err instanceof Error ? err.message : String(err),
          );
        },
        onDone: () => {},
      };

      try {
        if (kind === "outline") {
          await oneClickCompleteOutline(
            { project_id: projectId, chapter_id: chapterId, chapter_order: chapterOrder },
            handlers,
            controller.signal,
          );
        } else if (kind === "continue") {
          await oneClickContinueChapter(
            {
              project_id: projectId,
              chapter_id: chapterId,
              chapter_order: chapterOrder,
              target_word_count: 600,
            },
            handlers,
            controller.signal,
          );
        } else if (kind === "words") {
          await oneClickAlignWords(
            {
              project_id: projectId,
              chapter_id: chapterId,
              chapter_order: chapterOrder,
              target_word_count: targetWordCount ?? 0,
              tolerance_pct: 10,
            },
            handlers,
            controller.signal,
          );
        } else if (kind === "lexicon") {
          await oneClickScanLexicon(
            {
              project_id: projectId,
              chapter_id: chapterId,
              chapter_order: chapterOrder,
              lexicon_asset_ids: lexiconAssetIds,
            },
            handlers,
            controller.signal,
          );
        } else if (kind === "relations") {
          await oneClickFillRelationships(
            { project_id: projectId, chapter_id: chapterId, chapter_order: chapterOrder },
            handlers,
            controller.signal,
          );
        }
        if (settledRef.current) {
          onSettled?.(settledRef.current);
          if (!settledRef.current.error) {
            notifySuccess(
              "一键任务完成",
              `${settledRef.current.runner}: 生成 ${settledRef.current.cards.length} 张提案卡`,
            );
          }
        }
      } catch (err) {
        if ((err as { name?: string })?.name !== "AbortError") {
          notifyError(
            "一键任务失败",
            err instanceof Error ? err.message : String(err),
          );
        }
      } finally {
        setActiveKind(null);
        abortRef.current = null;
      }
    },
    [
      ready,
      activeKind,
      projectId,
      chapterId,
      chapterOrder,
      targetWordCount,
      lexiconAssetIds,
      onEvent,
      onSettled,
      notifySuccess,
      notifyError,
    ],
  );

  React.useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return (
    <div
      className={cn(
        "flex items-center gap-1 rounded-md border border-border/40 bg-card/60 p-1",
        className,
      )}
    >
      {actions.map(({ kind, icon: Icon, label, tooltip, disabled }) => {
        const isActive = activeKind === kind;
        const otherActive = activeKind !== null && activeKind !== kind;
        const isDisabled = !ready || !!disabled || otherActive;
        return (
          <Button
            key={kind}
            size="sm"
            variant="ghost"
            className="h-7 gap-1 px-2 text-[11px]"
            disabled={isDisabled}
            onClick={() => void runOneClick(kind)}
            title={disabled ?? tooltip}
          >
            {isActive ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Icon className="size-3.5" />
            )}
            <span>{label}</span>
          </Button>
        );
      })}
      {activeKind && (
        <span className="ml-1 inline-flex items-center gap-1 text-[10px] text-muted-foreground">
          <CheckCircle2 className="size-3" />
          运行中…
        </span>
      )}
    </div>
  );
}
