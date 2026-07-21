"use client";

import { ChevronDown, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { Chapter, Scene, WriterWebResult } from "../lib/writer-workspace-api";
import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { useWriterWorkbench } from "./writer-workbench-context";

export type WriterChapterSwitcherProps = {
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
 * Canvas heading chapter dropdown (doc 36 W4). Replaces the left structure rail
 * for everyday navigation; full chapter CRUD stays on the Structure panel via ⌘K.
 */
export function WriterChapterSwitcher(props: WriterChapterSwitcherProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const workbench = useWriterWorkbench();
  const href = `/${props.tenantSlug}/projects/${props.projectId}/writer`;
  const chapters = props.chapters.ok ? props.chapters.value : [];
  const selected = chapters.find((chapter) => chapter.chapter_id === props.selectedChapterId);
  const label = selected
    ? tx(props.locale, `第 ${selected.chapter_order} 章 · ${selected.title}`, `Ch. ${selected.chapter_order} · ${selected.title}`)
    : tx(props.locale, "选择章节", "Select chapter");

  useEffect(() => {
    if (!open) return;
    function onPointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="writer-chapter-switcher" ref={rootRef}>
      <button
        aria-controls={menuId}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="writer-chapter-switcher-trigger"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span className="writer-chapter-switcher-label">{label}</span>
        <ChevronDown aria-hidden="true" className="writer-chapter-switcher-caret" size={14} />
      </button>
      {open ? (
        <div className="writer-chapter-switcher-menu" id={menuId} role="listbox">
          {chapters.length === 0 ? (
            <p className="form-hint">
              <Bi zh="暂无章节。用 ⌘K 打开「章节管理」创建。" en="No chapters yet. Use ⌘K → Chapter management to create one." />
            </p>
          ) : (
            <ul className="writer-chapter-switcher-list">
              {chapters.map((chapter) => {
                const active = chapter.chapter_id === props.selectedChapterId;
                return (
                  <li key={chapter.chapter_id}>
                    <form action={href} method="get">
                      <input name="chapterId" type="hidden" value={chapter.chapter_id} />
                      {props.selectedDraftId ? <input name="draftId" type="hidden" value={props.selectedDraftId} /> : null}
                      <button
                        aria-selected={active}
                        className="writer-chapter-switcher-item"
                        data-active={active ? "true" : "false"}
                        type="submit"
                      >
                        <span>
                          {tx(props.locale, `第 ${chapter.chapter_order} 章`, `Ch. ${chapter.chapter_order}`)}
                        </span>
                        <strong>{chapter.title}</strong>
                      </button>
                    </form>
                    {active && props.scenes.ok && props.scenes.value.length > 0 ? (
                      <ul className="writer-chapter-switcher-scenes">
                        {props.scenes.value.map((scene) => (
                          <li key={scene.scene_id}>
                            <form action={href} method="get">
                              <input name="chapterId" type="hidden" value={chapter.chapter_id} />
                              <input name="sceneId" type="hidden" value={scene.scene_id} />
                              {props.selectedDraftId ? (
                                <input name="draftId" type="hidden" value={props.selectedDraftId} />
                              ) : null}
                              <button
                                className="writer-chapter-switcher-item is-scene"
                                data-active={props.selectedSceneId === scene.scene_id ? "true" : "false"}
                                type="submit"
                              >
                                <span>{scene.scene_order}</span>
                                <strong>{scene.title}</strong>
                              </button>
                            </form>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
          <button
            className="writer-chapter-switcher-manage"
            onClick={() => {
              workbench?.setDrawer("structure");
              setOpen(false);
            }}
            type="button"
          >
            <Plus aria-hidden="true" size={14} />
            <Bi zh="章节管理" en="Chapter management" />
          </button>
        </div>
      ) : null}
    </div>
  );
}
