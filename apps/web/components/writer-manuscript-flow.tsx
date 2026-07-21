"use client";

import { ArchiveRestore, GripVertical, ListRestart, MoreHorizontal, Plus, Save, Sparkles, Tags } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type {
  Chapter,
  ManuscriptBlock,
  ManuscriptVersion,
  PrivateManuscriptBlock,
  Scene,
  WriterWebResult,
} from "../lib/writer-workspace-api";
import { type Locale, tx } from "../lib/locale";
import { Bi, StatusValue } from "./bilingual-text";
import { ConfirmSubmitButton } from "./confirm-submit-button";
import type { PendingRevision } from "./writer-manuscript-editor";
import { WriterManuscriptPanelClient } from "./writer-manuscript-panel-client";
import { useWriterWorkbench } from "./writer-workbench-context";

type Action = (formData: FormData) => Promise<void>;

export type WriterManuscriptFlowProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  selectedDraftId: string;
  selectedChapterId: string;
  selectedSceneId: string;
  selectedBlockId: string;
  blockContents: PrivateManuscriptBlock[];
  blocks: WriterWebResult<ManuscriptBlock[]>;
  chapters: WriterWebResult<Chapter[]>;
  scenes: WriterWebResult<Scene[]>;
  blockVersions: WriterWebResult<ManuscriptVersion[]>;
  selectedBlock: WriterWebResult<PrivateManuscriptBlock | null>;
  actionStatus: { status: string; code: string } | null;
  localDraft?: string | null;
  pendingRevision?: PendingRevision | null;
  /** Live draft ghost rendered as the paper's last section (null when idle). */
  draftBlock?: ReactNode;
  actions: {
    createBlock: Action;
    updateBlock: Action;
    deleteBlock: Action;
    reorderBlocks: Action;
    moveBlock: Action;
    tagBlock: Action;
    restoreBlock: Action;
    reviseSelection?: Action;
  };
};

/**
 * Continuous manuscript document, redesigned: each section renders as pure
 * prose; its management lives behind a single hover ⋯ menu instead of a
 * permanently-mounted disclosure full of forms.
 */
