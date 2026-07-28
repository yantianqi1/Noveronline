"use client";

import {
  AlertTriangle,
  BookOpenText,
  Check,
  CheckCheck,
  CircleSlash,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  WriterError,
  fetchProjectReviewIssues,
  updateReviewIssueStatus,
} from "@/lib/api/writer-client";
import type {
  Chapter,
  ProjectDraftReviewBucket,
  ProjectReviewIssue,
} from "@/lib/api/writer-types";

/**
 * The review view (审校) — the canvas's third live view. A calm two-column
 * triage: on the left, the queue of drafts that still have open findings (with
 * chapter + the run's instruction so it reads "which chapter / what prompt");
 * on the right, the selected draft's issue cards. Each issue can be accepted,
 * dismissed, or marked resolved; the PATCH carries the issue's `updated_at` as
 * the optimistic-lock version, so a stale triage 409s and refetches rather than
 * silently clobbering a concurrent decision.
 *
 * Issues carry no manuscript-block anchor, so "在稿件中定位" degrades to opening
 * the draft's chapter in the manuscript view — the author re-reads from there.
 */
export function ReviewPanel({
  projectId,
  tenantId,
  csrfToken,
  chapters,
  onOpenInManuscript,
}: {
  projectId: string;
  tenantId: string;
  csrfToken: string | null;
  chapters: Chapter[];
  onOpenInManuscript: (chapterId: string) => void;
}) {
  const [queue, setQueue] = useState<ProjectDraftReviewBucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyIssueId, setBusyIssueId] = useState<string | null>(null);

  const chapterTitleById = useMemo(() => {
    const map = new Map<string, string>();
    for (const chapter of chapters) map.set(chapter.chapter_id, chapter.title);
    return map;
  }, [chapters]);

  const loadQueue = useCallback(
    async (keepSelection: boolean) => {
      setLoadError(null);
      try {
        const result = await fetchProjectReviewIssues(projectId, tenantId, "open");
        setQueue(result.items);
        setSelectedDraftId((prev) =>
          keepSelection && prev && result.items.some((b) => b.draft_id === prev)
            ? prev
            : (result.items[0]?.draft_id ?? null),
        );
      } catch (error) {
        setQueue([]);
        setSelectedDraftId(null);
        setLoadError(error instanceof Error ? error.message : "审校发现暂时读不出来,请重试。");
      } finally {
        setLoading(false);
      }
    },
    [projectId, tenantId],
  );

  useEffect(() => {
    void loadQueue(false);
  }, [loadQueue]);

  const selectedBucket = useMemo(
    () => queue.find((b) => b.draft_id === selectedDraftId) ?? null,
    [queue, selectedDraftId],
  );

  const totalOpen = useMemo(() => queue.reduce((sum, b) => sum + b.open_count, 0), [queue]);

  async function handleTriage(issue: ProjectReviewIssue, status: "accepted" | "dismissed" | "resolved") {
    if (!csrfToken || busyIssueId) return;
    setBusyIssueId(issue.issue_id);
    setActionError(null);
    try {
      await updateReviewIssueStatus(projectId, tenantId, csrfToken, issue.issue_id, {
        status,
        version: issue.updated_at ?? "",
      });
      // The issue leaves the "open" queue once triaged; refetch but stay on the
      // same draft so the author keeps their place while working through it.
      await loadQueue(true);
    } catch (error) {
      if (error instanceof WriterError && (error.status === 409 || error.code === "OPTIMISTIC_CONFLICT")) {
        setActionError("这条发现在别处被处理过了。已刷新队列,请再看一眼。");
        await loadQueue(true);
      } else {
        setActionError(error instanceof Error ? error.message : "处理失败,请重试。");
      }
    } finally {
      setBusyIssueId(null);
    }
  }

  function openChapter(chapterId?: string) {
    if (chapterId) onOpenInManuscript(chapterId);
  }

  return (
    <div className="mx-auto w-full max-w-[1040px] px-6 pb-16 pt-7">
      <div className="flex items-baseline gap-3">
        <h2 className="font-serif text-lg font-semibold text-ink">审校</h2>
        <span className="text-sm text-muted">
          {loading ? "读取中…" : `${totalOpen} 条待处理 · ${queue.length} 份稿件`}
        </span>
        <button
          type="button"
          onClick={() => void loadQueue(true)}
          disabled={loading}
          aria-label="刷新"
          title="刷新"
          className="ml-auto flex items-center gap-1 text-caption text-muted hover:text-accent disabled:opacity-50"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden /> 刷新
        </button>
      </div>
      <p className="mt-1 text-caption text-muted-soft">
        这是审校 Agent 对每份草稿的发现。逐条接受、忽略或标记已改;处理完就从队列里移除。想在稿件里对照,点「在稿件中定位」回到那一章。
      </p>

      {loadError ? (
        <div className="mt-4 rounded-panel border border-line bg-accent-wash px-4 py-2.5 text-sm text-accent" role="alert">
          {loadError}
        </div>
      ) : null}
      {actionError ? (
        <div className="mt-4 rounded-panel border border-line bg-accent-wash px-4 py-2.5 text-sm text-accent" role="alert">
          {actionError}
        </div>
      ) : null}

      {loading ? (
        <div className="mt-5 flex items-center justify-center gap-2 rounded-panel border border-line bg-panel px-4 py-16 text-sm text-muted-soft">
          <Loader2 className="size-4 animate-spin" aria-hidden /> 读取审校发现…
        </div>
      ) : queue.length === 0 && !loadError ? (
        <div className="mt-5 rounded-panel border border-line bg-panel px-6 py-16 text-center">
          <CheckCheck className="mx-auto size-6 text-success" aria-hidden />
          <p className="mt-3 font-serif text-base text-ink">没有待处理的审校发现</p>
          <p className="mt-1 text-sm text-muted-soft">让 Agent 跑一轮审校,或处理完的发现都会从这里清空。</p>
        </div>
      ) : (
        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
          {/* Draft queue */}
          <section className="overflow-hidden rounded-panel border border-line bg-panel">
            <header className="border-b border-line-soft px-4 py-2.5 text-caption text-muted">待处理稿件</header>
            <div className="max-h-[560px] overflow-y-auto">
              {queue.map((bucket) => (
                <button
                  key={bucket.draft_id}
                  type="button"
                  onClick={() => setSelectedDraftId(bucket.draft_id)}
                  className={`flex w-full items-start gap-2 border-b border-line-soft border-l-2 px-3 py-2.5 text-left transition-colors ${
                    bucket.draft_id === selectedDraftId ? "border-l-accent bg-accent-wash" : "border-l-transparent hover:bg-paper"
                  }`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-ink">
                      {chapterTitleById.get(bucket.chapter_id ?? "") ?? "未归章的草稿"}
                    </span>
                    {bucket.instruction ? (
                      <span className="mt-0.5 block truncate text-micro text-muted-soft">{bucket.instruction}</span>
                    ) : null}
                  </span>
                  <span className="shrink-0 rounded-full bg-candidate-wash px-2 py-0.5 font-mono text-micro text-candidate">
                    {bucket.open_count}
                  </span>
                </button>
              ))}
            </div>
          </section>

          {/* Selected draft's issues */}
          <div className="flex min-w-0 flex-col gap-4">
            {selectedBucket ? (
              <>
                <div className="flex items-center gap-3 rounded-panel border border-line bg-panel px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-serif text-base font-semibold text-ink">
                      {chapterTitleById.get(selectedBucket.chapter_id ?? "") ?? "未归章的草稿"}
                    </div>
                    <div className="text-caption text-muted-soft">
                      {selectedBucket.word_count.toLocaleString("en-US")} 字草稿 · {selectedBucket.open_count} 条待处理
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => openChapter(selectedBucket.chapter_id)}>
                    <BookOpenText className="size-4" aria-hidden /> 在稿件中定位
                  </Button>
                </div>

                {selectedBucket.issues.map((issue) => (
                  <IssueCard
                    key={issue.issue_id}
                    issue={issue}
                    disabled={!csrfToken}
                    busy={busyIssueId === issue.issue_id}
                    onTriage={handleTriage}
                  />
                ))}
              </>
            ) : (
              <div className="rounded-panel border border-line bg-panel px-6 py-16 text-center text-sm text-muted-soft">
                在左边选一份稿件,看它的审校发现。
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function IssueCard({
  issue,
  disabled,
  busy,
  onTriage,
}: {
  issue: ProjectReviewIssue;
  disabled: boolean;
  busy: boolean;
  onTriage: (issue: ProjectReviewIssue, status: "accepted" | "dismissed" | "resolved") => void;
}) {
  return (
    <article className="rounded-panel border border-line bg-panel px-5 py-4">
      <div className="flex items-center gap-2">
        <SeverityBadge severity={issue.severity} />
        {issue.category ? (
          <span className="rounded-full border border-line-soft px-2 py-0.5 text-micro text-muted">{issue.category}</span>
        ) : null}
        {busy ? <Loader2 className="ml-auto size-4 animate-spin text-muted" aria-hidden /> : null}
      </div>
      <p className="mt-2.5 text-sm leading-relaxed text-ink">{issue.summary}</p>
      {issue.suggestion ? (
        <p className="mt-2 rounded-control bg-paper px-3 py-2 text-sm leading-relaxed text-ink-soft">
          <span className="text-caption text-muted">建议:</span>
          {issue.suggestion}
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="primary" size="sm" disabled={disabled || busy} onClick={() => onTriage(issue, "accepted")}>
          <Check className="size-4" aria-hidden /> 接受
        </Button>
        <Button variant="outline" size="sm" disabled={disabled || busy} onClick={() => onTriage(issue, "resolved")}>
          <CheckCheck className="size-4" aria-hidden /> 已改
        </Button>
        <Button variant="outline" size="sm" disabled={disabled || busy} onClick={() => onTriage(issue, "dismissed")}>
          <CircleSlash className="size-4" aria-hidden /> 忽略
        </Button>
      </div>
    </article>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const { label, className } = severityBadge(severity);
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-micro ${className}`}>
      <AlertTriangle className="size-3" aria-hidden />
      {label}
    </span>
  );
}

function severityBadge(severity: string): { label: string; className: string } {
  switch (severity) {
    case "critical":
      return { label: "致命", className: "bg-danger-wash text-danger" };
    case "high":
      return { label: "严重", className: "bg-accent-wash text-accent" };
    case "medium":
      return { label: "中等", className: "bg-candidate-wash text-candidate" };
    case "low":
      return { label: "轻微", className: "bg-paper text-muted" };
    default:
      return { label: severity || "提示", className: "bg-paper text-muted" };
  }
}
