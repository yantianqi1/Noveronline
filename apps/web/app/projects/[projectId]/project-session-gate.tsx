"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { fetchCurrentUser, SessionError } from "@/lib/api/session";

type Selection = { tenant_id: string; project_id: string };
type SessionState = { status: "loading" | "ready" } | { status: "error"; message: string };

async function resolveSelection(projectId: string): Promise<Selection> {
  const user = await fetchCurrentUser();
  const project = user.active_projects.find((item) => item.project_id === projectId);
  if (!project || !user.active_tenants.some((tenant) => tenant.tenant_id === project.tenant_id)) {
    throw new SessionError("你目前无法访问这部作品，请返回书架选择可用作品。", "PROJECT_UNAVAILABLE");
  }
  return { tenant_id: project.tenant_id, project_id: project.project_id };
}

function rememberSelection(selection: Selection) {
  try {
    window.sessionStorage.setItem("mirofish.activeProject", JSON.stringify(selection));
  } catch {
    throw new SessionError("无法保存作品选择。请允许本站使用浏览器存储后重试。", "STORAGE_UNAVAILABLE");
  }
}

/** Initialize every workbench from real membership, including direct/new-tab links. */
export function ProjectSessionGate({ projectId, children }: { projectId: string; children: ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    void (async () => {
      try {
        const selection = await resolveSelection(projectId);
        if (!active) return;
        rememberSelection(selection);
        setState({ status: "ready" });
      } catch (error) {
        if (!active) return;
        if (error instanceof SessionError && error.status === 401) {
          const returnTo = window.location.pathname + window.location.search + window.location.hash;
          router.replace(`/login?returnTo=${encodeURIComponent(returnTo)}`);
          return;
        }
        setState({ status: "error", message: error instanceof SessionError ? error.message : "暂时无法打开作品，请重试。" });
      }
    })();
    return () => { active = false; };
  }, [projectId, attempt, router]);

  if (state.status === "ready") return children;
  return <ProjectSessionStatus state={state} onRetry={() => setAttempt((value) => value + 1)} />;
}

function ProjectSessionStatus({ state, onRetry }: { state: SessionState; onRetry: () => void }) {
  return (
    <main className="grid min-h-dvh place-content-center bg-paper px-6 text-center">
      {state.status === "error" ? (
        <>
          <h1 className="font-serif text-xl font-semibold text-ink">作品暂时打不开</h1>
          <p className="mt-3 max-w-md text-base text-muted" role="alert">{state.message}</p>
          <div className="mt-6 flex items-center justify-center gap-4">
            <Button className="h-11" onClick={onRetry}>重新加载</Button>
            <Link href="/workspace" className="inline-flex min-h-11 items-center rounded-control px-3 text-sm text-accent">返回书架</Link>
          </div>
        </>
      ) : <p role="status" className="text-base text-muted">正在打开作品…</p>}
    </main>
  );
}
