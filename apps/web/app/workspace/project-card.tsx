"use client";

import { motion, useReducedMotion } from "motion/react";

import { canWrite, roleLabel, type ProjectWithTenant } from "@/lib/workspace";

import "./shelf-book.css";

/** Number of deterministic cover palettes defined in shelf-book.css. */
const COVER_VARIANTS = 6;

/**
 * Pick a thread-bound cover palette from the project id, so each novel keeps
 * the same 书面 colour on every visit and every shelf.
 */
function coverVariant(projectId: string): number {
  let hash = 0;
  for (let i = 0; i < projectId.length; i += 1) {
    hash = (hash * 31 + projectId.charCodeAt(i)) % 9973;
  }
  return hash % COVER_VARIANTS;
}

/**
 * A single project as a standing thread-bound volume (线装书) on the shelf.
 *
 * The book is intrinsically sized (see shelf-book.css); the shelf row owns
 * bottom alignment. All texture — spine band, page edges, binding thread,
 * title slip, role seal — is pure CSS; this component only maps data onto
 * semantic hooks. Clicking enters the project's workspace.
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
  const reduceMotion = useReducedMotion();

  return (
    <motion.button
      type="button"
      onClick={() => onOpen(project)}
      aria-label={`进入《${project.name}》工作台`}
      initial={reduceMotion ? false : { opacity: 0, y: 26 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.08 + index * 0.06, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduceMotion ? undefined : { y: -10, rotate: -2 }}
      whileTap={reduceMotion ? undefined : { scale: 0.96 }}
      className={`shelf-book shelf-book--${coverVariant(project.project_id)}`}
    >
      <span className="shelf-book-pages" aria-hidden />
      <span className="shelf-book-spine" aria-hidden />
      <span className="shelf-book-frame" aria-hidden />
      <span className="shelf-book-binding" aria-hidden />

      <span className="shelf-book-label">
        <span className="shelf-book-title">{project.name}</span>
      </span>

      <span
        className={`shelf-book-seal ${
          writable ? "shelf-book-seal--vermilion" : "shelf-book-seal--ink"
        }`}
      >
        {roleLabel(project.role)}
      </span>
      <span className="shelf-book-tenant">{project.tenantName}</span>

      <span className="shelf-book-tab" aria-hidden>
        进入工作台
      </span>
    </motion.button>
  );
}