export function WriterManuscriptFlow(props: WriterManuscriptFlowProps) {
  const { locale, blockContents, selectedBlock } = props;
  const hasSections = blockContents.length > 0;
  const selectedPrivate =
    selectedBlock.ok && selectedBlock.value ? selectedBlock.value : null;

  if (!hasSections) {
    return (
      <section
        aria-labelledby="manuscript-workspace-heading"
        className="writer-prose-panel writer-canvas-empty-panel"
        data-manuscript-empty="true"
      >
        <h2 className="sr-only" id="manuscript-workspace-heading">
          <Bi zh="手稿正文" en="Manuscript prose" />
        </h2>
        {props.draftBlock}
        <div className="writer-canvas-empty">
          <span aria-hidden="true" className="writer-canvas-empty-ico">
            ✦
          </span>
          <p>
            <Bi zh="这一章还没有正文" en="This chapter has no prose yet" />
          </p>
          <p className="form-hint">
            <Bi
              zh="在右侧对话里让 Writer 起草，或自己开始写这一章。"
              en="Ask Writer to draft on the right, or start writing this chapter yourself."
            />
          </p>
          <form action={props.actions.createBlock} className="writer-create-block-form">
            <input name="chapterId" type="hidden" value={props.selectedChapterId} />
            <input name="sceneId" type="hidden" value={props.selectedSceneId} />
            <button type="submit">
              <Plus size={14} />
              <Bi zh="开始写这一章" en="Start writing this chapter" />
            </button>
          </form>
        </div>
      </section>
    );
  }

  const orderedIds = blockContents.map((block) => `${block.block_id}:${block.version}`);

  return (
    <section
      aria-labelledby="manuscript-workspace-heading"
      className="writer-prose-panel writer-manuscript-flow"
      data-manuscript-flow="true"
    >
      <h2 className="sr-only" id="manuscript-workspace-heading">
        <Bi zh="手稿正文" en="Manuscript prose" />
      </h2>

      <div className="writer-manuscript-document">
        {blockContents.map((block, index) => {
          const selected = props.selectedBlockId === block.block_id;
          const content =
            selected && selectedPrivate && selectedPrivate.block_id === block.block_id
              ? selectedPrivate.content_text
              : block.content_text;
          const version =
            selected && selectedPrivate && selectedPrivate.block_id === block.block_id
              ? selectedPrivate.version
              : block.version;
          const status =
            selected && selectedPrivate && selectedPrivate.block_id === block.block_id
              ? selectedPrivate.status
              : block.status;

          return (
            <ManuscriptSection
              block={block}
              content={content}
              index={index}
              key={block.block_id}
              locale={locale}
              orderedIds={orderedIds}
              props={props}
              sectionCount={blockContents.length}
              selected={selected}
              status={status}
              version={version}
            />
          );
        })}
        {props.draftBlock}
      </div>

      <AddSectionRow props={props} />
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* One section: prose + a single hover ⋯ menu                          */
/* ------------------------------------------------------------------ */

function ManuscriptSection({
  block,
  content,
  index,
  locale,
  orderedIds,
  props,
  sectionCount,
  selected,
  status,
  version,
}: {
  block: PrivateManuscriptBlock;
  content: string;
  index: number;
  locale: Locale;
  orderedIds: string[];
  props: WriterManuscriptFlowProps;
  sectionCount: number;
  selected: boolean;
  status: string;
  version: number;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onPointer(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  return (
    <article
      className={`writer-manuscript-section ${selected ? "is-selected" : ""}`}
      data-block-id={block.block_id}
      data-section-index={index + 1}
    >
      <div className="writer-section-divider">
        <span className="writer-section-divider-meta">
          <strong>
            <Bi zh={`片段 ${index + 1}`} en={`Section ${index + 1}`} />
          </strong>
          {!selected ? (
            <>
              <span>
                · {block.word_count} <Bi zh="字" en="words" />
              </span>
              <span>
                · <StatusValue value={status} />
              </span>
            </>
          ) : null}
          {block.tags.length > 0 ? (
            <span className="writer-section-tags">· {block.tags.join(", ")}</span>
          ) : null}
        </span>

        {/* single ⋯ menu replaces the old always-mounted manage disclosure */}
        <div ref={menuRef} style={{ position: "relative" }}>
          <button
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            aria-label={tx(locale, "管理这一段", "Manage this section")}
            className="writer-section-menu-button"
            onClick={() => setMenuOpen((value) => !value)}
            type="button"
          >
            <MoreHorizontal aria-hidden="true" size={18} />
          </button>
          {menuOpen ? (
            <SectionMenu
              actions={props.actions}
              block={block}
              chapters={props.chapters}
              close={() => setMenuOpen(false)}
              index={index}
              locale={locale}
              orderedIds={orderedIds}
              scenes={props.scenes}
              sectionCount={sectionCount}
              version={version}
              versions={selected ? props.blockVersions : { ok: true, value: [] }}
            />
          ) : null}
        </div>
      </div>

      {selected ? (
        <div className="writer-manuscript-section-editor">
          <WriterManuscriptPanelClient
            locale={locale}
            blockId={block.block_id}
            expectedVersion={version}
            content={content}
            status={status}
            chapterId={block.chapter_id ?? props.selectedChapterId}
            sceneId={block.scene_id ?? props.selectedSceneId}
            updateBlockAction={props.actions.updateBlock}
            createBlockAction={props.actions.createBlock}
            reviseAction={props.actions.reviseSelection}
            pendingRevision={props.pendingRevision ?? null}
            conflictLocalDraft={props.localDraft ?? null}
            workspaceStatus={props.actionStatus?.status ?? null}
            workspaceCode={props.actionStatus?.code ?? null}
          />
        </div>
      ) : (
        <SectionNavigateForm
          blockId={block.block_id}
          label={
            <div className="writer-manuscript-section-prose">
              {content.trim() ? (
                <p>{content}</p>
              ) : (
                <p className="writer-manuscript-section-empty">
                  <Bi zh="（空白片段 — 点击开始写）" en="(Empty section — click to write)" />
                </p>
              )}
            </div>
          }
          props={props}
        />
      )}
    </article>
  );
}

/* ------------------------------------------------------------------ */
/* The ⋯ popover menu                                                   */
/* ------------------------------------------------------------------ */

function SectionMenu({
  actions,
  block,
  chapters,
  close,
  index,
  locale,
  orderedIds,
  scenes,
  sectionCount,
  version,
  versions,
}: {
  actions: WriterManuscriptFlowProps["actions"];
  block: PrivateManuscriptBlock;
  chapters: WriterWebResult<Chapter[]>;
  close: () => void;
  index: number;
  locale: Locale;
  orderedIds: string[];
  scenes: WriterWebResult<Scene[]>;
  sectionCount: number;
  version: number;
  versions: WriterWebResult<ManuscriptVersion[]>;
}) {
  const [panel, setPanel] = useState<null | "tags" | "move" | "history">(null);

  return (
    <div className="writer-section-menu" role="menu">
      {/* reorder */}
      <div style={{ display: "flex", gap: 4 }}>
        <form action={actions.reorderBlocks} style={{ flex: 1 }}>
          {reorderedIds(orderedIds, index, -1).map((item) => (
            <input key={item} name="orderedBlockItems" type="hidden" value={item} />
          ))}
          <button disabled={index <= 0} onClick={close} type="submit">
            <span className="writer-menu-ico"><GripVertical size={15} /></span>
            <Bi zh="上移" en="Move up" />
          </button>
        </form>
        <form action={actions.reorderBlocks} style={{ flex: 1 }}>
          {reorderedIds(orderedIds, index, 1).map((item) => (
            <input key={item} name="orderedBlockItems" type="hidden" value={item} />
          ))}
          <button disabled={index >= sectionCount - 1} onClick={close} type="submit">
            <span className="writer-menu-ico"><GripVertical size={15} /></span>
            <Bi zh="下移" en="Move down" />
          </button>
        </form>
      </div>

      <button onClick={() => setPanel(panel === "tags" ? null : "tags")} type="button">
        <span className="writer-menu-ico"><Tags size={15} /></span>
        <Bi zh="加标签" en="Add tags" />
      </button>
      <button onClick={() => setPanel(panel === "move" ? null : "move")} type="button">
        <span className="writer-menu-ico"><ListRestart size={15} /></span>
        <Bi zh="移动到…" en="Move to…" />
      </button>
      <button onClick={() => setPanel(panel === "history" ? null : "history")} type="button">
        <span className="writer-menu-ico"><ArchiveRestore size={15} /></span>
        <Bi zh="历史版本" en="Version history" />
      </button>

      <div className="writer-menu-sep" />

      <form action={actions.deleteBlock}>
        <input name="blockId" type="hidden" value={block.block_id} />
        <input name="expectedVersion" type="hidden" value={version} />
        <ConfirmSubmitButton
          cancelLabel={<Bi zh="取消" en="Cancel" />}
          confirmDescription={<Bi zh="此操作会删除这一段（可找回）。确认继续？" en="This deletes the section (recoverable). Continue?" />}
          confirmLabel={<Bi zh="确认删除" en="Confirm delete" />}
          confirmTitle={<Bi zh="删除这一段" en="Delete this section" />}
          idleLabel={<Bi zh="删除这一段" en="Delete this section" />}
          pendingLabel={<Bi zh="处理中…" en="Working…" />}
          tone="danger"
        />
      </form>

      {/* expandable sub-panels */}
      {panel === "tags" ? (
        <div className="writer-menu-panel">
          <strong style={{ fontSize: "0.8rem" }}><Bi zh="标签" en="Tags" /></strong>
          <form action={actions.tagBlock}>
            <input name="blockId" type="hidden" value={block.block_id} />
            <input name="expectedVersion" type="hidden" value={version} />
            <input
              aria-label={tx(locale, "标签", "Tags")}
              defaultValue={block.tags.join(",")}
              name="tags"
              placeholder={tx(locale, "标签，逗号分隔", "Tags, comma-separated")}
            />
            <button onClick={close} type="submit">
              <Save size={13} />
              <Bi zh="保存标签" en="Save tags" />
            </button>
          </form>
        </div>
      ) : null}

      {panel === "move" ? (
        <div className="writer-menu-panel">
          <strong style={{ fontSize: "0.8rem" }}><Bi zh="移动到章节 / 场景" en="Move to chapter / scene" /></strong>
          <form action={actions.moveBlock}>
            <input name="blockId" type="hidden" value={block.block_id} />
            <input name="expectedVersion" type="hidden" value={version} />
            <ChapterSelect chapters={chapters} id={`move-ch-${block.block_id}`} locale={locale} name="chapterId" selectedId={block.chapter_id ?? ""} />
            <SceneSelect id={`move-sc-${block.block_id}`} locale={locale} name="sceneId" scenes={scenes} selectedId={block.scene_id ?? ""} />
            <button onClick={close} type="submit">
              <ListRestart size={13} />
              <Bi zh="移动" en="Move" />
            </button>
          </form>
        </div>
      ) : null}

      {panel === "history" ? (
        <div className="writer-menu-panel">
          <strong style={{ fontSize: "0.8rem" }}><Bi zh="历史版本" en="Version history" /></strong>
          {versions.ok && versions.value.length > 0 ? (
            versions.value.map((entry) => (
              <form action={actions.restoreBlock} key={entry.version_id}>
                <input name="blockId" type="hidden" value={block.block_id} />
                <input name="versionId" type="hidden" value={entry.version_id} />
                <input name="expectedVersion" type="hidden" value={version} />
                <span style={{ fontSize: "0.78rem", color: "var(--ink-3, #776b5c)" }}>
                  v{entry.version_number} / {entry.snapshot_reason}
                </span>
                <button onClick={close} type="submit">
                  <ArchiveRestore size={13} />
                  <Bi zh="恢复" en="Restore" />
                </button>
              </form>
            ))
          ) : (
            <p style={{ fontSize: "0.78rem", color: "var(--ink-3, #776b5c)", margin: "6px 0 0" }}>
              <Bi zh="暂无历史版本。" en="No versions yet." />
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 段尾: 写一段 / 让 AI 写                                              */
/* ------------------------------------------------------------------ */

function AddSectionRow({ props }: { props: WriterManuscriptFlowProps }) {
  const workbench = useWriterWorkbench();
  const { locale } = props;
  return (
    <div className="writer-paper-addrow">
      <form action={props.actions.createBlock}>
        <input name="chapterId" type="hidden" value={props.selectedChapterId} />
        <input name="sceneId" type="hidden" value={props.selectedSceneId} />
        <button type="submit">
          <Plus size={14} />
          <Bi zh="写一段" en="Write a section" />
        </button>
      </form>
      <button
        className="writer-add-ai"
        onClick={() => {
          workbench?.setMobileView("conversation");
          // Desktop keeps the agent dock visible; still move focus into the composer.
          requestAnimationFrame(() => {
            const composer = document.querySelector<HTMLTextAreaElement>(
              ".writer-agent-composer textarea, .writer-composer-input-row textarea",
            );
            composer?.focus();
          });
        }}
        title={tx(locale, "在右侧让 AI 接着写", "Ask the AI to continue on the right")}
        type="button"
      >
        <Sparkles size={14} />
        <Bi zh="让 AI 接着写" en="Let AI continue" />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

function SectionNavigateForm({
  blockId,
  label,
  props,
}: {
  blockId: string;
  label: ReactNode;
  props: Pick<
    WriterManuscriptFlowProps,
    | "tenantSlug"
    | "projectId"
    | "selectedDraftId"
    | "selectedChapterId"
    | "selectedSceneId"
    | "selectedBlockId"
  >;
}) {
  const href = `/${props.tenantSlug}/projects/${props.projectId}/writer`;
  return (
    <form action={href} className="writer-section-select-form" method="get">
      {props.selectedDraftId ? <input name="draftId" type="hidden" value={props.selectedDraftId} /> : null}
      {props.selectedChapterId ? <input name="chapterId" type="hidden" value={props.selectedChapterId} /> : null}
      {props.selectedSceneId ? <input name="sceneId" type="hidden" value={props.selectedSceneId} /> : null}
      <input name="blockId" type="hidden" value={blockId} />
      <button className="writer-section-select-button" type="submit">
        {label}
      </button>
    </form>
  );
}

function reorderedIds<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const next = [...items];
  const target = index + direction;
  if (index < 0 || target < 0 || target >= next.length) return next;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function ChapterSelect({
  chapters,
  id,
  locale,
  name,
  selectedId,
}: {
  chapters: WriterWebResult<Chapter[]>;
  id: string;
  locale: Locale;
  name: string;
  selectedId: string;
}) {
  if (!chapters.ok || chapters.value.length === 0) {
    return (
      <select aria-label={tx(locale, "章节", "Chapter")} disabled id={id} name={name}>
        <option value="">{tx(locale, "暂无章节", "No chapter")}</option>
      </select>
    );
  }
  return (
    <select
      aria-label={tx(locale, "章节", "Chapter")}
      defaultValue={selectedId || chapters.value[0]?.chapter_id}
      id={id}
      name={name}
    >
      <option value="">{tx(locale, "不指定章节", "No chapter")}</option>
      {chapters.value.map((chapter) => (
        <option key={chapter.chapter_id} value={chapter.chapter_id}>
          {chapter.chapter_order}. {chapter.title}
        </option>
      ))}
    </select>
  );
}

function SceneSelect({
  id,
  locale,
  name,
  scenes,
  selectedId,
}: {
  id: string;
  locale: Locale;
  name: string;
  scenes: WriterWebResult<Scene[]>;
  selectedId: string;
}) {
  if (!scenes.ok || scenes.value.length === 0) {
    return (
      <select aria-label={tx(locale, "场景", "Scene")} disabled id={id} name={name}>
        <option value="">{tx(locale, "暂无场景", "No scene")}</option>
      </select>
    );
  }
  return (
    <select
      aria-label={tx(locale, "场景", "Scene")}
      defaultValue={selectedId || scenes.value[0]?.scene_id}
      id={id}
      name={name}
    >
      <option value="">{tx(locale, "不指定场景", "No scene")}</option>
      {scenes.value.map((scene) => (
        <option key={scene.scene_id} value={scene.scene_id}>
          {scene.scene_order}. {scene.title}
        </option>
      ))}
    </select>
  );
}
