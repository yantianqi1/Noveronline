"use client";

import { Plus, Search, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import type { CurrentUser } from "@/lib/api/types";
import { groupProjectsByTenant, manageableTenants } from "@/lib/workspace";

import { CreateProjectPanel } from "./create-project-panel";
import { ProjectCard } from "./project-card";
import { EmptyShelf } from "./shelf-states";

export function ShelfContent({ currentUser }: { currentUser: CurrentUser }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchId = useId();
  const searchRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [createOpen, setCreateOpen] = useState(false);
  const tenants = useMemo(() => manageableTenants(currentUser), [currentUser]);
  const groups = useMemo(() => groupProjectsByTenant(currentUser), [currentUser]);
  const total = currentUser.active_projects.length;
  const normalizedQuery = query.normalize("NFKC").trim().toLocaleLowerCase("zh-CN");
  const visibleGroups = groups.map((group) => ({
    ...group,
    projects: group.projects.filter((project) =>
      project.name.normalize("NFKC").toLocaleLowerCase("zh-CN").includes(normalizedQuery)),
  })).filter((group) => group.projects.length > 0);
  const visibleCount = visibleGroups.reduce((count, group) => count + group.projects.length, 0);

  useEffect(() => { setQuery(searchParams.get("q") ?? ""); }, [searchParams]);

  function search(value: string) {
    setQuery(value);
    const url = new URL(window.location.href);
    if (value.trim()) url.searchParams.set("q", value);
    else url.searchParams.delete("q");
    window.history.replaceState(null, "", url);
  }

  function clearSearch() {
    search("");
    searchRef.current?.focus();
  }

  return (
    <>
      <div className="shelf-heading">
        <div className="min-w-0">
          <h1 className="font-serif text-display font-semibold text-ink">你的故事世界</h1>
          <p className="mt-2 text-base text-muted">
            {total > 0 ? "挑一部作品，接着写下去。" : "从一个名字开始，写下你的第一部作品。"}
          </p>
        </div>
        {tenants.length > 0 && total > 0 ? (
          <Button className="h-11 shrink-0" onClick={() => setCreateOpen(true)} aria-haspopup="dialog">
            <Plus className="size-4" aria-hidden />创建新作品
          </Button>
        ) : null}
      </div>

      {total > 0 ? (
        <div className="shelf-toolbar">
          <p className="text-sm text-muted" role="status" aria-live="polite" aria-atomic="true">
            {normalizedQuery ? "搜索结果" : "全部作品"}
            <span className="ml-2 font-medium tabular-nums text-ink">{visibleCount} 部</span>
          </p>
          <div className="shelf-search" role="search" aria-label="搜索作品">
            <label htmlFor={searchId} className="sr-only">搜索作品名称</label>
            <Search className="pointer-events-none absolute left-3 size-4 text-muted" aria-hidden />
            <Input id={searchId} ref={searchRef} type="search" name="q" autoComplete="off"
              value={query} onChange={(event) => search(event.target.value)}
              placeholder="搜索作品名称…" className="pl-10 pr-11"
              onKeyDown={(event) => { if (event.key === "Escape" && query) { event.preventDefault(); clearSearch(); } }} />
            {query ? <IconButton label="清除搜索" className="absolute right-1 size-11" onClick={clearSearch}>
              <X className="size-4" aria-hidden />
            </IconButton> : null}
          </div>
        </div>
      ) : null}

      {total === 0 ? <EmptyShelf canCreate={tenants.length > 0} onCreate={() => setCreateOpen(true)} /> : (
        <div className="shelf-groups">
          {visibleGroups.map(({ tenant, projects }) => (
            <section key={tenant.tenant_id} className="shelf-scene-layer" aria-label={tenant.name}>
              <div className="shelf-section-heading">
                <h2 className="min-w-0 break-words font-serif text-lg font-semibold text-ink">{tenant.name}</h2>
                {groups.length > 1 ? <span className="shrink-0 text-caption text-muted">{projects.length} 部</span> : null}
              </div>
              <div className="shelf-scene-row">
                {projects.map((project) => <ProjectCard key={project.project_id} project={project} />)}
              </div>
            </section>
          ))}
          {visibleCount === 0 ? (
            <div className="shelf-no-results">
              <Search className="size-6 text-muted" aria-hidden />
              <h2 className="mt-4 font-serif text-xl font-semibold">没有找到匹配的作品</h2>
              <p className="mt-2 text-base text-muted">试试书名中的其他字，或查看全部作品。</p>
              <Button variant="outline" className="mt-6 h-11" onClick={clearSearch}>清除搜索</Button>
            </div>
          ) : null}
        </div>
      )}

      {createOpen ? <CreateProjectPanel tenants={tenants} onClose={() => setCreateOpen(false)}
        onCreated={(project) => router.push(`/projects/${project.project_id}`)} /> : null}
    </>
  );
}
