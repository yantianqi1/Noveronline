import { computed, reactive } from "vue";

import { listProjects } from "../api/project.js";

const DEFAULT_PROJECT_LIMIT = 30;

export function createProjectCatalogStore(loadProjects, defaultLimit = DEFAULT_PROJECT_LIMIT) {
  const state = reactive({
    lastLimit: defaultLimit,
    projects: [],
  });
  const projects = computed(() => state.projects);
  const latestProject = computed(() => state.projects[0] || null);

  async function refreshProjects(limit = state.lastLimit) {
    state.lastLimit = limit;
    const response = await loadProjects(limit);
    state.projects = Array.isArray(response?.data) ? response.data : [];
    return state.projects;
  }

  return {
    projects,
    latestProject,
    refreshProjects,
  };
}

const sharedProjectCatalogStore = createProjectCatalogStore((limit) => listProjects(limit));

export function useProjectCatalog() {
  return sharedProjectCatalogStore;
}
