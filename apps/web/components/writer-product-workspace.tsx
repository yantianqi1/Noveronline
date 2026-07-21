import { ArchiveRestore, ArrowDown, ArrowUp, Check, FileClock, Play, Save, Trash2, X } from "lucide-react";
import type { ReactNode } from "react";

import type {
  AssetProposal, BookPlan, Chapter, DedupPattern, DistillationSettings, DraftReviewList, ExportRecord,
  ForbiddenEntry, ManuscriptBlock, ManuscriptCommand, ManuscriptVersion, OutlineVersion,
  PrivateManuscriptBlock, Scene, WriterPreset, WriterPlanningRun, WriterWebResult, WritingVersion,
} from "../lib/writer-workspace-api";
import { type Locale, tx } from "../lib/locale";
import {
  MANUSCRIPT_COMMAND_CHOICES,
  manuscriptCommandLabel,
  planningRunLabel,
} from "../lib/writer-command-labels";
import { Bi, StatusValue } from "./bilingual-text";
import { ConfirmSubmitButton } from "./confirm-submit-button";
import { SubmitButton } from "./submit-button";
import type { PendingRevision } from "./writer-manuscript-editor";
import { ActionToast } from "./writer-action-toast";
import { WriterCanvasStatus } from "./writer-canvas-status";
import { WriterChapterSwitcher } from "./writer-chapter-switcher";
import { WriterDrawers } from "./writer-drawers";
import { WriterHandlebar } from "./writer-handlebar";
import { WriterManuscriptFlow } from "./writer-manuscript-flow";
import { WriterTocRail } from "./writer-toc-rail";

type Action = (formData: FormData) => Promise<void>;
type Actions = {
  createChapter: Action; updateChapter: Action; deleteChapter: Action; reorderChapters: Action;
  createScene: Action; updateScene: Action; deleteScene: Action; reorderScenes: Action;
  createOutline: Action; restoreOutline: Action; createBookPlan: Action; updateBookPlan: Action; deleteBookPlan: Action; generateBookPlan: Action;
  createPreset: Action; deletePreset: Action; createLexicon: Action; deleteLexicon: Action;
  startReview: Action; updateReviewIssue: Action; createBlock: Action; updateBlock: Action; deleteBlock: Action; reorderBlocks: Action;
  moveBlock: Action; tagBlock: Action; restoreBlock: Action; startDedup: Action; decideDedup: Action; startCommand: Action;
  createExport: Action;
  startDistillation?: Action;
  decideProposal?: Action;
  patchDistillationSettings?: Action;
  reviseSelection?: Action;
};

export type WriterProductWorkspaceProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  selectedDraftId: string;
  selectedChapterId: string;
  selectedSceneId: string;
  selectedBlockId: string;
  selectedCommandId: string;
  actionStatus: { status: string; code: string } | null;
  localDraft?: string | null;
  pendingRevision?: PendingRevision | null;
  /** Live draft ghost rendered at the end of the manuscript paper. */
  draftBlock?: ReactNode;
  chapters: WriterWebResult<Chapter[]>;
  scenes: WriterWebResult<Scene[]>;
  chapterVersions: WriterWebResult<WritingVersion[]>;
  sceneVersions: WriterWebResult<WritingVersion[]>;
  outlines: WriterWebResult<OutlineVersion[]>;
  bookPlans: WriterWebResult<BookPlan[]>;
  presets: WriterWebResult<WriterPreset[]>;
  lexicon: WriterWebResult<ForbiddenEntry[]>;
  reviews: WriterWebResult<DraftReviewList>;
  blocks: WriterWebResult<ManuscriptBlock[]>;
  /** Private prose for the current chapter flow (ordered, capped). */
  blockContents?: PrivateManuscriptBlock[];
  selectedBlock: WriterWebResult<PrivateManuscriptBlock | null>;
  blockVersions: WriterWebResult<ManuscriptVersion[]>;
  dedupPatterns: WriterWebResult<DedupPattern[]>;
  command: WriterWebResult<ManuscriptCommand | null>;
  exports: WriterWebResult<ExportRecord[]>;
  planningRun: WriterWebResult<WriterPlanningRun | null>;
  proposals?: WriterWebResult<AssetProposal[]>;
  distillationSettings?: WriterWebResult<DistillationSettings | null>;
  actions: Actions;
};

/**
 * Redesigned writer workspace: the paper is the permanent primary surface,
 * with the chapter TOC rail on the left and three on-demand bottom drawers
 * (structure / tools / library). Review + proposals become a quiet strip.
 */
