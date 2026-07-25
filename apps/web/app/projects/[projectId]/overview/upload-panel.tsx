"use client";

import { AnimatePresence, motion } from "motion/react";
import { FileText, Loader2, Play, Trash2, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import { formatBytes, isSupportedSourceFile, UPLOAD_PHASE_LABELS, type UploadPhase } from "@/lib/api/upload";
import type { SourceFile } from "@/lib/api/overview-types";

/**
 * Source-text import card: a drop zone for TXT/MD/PDF plus the list of files
 * already imported, each with a "开始分析" action. The drop zone shows the
 * honest upload phase while a file is in flight.
 */
export function UploadPanel({
  sourceFiles,
  onUpload,
  onStart,
  onDelete,
  uploadPhase,
  uploadError,
  actionError,
  canAct,
  analysisRunning,
  deletingId,
}: {
  sourceFiles: SourceFile[];
  onUpload: (file: File) => void;
  onStart: (uploadId: string) => void;
  onDelete: (uploadId: string) => void;
  uploadPhase: UploadPhase | null;
  uploadError: string | null;
  actionError: string | null;
  canAct: boolean;
  analysisRunning: boolean;
  deletingId: string | null;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const busy = uploadPhase !== null;

  function pickFile(file: File | undefined | null) {
    setLocalError(null);
    if (!file) return;
    if (!isSupportedSourceFile(file.name)) {
      setLocalError("仅支持 TXT / MD / PDF 原文文件。");
      return;
    }
    onUpload(file);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    if (busy || !canAct) return;
    pickFile(event.dataTransfer.files?.[0]);
  }

  return (
    <section className="overflow-hidden rounded-card border border-line bg-panel shadow-[0_1px_2px_rgba(23,26,27,0.05)]">
      <div className="border-b border-line-soft px-6 py-4">
        <h2 className="font-serif text-[18px] font-semibold text-ink">原文</h2>
        <p className="mt-0.5 text-[12.5px] text-muted">上传小说原文，或从已有原文开始一次新的分析。</p>
      </div>

      <div className="px-6 py-5">
        {/* drop zone */}
        <div
          role="button"
          tabIndex={0}
          aria-label="上传原文"
          onClick={() => !busy && canAct && inputRef.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && canAct && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            if (!busy && canAct) setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-[12px] border border-dashed px-6 py-8 text-center transition-all duration-200 ${
            dragOver
              ? "border-accent bg-accent-wash"
              : "border-line bg-paper/60 hover:border-accent/40 hover:bg-accent-wash/50"
          } ${busy || !canAct ? "cursor-default opacity-70" : ""}`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
            className="hidden"
            onChange={(e) => {
              pickFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <AnimatePresence mode="wait">
            {busy ? (
              <motion.div
                key="busy"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center"
              >
                <Loader2 className="size-6 animate-spin text-accent" aria-hidden />
                <p className="mt-3 text-[13.5px] font-medium text-ink">
                  正在{UPLOAD_PHASE_LABELS[uploadPhase]}…
                </p>
                <p className="mt-1 text-[12px] text-muted">请勿关闭页面</p>
              </motion.div>
            ) : (
              <motion.div
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center"
              >
                <span className="grid size-11 place-items-center rounded-full bg-accent-wash text-accent">
                  <UploadCloud className="size-5" aria-hidden />
                </span>
                <p className="mt-3.5 text-[13.5px] font-medium text-ink">
                  拖拽原文到这里，或<span className="text-accent">点击选择文件</span>
                </p>
                <p className="mt-1 text-[12px] text-muted">支持 TXT / MD / PDF</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* errors */}
        <AnimatePresence>
          {(localError || uploadError || actionError) && (
            <motion.p
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden pt-3 text-[12.5px] text-accent"
            >
              {localError ?? uploadError ?? actionError}
            </motion.p>
          )}
        </AnimatePresence>

        {/* existing source files */}
        {sourceFiles.length > 0 && (
          <ul className="mt-5 space-y-2.5">
            {sourceFiles.map((file, index) => (
              <motion.li
                key={file.file_id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05, duration: 0.3 }}
                className="flex items-center gap-3.5 rounded-[10px] border border-line-soft bg-paper/50 px-4 py-3"
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-[8px] bg-accent-wash text-accent">
                  <FileText className="size-4" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] font-medium text-ink">{file.filename}</p>
                  <p className="mt-0.5 text-[11.5px] text-muted">
                    {formatBytes(file.size_bytes)} · {parseStatusLabel(file.parse_status)}
                  </p>
                </div>
                <Button
                  size="sm"
                  onClick={() => onStart(file.upload_id)}
                  disabled={!canAct || analysisRunning}
                  loading={false}
                >
                  <Play className="size-3.5" aria-hidden />
                  {analysisRunning ? "分析中" : "开始分析"}
                </Button>
                <button
                  type="button"
                  aria-label="删除原文"
                  title="删除原文"
                  onClick={() => onDelete(file.upload_id)}
                  disabled={!canAct || deletingId !== null}
                  className="grid size-9 shrink-0 place-items-center rounded-[8px] text-muted transition-colors hover:bg-accent-wash hover:text-accent disabled:pointer-events-none disabled:opacity-50"
                >
                  {deletingId === file.upload_id ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="size-4" aria-hidden />
                  )}
                </button>
              </motion.li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function parseStatusLabel(status: string): string {
  switch ((status ?? "").toLowerCase()) {
    case "completed":
    case "ready":
    case "parsed":
      return "已就绪";
    case "pending":
    case "processing":
      return "处理中";
    case "failed":
      return "解析失败";
    default:
      return status || "已上传";
  }
}
