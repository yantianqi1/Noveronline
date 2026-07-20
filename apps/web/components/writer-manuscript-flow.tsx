import { ArchiveRestore, ArrowDown, ArrowUp, ListRestart, Plus, Save } from "lucide-react";
import type { ReactNode } from "react";

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
 * Continuous manuscript document: sections render as prose in order;
 * the selected section expands into the TipTap editor in-place.
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

      <div className="writer-manuscript-document writer-manuscript-paper">
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
            <article
              className={`writer-manuscript-section ${selected ? "is-selected" : ""}`}
              data-block-id={block.block_id}
              data-section-index={index + 1}
              key={block.block_id}
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
                <details className="writer-section-manage">
                  <summary>
                    <Bi zh="管理" en="Manage" />
                  </summary>
                  <div className="writer-section-manage-panel">
                    <SectionManageForms
                      actions={props.actions}
                      block={block}
                      chapters={props.chapters}
                      index={index}
                      locale={locale}
                      orderedIds={orderedIds}
                      scenes={props.scenes}
                      sectionCount={blockContents.length}
                      versions={selected ? props.blockVersions : { ok: true, value: [] }}
                    />
                  </div>
                </details>
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
        })}
      </div>

      <form action={props.actions.createBlock} className="writer-add-section-form">
        <input name="chapterId" type="hidden" value={props.selectedChapterId} />
        <input name="sceneId" type="hidden" value={props.selectedSceneId} />
        <button type="submit">
          <Plus size={14} />
          <Bi zh="添加空白片段" en="Add blank section" />
        </button>
      </form>
    </section>
  );
}

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

function SectionManageForms({
  actions,
  block,
  chapters,
  index,
  locale,
  orderedIds,
  scenes,
  sectionCount,
  versions,
}: {
  actions: WriterManuscriptFlowProps["actions"];
  block: PrivateManuscriptBlock;
  chapters: WriterWebResult<Chapter[]>;
  index: number;
  locale: Locale;
  orderedIds: string[];
  scenes: WriterWebResult<Scene[]>;
  sectionCount: number;
  versions: WriterWebResult<ManuscriptVersion[]>;
}) {
  return (
    <div className="writer-section-manage-body">
      <div className="inline-controls writer-section-reorder">
        <ReorderButton
          action={actions.reorderBlocks}
          ariaLabel={tx(locale, "上移片段", "Move section up")}
          direction={-1}
          disabled={index <= 0}
          orderedBlockItems={reorderedIds(orderedIds, index, -1)}
        />
        <ReorderButton
          action={actions.reorderBlocks}
          ariaLabel={tx(locale, "下移片段", "Move section down")}
          direction={1}
          disabled={index >= sectionCount - 1}
          orderedBlockItems={reorderedIds(orderedIds, index, 1)}
        />
      </div>

      <form action={actions.updateBlock} className="inline-controls">
        <input name="blockId" type="hidden" value={block.block_id} />
        <input name="expectedVersion" type="hidden" value={block.version} />
        <input name="content" type="hidden" value={block.content_text ?? ""} />
        <label htmlFor={`section-status-${block.block_id}`}>
          <Bi zh="状态" en="Status" />
        </label>
        <select
          defaultValue={block.status}
          id={`section-status-${block.block_id}`}
          name="status"
        >
          <option value="active">{tx(locale, "进行中", "Active")}</option>
          <option value="deleted">{tx(locale, "已删除", "Deleted")}</option>
        </select>
        <button type="submit">
          <Save size={14} />
          <Bi zh="保存状态" en="Save status" />
        </button>
      </form>

      <form action={actions.tagBlock} className="inline-controls">
        <input name="blockId" type="hidden" value={block.block_id} />
        <input name="expectedVersion" type="hidden" value={block.version} />
        <input
          aria-label={tx(locale, "标签", "Tags")}
          defaultValue={block.tags.join(",")}
          name="tags"
          placeholder={tx(locale, "标签，逗号分隔", "Tags, comma-separated")}
        />
        <button type="submit">
          <Save size={14} />
          <Bi zh="保存标签" en="Save tags" />
        </button>
      </form>

      <form action={actions.moveBlock} className="binding-form">
        <input name="blockId" type="hidden" value={block.block_id} />
        <input name="expectedVersion" type="hidden" value={block.version} />
        <label htmlFor={`move-section-chapter-${block.block_id}`}>
          <Bi zh="目标章节" en="Target chapter" />
        </label>
        <ChapterSelect
          chapters={chapters}
          id={`move-section-chapter-${block.block_id}`}
          locale={locale}
          name="chapterId"
          selectedId={block.chapter_id ?? ""}
        />
        <label htmlFor={`move-section-scene-${block.block_id}`}>
          <Bi zh="目标场景" en="Target scene" />
        </label>
        <SceneSelect
          id={`move-section-scene-${block.block_id}`}
          locale={locale}
          name="sceneId"
          scenes={scenes}
          selectedId={block.scene_id ?? ""}
        />
        <button type="submit">
          <ListRestart size={14} />
          <Bi zh="移动片段" en="Move section" />
        </button>
      </form>

      <form action={actions.deleteBlock} className="inline-action-form">
        <input name="blockId" type="hidden" value={block.block_id} />
        <input name="expectedVersion" type="hidden" value={block.version} />
        <ConfirmSubmitButton
          cancelLabel={<Bi zh="取消" en="Cancel" />}
          confirmDescription={<Bi zh="此操作会归档该片段。确认继续？" en="This archives the section. Continue?" />}
          confirmLabel={<Bi zh="确认归档" en="Confirm archive" />}
          confirmTitle={<Bi zh="确认归档" en="Confirm archive" />}
          idleLabel={<Bi zh="归档片段" en="Archive section" />}
          pendingLabel={<Bi zh="处理中…" en="Working…" />}
          tone="danger"
        />
      </form>

      {versions.ok && versions.value.length > 0 ? (
        <div className="compact-action-list">
          <strong>
            <Bi zh="历史版本" en="Version history" />
          </strong>
          {versions.value.map((version) => (
            <form action={actions.restoreBlock} className="inline-controls" key={version.version_id}>
              <input name="blockId" type="hidden" value={block.block_id} />
              <input name="versionId" type="hidden" value={version.version_id} />
              <input name="expectedVersion" type="hidden" value={block.version} />
              <span>
                v{version.version_number} / {version.snapshot_reason}
              </span>
              <button type="submit">
                <ArchiveRestore size={14} />
                <Bi zh="恢复" en="Restore" />
              </button>
            </form>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ReorderButton({
  action,
  ariaLabel,
  direction,
  disabled,
  orderedBlockItems,
}: {
  action: Action;
  ariaLabel: string;
  direction: -1 | 1;
  disabled: boolean;
  orderedBlockItems: string[];
}) {
  return (
    <form action={action} className="inline-action-form">
      {orderedBlockItems.map((item) => (
        <input key={item} name="orderedBlockItems" type="hidden" value={item} />
      ))}
      <button aria-label={ariaLabel} disabled={disabled} type="submit">
        {direction === -1 ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
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
