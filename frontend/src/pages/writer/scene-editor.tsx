/**
 * SceneEditor — streaming-aware content editor for the active scene.
 * Displays streaming text with a blinking cursor or an editable textarea.
 */

import * as React from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

interface SceneEditorProps {
  content: string;
  streaming: boolean;
  readonly?: boolean;
  onUpdate?: (content: string) => void;
  onCommitSelection?: (text: string) => void;
}

export function SceneEditor({
  content,
  streaming,
  readonly,
  onUpdate,
  onCommitSelection,
}: SceneEditorProps) {
  const [showToolbar, setShowToolbar] = React.useState(false);
  const [toolbarPos, setToolbarPos] = React.useState({ top: 0, left: 0 });
  const selectedTextRef = React.useRef("");

  React.useEffect(() => {
    function handleSelectionChange() {
      const sel = window.getSelection();
      if (sel && sel.toString().trim().length > 0) {
        selectedTextRef.current = sel.toString();
        const range = sel.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        setToolbarPos({
          top: rect.top - 40,
          left: rect.left + rect.width / 2 - 60,
        });
        setShowToolbar(true);
      } else {
        setShowToolbar(false);
      }
    }

    document.addEventListener("selectionchange", handleSelectionChange);
    return () =>
      document.removeEventListener("selectionchange", handleSelectionChange);
  }, []);

  function handleCommitSelection() {
    if (selectedTextRef.current.trim() && onCommitSelection) {
      onCommitSelection(selectedTextRef.current);
      setShowToolbar(false);
    }
  }

  return (
    <div className="relative flex h-full flex-col">
      {streaming ? (
        <div className="flex-1 overflow-y-auto whitespace-pre-wrap break-words p-3.5 text-sm leading-relaxed text-foreground">
          {content}
          <span className="animate-pulse text-blue-400">&#x2588;</span>
        </div>
      ) : (
        <Textarea
          className="min-h-[400px] flex-1 resize-y border-0 p-3.5 text-sm leading-relaxed focus-visible:ring-0"
          value={content}
          onChange={(e) => onUpdate?.(e.target.value)}
          readOnly={readonly}
          placeholder="场景内容将在此处显示..."
        />
      )}

      {showToolbar && (
        <div
          className="fixed z-50 flex gap-1 rounded-md bg-gray-800 px-1.5 py-1 shadow-lg"
          style={{ top: toolbarPos.top, left: toolbarPos.left }}
        >
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs text-white hover:text-white"
            onClick={handleCommitSelection}
          >
            提交选中
          </Button>
        </div>
      )}
    </div>
  );
}
