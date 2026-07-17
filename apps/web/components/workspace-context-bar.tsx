"use client";

import { BookOpenText, ChevronRight } from "lucide-react";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Bi } from "./bilingual-text";

type WorkspaceContextBarProps = {
  projectName: ReactNode;
};

const STAGES: Record<string, { label: ReactNode; activity: ReactNode | null }> = {
  overview: {
    label: <Bi zh="项目总览" en="Overview" />,
    activity: <Bi zh="下一步与分析进度" en="Next step and analysis" />,
  },
  materials: {
    label: <Bi zh="资料" en="Library" />,
    activity: <Bi zh="资产、图谱与角色入口" en="Assets, graph, and characters" />,
  },
  me: {
    label: <Bi zh="我的" en="Me" />,
    activity: <Bi zh="账户与模型设置" en="Account and model settings" />,
  },
  assets: {
    label: <Bi zh="资产库" en="Assets" />,
    // Counts are injected by AssetLibraryShell into the command-meta slot.
    activity: null,
  },
  graph: {
    label: <Bi zh="故事图谱" en="Story Graph" />,
    activity: <Bi zh="探索关系与结构" en="Explore relations and structure" />,
  },
  worldline: {
    label: <Bi zh="世界线" en="Worldline" />,
    activity: <Bi zh="当前世界时间线" en="Current-world timeline" />,
  },
  "character-console": {
    label: <Bi zh="角色" en="Characters" />,
    activity: null,
  },
  characters: {
    label: <Bi zh="角色" en="Characters" />,
    activity: null,
  },
  writer: {
    label: <Bi zh="写作台" en="Writer" />,
    activity: <Bi zh="手稿正文与审校" en="Prose and review" />,
  },
  "llm-facility": {
    label: <Bi zh="模型设置" en="Model settings" />,
    activity: <Bi zh="能力绑定与渠道" en="Capability bindings" />,
  },
  llm: {
    label: <Bi zh="模型设置" en="Model settings" />,
    activity: <Bi zh="能力绑定与渠道" en="Capability bindings" />,
  },
  members: {
    label: <Bi zh="成员" en="Members" />,
    activity: <Bi zh="协作与邀请" en="Collaboration" />,
  },
  security: {
    label: <Bi zh="账户安全" en="Security" />,
    activity: <Bi zh="密码与会话" en="Password and sessions" />,
  },
};

export function WorkspaceContextBar({ projectName }: WorkspaceContextBarProps) {
  const pathname = usePathname() || "";
  const stage = stageFromPathname(pathname);

  return (
    <div className="app-command-bar project-context-bar" aria-label="工作区上下文 / Workspace context">
      <div className="app-breadcrumb">
        <span className="app-breadcrumb-icon" aria-hidden="true">
          <BookOpenText size={17} strokeWidth={1.8} />
        </span>
        <span>MiroFish Novel</span>
        <ChevronRight aria-hidden="true" size={14} />
        <strong>{projectName}</strong>
        <ChevronRight aria-hidden="true" size={14} />
        <span className="app-stage-label">{stage.label}</span>
      </div>
      <div className="app-command-trailing">
        <span className="workspace-command-meta" data-workspace-command-meta />
        {stage.activity ? (
          <span className="app-command-label">
            <span className="app-activity-dot" aria-hidden="true" />
            {stage.activity}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function stageFromPathname(pathname: string) {
  const parts = pathname.split("/").filter(Boolean);
  // /p/{key}/section or /tenant/projects/id/section
  let segment = "overview";
  const projectsIdx = parts.indexOf("projects");
  if (projectsIdx >= 0 && parts[projectsIdx + 2]) {
    segment = parts[projectsIdx + 2];
  } else if (parts[0] === "p" && parts[2]) {
    segment = parts[2];
  } else if (parts.length === 2 && parts[0] === "p") {
    segment = "overview";
  }
  return STAGES[segment] || STAGES.overview;
}
