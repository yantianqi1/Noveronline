/**
 * ReviewerPanel — renders the writer reviewer's rewrite suggestions and lets
 * the user pick which ones to apply. Surfaces in the right-hand TRACE & LOG
 * column after a draft has been committed.
 *
 * One-shot interaction: the user ticks issues, clicks "采纳改写" (triggers
 * `/api/writer-agent/apply-reviewer` via the parent's handler), or clicks
 * "保留原稿" to dismiss the panel. There is no second "commit" step — the
 * original draft is already persisted when this panel appears.
 */

import * as React from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type {
  ReviewerFeedback,
  ReviewerIssue,
} from "@/components/agent-trace-panel";

interface ReviewerPanelProps {
  feedback: ReviewerFeedback;
  streaming: boolean;
  onApply: (issueIds: string[]) => void;
  onDismiss: () => void;
}

const CATEGORY_LABEL: Record<string, string> = {
  cliche: "陈词滥调",
  pattern_reuse: "模式复用",
  pov_drift: "POV 漂移",
  timeline: "时间线冲突",
  pacing: "节奏",
  figurative_density: "比喻过密",
  redundant_modifier: "赘余修饰",
  voice: "语言风格",
};

const SEVERITY_VARIANT: Record<
  ReviewerIssue["severity"],
  "default" | "secondary" | "destructive" | "outline"
> = {
  high: "destructive",
  medium: "default",
  low: "secondary",
};

const SEVERITY_LABEL: Record<ReviewerIssue["severity"], string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export function ReviewerPanel({
  feedback,
  streaming,
  onApply,
  onDismiss,
}: ReviewerPanelProps) {
  const [selected, setSelected] = React.useState<Set<string>>(() => {
    // Default: pre-check high-severity items so the user just has to click apply.
    return new Set(
      (feedback.issues || [])
        .filter((i) => i.severity === "high")
        .map((i) => i.id),
    );
  });

  // Reset selection whenever the feedback payload changes (new review cycle).
  const feedbackKey = React.useMemo(
    () => (feedback.issues || []).map((i) => i.id).join("|"),
    [feedback],
  );
  React.useEffect(() => {
    setSelected(
      new Set(
        (feedback.issues || [])
          .filter((i) => i.severity === "high")
          .map((i) => i.id),
      ),
    );
  }, [feedbackKey, feedback]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (feedback.status === "skipped") {
    return (
      <div className="rounded-lg border border-border/40 p-2.5">
        <h3 className="mb-1 text-sm font-bold">写作审校</h3>
        <p className="text-xs text-muted-foreground">
          审校未执行：{feedback.reason || "writer_reviewer 模块未绑定或调用失败"}
        </p>
      </div>
    );
  }

  const issues = feedback.issues || [];
  const scorePct =
    feedback.overall_score !== null && feedback.overall_score !== undefined
      ? Math.round(feedback.overall_score * 100)
      : null;

  return (
    <div className="rounded-lg border border-border/40 p-2.5">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-bold">写作审校</h3>
        {scorePct !== null && (
          <Badge
            variant={
              scorePct >= 85 ? "default" : scorePct >= 70 ? "secondary" : "destructive"
            }
            className="text-[10px]"
          >
            {scorePct} / 100
          </Badge>
        )}
      </div>

      {feedback.summary && (
        <p className="mb-2 text-xs text-muted-foreground">{feedback.summary}</p>
      )}

      {issues.length === 0 ? (
        <p className="text-xs text-green-500">未发现需要修改的问题。</p>
      ) : (
        <>
          <div className="mb-2 space-y-2">
            {issues.map((issue) => {
              const isChecked = selected.has(issue.id);
              return (
                <label
                  key={issue.id}
                  className={`flex cursor-pointer gap-2 rounded-md border p-2 text-xs transition-colors ${
                    isChecked
                      ? "border-primary/60 bg-primary/5"
                      : "border-border/30 hover:bg-muted/30"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggle(issue.id)}
                    className="mt-0.5 shrink-0"
                  />
                  <div className="flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge
                        variant={SEVERITY_VARIANT[issue.severity]}
                        className="text-[10px]"
                      >
                        {SEVERITY_LABEL[issue.severity]}
                      </Badge>
                      <Badge variant="outline" className="text-[10px]">
                        {CATEGORY_LABEL[issue.category] || issue.category}
                      </Badge>
                      {issue.location && (
                        <span className="text-[10px] text-muted-foreground">
                          {issue.location}
                        </span>
                      )}
                    </div>
                    {issue.original && (
                      <div className="text-muted-foreground line-through decoration-red-400/60">
                        {issue.original}
                      </div>
                    )}
                    {issue.suggestion && (
                      <div className="text-foreground">→ {issue.suggestion}</div>
                    )}
                    {issue.reason && (
                      <div className="text-[11px] text-muted-foreground">
                        理由：{issue.reason}
                      </div>
                    )}
                  </div>
                </label>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              className="h-7"
              disabled={streaming || selected.size === 0}
              onClick={() => onApply(Array.from(selected))}
            >
              {streaming && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              采纳改写（{selected.size}）
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7"
              disabled={streaming}
              onClick={onDismiss}
            >
              保留原稿
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
