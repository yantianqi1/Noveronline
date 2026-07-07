"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { label: "Overview", path: "/overview" },
  { label: "Assets", path: "/assets" },
  { label: "Story Graph", path: "/graph" },
  { label: "Worldline", path: "/worldline" },
  { label: "Character Console", path: "/character-console" },
  { label: "Writer", path: "/writer" },
  { label: "LLM Facility", path: "/llm-facility" },
  { label: "Guide", path: "/guide" },
];

type ProjectNavProps = {
  basePath: string;
};

export function ProjectNav({ basePath }: ProjectNavProps) {
  const pathname = usePathname();

  return (
    <nav className="nav-list">
      {navItems.map((item) => {
        const href = `${basePath}${item.path}`;
        return (
          <Link
            aria-current={pathname === href ? "page" : undefined}
            className="nav-link"
            href={href}
            key={item.path}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
