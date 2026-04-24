/**
 * Book-plan status + active-plan polling hooks for the writer StatusBar.
 *
 * - `useBookPlanStatus(planId)` — polls GET /api/writer-agent/book-plans/{planId}/status
 *   every 10s while the tab is visible (refetchIntervalInBackground = false).
 *   Also pushes each response into `useBookRunStatusStore` so subscribers see
 *   a single source of truth.
 * - `useActiveBookPlan(projectId)` — one-shot fetch of the currently active
 *   plan for a project; StatusBar uses this to auto-focus when no plan is
 *   pinned by the user.
 */

import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { getActiveBookPlan, getBookPlanStatus } from "@/api/writer-agent";
import {
  useBookRunStatusStore,
  type BookRunPlanStatus,
} from "@/stores/book-run-store";

const STATUS_POLL_MS = 10_000;
const ACTIVE_PLAN_POLL_MS = 30_000;

export function useBookPlanStatus(planId: string | null) {
  const setPlanId = useBookRunStatusStore((s) => s.setPlanId);
  const setFromStatus = useBookRunStatusStore((s) => s.setFromStatus);

  React.useEffect(() => {
    setPlanId(planId);
  }, [planId, setPlanId]);

  const query = useQuery({
    queryKey: ["book-plan-status", planId],
    enabled: Boolean(planId),
    refetchInterval: STATUS_POLL_MS,
    refetchIntervalInBackground: false,
    queryFn: async () => {
      if (!planId) return null;
      const resp = await getBookPlanStatus(planId);
      return (resp.data as BookRunPlanStatus | null) ?? null;
    },
  });

  React.useEffect(() => {
    if (query.data) {
      setFromStatus(query.data);
    }
  }, [query.data, setFromStatus]);

  return {
    status: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error,
  } as const;
}

export function useActiveBookPlan(projectId: string | null) {
  const query = useQuery({
    queryKey: ["book-plan-active", projectId],
    enabled: Boolean(projectId),
    refetchInterval: ACTIVE_PLAN_POLL_MS,
    refetchIntervalInBackground: false,
    queryFn: async () => {
      if (!projectId) return null;
      const resp = await getActiveBookPlan(projectId);
      return (resp.data as { plan_id: string } | null) ?? null;
    },
  });
  return {
    activePlan: query.data ?? null,
    isLoading: query.isLoading,
  } as const;
}
