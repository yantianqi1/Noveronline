function normalizeProjectId(value) {
  if (typeof value !== "string") {
    return "";
  }
  return value.trim();
}

function normalizeProjectRecord(project) {
  if (!project || typeof project !== "object" || Array.isArray(project)) {
    return null;
  }
  const projectId = normalizeProjectId(project.project_id);
  if (!projectId) {
    return null;
  }
  const name = typeof project.name === "string" ? project.name.trim() : "";
  return {
    projectId,
    name,
  };
}

export function resolveSeedProjectId(projectIdOverride, fallbackProjectId) {
  const override = normalizeProjectId(projectIdOverride);
  if (override) {
    return override;
  }
  const fallback = normalizeProjectId(fallbackProjectId);
  return fallback || undefined;
}

export function buildSeedProjectOptions(projects = []) {
  if (!Array.isArray(projects)) {
    return [];
  }
  return projects
    .map(normalizeProjectRecord)
    .filter(Boolean)
    .map((project) => ({
      value: project.projectId,
      label: `${project.name || project.projectId} · ${project.projectId}`,
    }));
}

export function resolveSeedProjectSelection(projects = [], currentProjectId = "") {
  const options = buildSeedProjectOptions(projects);
  const current = normalizeProjectId(currentProjectId);
  if (current && options.some((item) => item.value === current)) {
    return current;
  }
  return options[0]?.value || "";
}
