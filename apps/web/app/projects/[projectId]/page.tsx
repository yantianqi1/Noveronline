import { redirect } from "next/navigation";

import { DEFAULT_SECTION } from "./workbench-nav";

/** The project root redirects into the default workbench (overview). */
export default async function ProjectWorkspacePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  redirect(`/projects/${projectId}/${DEFAULT_SECTION}`);
}
