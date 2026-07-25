"use client";

import { motion } from "motion/react";
import { ArrowUpRight, BookOpen } from "lucide-react";

import { canWrite, roleLabel, type ProjectWithTenant } from "@/lib/workspace";

/**
 * A single project "volume" on the shelf.
 *
 * Editorial treatment: a paper card with the project title in large serif, the
 * tenant name as a kicker, and a role seal. Writable projects get a vermilion
 * accent; read-only ones stay muted. Clicking enters the project's workspace.
 */
export function ProjectCard({
  project,
  index,
  onOpen,
}: {
  project: ProjectWithTenant;
  index: number;
  onOpen: (project: ProjectWithTenant) => void;
}) {
  const writable = canWrite(project.role);

  return (
    <motion.button
      type="button"
      onClick={() => onOpen(project)}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: 0.08 + index * 0.06, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -3 }}
      whileTap={{ scale: 0.985 }}
      className="group relative flex h-full flex-col overflow-hidden rounded-card border border-line bg-panel p-6 text-left shadow-[0_1px_2px_rgba(23,26,27,0.05)] transition-shadow duration-300 hover:border-accent/35 hover:shadow-panel"
    >
      {/* vermilion spine on the leading edge */}
      <span
        aria-hidden
        className={`absolute inset-y-0 left-0 w-[3px] transition-colors ${
          writable ? "bg-accent/70 group-hover:bg-accent" : "bg-line"
        }`}
      />

      <div className="flex items-start justify-between gap-3 pl-2">
        <span className="inline-flex items-center gap-1.5 text-[11.5px] font-medium tracking-[0.14em] text-muted">
          <BookOpen className="size-3.5" aria-hidden />
          {project.tenantName}
        </span>
        <span
          className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
            writable ? "bg-accent-wash text-accent-strong" : "bg-paper-deep text-muted"
          }`}
        >
          {roleLabel(project.role)}
        </span>
      </div>

      <h3 className="mt-4 line-clamp-2 pl-2 font-serif text-[22px] font-semibold leading-snug text-ink transition-colors group-hover:text-accent-strong">
        {project.name}
      </h3>

      <div className="mt-auto flex items-center justify-between gap-2 pt-5 pl-2">
        <span className="text-[12.5px] text-muted transition-colors group-hover:text-ink">
          进入工作台
        </span>
        <span className="grid size-7 place-items-center rounded-full border border-line text-muted transition-all duration-300 group-hover:border-accent group-hover:bg-accent group-hover:text-white">
          <ArrowUpRight className="size-3.5" aria-hidden />
        </span>
      </div>
    </motion.button>
  );
}
