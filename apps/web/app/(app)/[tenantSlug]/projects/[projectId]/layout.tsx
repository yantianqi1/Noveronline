import { ProjectNav } from "../../../../../components/project-nav";

export default async function ProjectLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ tenantSlug: string; projectId: string }>;
}>) {
  const { tenantSlug, projectId } = await params;
  const basePath = `/${tenantSlug}/projects/${projectId}`;

  return (
    <div className="app-frame">
      <aside className="app-sidebar" aria-label="Project navigation">
        <p className="eyebrow">Tenant</p>
        <h2>{tenantSlug}</h2>
        <p>Project: {projectId}</p>
        <ProjectNav basePath={basePath} />
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
