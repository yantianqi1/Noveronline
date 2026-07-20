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
  /**
   * When true, the in-panel tablist is hidden because chrome lives in the
   * canvas header via WriterArtifactTabChrome.
   */
  chromeInHeader?: boolean;
};

const tabIcons = {
  manuscript: BookOpenText,
  structure: ListTree,
  review: ShieldCheck,
  studio: SlidersHorizontal,
} satisfies Record<ArtifactTab, typeof BookOpenText>;

function tabLabel(locale: Locale, id: ArtifactTab) {
  if (locale === "zh-CN") {
    return (
      {
        manuscript: "稿件",
        structure: "章节",
        review: "审校",
        studio: "工具",
      } as const
    )[id];
  }
  return (
    {
      manuscript: "Manuscript",
      structure: "Structure",
      review: "Review",
      studio: "Tools",
    } as const
  )[id];
}

function useArtifactTabState() {
  const workbench = useWriterWorkbench();
  const [localTab, setLocalTab] = useState<ArtifactTab>("manuscript");
  const activeTab = workbench ? workbench.activeTab : localTab;
  const setActiveTab = workbench ? workbench.setActiveTab : setLocalTab;
  return { activeTab, setActiveTab };
}

/** Compact segmented control for the canvas header. */
export function WriterArtifactTabChrome({ locale }: { locale: Locale }) {
  const { activeTab, setActiveTab } = useArtifactTabState();
  const groupId = useId();
  const tabs: ArtifactTab[] = ["manuscript", "structure", "review", "studio"];

  return (
    <div
      aria-label={locale === "zh-CN" ? "稿件视图" : "Artifact views"}
      className="writer-artifact-tabchrome"
      data-chrome="header"
      role="tablist"
    >
      {tabs.map((id) => {
        const Icon = tabIcons[id];
        const selected = activeTab === id;
        return (
          <button
            aria-controls={`${groupId}-${id}-panel`}
            aria-selected={selected}
            className="writer-artifact-tabchrome-tab"
            id={`${groupId}-${id}-tab`}
            key={id}
            onClick={() => setActiveTab(id)}
            role="tab"
            type="button"
          >
            <Icon aria-hidden="true" size={14} strokeWidth={1.8} />
            <span>{tabLabel(locale, id)}</span>
          </button>
        );
      })}
    </div>
  );
}

export function WriterArtifactTabs(props: WriterArtifactTabsProps) {
  const { activeTab, setActiveTab } = useArtifactTabState();
  const groupId = useId();
  const chromeInHeader = props.chromeInHeader === true;
  const tabs: Array<{ id: ArtifactTab; label: string; content: ReactNode }> = [
    { id: "manuscript", label: tabLabel(props.locale, "manuscript"), content: props.manuscript },
    { id: "structure", label: tabLabel(props.locale, "structure"), content: props.structure },
    { id: "review", label: tabLabel(props.locale, "review"), content: props.review },
    { id: "studio", label: tabLabel(props.locale, "studio"), content: props.studio },
  ];

  return (
    <div
      className="writer-artifact-tabs"
      data-chrome={chromeInHeader ? "header" : "inline"}
    >
      {!chromeInHeader ? (
        <div
          aria-label={props.locale === "zh-CN" ? "稿件视图" : "Artifact views"}
          className="writer-artifact-tablist"
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
      ) : null}
      {tabs.map((tab) => (
        <section
          aria-label={chromeInHeader ? tab.label : undefined}
          aria-labelledby={chromeInHeader ? undefined : `${groupId}-${tab.id}-tab`}
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
