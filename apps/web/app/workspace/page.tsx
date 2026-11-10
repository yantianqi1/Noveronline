import type { Metadata } from "next";
import { Suspense } from "react";

import { WorkspaceShelf } from "./workspace-shelf";

export const metadata: Metadata = {
  title: "书架 · MiroFish Novel",
};

/**
 * Workspace home — the landing surface after sign-in.
 * The shelf is a client component that fetches the current user + projects
 * through the BFF; this file is just the route entry.
 */
export default function WorkspacePage() {
  return <Suspense><WorkspaceShelf /></Suspense>;
}
