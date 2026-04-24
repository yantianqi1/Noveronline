/**
 * RetryFailedSegmentsBanner — 仅在深度阅读阶段留下 retry_needed 段落时出现。
 *
 * 设计原则:主工作流区域应对自动重试无感;当自动重试耗尽预算仍有剩余
 * 失败段落时,给用户一个"一键重读"出口。
 */
import { Button } from "@/components/ui/button";
import type { SequentialReadingRetry } from "@/lib/seed-upload-task-state";

interface RetryFailedSegmentsBannerProps {
  retry?: SequentialReadingRetry;
  projectId: string;
  taskStatus: string;
  uploadBusy: boolean;
  onRetry: (projectId: string) => void;
}

export default function RetryFailedSegmentsBanner({
  retry,
  projectId,
  taskStatus,
  uploadBusy,
  onRetry,
}: RetryFailedSegmentsBannerProps) {
  if (!retry || retry.count <= 0 || !projectId) return null;
  const disabled = uploadBusy || taskStatus === "processing";
  const sample = retry.pendingSegments.slice(0, 3).join("、");
  const more = retry.pendingSegments.length > 3
    ? `等 ${retry.pendingSegments.length} 段`
    : "";

  return (
    <section
      role="status"
      className="rounded-lg border border-amber-300/70 bg-amber-50/80 p-3 flex items-start gap-3 shadow-sm"
    >
      <div className="mt-0.5 text-amber-600" aria-hidden>
        ⚠
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-amber-900">
          {retry.count} 个段落深度阅读未自动完成
        </div>
        <div className="text-xs text-amber-800 mt-0.5 truncate">
          {sample ? `涉及段落 ${sample}${more}` : "点击右侧按钮即可触发二次重读。"}
        </div>
        <div className="text-[11px] text-amber-700/80 mt-1">
          其余段落已正常完成;点击"一键重读"将以更宽松的预算再跑一次失败段落,
          全部成功后会自动刷新角色档案与故事本体。
        </div>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="border-amber-500/60 text-amber-900 hover:bg-amber-100"
        disabled={disabled}
        onClick={() => onRetry(projectId)}
      >
        {disabled ? "处理中…" : "一键重读"}
      </Button>
    </section>
  );
}
