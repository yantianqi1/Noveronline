/**
 * Seed project ID helpers — ported from src-vue/views/overview/seedProjectId.js
 */

function normalizeProjectId(value: unknown): string {
  if (typeof value !== "string") return "";
  return value.trim();
}

interface ProjectRecord {
  projectId: string;
  name: string;
}

function normalizeProjectRecord(
  project: { id?: string; project_id?: string; name?: string } | null,
): ProjectRecord | null {
  if (!project || typeof project !== "object" || Array.isArray(project)) return null;
  const projectId = normalizeProjectId(project.id ?? project.project_id);
  if (!projectId) return null;
  const name = typeof project.name === "string" ? project.name.trim() : "";
  return { projectId, name };
}

export function resolveSeedProjectId(
  projectIdOverride: string,
  fallbackProjectId: string,
): string | undefined {
  const override = normalizeProjectId(projectIdOverride);
  if (override) return override;
  const fallback = normalizeProjectId(fallbackProjectId);
  return fallback || undefined;
}

export function buildSeedProjectOptions(
  projects: Array<{ id?: string; project_id?: string; name?: string }> = [],
): Array<{ value: string; label: string }> {
  if (!Array.isArray(projects)) return [];
  return projects
    .map(normalizeProjectRecord)
    .filter((p): p is ProjectRecord => p !== null)
    .map((project) => ({
      value: project.projectId,
      label: `${project.name || project.projectId} \u00b7 ${project.projectId}`,
    }));
}

export function resolveSeedProjectSelection(
  projects: Array<{ id?: string; project_id?: string; name?: string }> = [],
  currentProjectId = "",
): string {
  const options = buildSeedProjectOptions(projects);
  const current = normalizeProjectId(currentProjectId);
  if (current && options.some((item) => item.value === current)) return current;
  return options[0]?.value || "";
}
