import Link from "next/link";
import { Boxes, ChevronRight, GitBranch, Network, UsersRound } from "lucide-react";

import { Bi } from "./bilingual-text";
import { workspacePathForProject } from "../lib/workspace-route";

type MaterialsHubProps = {
  tenantSlug: string;
  projectId: string;
  projectName?: string;
  basePath: string;
  tenantName?: string;
};

const entries = [
  {
    path: "/assets",
    zh: "资产库",
    en: "Asset library",
    hintZh: "世界规则、角色、风格与素材",
    hintEn: "Rules, characters, style, and materials",
    icon: Boxes,
  },
  {
    path: "/graph",
    zh: "故事图谱",
    en: "Story graph",
    hintZh: "实体关系与构建进度",
    hintEn: "Entities, bonds, and build progress",
    icon: Network,
  },
  {
    path: "/worldline",
    zh: "世界线",
    en: "Worldline",
    hintZh: "当前世界推演与事件",
    hintEn: "Simulation and events",
    icon: GitBranch,
  },
  {
    path: "/character-console",
    zh: "角色控制台",
    en: "Character console",
    hintZh: "角色互动与档案",
    hintEn: "Interaction and dossiers",
    icon: UsersRound,
  },
] as const;

export function MaterialsHub({
  tenantSlug,
  projectId,
  projectName,
  basePath,
  tenantName: _tenantName,
}: MaterialsHubProps) {
  void _tenantName;
  const project = { tenant_id: tenantSlug, project_id: projectId, name: projectName || projectId };

  return (
    <div className="mobile-hub materials-hub">
      <header className="mobile-hub-hero mobile-layer" data-layer="hero">
        <p className="eyebrow"><Bi zh="资料" en="Library" /></p>
        <h1><Bi zh="故事资料" en="Story materials" /></h1>
        <p>
          <Bi
            zh="在这里整理资产、图谱、世界线与角色。进入任一模块继续深度编辑。智能拆解完成后会自动写入素材库，可直接在资产库查看与编辑。"
            en="Organize assets, graph, worldline, and characters. Open a module to continue. Analysis results are auto-imported into the library when a run finishes."
          />
        </p>
      </header>

      <section
        aria-label="资料模块 / Material modules"
        className="mobile-paper-stack mobile-layer"
        data-layer="stack"
      >
        {entries.map((entry, index) => {
          const href = basePath
            ? workspacePathForProject([], project, entry.path)
            : `/${tenantSlug}/projects/${projectId}${entry.path}`;
          const Icon = entry.icon;
          return (
            <Link
              className="mobile-hub-card mobile-stack-row"
              href={href}
              key={entry.path}
              style={{ ["--stack-index" as string]: String(index) }}
            >
              <span className="mobile-hub-card-icon" aria-hidden="true">
                <Icon size={22} strokeWidth={1.8} />
              </span>
              <span className="mobile-hub-card-body">
                <strong><Bi zh={entry.zh} en={entry.en} /></strong>
                <small><Bi zh={entry.hintZh} en={entry.hintEn} /></small>
              </span>
              <ChevronRight aria-hidden="true" className="mobile-hub-card-chevron" size={18} />
            </Link>
          );
        })}
      </section>
    </div>
  );
}