export function WriterProductWorkspace(props: WriterProductWorkspaceProps) {
  const blockCount = props.blocks.ok ? props.blocks.value.length : 0;
  const wordCount = props.blocks.ok
    ? props.blocks.value.reduce((sum, block) => sum + (block.word_count ?? 0), 0)
    : 0;
  const flowWordCount = (props.blockContents ?? []).reduce(
    (sum, block) => sum + (block.word_count ?? 0),
    0,
  );
  const flowSectionCount = props.blockContents?.length ?? blockCount;

  const pendingReviews =
    (props.reviews.ok ? props.reviews.value.reviews.reduce((n, r) => n + r.issues.filter((i) => i.status === "open").length, 0) : 0)
    + (props.proposals?.ok ? props.proposals.value.filter((p) => p.review_status === "pending" || p.review_status === "conflict").length : 0);

  return (
    <div className="writer-redesign" data-nav="conversation-first">
      <div className="writer-redesign-stage">
        <WriterTocRail
          chapters={props.chapters}
          locale={props.locale}
          projectId={props.projectId}
          scenes={props.scenes}
          selectedChapterId={props.selectedChapterId}
          selectedDraftId={props.selectedDraftId}
          selectedSceneId={props.selectedSceneId}
          tenantSlug={props.tenantSlug}
        />

        <div className="writer-redesign-paper-scroll">
          <header className="writer-canvas-head">
            <div className="writer-canvas-head-primary">
              <WriterChapterSwitcher
                chapters={props.chapters}
                locale={props.locale}
                projectId={props.projectId}
                scenes={props.scenes}
                selectedChapterId={props.selectedChapterId}
                selectedDraftId={props.selectedDraftId}
                selectedSceneId={props.selectedSceneId}
                tenantSlug={props.tenantSlug}
              />
            </div>
            <div className="writer-canvas-head-side">
              <WriterCanvasStatus locale={props.locale} />
              <p className="writer-canvas-meta" aria-label={tx(props.locale, "稿件统计", "Manuscript stats")}>
                <span>
                  {flowWordCount || wordCount} <Bi zh="字" en="words" />
                </span>
                <span aria-hidden="true">·</span>
                <span>
                  {flowSectionCount} <Bi zh="片段" en="sections" />
                </span>
              </p>
            </div>
          </header>

          {props.actionStatus ? <ActionToast code={props.actionStatus.code} locale={props.locale} status={props.actionStatus.status} /> : null}

          {/* Always mount review/distillation controls so authors can start a pass
              after a finished run even when no open issues remain. */}
          <ReviewStrip count={pendingReviews} locale={props.locale} props={props} />

          <div className="writer-redesign-paper">
            <WriterManuscriptFlow
              actionStatus={props.actionStatus}
              actions={{
                createBlock: props.actions.createBlock,
                updateBlock: props.actions.updateBlock,
                deleteBlock: props.actions.deleteBlock,
                reorderBlocks: props.actions.reorderBlocks,
                moveBlock: props.actions.moveBlock,
                tagBlock: props.actions.tagBlock,
                restoreBlock: props.actions.restoreBlock,
                reviseSelection: props.actions.reviseSelection,
              }}
              blockContents={props.blockContents ?? []}
              blocks={props.blocks}
              blockVersions={props.blockVersions}
              chapters={props.chapters}
              draftBlock={props.draftBlock}
              locale={props.locale}
              localDraft={props.localDraft}
              pendingRevision={props.pendingRevision}
              projectId={props.projectId}
              scenes={props.scenes}
              selectedBlock={props.selectedBlock}
              selectedBlockId={props.selectedBlockId}
              selectedChapterId={props.selectedChapterId}
              selectedDraftId={props.selectedDraftId}
              selectedSceneId={props.selectedSceneId}
              tenantSlug={props.tenantSlug}
            />
          </div>
        </div>
      </div>

      <WriterHandlebar locale={props.locale} />
      <WriterDrawers
        library={<LibraryDrawer locale={props.locale} />}
        locale={props.locale}
        structure={<StructureDrawer {...props} />}
        tools={<ToolsDrawer {...props} />}
      />
    </div>
  );
}

/** Quiet review entry on the paper — reachable without becoming a tab. */
function ReviewStrip({ count, locale, props }: { count: number; locale: Locale; props: WriterProductWorkspaceProps }) {
  return (
    <div className={`writer-review-strip${count > 0 ? " is-pending" : ""}`} role="status">
      <span>
        {count > 0 ? (
          <Bi
            zh={`有 ${count} 条待处理的审校与新设定`}
            en={`${count} review notes and new settings pending`}
          />
        ) : (
          <Bi zh="审校与设定提取" en="Review and setting extraction" />
        )}
      </span>
      <ReviewStripBody locale={locale} props={props} />
    </div>
  );
}

function ReviewStripBody({ locale, props }: { locale: Locale; props: WriterProductWorkspaceProps }) {
  return (
    <details style={{ marginLeft: "auto" }}>
      <summary style={{ cursor: "pointer", color: "var(--cinnabar, #8f211b)", fontWeight: 600 }}>
        <Bi zh="查看" en="Review" />
      </summary>
      <div style={{ paddingTop: 12 }}>
        <ReviewerPanel {...props} />
        <ProposalReviewPanel {...props} />
      </div>
    </details>
  );
}

export function WriterProductWorkspaceLoading() {
  return (
    <div className="writer-product-modules writer-product-modules-loading" aria-hidden="true">
      <div className="writer-artifact-loading-tabs">
        {["稿件", "章节", "审校", "工具"].map((label) => <span key={label}>{label}</span>)}
      </div>
      <div className="writer-module-loading">
        <span>稿件</span>
        <i />
      </div>
    </div>
  );
}

/* ============================ 结构抽屉 ============================ */

function StructureDrawer(props: WriterProductWorkspaceProps) {
  return (
    <div className="writer-artifact-stack">
      {props.chapters.ok && props.chapters.value.length === 0 ? <EmptyWriterBootstrap props={props} /> : null}
      <ChapterScenePanel {...props} />
    </div>
  );
}

/* ============================ 工具抽屉 ============================ */

function ToolsDrawer(props: WriterProductWorkspaceProps) {
  const { locale } = props;
  return (
    <div className="writer-toolgrid">
      <ToolCard
        desc={tx(locale, "大纲 · 书籍计划 · 写作预设", "Outlines, plans and presets")}
        icon="🗺"
        title={tx(locale, "规划", "Plan")}
        tone="plan"
      >
        <PlanningPanel {...props} />
      </ToolCard>

      <ToolCard
        desc={tx(locale, "重复的句子 · 禁用词", "Repeated sentences and banned words")}
        icon="✓"
        title={tx(locale, "检查", "Check")}
        tone="check"
      >
        <DedupPanel {...props} />
        <LexiconPanel {...props} />
      </ToolCard>

      <ToolCard
        desc={tx(locale, "一键命令 · 从正文提取设定", "One-click commands and setting extraction")}
        icon="✦"
        title={tx(locale, "AI 命令", "AI commands")}
        tone="ai"
      >
        <CommandPanel {...props} />
      </ToolCard>

      <ToolCard
        desc={tx(locale, "生成 TXT / 下载", "Generate TXT and download")}
        icon="⤓"
        title={tx(locale, "导出", "Export")}
        tone="export"
      >
        <ExportPanel {...props} />
      </ToolCard>
    </div>
  );
}

function ToolCard({
  children,
  desc,
  icon,
  title,
  tone,
}: {
  children: ReactNode;
  desc: string;
  icon: string;
  title: string;
  tone: "plan" | "check" | "ai" | "export";
}) {
  return (
    <details className="writer-toolcard">
      <summary>
        <span className={`writer-tool-ico writer-tone-${tone}`}>{icon}</span>
        <div>
          <h3>{title}</h3>
          <div className="writer-tool-desc">{desc}</div>
        </div>
        <span className="writer-tool-chev">▾</span>
      </summary>
      <div className="writer-tool-body">{children}</div>
    </details>
  );
}

