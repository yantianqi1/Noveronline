"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { roleLabel, type ProjectWithTenant } from "@/lib/workspace";

import "./shelf-book.css";

/** Keep a novel's cover colour stable across visits. */
function coverVariant(projectId: string): number {
  let hash = 0;
  for (let i = 0; i < projectId.length; i += 1) {
    hash = (hash * 31 + projectId.charCodeAt(i)) % 9973;
  }
  return hash % 6;
}

/** Decorative binding above the full, readable title and real membership role. */
export function ProjectCard({ project }: {
  project: ProjectWithTenant;
}) {
  return (
    <Link
      href={`/projects/${project.project_id}`}
      prefetch={false}
      aria-label={`进入《${project.name}》工作台`}
      className="shelf-project"
    >
      <span className="shelf-project-cover" aria-hidden="true">
        <span className={`shelf-book shelf-book--${coverVariant(project.project_id)}`}>
          <span className="shelf-book-pages" />
          <span className="shelf-book-spine" />
          <span className="shelf-book-frame" />
          <span className="shelf-book-binding" />
          <span className="shelf-book-label"><span className="shelf-book-title">{project.name}</span></span>
        </span>
      </span>
      <span className="shelf-project-caption">
        <span className="shelf-project-title">{project.name}</span>
        <span className="shelf-project-meta">
          <span>{roleLabel(project.role)}</span>
          <span className="shelf-project-open">打开作品<ArrowUpRight className="size-3.5" aria-hidden /></span>
        </span>
      </span>
    </Link>
  );
}
