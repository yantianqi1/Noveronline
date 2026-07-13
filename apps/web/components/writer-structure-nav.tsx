import { FileText, Layers } from "lucide-react";
import type { ReactNode } from "react";

import type { Chapter, ManuscriptBlock, Scene, WriterWebResult } from "../lib/writer-workspace-api";
import { type Locale, tx } from "../lib/locale";
import { Bi, StatusValue } from "./bilingual-text";

export type WriterStructureNavProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  selectedChapterId: string;
  selectedSceneId: string;
  selectedBlockId: string;
  selectedDraftId?: string;
  chapters: WriterWebResult<Chapter[]>;
  scenes: WriterWebResult<Scene[]>;
  blocks: WriterWebResult<ManuscriptBlock[]>;
};

// Persistent left-rail navigator for the manuscript-primary studio. Navigation only:
// structure editing (create/reorder/version) stays in the center Structure tab.
export function WriterStructureNav(props: WriterStructureNavProps) {
  const { locale, chapters, scenes, blocks, selectedChapterId, selectedSceneId, selectedBlockId } = props;
  const href = `/${props.tenantSlug}/projects/${props.projectId}/writer`;
  const keepDraft = { draftId: props.selectedDraftId };
  const chapterCount = chapters.ok ? chapters.value.length : 0;
  const blockCount = blocks.ok ? blocks.value.length : 0;
  return (
    <div className="writer-structure-nav">
      <div className="writer-structure-nav-head">
        <p className="eyebrow"><Bi zh="结构" en="Structure" /></p>
        <h2><Bi zh="章节与正文" en="Chapters & manuscript" /></h2>
      </div>
      <nav className="writer-structure-nav-scroll" aria-label={tx(locale, "章节与正文导航", "Chapter and manuscript navigation")}>
        <div className="writer-structure-group">
          <p className="writer-structure-group-title">
            <Layers aria-hidden="true" size={13} /><Bi zh="章节" en="Chapters" /><span>{chapterCount}</span>
          </p>
          {chapters.ok && chapters.value.length > 0 ? (
            <ul className="writer-structure-list">
              {chapters.value.map((chapter) => {
                const active = selectedChapterId === chapter.chapter_id;
                return (
                  <li key={chapter.chapter_id}>
                    <NavRow
                      active={active}
                      fields={{ chapterId: chapter.chapter_id, blockId: selectedBlockId, ...keepDraft }}
                      href={href}
                    >
                      <span className="writer-structure-row-index">{chapter.chapter_order}</span>
                      <span className="writer-structure-row-title">{chapter.title}</span>
                      <small><StatusValue value={chapter.status} /></small>
                    </NavRow>
                    {active && scenes.ok && scenes.value.length > 0 ? (
                      <ul className="writer-structure-scene-list">
                        {scenes.value.map((scene) => (
                          <li key={scene.scene_id}>
                            <NavRow
                              active={selectedSceneId === scene.scene_id}
                              fields={{ chapterId: chapter.chapter_id, sceneId: scene.scene_id, blockId: selectedBlockId, ...keepDraft }}
                              href={href}
                              indent
                            >
                              <span className="writer-structure-row-index">{scene.scene_order}</span>
                              <span className="writer-structure-row-title">{scene.title}</span>
                            </NavRow>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="form-hint writer-structure-empty">
              <Bi zh="暂无章节。在中间「章节」标签创建。" en="No chapters yet. Create one in the Structure tab." />
            </p>
          )}
        </div>
        <div className="writer-structure-group">
          <p className="writer-structure-group-title">
            <FileText aria-hidden="true" size={13} /><Bi zh="正文块" en="Manuscript" /><span>{blockCount}</span>
          </p>
          {blocks.ok && blocks.value.length > 0 ? (
            <ul className="writer-structure-list">
              {blocks.value.map((block) => (
                <li key={block.block_id}>
                  <NavRow
                    active={selectedBlockId === block.block_id}
                    fields={{ blockId: block.block_id, chapterId: selectedChapterId, sceneId: selectedSceneId, ...keepDraft }}
                    href={href}
                  >
                    <span className="writer-structure-row-index">#{block.block_order}</span>
                    <span className="writer-structure-row-title">{block.word_count} {tx(locale, "字", "words")}</span>
                    <small><StatusValue value={block.status} /></small>
                  </NavRow>
                </li>
              ))}
            </ul>
          ) : (
            <p className="form-hint writer-structure-empty">
              <Bi zh="暂无正文块。采用草稿后出现。" en="No blocks yet. Adopt a draft to populate." />
            </p>
          )}
        </div>
      </nav>
    </div>
  );
}

export function WriterStructureNavLoading() {
  return (
    <div className="writer-structure-nav writer-structure-nav-loading" aria-hidden="true">
      <div className="writer-structure-nav-head">
        <p className="eyebrow">结构</p>
        <h2>章节与正文</h2>
      </div>
      <div className="writer-structure-nav-scroll">
        {[0, 1, 2, 3, 4].map((index) => <i className="writer-structure-skeleton-row" key={index} />)}
      </div>
    </div>
  );
}

function NavRow({
  active,
  children,
  fields,
  href,
  indent,
}: {
  active: boolean;
  children: ReactNode;
  fields: Record<string, string | undefined>;
  href: string;
  indent?: boolean;
}) {
  return (
    <form action={href} className="writer-structure-nav-form" method="get">
      {Object.entries(fields).map(([name, value]) => (value ? <input key={name} name={name} type="hidden" value={value} /> : null))}
      <button
        aria-current={active ? "true" : undefined}
        className={`writer-structure-row ${active ? "is-selected" : ""} ${indent ? "is-scene" : ""}`}
        type="submit"
      >
        {children}
      </button>
    </form>
  );
}
