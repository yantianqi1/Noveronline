"use client";

import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Bold, Italic, Quote, Redo2, Type, Undo2 } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import {
  acceptAllHunks,
  applyHunkDecisions,
  computeRevisionHunks,
  type ApplyHunkDecision,
  type DiffHunk,
} from "../lib/writer-diff";
import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { WriterRevisionDiff } from "./writer-revision-diff";
import { WriterSelectionToolbar, type SelectionAction } from "./writer-selection-toolbar";

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
  /** Optional revise run starter; receives selection + instruction fields. */
  onReviseSelection?: (payload: {
    action: SelectionAction;
    instruction: string;
    selectionText: string;
    selectionStart: number;
    selectionEnd: number;
  }) => void;
  pendingRevision?: PendingRevision | null;
  onRevisionResolved?: () => void;
  /** Called when the hidden textarea content changes (for parent save-state chips). */
  onContentChange?: (text: string, meta: { dirty: boolean; wordCount: number }) => void;
  /** Blur auto-save: parent form should call requestSubmit. */
  onRequestSave?: () => void;
};

/**
 * TipTap manuscript surface with progressive-enhancement form source.
 *
 * Renders a hidden `<textarea name="content">` as the true form field so
 * no-JS and server actions keep working. Parent form owns `action`, blockId,
 * expectedVersion, status, and submit controls.
 */
export default function WriterManuscriptEditorInner({
  locale,
  blockId,
  content,
  onReviseSelection,
  pendingRevision = null,
  onRevisionResolved,
  onContentChange,
  onRequestSave,
}: WriterManuscriptEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const paperRef = useRef<HTMLDivElement>(null);
  const [wordCount, setWordCount] = useState(() => countWords(content));
  const [dirty, setDirty] = useState(false);
  const [selection, setSelection] = useState<{ text: string; from: number; to: number } | null>(null);
  const [hunks, setHunks] = useState<DiffHunk[]>([]);
  const [decisions, setDecisions] = useState<Record<string, ApplyHunkDecision>>({});
  const blurTimer = useRef<number | null>(null);
  const editorId = useId();

  const syncText = useCallback(
    (text: string, nextDirty: boolean) => {
      const words = countWords(text);
      setWordCount(words);
      setDirty(nextDirty);
      if (textareaRef.current) {
        textareaRef.current.value = text;
      }
      onContentChange?.(text, { dirty: nextDirty, wordCount: words });
    },
    [onContentChange],
  );

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        code: false,
        horizontalRule: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
      }),
      Placeholder.configure({
        placeholder: tx(locale, "在此书写正文……", "Write manuscript prose here…"),
      }),
    ],
    content: plainTextToDoc(content),
    editorProps: {
      attributes: {
        class: "writer-manuscript-prose",
        "aria-label": tx(locale, "手稿正文", "Manuscript prose"),
        id: `writer-manuscript-surface-${editorId}`,
      },
    },
    onUpdate: ({ editor: next }) => {
      syncText(next.getText({ blockSeparator: "\n" }), true);
    },
    onSelectionUpdate: ({ editor: next }) => {
      const { from, to, empty } = next.state.selection;
      if (empty) {
        setSelection(null);
        return;
      }
      const selected = next.state.doc.textBetween(from, to, "\n");
      if (!selected.trim()) {
        setSelection(null);
        return;
      }
      const before = next.state.doc.textBetween(0, from, "\n");
      setSelection({
        text: selected,
        from: before.length,
        to: before.length + selected.length,
      });
    },
    immediatelyRender: false,
  });

  useEffect(() => {
    if (!editor) return;
    const current = editor.getText({ blockSeparator: "\n" });
    if (current === content) return;
    editor.commands.setContent(plainTextToDoc(content), { emitUpdate: false });
    syncText(content, false);
  }, [blockId, content, editor, syncText]);

  useEffect(() => {
    if (!pendingRevision) {
      setHunks([]);
      setDecisions({});
      return;
    }
    setHunks(computeRevisionHunks(pendingRevision.baseText, pendingRevision.proposedText));
    setDecisions({});
  }, [pendingRevision]);

  useEffect(() => {
    return () => {
      if (blurTimer.current) window.clearTimeout(blurTimer.current);
    };
  }, []);

  const handleBlur = useCallback(() => {
    if (blurTimer.current) window.clearTimeout(blurTimer.current);
    blurTimer.current = window.setTimeout(() => {
      if (dirty) onRequestSave?.();
    }, 450);
  }, [dirty, onRequestSave]);

  const handleSelectionAction = useCallback(
    (action: SelectionAction, freeInstruction?: string) => {
      if (!selection || !onReviseSelection) return;
      const instruction = freeInstruction?.trim() || presetInstruction(locale, action);
      onReviseSelection({
        action,
        instruction,
        selectionText: selection.text,
        selectionStart: selection.from,
        selectionEnd: selection.to,
      });
      setSelection(null);
    },
    [locale, onReviseSelection, selection],
  );

  const applyRevisionToEditor = useCallback(
    (nextText: string) => {
      // Accept applies a full-block optimistic patch via the parent form's
      // updateManuscriptBlock path — never draft adoption.
      editor?.commands.setContent(plainTextToDoc(nextText), { emitUpdate: false });
      syncText(nextText, true);
      setHunks([]);
      setDecisions({});
      window.setTimeout(() => onRequestSave?.(), 0);
      onRevisionResolved?.();
    },
    [editor, onRequestSave, onRevisionResolved, syncText],
  );

  return (
    <div className="writer-manuscript-editor" data-editor="tiptap" data-dirty={dirty ? "true" : "false"}>
      <div className="writer-manuscript-chrome">
        <div className="writer-manuscript-toolbar" role="toolbar" aria-label={tx(locale, "正文格式", "Prose formatting")}>
          <ToolbarButton
            label={tx(locale, "段落", "Paragraph")}
            disabled={!editor}
            onClick={() => editor?.chain().focus().setParagraph().run()}
          >
            <Type aria-hidden="true" size={15} />
          </ToolbarButton>
          <ToolbarButton
            label={tx(locale, "强调", "Bold")}
            pressed={editor?.isActive("bold")}
            disabled={!editor}
            onClick={() => editor?.chain().focus().toggleBold().run()}
          >
            <Bold aria-hidden="true" size={15} />
          </ToolbarButton>
          <ToolbarButton
            label={tx(locale, "斜体", "Italic")}
            pressed={editor?.isActive("italic")}
            disabled={!editor}
            onClick={() => editor?.chain().focus().toggleItalic().run()}
          >
            <Italic aria-hidden="true" size={15} />
          </ToolbarButton>
          <ToolbarButton
            label={tx(locale, "引用", "Blockquote")}
            pressed={editor?.isActive("blockquote")}
            disabled={!editor}
            onClick={() => editor?.chain().focus().toggleBlockquote().run()}
          >
            <Quote aria-hidden="true" size={15} />
          </ToolbarButton>
          <span className="writer-toolbar-sep" aria-hidden="true" />
          <ToolbarButton
            label={tx(locale, "撤销", "Undo")}
            disabled={!editor?.can().undo()}
            onClick={() => editor?.chain().focus().undo().run()}
          >
            <Undo2 aria-hidden="true" size={15} />
          </ToolbarButton>
          <ToolbarButton
            label={tx(locale, "重做", "Redo")}
            disabled={!editor?.can().redo()}
            onClick={() => editor?.chain().focus().redo().run()}
          >
            <Redo2 aria-hidden="true" size={15} />
          </ToolbarButton>
          <span className="writer-word-count" aria-live="polite">
            {wordCount} <Bi zh="字" en="words" />
          </span>
        </div>

        <div ref={paperRef} className="writer-manuscript-paper" onBlur={handleBlur}>
          {selection && onReviseSelection ? (
            <WriterSelectionToolbar
              locale={locale}
              selectionText={selection.text}
              onAction={handleSelectionAction}
            />
          ) : null}
          <EditorContent editor={editor} />
        </div>
      </div>

      {hunks.length > 0 && pendingRevision ? (
        <WriterRevisionDiff
          locale={locale}
          hunks={hunks}
          decisions={decisions}
          onDecide={(id, decision) => setDecisions((current) => ({ ...current, [id]: decision }))}
          onAcceptAll={() =>
            applyRevisionToEditor(acceptAllHunks(pendingRevision.baseText, pendingRevision.proposedText))
          }
          onRejectAll={() => {
            setHunks([]);
            setDecisions({});
            onRevisionResolved?.();
          }}
          onApplyPartial={() =>
            applyRevisionToEditor(applyHunkDecisions(pendingRevision.baseText, hunks, decisions))
          }
        />
      ) : null}

      {/* Parent form owns the PE textarea name="content"; this editor only mirrors into it. */}
      <textarea
        ref={textareaRef}
        className="writer-prose-textarea writer-prose-textarea-mirror"
        defaultValue={content}
        rows={2}
        tabIndex={-1}
        aria-hidden="true"
        data-editor-mirror="true"
        readOnly
        hidden
      />
    </div>
  );
}