/* ============================ 资料抽屉 ============================ */

/**
 * The context checkboxes belong to the writer-run composer form, so they stay
 * attached there. This drawer orients the author: what the library is and how
 * to feed it (accept extracted settings, save worldline paths).
 */
function LibraryDrawer({ locale }: { locale: Locale }) {
  return (
    <div className="writer-artifact-stack">
      <section className="panel">
        <p className="eyebrow"><Bi zh="资料" en="Library" /></p>
        <h2><Bi zh="写作参考资料" en="Writing references" /></h2>
        <p className="form-hint">
          <Bi
            zh="人物、场景、设定和世界线路径会作为 AI 写作时的参考。在右侧输入框上方的「添加创作上下文」里勾选本次要用的资料。"
            en="Characters, scenes, settings and worldline paths act as references when the AI writes. Pick what to use this run from “Add story context” above the composer on the right."
          />
        </p>
        <ol className="writer-empty-bootstrap-steps">
          <li><Bi zh="在「工具 → AI 命令」里从正文提取设定" en="Extract settings from prose under Tools → AI commands" /></li>
          <li><Bi zh="在审校条里把新设定「存进资料库」" en="Save new settings to the library from the review strip" /></li>
          <li><Bi zh="发起写作时勾选要用的人物 / 场景 / 路径" en="Check the characters / scenes / paths to use when you start a run" /></li>
        </ol>
      </section>
    </div>
  );
}

/* ============================ 审校 / 设定候选 ============================ */

