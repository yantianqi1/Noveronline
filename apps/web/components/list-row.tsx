import type { ReactNode } from "react";

type ListRowProps = {
  href?: string;
  title: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
  className?: string;
};

/**
 * Title-first browsable row. Prefer linking the whole title for navigation.
 */
export function ListRow({ className = "", href, meta, title, trailing }: ListRowProps) {
  const titleNode = href ? (
    <a className="list-row-title-link" href={href}>
      {title}
    </a>
  ) : (
    <span className="list-row-title">{title}</span>
  );

  return (
    <div className={["list-row", className].filter(Boolean).join(" ")}>
      <div className="list-row-main">
        {titleNode}
        {meta ? <div className="list-row-meta">{meta}</div> : null}
      </div>
      {trailing ? <div className="list-row-trailing">{trailing}</div> : null}
    </div>
  );
}
