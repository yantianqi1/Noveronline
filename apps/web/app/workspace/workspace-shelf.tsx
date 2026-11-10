"use client";

import { Feather } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { fetchCurrentUser, SessionError } from "@/lib/api/session";
import type { CurrentUser } from "@/lib/api/types";

import { ShelfContent } from "./shelf-content";
import { ShelfError, ShelfSkeleton } from "./shelf-states";
import { UserMenu } from "./user-menu";
import "./shelf-scene.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; currentUser: CurrentUser };

/** Authenticated project shelf; account and project data comes from the BFF. */
export function WorkspaceShelf() {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "ready", currentUser: await fetchCurrentUser() });
    } catch (error) {
      if (error instanceof SessionError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setState({ status: "error", message: error instanceof Error ? error.message : "加载失败，请重试。" });
    }
  }, [router]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="shelf-scene min-h-screen bg-paper">
      <a className="shelf-skip-link" href="#workspace-main">跳到作品书架</a>
      <header className="shelf-header">
        <div className="shelf-container flex h-16 items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-panel bg-accent text-panel">
              <Feather className="size-4" aria-hidden />
            </span>
            <div>
              <p className="font-brush text-lg text-ink">墨鱼小说</p>
              <p className="text-caption text-muted">长篇小说工作台</p>
            </div>
          </div>
          {state.status === "ready" ? <UserMenu currentUser={state.currentUser} /> : null}
        </div>
      </header>
      <main id="workspace-main" tabIndex={-1} className="shelf-container shelf-main">
        {state.status === "loading" ? <ShelfSkeleton /> : state.status === "error" ? (
          <ShelfError message={state.message} onRetry={load} />
        ) : <ShelfContent currentUser={state.currentUser} />}
      </main>
    </div>
  );
}
