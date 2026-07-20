"use client";

import { Check, Loader2, Save } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { type Locale, tx } from "../lib/locale";
import { encodeLocalDraft, localDraftStorageKey } from "../lib/writer-local-draft";
import { Bi } from "./bilingual-text";
import { WriterManuscriptEditor, type PendingRevision } from "./writer-manuscript-editor";
import type { SelectionAction } from "./writer-selection-toolbar";

type WriterManuscriptPanelClientProps = {
  locale: Locale;
  blockId: string;
  expectedVersion: number;
  content: string;
  status: string;
  chapterId?: string;
  sceneId?: string;
  updateBlockAction: (formData: FormData) => Promise<void>;
  createBlockAction?: (formData: FormData) => Promise<void>;
  reviseAction?: (formData: FormData) => Promise<void>;
  pendingRevision?: PendingRevision | null;
  conflictLocalDraft?: string | null;
  workspaceStatus?: string | null;
  workspaceCode?: string | null;
};

type SaveState = "idle" | "dirty" | "saving" | "saved";

const AUTO_SAVE_DELAY_MS = 3000;

/**
 * Client boundary for manuscript form + TipTap hydrate + revise selection + conflict recovery.
 *
 * Always renders `<textarea name="content">` as the progressive-enhancement form
 * source; TipTap (dynamic, ssr:false) mirrors into it when available.
 *
 * Auto-save: content changes trigger a debounced save after 3 s of inactivity.
 * A compact indicator in the editor corner shows save state.
 */
