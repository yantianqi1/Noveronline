/**
 * WriterStatusBarHost — owns plan discovery + status polling + renders the
 * top StatusBar. Keeps plumbing out of page.tsx.
 *
 * - Resolves the focused plan id: pinnedPlanId (store) falls back to the
 *   most recently updated active plan for the current project.
 * - Polls GET /book-plans/{planId}/status via useBookPlanStatus, which
 *   pushes into useBookRunStatusStore.
 * - Renders BookRunStatusBar.
 */

import * as React from "react";

import {
  useBookPlanStatus,
  useActiveBookPlan,
} from "@/hooks/use-book-plan-status";
import { useBookRunStatusStore } from "@/stores/book-run-store";
import { useWriterLayoutStore } from "@/stores/writer-layout-store";
import { abortBookRun } from "@/api/writer-agent";

import { BookRunStatusBar } from "./book-run-status-bar";

export interface WriterStatusBarHostProps {
  projectId: string;
  onOpenDrawer: () => void;
}

export function WriterStatusBarHost({
  projectId,
  onOpenDrawer,
}: WriterStatusBarHostProps) {
  const pinnedPlanId = useWriterLayoutStore((s) => s.pinnedPlanId);
  const { activePlan } = useActiveBookPlan(projectId || null);
  const resolvedPlanId = pinnedPlanId ?? activePlan?.plan_id ?? null;

  useBookPlanStatus(resolvedPlanId);

  const status = useBookRunStatusStore((s) => s.status);
  const running = useBookRunStatusStore((s) => s.running);

  const handleAbort = React.useCallback(async () => {
    if (!status?.plan_id) return;
    try {
      await abortBookRun(status.plan_id);
    } catch {
      // Non-cooperative abort path; UI will reflect via next poll.
    }
  }, [status?.plan_id]);

  return (
    <BookRunStatusBar
      onOpenDrawer={onOpenDrawer}
      onAbort={running ? handleAbort : undefined}
      onCreatePlan={onOpenDrawer}
    />
  );
}
