"use client";

import { BookOpenText, ListTree, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import type { Locale } from "../lib/locale";
import { useWriterWorkbench } from "./writer-workbench-context";

type ArtifactTab = "manuscript" | "structure" | "review" | "studio";

type WriterArtifactTabsProps = {
  locale: Locale;
  manuscript: ReactNode;
  structure: ReactNode;
  review: ReactNode;
  studio: ReactNode;
  /** Hide the tab chrome; panels stay for ⌘K / setActiveTab (doc 36 W4). */
  hideChrome?: boolean;
};

const tabIcons = {
  manuscript: BookOpenText,
  structure: ListTree,
  review: ShieldCheck,
  studio: SlidersHorizontal,
} satisfies Record<ArtifactTab, typeof BookOpenText>;

export function WriterArtifactTabs(props: WriterArtifactTabsProps) {
  const workbench = useWriterWorkbench();
  const [localTab, setLocalTab] = useState<ArtifactTab>("manuscript");
  // Prefer shared workbench state so the ⌘K palette can drive tabs; fall back to local state standalone.
  const activeTab = workbench ? workbench.activeTab : localTab;
  const setActiveTab = workbench ? workbench.setActiveTab : setLocalTab;
  const groupId = useId();
  const hideChrome = props.hideChrome === true;
  const tabs: Array<{ id: ArtifactTab; label: string; content: ReactNode }> = [
    { id: "manuscript", label: props.locale === "zh-CN" ? "稿件" : "Manuscript", content: props.manuscript },
    { id: "structure", label: props.locale === "zh-CN" ? "章节" : "Structure", content: props.structure },
    { id: "review", label: props.locale === "zh-CN" ? "审校" : "Review", content: props.review },
    { id: "studio", label: props.locale === "zh-CN" ? "工作室" : "Studio", content: props.studio },
  ];

  return (
    <div className="writer-artifact-tabs" data-chrome={hideChrome ? "hidden" : "visible"}>
      <div
        aria-label={props.locale === "zh-CN" ? "稿件视图" : "Artifact views"}
        className="writer-artifact-tablist"
        hidden={hideChrome}
        role="tablist"
      >
        {tabs.map((tab) => {
          const Icon = tabIcons[tab.id];
          const selected = activeTab === tab.id;
          return (
            <button
              aria-controls={`${groupId}-${tab.id}-panel`}
              aria-selected={selected}
              className="writer-artifact-tab"
              id={`${groupId}-${tab.id}-tab`}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              type="button"
            >
              <Icon aria-hidden="true" size={16} strokeWidth={1.8} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <section
          aria-labelledby={`${groupId}-${tab.id}-tab`}
          className="writer-artifact-tabpanel"
          hidden={activeTab !== tab.id}
          id={`${groupId}-${tab.id}-panel`}
          key={tab.id}
          role="tabpanel"
        >
          {tab.content}
        </section>
      ))}
    </div>
  );
}
