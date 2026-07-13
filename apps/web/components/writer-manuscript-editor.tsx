"use client";

import dynamic from "next/dynamic";

import type { Locale } from "../lib/locale";
import type { SelectionAction } from "./writer-selection-toolbar";

export type PendingRevision = {
  baseText: string;
  proposedText: string;
  blockId?: string;
  selectionText?: string;
  proposedSelectionText?: string;
  selectionStart?: number;
  selectionEnd?: number;
  expectedVersion?: number;
  instruction?: string;
  eventId?: string;
};

export type WriterManuscriptEditorProps = {
  locale: Locale;
  blockId: string;
  content: string;
  onReviseSelection?: (payload: {
    action: SelectionAction;
    instruction: string;
    selectionText: string;
    selectionStart: number;
    selectionEnd: number;
  }) => void;
  pendingRevision?: PendingRevision | null;
  onRevisionResolved?: () => void;
  onContentChange?: (text: string, meta: { dirty: boolean; wordCount: number }) => void;
  onRequestSave?: () => void;
};

/**
 * Dynamically loaded TipTap manuscript editor (ssr: false).
 * Heavy ProseMirror dependencies stay in a separate client chunk so the base
 * writer route does not pay for the editor until the manuscript panel hydrates.
 */
export const WriterManuscriptEditor = dynamic<WriterManuscriptEditorProps>(
  () => import("./writer-manuscript-editor-inner"),
  {
    ssr: false,
    loading: () => (
      <div className="writer-manuscript-editor-loading" aria-hidden="true">
        <div className="writer-manuscript-paper writer-manuscript-skeleton" />
      </div>
    ),
  },
);
