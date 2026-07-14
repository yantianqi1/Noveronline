"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTransition } from "react";
import { BookOpen, LayoutDashboard, PenLine, UserRound } from "lucide-react";

import { Bi } from "./bilingual-text";
import {
  signalWorkspaceNavigationComplete,
  signalWorkspaceNavigationStart,
} from "./workspace-route-transition";
import { matchesWorkspaceNavigationPath, workspacePathForProject } from "../lib/workspace-route";
import type { CurrentUserSummary } from "../lib/api";

type MobileTabBarProps = {
  tenantSlug: string;
  projectId: string;
  currentUser: CurrentUserSummary;
};

const tabs = [
  {
    id: "overview",
    path: "/overview",
    matchPaths: ["/overview"],
    zh: "总览",
    en: "Home",
    icon: LayoutDashboard,
  },
  {
    id: "materials",
    path: "/materials",
    matchPaths: ["/materials", "/assets", "/graph", "/worldline", "/character-console"],
    zh: "资料",
    en: "Library",
    icon: BookOpen,
  },
  {
    id: "writer",
    path: "/writer",
    matchPaths: ["/writer"],
    zh: "创作",
    en: "Write",
    icon: PenLine,
  },
  {
    id: "me",
    path: "/me",
    matchPaths: ["/me", "/llm-facility", "/security", "/members"],
    zh: "我的",
    en: "Me",
    icon: UserRound,
  },
] as const;

export function MobileTabBar({ tenantSlug, projectId, currentUser }: MobileTabBarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const activeTenants = currentUser.ok ? currentUser.active_tenants : [];
  const activeProjects = currentUser.ok ? currentUser.active_projects : [];
  const currentProject = activeProjects.find(
    (project) => project.tenant_id === tenantSlug && project.project_id === projectId,
  );

  return (
    <nav
      aria-busy={pending || undefined}
      aria-label="手机主导航 / Mobile primary navigation"
      className="mobile-tabbar"
    >
      {tabs.map((tab) => {
        const href = currentProject
          ? workspacePathForProject(activeTenants, currentProject, tab.path)
          : `/${tenantSlug}/projects/${projectId}${tab.path === "/overview" ? "/overview" : tab.path}`;
        const active = tab.matchPaths.some((section) =>
          matchesWorkspaceNavigationPath(
            pathname,
            currentProject
              ? workspacePathForProject(activeTenants, currentProject, section)
              : `/${tenantSlug}/projects/${projectId}${section === "/overview" ? "/overview" : section}`,
            section,
          ),
        );
        const Icon = tab.icon;
        return (
          <Link
            aria-current={active ? "page" : undefined}
            className="mobile-tabbar-item"
            data-active={active ? "true" : "false"}
            href={href}
            key={tab.id}
            onNavigate={(event) => {
              if (href === pathname) {
                return;
              }
              event.preventDefault();
              signalWorkspaceNavigationStart();
              startTransition(() => {
                router.push(href);
                signalWorkspaceNavigationComplete();
              });
            }}
            prefetch
          >
            <Icon aria-hidden="true" size={20} strokeWidth={active ? 2.1 : 1.8} />
            <span>
              <Bi zh={tab.zh} en={tab.en} />
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