function ProposalReviewPanel(props: WriterProductWorkspaceProps) {
  const { locale, proposals, distillationSettings, selectedBlockId } = props;
  return (
    <section className="panel" aria-labelledby="asset-proposal-heading" data-asset-proposal-rail="true">
      <p className="eyebrow"><Bi zh="设定提取" en="Setting extraction" /></p>
      <h2 id="asset-proposal-heading"><Bi zh="新发现的设定" en="New settings found" /></h2>
      <p className="form-hint">
        <Bi
          zh="自动模式只生成候选，不会改动正文。接受后才会进入写作参考。"
          en="Automatic mode only creates candidates and never rewrites the manuscript. Accepted settings enter writing references."
        />
      </p>
      {distillationSettings?.ok && distillationSettings.value ? (
        <p className="form-hint">
          <Bi zh="什么时候自动提取：" en="When to extract automatically: " />
          <StatusValue value={distillationSettings.value.trigger_mode} />
        </p>
      ) : null}
      {props.actions.patchDistillationSettings ? (
        <form action={props.actions.patchDistillationSettings} className="inline-controls">
          <label htmlFor="distill-trigger"><Bi zh="什么时候自动提取" en="Auto-extract" /></label>
          <select id="distill-trigger" name="triggerMode" defaultValue={distillationSettings?.ok ? distillationSettings.value?.trigger_mode : "manual"}>
            <option value="off">{tx(locale, "关闭", "Off")}</option>
            <option value="manual">{tx(locale, "仅手动", "Manual only")}</option>
            <option value="after_adoption">{tx(locale, "正文采用后", "After adoption")}</option>
            <option value="chapter_complete">{tx(locale, "章节完成后", "Chapter complete")}</option>
          </select>
          <button type="submit"><Save size={14} /><Bi zh="保存设置" en="Save settings" /></button>
        </form>
      ) : null}
      {props.actions.startDistillation ? (
        <form action={props.actions.startDistillation} className="inline-action-form">
          {selectedBlockId ? <input name="blockId" type="hidden" value={selectedBlockId} /> : null}
          <SubmitButton
            idleLabel={<><Play size={14} /><Bi zh="从这段提取设定" en="Extract settings from this section" /></>}
            pendingLabel={<Bi zh="提交中…" en="Submitting…" />}
            disabled={!selectedBlockId}
          />
        </form>
      ) : null}
      <ResultBoundary
        locale={locale}
        result={proposals ?? { ok: true, value: [] }}
        empty={tx(locale, "暂无待审设定。", "No pending settings.")}
        render={(items) => (
          <div className="compact-action-list">
            {items.map((item) => (
              <article className="tool-result-item" key={item.candidate_asset_id}>
                <strong>{item.title}</strong>
                <small>{item.asset_type} / <StatusValue value={item.operation} /> / <StatusValue value={item.review_status} /> / {item.evidence_count} evidence</small>
                {item.summary ? <span>{item.summary}</span> : null}
                {props.actions.decideProposal && (item.review_status === "pending" || item.review_status === "conflict") ? (
                  <div className="inline-controls">
                    {item.operation === "create" || item.review_status === "conflict" ? (
                      <form action={props.actions.decideProposal}>
                        <input name="candidateAssetId" type="hidden" value={item.candidate_asset_id} />
                        <input name="decision" type="hidden" value="accept_create" />
                        <input name="targetLifecycle" type="hidden" value="canon" />
                        <button type="submit"><Check size={14} /><Bi zh="存进资料库" en="Save to library" /></button>
                      </form>
                    ) : null}
                    {item.operation === "update" && item.target_asset_id ? (
                      <form action={props.actions.decideProposal}>
                        <input name="candidateAssetId" type="hidden" value={item.candidate_asset_id} />
                        <input name="decision" type="hidden" value="accept_update" />
                        <input name="targetAssetId" type="hidden" value={item.target_asset_id} />
                        <input name="expectedTargetVersion" type="hidden" value={String(item.expected_target_version ?? 1)} />
                        <input name="targetLifecycle" type="hidden" value="canon" />
                        <button type="submit"><Check size={14} /><Bi zh="更新已有的设定" en="Update existing setting" /></button>
                      </form>
                    ) : null}
                    <form action={props.actions.decideProposal}>
                      <input name="candidateAssetId" type="hidden" value={item.candidate_asset_id} />
                      <input name="decision" type="hidden" value="reject" />
                      <button type="submit"><X size={14} /><Bi zh="忽略" en="Dismiss" /></button>
                    </form>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
      />
    </section>
  );
}

function EmptyWriterBootstrap({ props }: { props: WriterProductWorkspaceProps }) {
  const { locale, tenantSlug, projectId } = props;
  return (
    <section className="panel writer-empty-bootstrap" data-empty-writer-bootstrap="true" aria-labelledby="writer-empty-bootstrap-heading">
      <p className="eyebrow"><Bi zh="从零创作" en="Zero-start writing" /></p>
      <h2 id="writer-empty-bootstrap-heading"><Bi zh="空项目可直接写作" en="Empty projects can write immediately" /></h2>
      <p className="form-hint">
        <Bi
          zh="不需要先上传小说或运行 Seed。先创建书籍计划与章节，再启动写作任务并采用草稿进入手稿。"
          en="You do not need to upload a novel or run Seed first. Create a book plan and chapter, then start a writer run and adopt a draft into the manuscript."
        />
      </p>
      <ol className="writer-empty-bootstrap-steps">
        <li><Bi zh="在下方创建书籍计划与第一章" en="Create a book plan and chapter one below" /></li>
        <li><Bi zh="启动 Writer 生成候选草稿，或稍后继续手写结构" en="Start Writer for a candidate draft, or keep building structure by hand" /></li>
        <li><Bi zh="显式采用草稿后进入 manuscript" en="Explicitly adopt a draft into the manuscript" /></li>
      </ol>
      <div className="inline-controls">
        <a className="overview-next-link" href={`/${encodeURIComponent(tenantSlug)}/projects/${encodeURIComponent(projectId)}/overview`}>
          <Bi zh="返回总览双入口" en="Back to overview dual entry" />
        </a>
      </div>
    </section>
  );
}

function ReviewerPanel(props: WriterProductWorkspaceProps) {
  const { locale, reviews, selectedDraftId } = props;
  return (
    <section className="panel" aria-labelledby="reviewer-workspace-heading">
      <p className="eyebrow"><Bi zh="审校" en="Reviewer" /></p>
      <h2 id="reviewer-workspace-heading"><Bi zh="草稿审校" en="Draft review" /></h2>
      {!selectedDraftId ? <p className="form-hint"><Bi zh="完成写作任务后选择候选草稿。" en="Select a candidate draft after a writer run completes." /></p> : (
        <form action={props.actions.startReview} className="inline-action-form">
          <input name="draftId" type="hidden" value={selectedDraftId} />
          <SubmitButton idleLabel={<><Play size={16} aria-hidden="true" /><Bi zh="开始审校" en="Start review" /></>} pendingLabel={<Bi zh="提交中…" en="Submitting…" />} />
        </form>
      )}
      <ResultBoundary locale={locale} result={reviews} empty={tx(locale, "暂无审校记录。", "No reviews yet.")} render={(value) => (
        <div className="compact-action-list">
          {value.reviews.map((review) => (
            <article className="tool-result-card" key={review.review_id}>
              <strong><Bi zh="审校记录" en="Review" /> {value.reviews.indexOf(review) + 1}</strong>
              <small><StatusValue value={review.status} /> / {review.issues.length} issues</small>
              {review.issues.map((issue) => (
                <div className="tool-result-item" key={issue.issue_id}>
                  <strong>{issue.category} / {issue.severity}</strong>
                  <span>{issue.summary}</span>
                  {issue.suggestion ? <small>{issue.suggestion}</small> : null}
                  <small><StatusValue value={issue.status} /></small>
                  {issue.status === "open" && issue.updated_at ? <div className="inline-controls">
                    {(["accepted", "dismissed", "resolved"] as const).map((status) => (
                      <form action={props.actions.updateReviewIssue} key={status}>
                        <input name="draftId" type="hidden" value={selectedDraftId} />
                        <input name="issueId" type="hidden" value={issue.issue_id} />
                        <input name="status" type="hidden" value={status} />
                        <input name="version" type="hidden" value={issue.updated_at} />
                        <button type="submit">{status === "dismissed" ? <X size={14} /> : <Check size={14} />}<StatusValue value={status} /></button>
                      </form>
                    ))}
                  </div> : null}
                </div>
              ))}
            </article>
          ))}
        </div>
      )} />
    </section>
  );
}

function ChapterScenePanel({ compact = false, ...props }: WriterProductWorkspaceProps & { compact?: boolean }) {
  const { locale, chapters, scenes, chapterVersions, sceneVersions } = props;
  return (
    <section className={`panel writer-structure-panel ${compact ? "writer-structure-compact" : ""}`} aria-labelledby="chapter-scene-heading">
      <p className="eyebrow"><Bi zh="结构" en="Structure" /></p>
      <h2 id="chapter-scene-heading"><Bi zh="章节管理" en="Chapter management" /></h2>
      <p className="form-hint">
        <Bi
          zh="点章节标题切换写作位置；改名、写大纲或归档放在每章的「编辑」里。"
          en="Click a chapter title to switch where you write. Renaming, outlines and archiving live inside each chapter's Edit."
        />
      </p>
      <form action={props.actions.createChapter} className="binding-form writer-structure-create">
        <input aria-label={tx(locale, "新章节标题", "New chapter title")} name="title" required placeholder={tx(locale, "新章节标题，例如「第一章 归乡」", "New chapter title")} />
        <button data-tone="primary" type="submit"><Save size={16} /><Bi zh="新建章节" en="New chapter" /></button>
      </form>
      <ResultBoundary locale={locale} result={chapters} empty={tx(locale, "暂无章节。先在上方创建第一章。", "No chapters yet. Create chapter one above.")} render={(items) => (
        <div className="compact-action-list writer-chapter-tree">
          {items.map((chapter, index) => (
            <article className={`writer-structure-card ${props.selectedChapterId === chapter.chapter_id ? "is-selected" : ""}`} key={chapter.chapter_id}>
              <div className="writer-structure-card-row">
                <ChapterNavigateForm props={props} chapterId={chapter.chapter_id} label={<strong>{chapter.chapter_order}. {chapter.title}</strong>} />
                <small><StatusValue value={chapter.status} /></small>
                {!compact ? (
                  <span className="writer-structure-reorder">
                    <ReorderButton action={props.actions.reorderChapters} ariaLabel={tx(locale, "上移章节", "Move chapter up")} direction={-1} disabled={index <= 0} orderedIds={reorderedIds(items.map((item) => item.chapter_id), index, -1)} />
                    <ReorderButton action={props.actions.reorderChapters} ariaLabel={tx(locale, "下移章节", "Move chapter down")} direction={1} disabled={index >= items.length - 1} orderedIds={reorderedIds(items.map((item) => item.chapter_id), index, 1)} />
                  </span>
                ) : null}
              </div>
              {!compact ? (
                <details className="writer-structure-edit">
                  <summary><Bi zh="编辑" en="Edit" /></summary>
                  <div className="writer-structure-edit-body">
                    <form action={props.actions.updateChapter} className="binding-form">
                      <input name="chapterId" type="hidden" value={chapter.chapter_id} /><input name="expectedVersion" type="hidden" value={chapter.optimistic_version} />
                      <input name="title" defaultValue={chapter.title} aria-label={`Chapter title ${chapter.title}`} />
                      <textarea name="outline" defaultValue={chapter.private?.outline ?? ""} placeholder={tx(locale, "章节大纲（可选）", "Chapter outline (optional)")} rows={2} />
                      <button type="submit"><Save size={14} /><Bi zh="保存" en="Save" /></button>
                    </form>
                    <DeleteForm action={props.actions.deleteChapter} idName="chapterId" id={chapter.chapter_id} version={chapter.optimistic_version} label={tx(locale, "删除这一章", "Delete this chapter")} />
                  </div>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      )} />
      {props.selectedChapterId ? (
        <div className="compact-action-list">
          <h3><Bi zh="当前章节的场景" en="Scenes in this chapter" /></h3>
          <form action={props.actions.createScene} className="binding-form writer-structure-create">
            <input name="chapterId" type="hidden" value={props.selectedChapterId} />
            <input aria-label={tx(locale, "新场景标题", "New scene title")} name="title" required placeholder={tx(locale, "新场景标题", "New scene title")} />
            <button type="submit"><Save size={14} /><Bi zh="新建场景" en="New scene" /></button>
          </form>
          <ResultBoundary locale={locale} result={scenes} empty={tx(locale, "暂无场景。场景是可选的细分。", "No scenes. Scenes are optional subdivisions.")} render={(items) => (
            <>
              {items.map((scene, index) => (
                <article className={`writer-structure-card is-scene ${props.selectedSceneId === scene.scene_id ? "is-selected" : ""}`} key={scene.scene_id}>
                  <div className="writer-structure-card-row">
                    <SceneNavigateForm props={props} chapterId={scene.chapter_id} sceneId={scene.scene_id} label={<strong>{scene.scene_order}. {scene.title}</strong>} />
                    <small><StatusValue value={scene.status} /></small>
                    {!compact ? (
                      <span className="writer-structure-reorder">
                        <ReorderButton action={props.actions.reorderScenes} ariaLabel={tx(locale, "上移场景", "Move scene up")} direction={-1} disabled={index <= 0} extraFields={{ chapterId: props.selectedChapterId }} orderedIds={reorderedIds(items.map((item) => item.scene_id), index, -1)} />
                        <ReorderButton action={props.actions.reorderScenes} ariaLabel={tx(locale, "下移场景", "Move scene down")} direction={1} disabled={index >= items.length - 1} extraFields={{ chapterId: props.selectedChapterId }} orderedIds={reorderedIds(items.map((item) => item.scene_id), index, 1)} />
                      </span>
                    ) : null}
                  </div>
                  {!compact ? (
                    <details className="writer-structure-edit">
                      <summary><Bi zh="编辑" en="Edit" /></summary>
                      <div className="writer-structure-edit-body">
                        <form action={props.actions.updateScene} className="binding-form">
                          <input name="sceneId" type="hidden" value={scene.scene_id} /><input name="expectedVersion" type="hidden" value={scene.optimistic_version} />
                          <input name="title" defaultValue={scene.title} aria-label={`Scene title ${scene.title}`} />
                          <textarea name="outline" defaultValue={scene.private?.outline ?? ""} placeholder={tx(locale, "场景大纲（可选）", "Scene outline (optional)")} rows={2} />
                          <button type="submit"><Save size={14} /><Bi zh="保存" en="Save" /></button>
                        </form>
                        <DeleteForm action={props.actions.deleteScene} idName="sceneId" id={scene.scene_id} version={scene.optimistic_version} label={tx(locale, "删除这个场景", "Delete this scene")} />
                      </div>
                    </details>
                  ) : null}
                </article>
              ))}
            </>
          )} />
          {!compact ? (
            <details className="writer-structure-versions">
              <summary><Bi zh="历史版本" en="Version history" /></summary>
              <div className="writer-structure-edit-body">
                <VersionList locale={locale} label={tx(locale, "章节版本", "Chapter versions")} result={chapterVersions} />
                <VersionList locale={locale} label={tx(locale, "场景版本", "Scene versions")} result={sceneVersions} />
              </div>
            </details>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function PlanningPanel(props: WriterProductWorkspaceProps) {
  const { locale } = props;
  return (
    <div>
      <form action={props.actions.createOutline} className="binding-form">
        <input name="scopeType" type="hidden" value="project" /><input name="title" required placeholder={tx(locale, "大纲版本标题", "Outline version title")} />
        <textarea name="outlineText" required rows={3} placeholder={tx(locale, "大纲正文", "Outline text")} />
        <button type="submit"><Save size={14} /><Bi zh="保存大纲版本" en="Save outline version" /></button>
      </form>
      <ResultBoundary locale={locale} result={props.outlines} empty={tx(locale, "暂无大纲版本。", "No outline versions.")} render={(items) => <div className="compact-action-list">{items.map((item) => <article className="tool-result-item" key={item.outline_version_id}><strong>{item.title} / v{item.version_number}</strong><span>{item.outline_text}</span><form action={props.actions.restoreOutline}><input name="outlineVersionId" type="hidden" value={item.outline_version_id} /><button type="submit"><ArchiveRestore size={14} /><Bi zh="恢复此版本" en="Restore version" /></button></form></article>)}</div>} />
      <h3><Bi zh="书籍计划" en="Book plans" /></h3>
      <form action={props.actions.createBookPlan} className="binding-form"><input name="title" required placeholder={tx(locale, "计划名称", "Plan title")} /><textarea name="premise" required rows={2} placeholder={tx(locale, "故事前提", "Premise")} /><input name="targetCount" type="number" min="1" placeholder={tx(locale, "目标章节数", "Target chapters")} /><button type="submit"><Save size={14} /><Bi zh="创建计划" en="Create plan" /></button></form>
      <ResultBoundary locale={locale} result={props.bookPlans} empty={tx(locale, "暂无计划。", "No plans.")} render={(items) => <div className="compact-action-list">{items.map((item) => <article className="tool-result-item" key={item.book_plan_id}><strong>{item.title}</strong><span>{item.premise}</span><small><StatusValue value={item.status} /> / v{item.optimistic_version}{item.last_run_status ? <> / <StatusValue value={item.last_run_status} /></> : null}</small>{item.status === "draft" ? <form action={props.actions.generateBookPlan} className="inline-action-form"><input name="bookPlanId" type="hidden" value={item.book_plan_id} /><input name="expectedVersion" type="hidden" value={item.optimistic_version} /><button type="submit" disabled={item.last_run_status === "queued" || item.last_run_status === "running"}><Play size={14} /><Bi zh="生成候选计划" en="Generate candidate plan" /></button></form> : null}<form action={props.actions.updateBookPlan} className="inline-controls"><input name="bookPlanId" type="hidden" value={item.book_plan_id} /><input name="expectedVersion" type="hidden" value={item.optimistic_version} /><input name="title" defaultValue={item.title} /><button type="submit"><Save size={14} /><Bi zh="保存" en="Save" /></button></form><DeleteForm action={props.actions.deleteBookPlan} idName="bookPlanId" id={item.book_plan_id} version={item.optimistic_version} label={tx(locale, "删除计划", "Delete plan")} /></article>)}</div>} />
      <h3><Bi zh="写作预设" en="Writer presets" /></h3>
      <form action={props.actions.createPreset} className="binding-form"><select name="scope" defaultValue="project"><option value="project">{tx(locale, "项目", "Project")}</option><option value="tenant">{tx(locale, "工作区 owner/admin", "Workspace owner/admin")}</option></select><input name="name" required placeholder={tx(locale, "预设名称", "Preset name")} /><textarea name="settings" required defaultValue="{}" rows={2} /><button type="submit"><Save size={14} /><Bi zh="保存预设" en="Save preset" /></button></form>
      <SimpleDeleteList locale={locale} result={props.presets} idKey="writer_preset_id" action={props.actions.deletePreset} idName="presetId" empty={tx(locale, "暂无预设。", "No presets.")} label={(item) => `${item.name} / ${item.scope}`} />
    </div>
  );
}

function LexiconPanel(props: WriterProductWorkspaceProps) {
  const { locale } = props;
  return (
    <div>
      <h3><Bi zh="禁用词" en="Banned words" /></h3>
      <form action={props.actions.createLexicon} className="binding-form"><input name="term" required placeholder={tx(locale, "词语", "Term")} /><input name="guidance" placeholder={tx(locale, "替换建议", "Replacement guidance")} /><select name="severity" defaultValue="warning"><option value="warning">warning</option><option value="error">error</option></select><button type="submit"><Save size={14} /><Bi zh="添加词语" en="Add term" /></button></form>
      <SimpleDeleteList locale={locale} result={props.lexicon} idKey="lexicon_entry_id" action={props.actions.deleteLexicon} idName="entryId" empty={tx(locale, "词库为空。", "Lexicon is empty.")} label={(item) => `${item.term} / ${item.severity}`} />
    </div>
  );
}

function DedupPanel(props: WriterProductWorkspaceProps) {
  const { locale } = props;
  return (
    <div>
      <h3><Bi zh="重复的句子" en="Repeated sentences" /></h3>
      <form action={props.actions.startDedup} className="binding-form">
        <label htmlFor="dedup-source-kind"><Bi zh="从正文里找" en="Search in manuscript" /></label>
        <select id="dedup-source-kind" name="sourceKind" defaultValue={props.selectedBlockId ? "block" : "chapter"}>
          <option value="block">{tx(locale, "所选片段", "Selected section")}</option>
          <option value="chapter">{tx(locale, "所选章节", "Selected chapter")}</option>
        </select>
        <label htmlFor="dedup-block"><Bi zh="片段" en="Section" /></label>
        <BlockSelect id="dedup-block" blocks={props.blocks} locale={locale} name="blockId" selectedId={props.selectedBlockId} />
        <label htmlFor="dedup-chapter"><Bi zh="章节" en="Chapter" /></label>
        <ChapterSelect id="dedup-chapter" locale={locale} chapters={props.chapters} name="chapterId" selectedId={props.selectedChapterId} />
        <button type="submit" disabled={!props.selectedBlockId && !props.selectedChapterId}><Play size={14} /><Bi zh="找出重复的句子" en="Find repeated sentences" /></button>
      </form>
      {props.planningRun.ok && props.planningRun.value ? <div className="tool-result-item"><strong>{planningRunLabel(props.planningRun.value.workflow_type, locale)}</strong><span><StatusValue value={props.planningRun.value.status} /> / {props.planningRun.value.progress}%</span><WriterRefreshForm props={props} extra={{ planningRunId: props.planningRun.value.run_id }}><button type="submit"><FileClock size={14} /> <Bi zh="刷新进度" en="Refresh progress" /></button></WriterRefreshForm></div> : null}
      <ResultBoundary locale={locale} result={props.dedupPatterns} empty={tx(locale, "暂无重复候选。", "No repeated candidates.")} render={(patterns) => <div className="compact-action-list">{patterns.map((pattern) => <article className="tool-result-item" key={pattern.pattern_id}><strong>{pattern.pattern_text}</strong><small>{pattern.occurrence_count} occurrences / <StatusValue value={pattern.lifecycle} /></small><div className="inline-controls">{(["accept", "reject"] as const).map((decision) => <form action={props.actions.decideDedup} key={decision}><input name="patternId" type="hidden" value={pattern.pattern_id} /><input name="decision" type="hidden" value={decision} /><button type="submit">{decision === "accept" ? <Check size={14} /> : <X size={14} />}<StatusValue value={decision} /></button></form>)}</div></article>)}</div>} />
    </div>
  );
}

function CommandPanel(props: WriterProductWorkspaceProps) {
  const { locale } = props;
  return (
    <div>
      <form action={props.actions.startCommand} className="binding-form">
        <label htmlFor="writer-command-choice"><Bi zh="命令" en="Command" /></label>
        <select id="writer-command-choice" name="commandChoice" defaultValue="complete-outline">
          {MANUSCRIPT_COMMAND_CHOICES.map((command) => (
            <option key={command.choice} value={command.choice}>{tx(locale, command.zh, command.en)}</option>
          ))}
        </select>
        <label htmlFor="writer-command-chapter"><Bi zh="目标章节" en="Target chapter" /></label>
        <ChapterSelect id="writer-command-chapter" locale={locale} chapters={props.chapters} name="targetChapterId" selectedId={props.selectedChapterId} />
        <label htmlFor="writer-command-scene"><Bi zh="目标场景" en="Target scene" /></label>
        <SceneSelect id="writer-command-scene" locale={locale} name="targetSceneId" scenes={props.scenes} selectedId={props.selectedSceneId} />
        <label htmlFor="writer-command-block"><Bi zh="目标片段" en="Target section" /></label>
        <BlockSelect id="writer-command-block" blocks={props.blocks} locale={locale} name="targetBlockId" selectedId={props.selectedBlockId} />
        <button type="submit"><Play size={14} /><Bi zh="运行命令" en="Run command" /></button>
      </form>
      {props.command.ok && props.command.value ? <div className="tool-result-item"><strong>{manuscriptCommandLabel(props.command.value.command_type, locale)}</strong><span><StatusValue value={props.command.value.status} /></span><WriterRefreshForm props={props} extra={{ commandId: props.command.value.command_run_id }}><button type="submit"><FileClock size={14} /> <Bi zh="刷新进度" en="Refresh progress" /></button></WriterRefreshForm></div> : null}
    </div>
  );
}

function ExportPanel(props: WriterProductWorkspaceProps) {
  const { locale } = props;
  const completedExport = props.exports.ok ? props.exports.value.find((item) => item.status === "completed" && item.export_id && item.artifact_sha256) : undefined;
  return (
    <div>
      <form action={props.actions.createExport} className="inline-action-form"><input name="format" type="hidden" value="txt" /><button type="submit"><Play size={14} /><Bi zh="生成 TXT" en="Generate TXT" /></button></form>
      <ResultBoundary locale={locale} result={props.exports} empty={tx(locale, "暂无导出记录。", "No export records.")} render={(records) => <div className="compact-action-list">{records.map((record, index) => <div className="tool-result-item" key={record.export_id}><strong><Bi zh="导出" en="Export" /> {index + 1}</strong><span><StatusValue value={record.status} /> / {record.block_count} blocks</span></div>)}</div>} />
      {completedExport ? <a className="nav-link" download href={`/api/manuscript-export/${encodeURIComponent(props.tenantSlug)}/${encodeURIComponent(props.projectId)}?exportId=${encodeURIComponent(completedExport.export_id)}`}><Check size={14} /><Bi zh="下载已完成的 TXT" en="Download completed TXT" /></a> : null}
    </div>
  );
}

function ResultBoundary<T>({ locale, result, empty, render }: { locale: Locale; result: WriterWebResult<T[]> | WriterWebResult<T>; empty: string; render: (value: T[] & T) => React.ReactNode }) {
  if (!result.ok) return <p className="form-status error-box" role="alert">{tx(locale, "请求失败，请刷新后重试。", "Request failed. Refresh and retry.")}</p>;
  const value = result.value;
  if (Array.isArray(value) && value.length === 0) return <p className="form-hint">{empty}</p>;
  if (!Array.isArray(value) && isEmptyReviewList(value)) return <p className="form-hint">{empty}</p>;
  return <>{render(value as T[] & T)}</>;
}

function isEmptyReviewList(value: unknown) { return typeof value === "object" && value !== null && "reviews" in value && Array.isArray((value as { reviews: unknown[] }).reviews) && (value as { reviews: unknown[] }).reviews.length === 0; }
function DeleteForm({ action, idName, id, version, label }: { action: Action; idName: string; id: string; version: number; label: string }) {
  return (
    <form action={action} className="inline-action-form">
      <input name={idName} type="hidden" value={id} />
      <input name="expectedVersion" type="hidden" value={version} />
      <ConfirmSubmitButton
        cancelLabel={<Bi zh="取消" en="Cancel" />}
        confirmDescription={<Bi zh="此操作会删除该条目（可找回）。确认继续？" en="This deletes the item (recoverable). Continue?" />}
        confirmLabel={<Bi zh="确认删除" en="Confirm delete" />}
        confirmTitle={<Bi zh="确认删除" en="Confirm delete" />}
        idleLabel={<><Trash2 size={14} />{label}</>}
        pendingLabel={<Bi zh="处理中…" en="Working…" />}
        tone="danger"
      />
    </form>
  );
}
function VersionList({ locale, label, result }: { locale: Locale; label: string; result: WriterWebResult<WritingVersion[]> }) { return <div><h3>{label}</h3><ResultBoundary locale={locale} result={result} empty={tx(locale, "暂无版本。", "No versions.")} render={(items) => <div className="compact-action-list">{items.map((item) => <div className="tool-result-item" key={item.version_id}><strong>v{item.version_number} / {item.title}</strong><small>{item.change_kind}</small></div>)}</div>} /></div>; }
function SimpleDeleteList<T extends Record<string, unknown>>({ locale, result, idKey, action, idName, empty, label }: { locale: Locale; result: WriterWebResult<T[]>; idKey: keyof T; action: Action; idName: string; empty: string; label: (item: T) => string }) { return <ResultBoundary locale={locale} result={result} empty={empty} render={(items) => <div className="compact-action-list">{items.map((item) => <div className="tool-result-item" key={String(item[idKey])}><strong>{label(item)}</strong><form action={action}><input name={idName} type="hidden" value={String(item[idKey])} /><button type="submit"><Trash2 size={14} /><Bi zh="删除" en="Delete" /></button></form></div>)}</div>} />; }

function writerHref(props: Pick<WriterProductWorkspaceProps, "tenantSlug" | "projectId">) { return `/${props.tenantSlug}/projects/${props.projectId}/writer`; }

function reorderedIds<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const next = [...items];
  const target = index + direction;
  if (index < 0 || target < 0 || target >= next.length) return next;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function WriterSelectionFields({
  selectedBlockId,
  selectedChapterId,
  selectedCommandId,
  selectedDraftId,
  selectedSceneId,
}: Pick<WriterProductWorkspaceProps, "selectedBlockId" | "selectedChapterId" | "selectedCommandId" | "selectedDraftId" | "selectedSceneId">) {
  return (
    <>
      {selectedDraftId ? <input name="draftId" type="hidden" value={selectedDraftId} /> : null}
      {selectedChapterId ? <input name="chapterId" type="hidden" value={selectedChapterId} /> : null}
      {selectedSceneId ? <input name="sceneId" type="hidden" value={selectedSceneId} /> : null}
      {selectedBlockId ? <input name="blockId" type="hidden" value={selectedBlockId} /> : null}
      {selectedCommandId ? <input name="commandId" type="hidden" value={selectedCommandId} /> : null}
    </>
  );
}

function WriterRefreshForm({ children, extra, props }: { children: React.ReactNode; extra?: Record<string, string>; props: WriterProductWorkspaceProps }) {
  return (
    <form action={writerHref(props)} className="inline-action-form" method="get">
      <WriterSelectionFields
        selectedBlockId={props.selectedBlockId}
        selectedChapterId={props.selectedChapterId}
        selectedCommandId={props.selectedCommandId}
        selectedDraftId={props.selectedDraftId}
        selectedSceneId={props.selectedSceneId}
      />
      {extra ? Object.entries(extra).map(([key, value]) => value ? <input key={key} name={key} type="hidden" value={value} /> : null) : null}
      {children}
    </form>
  );
}

function ChapterNavigateForm({ chapterId, label, props }: { chapterId: string; label: React.ReactNode; props: WriterProductWorkspaceProps }) {
  return (
    <form action={writerHref(props)} className="inline-action-form" method="get">
      <WriterSelectionFields
        selectedBlockId={props.selectedBlockId}
        selectedChapterId={props.selectedChapterId}
        selectedCommandId={props.selectedCommandId}
        selectedDraftId={props.selectedDraftId}
        selectedSceneId={props.selectedSceneId}
      />
      <input name="chapterId" type="hidden" value={chapterId} />
      <button type="submit">{label}</button>
    </form>
  );
}

function SceneNavigateForm({ chapterId, label, props, sceneId }: { chapterId: string; label: React.ReactNode; props: WriterProductWorkspaceProps; sceneId: string }) {
  return (
    <form action={writerHref(props)} className="inline-action-form" method="get">
      <WriterSelectionFields
        selectedBlockId={props.selectedBlockId}
        selectedChapterId={props.selectedChapterId}
        selectedCommandId={props.selectedCommandId}
        selectedDraftId={props.selectedDraftId}
        selectedSceneId={props.selectedSceneId}
      />
      <input name="chapterId" type="hidden" value={chapterId} />
      <input name="sceneId" type="hidden" value={sceneId} />
      <button type="submit">{label}</button>
    </form>
  );
}

function ReorderButton({ action, ariaLabel, direction, disabled, extraFields, orderedBlockItems, orderedIds }: { action: Action; ariaLabel: string; direction: -1 | 1; disabled: boolean; extraFields?: Record<string, string>; orderedBlockItems?: string[]; orderedIds?: string[] }) {
  return (
    <form action={action} className="inline-action-form">
      {extraFields ? Object.entries(extraFields).map(([key, value]) => <input key={key} name={key} type="hidden" value={value} />) : null}
      {orderedIds?.map((id) => <input key={id} name="orderedIds" type="hidden" value={id} />)}
      {orderedBlockItems?.map((item) => <input key={item} name="orderedBlockItems" type="hidden" value={item} />)}
      <button aria-label={ariaLabel} disabled={disabled} type="submit">{direction === -1 ? <ArrowUp size={14} /> : <ArrowDown size={14} />}</button>
    </form>
  );
}

function ChapterSelect({ chapters, id, locale, name, selectedId }: { chapters: WriterWebResult<Chapter[]>; id: string; locale: Locale; name: string; selectedId: string }) {
  if (!chapters.ok || chapters.value.length === 0) {
    return <select aria-label={tx(locale, "章节", "Chapter")} disabled id={id} name={name}><option value="">{tx(locale, "暂无章节", "No chapter")}</option></select>;
  }
  return (
    <select aria-label={tx(locale, "章节", "Chapter")} defaultValue={selectedId || chapters.value[0]?.chapter_id} id={id} name={name}>
      <option value="">{tx(locale, "不指定章节", "No chapter")}</option>
      {chapters.value.map((chapter) => <option key={chapter.chapter_id} value={chapter.chapter_id}>{chapter.chapter_order}. {chapter.title}</option>)}
    </select>
  );
}

function SceneSelect({ id, locale, name, scenes, selectedId }: { id: string; locale: Locale; name: string; scenes: WriterWebResult<Scene[]>; selectedId: string }) {
  if (!scenes.ok || scenes.value.length === 0) {
    return <select aria-label={tx(locale, "场景", "Scene")} disabled id={id} name={name}><option value="">{tx(locale, "暂无场景", "No scene")}</option></select>;
  }
  return (
    <select aria-label={tx(locale, "场景", "Scene")} defaultValue={selectedId || scenes.value[0]?.scene_id} id={id} name={name}>
      <option value="">{tx(locale, "不指定场景", "No scene")}</option>
      {scenes.value.map((scene) => <option key={scene.scene_id} value={scene.scene_id}>{scene.scene_order}. {scene.title}</option>)}
    </select>
  );
}

function BlockSelect({ blocks, id, locale, name, selectedId }: { blocks: WriterWebResult<ManuscriptBlock[]>; id: string; locale: Locale; name: string; selectedId: string }) {
  if (!blocks.ok || blocks.value.length === 0) {
    return <select aria-label={tx(locale, "片段", "Section")} disabled id={id} name={name}><option value="">{tx(locale, "暂无片段", "No section")}</option></select>;
  }
  return (
    <select aria-label={tx(locale, "片段", "Section")} defaultValue={selectedId || blocks.value[0]?.block_id} id={id} name={name}>
      <option value="">{tx(locale, "不指定片段", "No section")}</option>
      {blocks.value.map((block) => (
        <option key={block.block_id} value={block.block_id}>
          {tx(locale, `片段 ${block.block_order}`, `Section ${block.block_order}`)} / {block.word_count} {tx(locale, "字", "words")}
        </option>
      ))}
    </select>
  );
}
