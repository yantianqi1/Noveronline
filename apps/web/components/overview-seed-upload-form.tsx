"use client";

import { Upload } from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

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
  const maxLabel = useMemo(() => formatMegabytes(SOURCE_UPLOAD_MAX_BYTES), []);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    const form = event.currentTarget;
    const input = form.elements.namedItem("file");
    if (!(input instanceof HTMLInputElement) || !input.files?.length) {
      setError(tx(locale, "请选择源文件", "Choose a source file"));
      event.preventDefault();
      return;
    }
    const file = input.files[0];
    if (file.size <= 0) {
      setError(tx(locale, "请选择源文件", "Choose a source file"));
      event.preventDefault();
      return;
    }
    if (file.size > SOURCE_UPLOAD_MAX_BYTES) {
      setError(
        tx(
          locale,
          `文件超过 ${maxLabel} 上限，请压缩或拆分后再上传。`,
          `File exceeds the ${maxLabel} limit. Compress or split it, then try again.`,
        ),
      );
      event.preventDefault();
      return;
    }
    setError("");
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
      <form action={action} className="binding-form" onSubmit={onSubmit}>
        <label htmlFor="source-file"><Bi zh="源文件" en="Source file" /></label>
        <input
          accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
          id="source-file"
          name="file"
          onChange={() => setError("")}
          required
          type="file"
        />
        <label htmlFor="seed-mode"><Bi zh="分析方式" en="Analysis mode" /></label>
        <select id="seed-mode" name="mode" defaultValue="full">
          <option value="full">{tx(locale, "完整分析", "Full analysis")}</option>
          <option value="resume">{tx(locale, "继续分析", "Continue analysis")}</option>
        </select>
        <SubmitButton
          idleLabel={<><Upload aria-hidden="true" size={18} /><Bi zh="上传并开始分析" en="Upload and start analysis" /></>}
          pendingLabel={<Bi zh="上传中…" en="Uploading…" />}
        />
      </form>
      <p className="form-hint">
        <Bi
          zh={`支持 TXT、Markdown 和 PDF 文件，单个文件最大 ${maxLabel}。`}
          en={`Supports TXT, Markdown, and PDF files up to ${maxLabel}.`}
        />
      </p>
    </>
  );
}

function formatMegabytes(bytes: number) {
  const mb = bytes / (1024 * 1024);
  return Number.isInteger(mb) ? `${mb} MB` : `${mb.toFixed(1)} MB`;
}