function ToolbarButton({
  label,
  pressed,
  disabled,
  onClick,
  children,
}: {
  label: string;
  pressed?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className="writer-editor-tool"
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function plainTextToDoc(text: string) {
  const paragraphs = String(text ?? "").split("\n");
  return {
    type: "doc",
    content: paragraphs.map((line) => ({
      type: "paragraph",
      content: line ? [{ type: "text", text: line }] : [],
    })),
  };
}

function countWords(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  const cjk = trimmed.match(/[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]/g)?.length ?? 0;
  const latin = trimmed
    .replace(/[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]/g, " ")
    .split(/\s+/)
    .filter(Boolean).length;
  return cjk + latin;
}

function presetInstruction(locale: Locale, action: SelectionAction) {
  switch (action) {
    case "rewrite":
      return tx(locale, "改写选中段落，保持人物与语气一致。", "Rewrite the selection; keep voice and characters.");
    case "expand":
      return tx(locale, "扩写选中段落，补充细节与画面。", "Expand the selection with concrete detail.");
    case "condense":
      return tx(locale, "精简选中段落，去掉冗余。", "Condense the selection; remove redundancy.");
    case "polish":
      return tx(locale, "润色选中段落的文笔与节奏。", "Polish the selection for cadence and diction.");
    case "correct":
      return tx(locale, "按设定校正选中段落中的事实与称呼。", "Correct the selection against established canon.");
    default:
      return tx(locale, "修订选中段落。", "Revise the selection.");
  }
}
