/**
 * SeedUploadPanel — file upload form with drag-and-drop, project name, analysis goal.
 */

import { useCallback, useRef, useState, type DragEvent, type ChangeEvent } from "react";
import { Upload, X, ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useSeedUpload } from "@/hooks/use-seed-upload";

/* ---------- Props ---------- */

interface SeedUploadPanelProps {
  initiallyExpanded?: boolean;
}

/* ---------- Component ---------- */

export default function SeedUploadPanel({
  initiallyExpanded = true,
}: SeedUploadPanelProps) {
  const upload = useSeedUpload();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [panelExpanded, setPanelExpanded] = useState(initiallyExpanded);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);

  const canSubmit =
    upload.analysisGoal.trim().length > 0 && upload.files.length > 0;

  /* ---- File handling ---- */

  const openPicker = useCallback(() => {
    if (upload.uploadBusy) return;
    fileInputRef.current?.click();
  }, [upload.uploadBusy]);

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      upload.appendFiles(Array.from(e.target.files || []));
      if (e.target) e.target.value = "";
    },
    [upload],
  );

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    upload.setField("dragActive", true);
  }, [upload]);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    upload.setField("dragActive", false);
  }, [upload]);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      if (upload.uploadBusy) return;
      upload.setField("dragActive", false);
      upload.appendFiles(Array.from(e.dataTransfer?.files || []));
    },
    [upload],
  );

  const handleSubmit = useCallback(async () => {
    try {
      await upload.submitUpload();
    } catch {
      /* error handled in hook */
    }
  }, [upload]);

  const handleConfirmCancel = useCallback(() => {
    setCancelDialogOpen(false);
    void upload.cancelUpload();
  }, [upload]);

  /* ---- Collapsed summary ---- */
  const collapsedSummary = upload.uploadBusy
    ? "后台已有任务运行中。展开面板可查看当前输入并继续调整。"
    : upload.files.length
      ? `已准备 ${upload.files.length} 份文件，项目名：${upload.projectName || "未命名卷宗"}`
      : "当前未展开上传表单。展开后可直接发起新的种子分析。";

  return (
    <Card>
      <CardContent className="p-3.5 space-y-3">
        {/* Header */}
        <header className="flex items-start justify-between gap-3">
          <div>
            <div className="font-mono text-xs text-muted-foreground">启动新任务</div>
            <h2 className="mt-0.5 font-serif text-lg font-bold">卷宗投放</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              上传小说文本，填写分析目标，开始分析。
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setPanelExpanded(!panelExpanded)}
          >
            {panelExpanded ? "收起面板" : "展开面板"}
          </Button>
        </header>

        {/* Collapsed summary */}
        {!panelExpanded && (
          <div className="flex items-start justify-between gap-3 mt-3 rounded-xl border border-dashed bg-white/70 p-3">
            <span className="text-sm text-muted-foreground">{collapsedSummary}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPanelExpanded(true)}
            >
              继续编辑
            </Button>
          </div>
        )}

        {/* Expanded form */}
        {panelExpanded && (
          <div className="space-y-4 mt-3">
            {/* Project name */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium">项目/卷宗名称</label>
              <Input
                value={upload.projectName}
                onChange={(e) => upload.setField("projectName", e.target.value)}
                placeholder="例如：天穹秘约"
                disabled={upload.uploadBusy}
              />
            </div>

            {/* Dropzone */}
            <div
              className={cn(
                "flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all",
                upload.dragActive
                  ? "border-amber-600 bg-amber-50/30"
                  : "border-border hover:border-amber-500 hover:bg-white",
                upload.uploadBusy && "cursor-wait opacity-70",
              )}
              onDragEnter={handleDragOver}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={openPicker}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".txt,.md,.markdown,.pdf"
                className="hidden"
                onChange={handleChange}
              />
              <Upload className="h-10 w-10 text-muted-foreground/60" />
              {upload.files.length === 0 ? (
                <div>
                  <strong className="block text-base text-foreground">
                    拖拽文件到这里
                  </strong>
                  <span className="text-sm text-muted-foreground">
                    或点击选择 (txt, md, pdf)
                  </span>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2 justify-center">
                  {upload.files.map((file) => (
                    <div
                      key={upload.fileKey(file)}
                      className="flex items-center gap-1.5 rounded-full border bg-white px-3 py-1 text-sm shadow-sm"
                    >
                      <span className="truncate max-w-[160px]">{file.name}</span>
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          upload.removeFile(file);
                        }}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Advanced toggle */}
            <button
              type="button"
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-amber-700 select-none"
              onClick={() => setShowAdvanced(!showAdvanced)}
            >
              {showAdvanced ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              高级分析配置
            </button>

            {/* Advanced fields */}
            {showAdvanced && (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">分析目标</label>
                  <Textarea
                    value={upload.analysisGoal}
                    onChange={(e) =>
                      upload.setField("analysisGoal", e.target.value)
                    }
                    placeholder="明确您的分析重点，如：重点提取支线剧情与隐藏关系。"
                    disabled={upload.uploadBusy}
                    rows={3}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">补充背景</label>
                  <Textarea
                    value={upload.additionalContext}
                    onChange={(e) =>
                      upload.setField("additionalContext", e.target.value)
                    }
                    placeholder="提供世界观、术语表或既定设定，有助于提升分析精度。"
                    disabled={upload.uploadBusy}
                    rows={3}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">每段令牌上限</label>
                  <Input
                    type="number"
                    value={upload.segmentTokenLimit || ""}
                    onChange={(e) => {
                      const val = Number(e.target.value);
                      upload.setField(
                        "segmentTokenLimit",
                        Number.isNaN(val) ? 50000 : val,
                      );
                    }}
                    min={5000}
                    max={200000}
                    step={5000}
                    placeholder="50000"
                    disabled={upload.uploadBusy}
                  />
                  <span className="text-xs text-muted-foreground">
                    控制每个阅读段的最大令牌数，影响分析精度和速度。默认 50000。
                  </span>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-center gap-3 mt-3">
              <Button
                size="lg"
                disabled={!canSubmit || upload.uploadBusy}
                onClick={handleSubmit}
              >
                {upload.uploadBusy ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    分析进行中...
                  </>
                ) : (
                  "开始分析"
                )}
              </Button>
              {upload.uploadBusy && upload.uploadPhase === "processing" && (
                <Button
                  variant="outline"
                  size="lg"
                  onClick={() => setCancelDialogOpen(true)}
                >
                  取消分析
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Error */}
        {upload.error && (
          <div className="mt-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm font-mono text-destructive">
            {upload.error}
          </div>
        )}

        {/* Cancel confirmation dialog */}
        <Dialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>取消分析</DialogTitle>
              <DialogDescription>
                确定要取消当前分析任务吗？已完成的分析数据将保留。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setCancelDialogOpen(false)}
              >
                继续分析
              </Button>
              <Button variant="destructive" onClick={handleConfirmCancel}>
                确认取消
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}
