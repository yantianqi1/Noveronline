"use client";

import { Save } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { WriterManuscriptEditor, type PendingRevision } from "./writer-manuscript-editor";
import type { SelectionAction } from "./writer-selection-toolbar";

type WriterManuscriptPanelClientProps = {
  locale: Locale;
  blockId: string;
  expectedVersion: number;
  content: string;
  status: string;
  updateBlockAction: (formData: FormData) => Promise<void>;
  reviseAction?: (formData: FormData) => Promise<void>;
  pendingRevision?: PendingRevision | null;
};

/**
 * Client boundary for manuscript form + TipTap hydrate + revise selection.
 *
 * Always renders `<textarea name="content">` as the progressive-enhancement form
 * source; TipTap (dynamic, ssr:false) mirrors into it when available.
 */
export function WriterManuscriptPanelClient({
  locale,
  blockId,
  expectedVersion,
  content,
  status,
  updateBlockAction,
  reviseAction,
  pendingRevision = null,
}: WriterManuscriptPanelClientProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const peTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [revision, setRevision] = useState<PendingRevision | null>(pendingRevision);
  const [statusValue, setStatusValue] = useState(status);
  const [enhanced, setEnhanced] = useState(false);

  const requestSave = useCallback(() => {
    formRef.current?.requestSubmit();
  }, []);

  const handleContentChange = useCallback((text: string) => {
    if (peTextareaRef.current) {
      peTextareaRef.current.value = text;
    }
    setEnhanced(true);
  }, []);

  const handleRevise = useCallback(
    (payload: {
      action: SelectionAction;
      instruction: string;
      selectionText: string;
      selectionStart: number;
      selectionEnd: number;
    }) => {
      if (!reviseAction) return;
      const data = new FormData();
      data.set("mode", "revise");
      data.set("instruction", payload.instruction);
      data.set("blockId", blockId);
      data.set("selectionText", payload.selectionText);
      data.set("selectionStart", String(payload.selectionStart));
      data.set("selectionEnd", String(payload.selectionEnd));
      data.set("expectedVersion", String(expectedVersion));
      data.set("reviseAction", payload.action);
      void reviseAction(data);
    },
    [blockId, expectedVersion, reviseAction],
  );

  return (
    <form ref={formRef} action={updateBlockAction} className="binding-form writer-prose-form" data-manuscript-editor-form="true">
      <input name="blockId" type="hidden" value={blockId} />
      <input name="expectedVersion" type="hidden" value={expectedVersion} />

      <WriterManuscriptEditor
        locale={locale}
        blockId={blockId}
        content={content}
        onRequestSave={requestSave}
        onContentChange={(text) => handleContentChange(text)}
        onReviseSelection={reviseAction ? handleRevise : undefined}
        pendingRevision={revision}
        onRevisionResolved={() => setRevision(null)}
      />

      {/* Form truth source — always present for PE / no-JS / pre-hydrate. */}
      <textarea
        ref={peTextareaRef}
        name="content"
        className={enhanced ? "writer-prose-textarea writer-prose-textarea-mirror" : "writer-prose-textarea"}
        defaultValue={content}
        rows={16}
        aria-label={tx(locale, "手稿正文", "Manuscript prose")}
        data-pe-source="true"
      />

      <div className="writer-prose-toolbar">
        <select
          aria-label={tx(locale, "状态", "Status")}
          name="status"
          value={statusValue}
          onChange={(event) => setStatusValue(event.target.value)}
        >
          <option value="active">{tx(locale, "进行中", "Active")}</option>
          <option value="draft">{tx(locale, "草稿", "Draft")}</option>
          <option value="archived">{tx(locale, "已归档", "Archived")}</option>
        </select>
        <button data-tone="primary" type="submit">
          <Save size={14} />
          <Bi zh="保存正文" en="Save prose" />
        </button>
      </div>
    </form>
  );
}
