"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Feather, Plus, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { fetchCurrentUser, SessionError } from "@/lib/api/session";
import type { CurrentUser, TenantMembershipSummary } from "@/lib/api/types";
import {
  groupProjectsByTenant,
  manageableTenants,
  projectCount,
  type ProjectWithTenant,
} from "@/lib/workspace";

import { CreateProjectPanel } from "./create-project-panel";
import { ProjectCard } from "./project-card";
import { UserMenu } from "./user-menu";
import "./shelf-scene.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; currentUser: CurrentUser };

/**
 * The workspace shelf — the landing surface after sign-in.
 *
 * Fetches `GET /v1/me` (via the BFF) for the user plus every tenant/project
 * they belong to, then lays the room out as a warm study (see shelf-scene.css):
 * each tenant is one walnut shelf — a plaque, a row of standing volumes, and
 * a plank. Picking a volume stores the {tenant_id, project_id} selection and
 * routes into that project's workspace.
 */
export function WorkspaceShelf() {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const currentUser = await fetchCurrentUser();
      setState({ status: "ready", currentUser });
    } catch (error) {
      if (error instanceof SessionError && error.status === 401) {
        // Session expired or absent — back to sign-in.
        router.replace("/login");
        return;
      }
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "加载失败，请重试。",
      });
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  function persistSelection(tenantId: string, projectId: string) {
    // Selection is client-side state; scoped API calls will send X-Tenant-Id
    // plus the /v1/projects/{id} path. Persist it so the workspace can read it.
    try {
      window.sessionStorage.setItem(
        "mirofish.activeProject",
        JSON.stringify({ tenant_id: tenantId, project_id: projectId }),
      );
    } catch {
      // storage may be unavailable (private mode) — routing still works.
    }
  }

  function openProject(project: ProjectWithTenant) {
    persistSelection(project.tenant_id, project.project_id);
    router.push(`/projects/${project.project_id}`);
  }

  function enterCreated(project: { tenant_id: string; project_id: string }) {
    persistSelection(project.tenant_id, project.project_id);
    router.push(`/projects/${project.project_id}`);
  }

  return (
    <div className="shelf-scene flex min-h-screen flex-col bg-paper">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-6">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-panel bg-accent text-panel shadow-accent">
              <Feather className="size-4" aria-hidden />
            </span>
            <div className="leading-tight">
              <p className="font-brush text-lg text-ink">墨鱼小说</p>
              <p className="text-caption tracking-label text-muted">长篇小说工作台</p>
            </div>
          </div>
          {state.status === "ready" ? <UserMenu currentUser={state.currentUser} /> : null}
        </div>
      </header>

      {/* ── Shelf body ──────────────────────────────────────────────── */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 pb-24 pt-10">
        <AnimatePresence mode="wait">
          {state.status === "loading" ? (
            <ShelfSkeleton key="loading" />
          ) : state.status === "error" ? (
            <ErrorState key="error" message={state.message} onRetry={load} />
          ) : (
            <ShelfContent
              key="ready"
              currentUser={state.currentUser}
              onOpen={openProject}
              onCreated={enterCreated}
            />
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function ShelfContent({
  currentUser,
  onOpen,
  onCreated,
}: {
  currentUser: CurrentUser;
  onOpen: (project: ProjectWithTenant) => void;
  onCreated: (project: { tenant_id: string; project_id: string }) => void;
}) {
  const groups = groupProjectsByTenant(currentUser);
  const total = projectCount(currentUser);
  const creatableTenants = manageableTenants(currentUser);
  const [createOpen, setCreateOpen] = useState(false);
  // Stagger index runs across tenant boundaries so the whole room rises in
  // sequence; each layer owns a contiguous run (slot included, matching the
  // previous single-loop numbering).
  let nextIndex = 0;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* shelf heading */}
      <div className="mb-9 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-1.5 text-caption font-medium tracking-label text-muted">书架</p>
          <h1 className="font-serif text-display font-semibold leading-tight text-ink">
            你的故事世界
          </h1>
          <p className="mt-2 text-base text-muted">
            {total > 0
              ? `共 ${total} 部作品，分布在 ${groups.length} 个工作区。挑一部，继续写下去。`
              : "这里还空着，等你的第一部作品。"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {total > 0 ? (
            <div className="hidden items-baseline gap-2 rounded-modal border border-line bg-panel px-4 py-2.5 sm:flex">
              <span className="font-serif text-display font-semibold text-accent-strong">
                {total}
              </span>
              <span className="text-caption text-muted">部作品</span>
            </div>
          ) : null}
          {creatableTenants.length > 0 ? (
            <Button
              type="button"
              size="sm"
              onClick={() => setCreateOpen((open) => !open)}
              aria-expanded={createOpen}
            >
              <Plus className="size-4" aria-hidden />
              创建新作品
            </Button>
          ) : null}
        </div>
      </div>

      {creatableTenants.length > 0 ? (
        <CreateProjectPanel
          tenants={creatableTenants}
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={onCreated}
        />
      ) : null}

      {total === 0 ? (
        createOpen ? null : (
          <EmptyShelf
            canCreate={creatableTenants.length > 0}
            onCreate={() => setCreateOpen(true)}
          />
        )
      ) : (
        <div className="space-y-14">
          {groups.map(({ tenant, projects }) => {
            const startIndex = nextIndex;
            nextIndex += projects.length;
            return (
              <TenantShelf
                key={tenant.tenant_id}
                tenant={tenant}
                projects={projects}
                startIndex={startIndex}
                canCreate={canCreateInTenant(creatableTenants, tenant.tenant_id)}
                onOpen={onOpen}
                onCreate={() => setCreateOpen(true)}
              />
            );
          })}
        </div>
      )}
    </motion.div>
  );
}

/** One tenant's shelf: plaque above, volumes bottom-aligned on per-line planks. */
function TenantShelf({
  tenant,
  projects,
  startIndex,
  canCreate,
  onOpen,
  onCreate,
}: {
  tenant: TenantMembershipSummary;
  projects: ProjectWithTenant[];
  startIndex: number;
  canCreate: boolean;
  onOpen: (project: ProjectWithTenant) => void;
  onCreate: () => void;
}) {
  return (
    <section className="shelf-scene-layer">
      {/* plaque hung above the shelf */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="shelf-scene-plaque font-serif text-sm tracking-label">{tenant.name}</h2>
        <span className="text-caption text-muted-soft">{projects.length} 部</span>
      </div>
      {/* volumes standing on the planks, bottom-aligned by the row; each
          wrapped line gets its own plank from shelf-scene.css */}
      <div className="shelf-scene-row">
        {projects.map((project, i) => (
          <ProjectCard
            key={project.project_id}
            project={project}
            index={startIndex + i}
            onOpen={onOpen}
          />
        ))}
        {canCreate ? (
          <CreateVolumeCard index={startIndex + projects.length} onClick={onCreate} />
        ) : null}
      </div>
    </section>
  );
}

function canCreateInTenant(tenants: TenantMembershipSummary[], tenantId: string): boolean {
  return tenants.some((tenant) => tenant.tenant_id === tenantId);
}

/** A book-sized dashed slot standing on the plank, holding the next volume's place. */
function CreateVolumeCard({ index, onClick }: { index: number; onClick: () => void }) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.button
      type="button"
      onClick={onClick}
      initial={reduceMotion ? false : { opacity: 0, y: 26 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.08 + index * 0.06, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduceMotion ? undefined : { y: -10, rotate: -2 }}
      whileTap={reduceMotion ? undefined : { scale: 0.96 }}
      className="shelf-scene-slot"
    >
      <span className="shelf-scene-slot-mark" aria-hidden>
        <Plus className="size-4" aria-hidden />
      </span>
      <span className="shelf-scene-slot-title font-serif text-lg font-semibold">新建作品</span>
    </motion.button>
  );
}

/** An empty plank in the study: bare wood, a quill, and a paperweight. */
function EmptyShelf({ canCreate, onCreate }: { canCreate: boolean; onCreate: () => void }) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="shelf-scene-empty"
    >
      <div className="shelf-scene-empty-stage" aria-hidden="true">
        <Feather className="shelf-scene-empty-quill" aria-hidden />
        <span className="shelf-scene-empty-stone" aria-hidden />
        <div className="shelf-scene-plank shelf-scene-empty-plank" aria-hidden />
      </div>
      <h3 className="mt-8 font-serif text-xl font-semibold text-ink">还没有作品</h3>
      <p className="shelf-scene-empty-copy mt-2 text-sm leading-relaxed text-muted">
        {canCreate
          ? "书架还是空的。写下第一部作品的名字，开始你的故事世界。"
          : "你加入的工作区里还没有任何小说项目。请联系工作区管理员为你创建第一部作品，或接受邀请加入已有的项目。"}
      </p>
      {canCreate ? (
        <Button type="button" className="mt-6" onClick={onCreate}>
          <Plus className="size-4" aria-hidden />
          创建新作品
        </Button>
      ) : null}
    </motion.div>
  );
}

/** The same study stage with two toppled volumes — the shelf cannot be opened. */
function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="shelf-scene-empty"
    >
      <div className="shelf-scene-empty-stage" aria-hidden="true">
        <span className="shelf-scene-fallen shelf-scene-fallen-a" aria-hidden />
        <span className="shelf-scene-fallen shelf-scene-fallen-b" aria-hidden />
        <div className="shelf-scene-plank shelf-scene-empty-plank" aria-hidden />
      </div>
      <h3 className="mt-8 font-serif text-xl font-semibold text-ink">书架暂时打不开</h3>
      <p className="shelf-scene-empty-copy mt-2 text-sm leading-relaxed text-muted">{message}</p>
      <Button onClick={onRetry} variant="outline" className="mt-6">
        <RefreshCw className="size-4" aria-hidden />
        重新加载
      </Button>
    </motion.div>
  );
}

/** Loading placeholder: heading bars plus grey stand-in volumes on a plank. */
function ShelfSkeleton() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="mb-9">
        <div className="shelf-scene-skel-bar shelf-scene-skel-bar-eyebrow" />
        <div className="shelf-scene-skel-bar shelf-scene-skel-bar-title" />
        <div className="shelf-scene-skel-bar shelf-scene-skel-bar-copy" />
      </div>
      <div className="shelf-scene-layer">
        <div className="mb-4">
          <div className="shelf-scene-skel-bar shelf-scene-skel-bar-plaque" />
        </div>
        <div className="shelf-scene-row">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="shelf-scene-ghost" />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
