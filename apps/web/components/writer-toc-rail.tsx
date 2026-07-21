"use client";

import { ChevronLeft } from "lucide-react";
import { useState } from "react";

import type { Chapter, Scene, WriterWebResult } from "../lib/writer-workspace-api";
import { type Locale, tx } from "../lib/locale";
import { useWriterSelection } from "./writer-selection";

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
 * Client-side selection — clicking a chapter swaps the paper in place with no
 * page reload. Collapses to a thin strip; full chapter CRUD lives in the
 * Structure drawer.
 */
export function WriterTocRail(props: WriterTocRailProps) {
  const [collapsed, setCollapsed] = useState(false);
  const selection = useWriterSelection();
  const chapters = props.chapters.ok ? props.chapters.value : [];

  // Prefer live client selection when the provider is present; fall back to
  // server-provided selection on first paint.
  const currentChapterId = selection?.chapterId ?? props.selectedChapterId;
  const currentSceneId = selection?.sceneId ?? props.selectedSceneId;
  const scenes = selection ? selection.scenes : props.scenes.ok ? props.scenes.value : [];

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
        const current = chapter.chapter_id === currentChapterId;
        return (
          <div key={chapter.chapter_id}>
            <button
              className={`writer-toc-item ${current ? "is-current" : ""}`}
              onClick={() => selection?.selectChapter(chapter.chapter_id)}
              type="button"
            >
              <span className="writer-toc-title">
                {tx(props.locale, `第 ${chapter.chapter_order} 章 · ${chapter.title}`, `Ch. ${chapter.chapter_order} · ${chapter.title}`)}
              </span>
            </button>
            {current && scenes.length > 0
              ? scenes.map((scene) => (
                  <button
                    className={`writer-toc-item is-scene ${currentSceneId === scene.scene_id ? "is-current" : ""}`}
                    key={scene.scene_id}
                    onClick={() => selection?.selectScene(chapter.chapter_id, scene.scene_id)}
                    style={{ paddingLeft: 22 }}
                    type="button"
                  >
                    <span className="writer-toc-title">{scene.title}</span>
                  </button>
                ))
              : null}
          </div>
        );
      })}
    </aside>
  );
}
