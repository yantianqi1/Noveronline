"use client";

import { FileUp, Upload } from "lucide-react";
import { useMemo, useState, type ChangeEvent, type DragEvent, type FormEvent, type ReactNode } from "react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { SubmitButton } from "./submit-button";

/** Keep in sync with apps/web/next.config.ts experimental.serverActions.bodySizeLimit. */
export const SOURCE_UPLOAD_MAX_BYTES = 64 * 1024 * 1024;

type OverviewSeedUploadFormProps = {
  action: (formData: FormData) => Promise<void>;
  locale: Locale;
  sourceStatus: ReactNode;
  seedStatus: ReactNode;
};

export function OverviewSeedUploadForm({
  action,
  locale,
  sourceStatus,
  seedStatus,
}: OverviewSeedUploadFormProps) {
  const [error, setError] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const maxLabel = useMemo(() => formatMegabytes(SOURCE_UPLOAD_MAX_BYTES), []);

  function validateFile(file: File | undefined | null) {
    if (!file) {
      return tx(locale, "请选择源文件", "Choose a source file");
    }
    if (file.size <= 0) {
      return tx(locale, "请选择源文件", "Choose a source file");
    }
    if (file.size > SOURCE_UPLOAD_MAX_BYTES) {
      return tx(
        locale,
        `文件超过 ${maxLabel} 上限，请压缩或拆分后再上传。`,
        `File exceeds the ${maxLabel} limit. Compress or split it, then try again.`,
      );
    }
    return "";
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    const form = event.currentTarget;
    const input = form.elements.namedItem("file");
    if (!(input instanceof HTMLInputElement) || !input.files?.length) {
      setError(tx(locale, "请选择源文件", "Choose a source file"));
      event.preventDefault();
      return;
    }
    const message = validateFile(input.files[0]);
    if (message) {
      setError(message);
      event.preventDefault();
      return;
    }
    setError("");
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    setFileName(file?.name ?? "");
    setError(file ? validateFile(file) : "");
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    const input = event.currentTarget.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) {
      return;
    }
    const file = event.dataTransfer.files?.[0];
    if (!file) {
      return;
    }
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    setFileName(file.name);
    setError(validateFile(file));
  }

  return (
    <>
      {sourceStatus}
      {seedStatus}
      {error ? (
        <p className="form-status error-box" role="alert">
          {error}
        </p>
      ) : null}
      <form action={action} className="binding-form overview-upload-form" onSubmit={onSubmit}>
        <label
          className="overview-dropzone"
          data-dragging={dragging ? "true" : "false"}
          data-has-file={fileName ? "true" : "false"}
          htmlFor="source-file"
          onDragEnter={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
              return;
            }
            setDragging(false);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDrop={onDrop}
        >
          <span className="overview-dropzone-icon" aria-hidden="true">
            {fileName ? <FileUp size={20} strokeWidth={1.6} /> : <Upload size={20} strokeWidth={1.6} />}
          </span>
          <span className="overview-dropzone-copy">
            <strong>
              {fileName
                ? fileName
                : <Bi zh="选择或拖入小说文件" en="Choose or drop a manuscript" />}
            </strong>
            <small>
              {fileName
                ? <Bi zh="点击可重新选择" en="Click to choose another file" />
                : <Bi zh="TXT / Markdown / PDF" en="TXT / Markdown / PDF" />}
            </small>
          </span>
          <input
            accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
            className="overview-dropzone-input"
            id="source-file"
            name="file"
            onChange={onFileChange}
            required
            type="file"
          />
        </label>

        <div className="overview-upload-controls">
          <label htmlFor="seed-mode"><Bi zh="分析方式" en="Analysis mode" /></label>
          <select id="seed-mode" name="mode" defaultValue="full">
            <option value="full">{tx(locale, "完整分析", "Full analysis")}</option>
            <option value="focused">{tx(locale, "重点分析", "Focused analysis")}</option>
            <option value="resume">{tx(locale, "继续分析", "Continue analysis")}</option>
          </select>
          <label htmlFor="analysis-hints"><Bi zh="分析提示（可选）" en="Analysis hints (optional)" /></label>
          <textarea
            id="analysis-hints"
            name="hints"
            rows={3}
            placeholder={tx(
              locale,
              "例如：先拆前 10 章；关注权谋线与主要人物关系",
              "e.g. Focus on the first 10 chapters; track intrigue and main relationships",
            )}
          />
          <SubmitButton
            idleLabel={<><Upload aria-hidden="true" size={18} /><Bi zh="上传并开始分析" en="Upload and start analysis" /></>}
            pendingLabel={<Bi zh="上传中…" en="Uploading…" />}
          />
        </div>
      </form>
    </>
  );
}

function formatMegabytes(bytes: number) {
  const mb = bytes / (1024 * 1024);
  return Number.isInteger(mb) ? `${mb} MB` : `${mb.toFixed(1)} MB`;
}
