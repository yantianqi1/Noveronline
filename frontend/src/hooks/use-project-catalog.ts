/**
 * Project catalog hook — lists projects via TanStack Query.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import { listProjects } from "@/api/project";
import type { Project } from "@/types/project";

const DEFAULT_PROJECT_LIMIT = 30;

export function useProjectCatalog(limit = DEFAULT_PROJECT_LIMIT) {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["projects", limit],
    queryFn: async () => {
      const response = await listProjects(limit);
      const raw = Array.isArray(response.data) ? response.data : [];
      // Backend returns project_id; frontend expects id.
      return raw.map((p: Record<string, unknown>) => ({
        ...p,
        id: p.project_id ?? p.id,
      })) as Project[];
    },
  });

  const projects = data ?? [];
  const latestProject = useMemo(() => projects[0] ?? null, [projects]);

  const refreshProjects = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
  }, [queryClient]);

  return { projects, latestProject, refreshProjects, isLoading, error } as const;
}