export function WriterManuscriptPanelClient({
  locale,
  blockId,
  expectedVersion,
  content,
  status,
  chapterId = "",
  sceneId = "",
  updateBlockAction,
  createBlockAction,
  reviseAction,
  pendingRevision = null,
  conflictLocalDraft = null,
  workspaceStatus = null,
  workspaceCode = null,
}: WriterManuscriptPanelClientProps) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const peTextareaRef = useRef<HTMLTextAreaElement>(null);
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [revision, setRevision] = useState<PendingRevision | null>(pendingRevision);
  const [statusValue] = useState(status);
  const [enhanced, setEnhanced] = useState(false);
  const [liveContent, setLiveContent] = useState(content);
  const [localDraft, setLocalDraft] = useState(() => conflictLocalDraft ?? "");
  const [showConflict, setShowConflict] = useState(
    () => Boolean(conflictLocalDraft) && workspaceCode === "OPTIMISTIC_CONFLICT",
  );
  const [saveState, setSaveState] = useState<SaveState>("idle");

  useEffect(() => {
    setRevision(pendingRevision);
  }, [pendingRevision]);

  useEffect(() => {
    setEnhanced(true);
  }, [blockId]);

  useEffect(() => {
    setLiveContent(content);
    setSaveState("idle");
    if (peTextareaRef.current && !showConflict) {
      peTextareaRef.current.value = content;
    }
  }, [blockId, content, showConflict]);

  useEffect(() => {
    const fromQuery =
      conflictLocalDraft && conflictLocalDraft !== "session" ? conflictLocalDraft : "";
    let fromSession = "";
    try {
      fromSession = sessionStorage.getItem(localDraftStorageKey(blockId)) ?? "";
    } catch {
      fromSession = "";
    }
    const recovered = fromQuery || fromSession;
    if (!recovered) return;
    if (workspaceCode === "OPTIMISTIC_CONFLICT" || (workspaceStatus === "error" && recovered)) {
      setLocalDraft(recovered);
      setShowConflict(true);
      if (fromQuery) {
        try {
          sessionStorage.setItem(localDraftStorageKey(blockId), fromQuery);
        } catch {
          // sessionStorage may be unavailable; query-encoded draft remains.
        }
      }
    }
  }, [blockId, conflictLocalDraft, workspaceCode, workspaceStatus]);

  // Cleanup auto-save timer on unmount or block switch
  useEffect(() => {
    return () => {
      if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    };
  }, [blockId]);

  const doSave = useCallback(() => {
    if (!formRef.current) return;
    setSaveState("saving");
    formRef.current.requestSubmit();
  }, []);

  const requestSave = useCallback(() => {
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    doSave();
  }, [doSave]);

  const handleContentChange = useCallback((text: string) => {
    setLiveContent(text);
    if (peTextareaRef.current) {
      peTextareaRef.current.value = text;
    }
    setEnhanced(true);
    setSaveState("dirty");
    try {
      sessionStorage.setItem(localDraftStorageKey(blockId), text);
    } catch {
      // ignore
    }
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(() => {
      doSave();
    }, AUTO_SAVE_DELAY_MS);
  }, [blockId, doSave]);

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

  const clearConflictQuery = useCallback(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.delete("localDraft");
    if (url.searchParams.get("workspaceCode") === "OPTIMISTIC_CONFLICT") {
      url.searchParams.delete("workspaceCode");
      url.searchParams.delete("workspaceStatus");
    }
    router.replace(`${url.pathname}?${url.searchParams.toString()}`);
  }, [router]);

  const submitBlockUpdate = useCallback(
    (nextContent: string, version: number) => {
      const data = new FormData();
      data.set("blockId", blockId);
      data.set("expectedVersion", String(version));
      data.set("content", nextContent);
      data.set("status", statusValue);
      data.set("localDraft", nextContent);
      void updateBlockAction(data);
    },
    [blockId, statusValue, updateBlockAction],
  );

  const overwriteWithLocal = useCallback(() => {
    submitBlockUpdate(localDraft, expectedVersion);
  }, [expectedVersion, localDraft, submitBlockUpdate]);

  const saveAsNewBlock = useCallback(() => {
    if (!createBlockAction) return;
    const data = new FormData();
    data.set("chapterId", chapterId);
    data.set("sceneId", sceneId);
    data.set("content", localDraft);
    data.set("contentText", localDraft);
    void createBlockAction(data);
  }, [chapterId, createBlockAction, localDraft, sceneId]);

  const discardLocal = useCallback(() => {
    setShowConflict(false);
    setLocalDraft("");
    setLiveContent(content);
    if (peTextareaRef.current) {
      peTextareaRef.current.value = content;
    }
    try {
      sessionStorage.removeItem(localDraftStorageKey(blockId));
    } catch {
      // ignore
    }
    clearConflictQuery();
  }, [blockId, clearConflictQuery, content]);

  const keepLocalInEditor = useCallback(() => {
    setShowConflict(false);
    setLiveContent(localDraft);
    if (peTextareaRef.current) {
      peTextareaRef.current.value = localDraft;
    }
    setEnhanced(true);
    clearConflictQuery();
  }, [clearConflictQuery, localDraft]);

  const handleFormAction = useCallback(
    async (formData: FormData) => {
      const contentText = String(formData.get("content") ?? liveContent);
      formData.set("content", contentText);
      formData.set("localDraft", contentText);
      formData.set("expectedVersion", String(expectedVersion));
      formData.set("blockId", blockId);
      formData.set("status", statusValue);
      try {
        sessionStorage.setItem(localDraftStorageKey(blockId), contentText);
      } catch {
        // ignore
      }
      await updateBlockAction(formData);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    },
    [blockId, expectedVersion, liveContent, statusValue, updateBlockAction],
  );

  const editorContent = showConflict && localDraft ? localDraft : liveContent;

  return (
    <div className="writer-manuscript-panel-client" data-conflict={showConflict ? "true" : "false"}>
      {showConflict && localDraft ? (
        <section className="writer-conflict-compare" data-conflict-panel="true" aria-labelledby="writer-conflict-heading">
          <header className="writer-conflict-compare-head">
            <div>
              <p className="eyebrow"><Bi zh="并发冲突" en="Concurrent edit" /></p>
              <h3 id="writer-conflict-heading">
                <Bi zh="服务端正文与本地草稿不一致" en="Server content differs from your local draft" />
              </h3>
              <p className="form-hint">
                <Bi
                  zh="保存时版本已变化。请比较后选择覆盖、另存新片段，或丢弃本地修改。"
                  en="The section version changed while you were editing. Compare, then overwrite, save as a new section, or discard your local draft."
                />
              </p>
            </div>
          </header>
          <div className="writer-conflict-columns">
            <article className="writer-conflict-column" data-side="server">
              <strong><Bi zh="服务端当前正文" en="Server content" /></strong>
              <pre className="writer-conflict-body">{content || tx(locale, "（空）", "(empty)")}</pre>
              <small>v{expectedVersion}</small>
            </article>
            <article className="writer-conflict-column" data-side="local">
              <strong><Bi zh="你的本地草稿" en="Your local draft" /></strong>
              <pre className="writer-conflict-body">{localDraft || tx(locale, "（空）", "(empty)")}</pre>
            </article>
          </div>
          <div className="writer-conflict-actions">
            <button type="button" data-tone="primary" onClick={overwriteWithLocal}>
              <Bi zh="用本地草稿覆盖（刷新期望版本）" en="Overwrite with local draft (refresh expected version)" />
            </button>
            {createBlockAction ? (
              <button type="button" onClick={saveAsNewBlock}>
                <Bi zh="另存为新片段" en="Save as new section" />
              </button>
            ) : null}
            <button type="button" onClick={keepLocalInEditor}>
              <Bi zh="保留本地并继续编辑" en="Keep local and continue editing" />
            </button>
            <button type="button" data-tone="danger" onClick={discardLocal}>
              <Bi zh="丢弃本地草稿" en="Discard local draft" />
            </button>
          </div>
          <input type="hidden" name="localDraftEncoded" value={encodeLocalDraft(localDraft)} readOnly />
        </section>
      ) : null}

      <form ref={formRef} action={handleFormAction} className="binding-form writer-prose-form" data-manuscript-editor-form="true">
        <input name="blockId" type="hidden" value={blockId} />
        <input name="expectedVersion" type="hidden" value={expectedVersion} />
        <input name="localDraft" type="hidden" value={editorContent} />
        <input name="status" type="hidden" value={statusValue} />

        <div className="writer-editor-save-indicator" data-save-state={saveState}>
          {saveState === "saving" ? (
            <><Loader2 size={13} className="writer-save-spin" /><Bi zh="保存中" en="Saving" /></>
          ) : saveState === "saved" ? (
            <><Check size={13} /><Bi zh="已保存" en="Saved" /></>
          ) : saveState === "dirty" ? (
            <button className="writer-save-btn" onClick={requestSave} title={tx(locale, "保存", "Save")} type="button">
              <Save size={13} />
            </button>
          ) : null}
        </div>

        <WriterManuscriptEditor
          locale={locale}
          blockId={blockId}
          content={editorContent}
          onRequestSave={requestSave}
          onContentChange={(text) => handleContentChange(text)}
          onReviseSelection={reviseAction ? handleRevise : undefined}
          pendingRevision={revision}
          onRevisionResolved={() => setRevision(null)}
        />

        <textarea
          ref={peTextareaRef}
          name="content"
          className={enhanced ? "writer-prose-textarea writer-prose-textarea-mirror" : "writer-prose-textarea"}
          defaultValue={editorContent}
          rows={16}
          aria-label={tx(locale, "手稿正文", "Manuscript prose")}
          data-pe-source="true"
        />
      </form>
    </div>
  );
}
