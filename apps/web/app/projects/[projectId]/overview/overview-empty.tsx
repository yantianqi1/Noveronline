"use client";

import { motion } from "motion/react";
import { FileUp, Sparkles } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { isSupportedSourceFile, UPLOAD_PHASE_LABELS, type UploadPhase } from "@/lib/api/upload";

/**
 * First-run empty state: no source files, no analysis yet. A calm, inviting
 * drop zone that explains what analysis will produce, in the same editorial
 * voice as the login cover.
 */
export function OverviewEmpty({
  onUpload,
  uploadPhase,
  uploadError,
  canAct,
}: {
  onUpload: (file: File) => void;
  uploadPhase: UploadPhase | null;
  uploadError: string | null;
  canAct: boolean;
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
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="mt-8"
    >
      <div className="mx-auto max-w-[680px] overflow-hidden rounded-card border border-line bg-panel shadow-panel">
        {/* intro */}
        <div className="border-b border-line-soft px-9 pt-9 pb-7 text-center">
          <span className="mx-auto grid size-14 place-items-center rounded-full bg-accent-wash text-accent">
            <Sparkles className="size-6" aria-hidden />
          </span>
          <h2 className="mt-5 font-serif text-[24px] font-semibold text-ink">从一份原文开始</h2>
          <p className="mx-auto mt-2.5 max-w-[440px] text-[13.5px] leading-relaxed text-muted">
            上传小说原文，分析会读出人物、关系、伏笔与世界规则，为这部作品搭起可探索、可写作的底子。
          </p>
        </div>

        {/* drop zone */}
        <div className="px-9 py-8">
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
            className={`flex cursor-pointer flex-col items-center justify-center rounded-[12px] border border-dashed px-8 py-12 text-center transition-all duration-200 ${
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
            {busy ? (
              <>
                <span className="grid size-12 place-items-center rounded-full bg-accent text-white">
                  <motion.span
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    className="block size-5 rounded-full border-2 border-white/40 border-t-white"
                  />
                </span>
                <p className="mt-4 text-[14px] font-medium text-ink">
                  正在{UPLOAD_PHASE_LABELS[uploadPhase]}…
                </p>
              </>
            ) : (
              <>
                <span className="grid size-12 place-items-center rounded-full bg-accent-wash text-accent">
                  <FileUp className="size-5" aria-hidden />
                </span>
                <p className="mt-4 text-[14px] font-medium text-ink">
                  拖拽原文到这里，或<span className="text-accent">点击选择文件</span>
                </p>
                <p className="mt-1.5 text-[12px] text-muted">支持 TXT / MD / PDF，上传后即可开始分析</p>
              </>
            )}
          </div>

          {(localError || uploadError) && (
            <p className="pt-3 text-center text-[12.5px] text-accent">{localError ?? uploadError}</p>
          )}
        </div>
      </div>
    </motion.div>
  );
}
