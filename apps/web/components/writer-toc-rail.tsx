"use client";

import { ChevronLeft } from "lucide-react";
import { useState } from "react";

import type { Chapter, Scene, WriterWebResult } from "../lib/writer-workspace-api";
import { type Locale, tx } from "../lib/locale";

export type WriterTocRailProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  selectedChapterId: string;
  selectedSceneId: string;
  selectedDraftId?: string;
  chapters: WriterWebResult<Chapter[]>;
  scenes: WriterWebResult<Scene[]>;
};

/**
 * Left table-of-contents rail: everyday chapter navigation made permanent.
 * Collapses to a thin strip; the full chapter CRUD lives in the Structure drawer.
 */
export function WriterTocRail(props: WriterTocRailProps) {
  const [collapsed, setCollapsed] = useState(false);
  const href = `/${props.tenantSlug}/projects/${props.projectId}/writer`;
  const chapters = props.chapters.ok ? props.chapters.value : [];
  const scenes = props.scenes.ok ? props.scenes.value : [];

  return (
    <aside
      aria-label={tx(props.locale, "章节目录", "Chapter outline")}
      className={`writer-toc ${collapsed ? "is-collapsed" : ""}`}
    >
      <div className="writer-toc-head">
        <span>{tx(props.locale, "目录", "Contents")}</span>
        <button
          aria-label={collapsed ? tx(props.locale, "展开目录", "Expand outline") : tx(props.locale, "收起目录", "Collapse outline")}
          className="writer-toc-fold"
          onClick={() => setCollapsed((value) => !value)}
          type="button"
        >
          <ChevronLeft aria-hidden="true" size={14} />
        </button>
      </div>
      {chapters.map((chapter) => {
        const current = chapter.chapter_id === props.selectedChapterId;
        return (
          <div key={chapter.chapter_id}>
            <form action={href} method="get">
              <input name="chapterId" type="hidden" value={chapter.chapter_id} />
              {props.selectedDraftId ? <input name="draftId" type="hidden" value={props.selectedDraftId} /> : null}
              <button
                className={`writer-toc-item ${current ? "is-current" : ""}`}
                type="submit"
              >
                <span className="writer-toc-title">
                  {tx(props.locale, `第 ${chapter.chapter_order} 章 · ${chapter.title}`, `Ch. ${chapter.chapter_order} · ${chapter.title}`)}
                </span>
              </button>
            </form>
            {current && scenes.length > 0
              ? scenes.map((scene) => (
                  <form action={href} key={scene.scene_id} method="get">
                    <input name="chapterId" type="hidden" value={chapter.chapter_id} />
                    <input name="sceneId" type="hidden" value={scene.scene_id} />
                    {props.selectedDraftId ? <input name="draftId" type="hidden" value={props.selectedDraftId} /> : null}
                    <button
                      className={`writer-toc-item is-scene ${props.selectedSceneId === scene.scene_id ? "is-current" : ""}`}
                      style={{ paddingLeft: 22 }}
                      type="submit"
                    >
                      <span className="writer-toc-title">{scene.title}</span>
                    </button>
                  </form>
                ))
              : null}
          </div>
        );
      })}
    </aside>
  );
}
