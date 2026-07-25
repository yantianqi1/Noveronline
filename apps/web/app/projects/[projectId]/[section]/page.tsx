import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { isValidSection, sectionBySlug, DEFAULT_SECTION } from "../workbench-nav";
import { WorkbenchPlaceholder } from "../workbench-placeholder";
import { OverviewWorkspace } from "../overview/overview-workspace";
import { SettingsWorkspace } from "../settings/settings-workspace";
import { WriterWorkspace } from "../writer/writer-workspace";
import { AssetWorkspace } from "../assets/asset-workspace";
import { GraphWorkspace } from "../graph/graph-workspace";
import { WorldlineWorkspace } from "../worldline/worldline-workspace";
import { CharacterConsoleWorkspace } from "../characters/character-console-workspace";

export const metadata: Metadata = {
  title: "工作台 · MiroFish Novel",
};

/**
 * A single workbench surface.
 *
 * The overview section renders the real import + analysis workbench; the other
 * mandated sections still show an honest placeholder until their domain
 * surfaces are built. Unknown slugs fall back to overview.
 */
export default async function WorkbenchSectionPage({
  params,
}: {
  params: Promise<{ projectId: string; section: string }>;
}) {
  const { projectId, section } = await params;

  if (!isValidSection(section)) {
    redirect(`/projects/${projectId}/${DEFAULT_SECTION}`);
  }

  const config = sectionBySlug(section);
  if (!config) {
    notFound();
  }

  if (section === "overview") {
    return <OverviewWorkspace projectId={projectId} />;
  }

  if (section === "settings") {
    return <SettingsWorkspace projectId={projectId} />;
  }

  if (section === "writer") {
    return <WriterWorkspace projectId={projectId} />;
  }

  if (section === "assets") {
    return <AssetWorkspace projectId={projectId} />;
  }

  if (section === "graph") {
    return <GraphWorkspace projectId={projectId} />;
  }

  if (section === "worldline") {
    return <WorldlineWorkspace projectId={projectId} />;
  }

  if (section === "characters") {
    return <CharacterConsoleWorkspace projectId={projectId} />;
  }

  return (
    <WorkbenchPlaceholder
      icon={config.icon}
      title={config.label}
      tagline={config.tagline}
    />
  );
}
