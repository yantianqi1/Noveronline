"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { WriterRunEvent } from "../lib/api";
import { WriterRunStreamProvider, useWriterRunStream } from "./writer-run-stream";

type WriterRunSessionValue = {
  /** True while admission is in flight or the focused run is still streaming. */
  busy: boolean;
  /** Optimistic user instruction shown until the server thread catches up. */
  pendingInstruction: string | null;
  /** Client-admitted run id before RSC props catch up. */
  optimisticRunId: string | null;
  /** Home → task transition after the first successful admission. */
  hasLeftHome: boolean;
  beginSubmit: (instruction: string) => void;
  admitRun: (runId: string) => void;
  failSubmit: () => void;
  clearPendingInstruction: () => void;
};

const WriterRunSessionContext = createContext<WriterRunSessionValue | null>(null);

type WriterRunSessionProviderProps = {
  serverRunId: string;
  serverActive: boolean;
  initialEvents: WriterRunEvent[];
  tenantSlug: string;
  projectId: string;
  intervalMs?: number;
  children: ReactNode;
};

/**
 * Client session over the writer workbench: optimistic send feedback, immediate
 * SSE attach for a newly admitted run, and composer busy-lock while the run streams.
 */
export function WriterRunSessionProvider({
  serverRunId,
  serverActive,
  initialEvents,
  tenantSlug,
  projectId,
  intervalMs,
  children,
}: WriterRunSessionProviderProps) {
  const [pendingInstruction, setPendingInstruction] = useState<string | null>(null);
  const [optimisticRunId, setOptimisticRunId] = useState<string | null>(null);
  const [admissionPending, setAdmissionPending] = useState(false);
  const [hasLeftHome, setHasLeftHome] = useState(false);

  const runId = optimisticRunId || serverRunId;
  const streamEvents = runId === serverRunId ? initialEvents : [];
  // Stay subscribed for optimistic / in-flight runs so token events reach the thread
  // before RSC props catch up. Terminal events still collapse stream.active.
  const streamActiveProp =
    Boolean(runId) && (admissionPending || Boolean(optimisticRunId) || serverActive);

  useEffect(() => {
    if (!optimisticRunId) return;
    if (serverRunId === optimisticRunId && !serverActive) {
      setOptimisticRunId(null);
    }
  }, [optimisticRunId, serverRunId, serverActive]);

  const beginSubmit = useCallback((instruction: string) => {
    setPendingInstruction(instruction);
    setAdmissionPending(true);
  }, []);

  const admitRun = useCallback((nextRunId: string) => {
    setOptimisticRunId(nextRunId);
    setHasLeftHome(true);
  }, []);

  const failSubmit = useCallback(() => {
    setAdmissionPending(false);
    setPendingInstruction(null);
  }, []);

  const clearPendingInstruction = useCallback(() => {
    setPendingInstruction(null);
  }, []);

  return (
    <WriterRunStreamProvider
      active={streamActiveProp && Boolean(runId)}
      initialEvents={streamEvents}
      intervalMs={intervalMs}
      projectId={projectId}
      runId={runId}
      tenantSlug={tenantSlug}
    >
      <WriterRunSessionBridge
        admissionPending={admissionPending}
        admitRun={admitRun}
        beginSubmit={beginSubmit}
        clearPendingInstruction={clearPendingInstruction}
        failSubmit={failSubmit}
        hasLeftHome={hasLeftHome}
        optimisticRunId={optimisticRunId}
        pendingInstruction={pendingInstruction}
        serverActive={serverActive}
        setAdmissionPending={setAdmissionPending}
      >
        {children}
      </WriterRunSessionBridge>
    </WriterRunStreamProvider>
  );
}

function WriterRunSessionBridge({
  admissionPending,
  setAdmissionPending,
  pendingInstruction,
  optimisticRunId,
  hasLeftHome,
  serverActive,
  beginSubmit,
  admitRun,
  failSubmit,
  clearPendingInstruction,
  children,
}: {
  admissionPending: boolean;
  setAdmissionPending: (value: boolean) => void;
  pendingInstruction: string | null;
  optimisticRunId: string | null;
  hasLeftHome: boolean;
  serverActive: boolean;
  beginSubmit: (instruction: string) => void;
  admitRun: (runId: string) => void;
  failSubmit: () => void;
  clearPendingInstruction: () => void;
  children: ReactNode;
}) {
  const stream = useWriterRunStream();

  useEffect(() => {
    if (!admissionPending || !optimisticRunId) return;
    if (stream?.runId === optimisticRunId) {
      setAdmissionPending(false);
    }
  }, [admissionPending, optimisticRunId, setAdmissionPending, stream?.runId]);

  const busy =
    admissionPending ||
    stream?.active === true ||
    (serverActive && !optimisticRunId);

  const value = useMemo<WriterRunSessionValue>(
    () => ({
      busy,
      pendingInstruction,
      optimisticRunId,
      hasLeftHome,
      beginSubmit,
      admitRun,
      failSubmit,
      clearPendingInstruction,
    }),
    [
      admitRun,
      beginSubmit,
      busy,
      clearPendingInstruction,
      failSubmit,
      hasLeftHome,
      optimisticRunId,
      pendingInstruction,
    ],
  );

  return <WriterRunSessionContext.Provider value={value}>{children}</WriterRunSessionContext.Provider>;
}

/** Optimistic writer session controls; null outside WriterRunSessionProvider. */
export function useWriterRunSession(): WriterRunSessionValue | null {
  return useContext(WriterRunSessionContext);
}

type WriterHomeOrTaskProps = {
  showHomeInitially: boolean;
  home: ReactNode;
  task: ReactNode;
};

/** Keeps the home composer mounted through admission, then swaps to task layout. */
export function WriterHomeOrTask({ showHomeInitially, home, task }: WriterHomeOrTaskProps) {
  const session = useWriterRunSession();
  const showHome = showHomeInitially && !session?.hasLeftHome;
  return <>{showHome ? home : task}</>;
}
