import type { ReactNode } from "react";

export type CompactFilterChip = {
  href: string;
  key: string;
  label: string;
  removeLabel: string;
};

type CompactFilterBarProps = {
  appliedFilters?: CompactFilterChip[];
  children?: ReactNode;
  clearHref?: string;
  clearLabel?: ReactNode;
  disclosure?: ReactNode;
  searchField: ReactNode;
  submitControl: ReactNode;
};

/**
 * Compact filter surface: primary search row, optional disclosure panel, chips.
 * Disclosure sits in the action cluster so open panels can overlay without
 * stretching a long vertical stack through the whole page.
 */
export function CompactFilterBar({
  appliedFilters = [],
  children,
  clearHref,
  clearLabel,
  disclosure,
  searchField,
  submitControl,
}: CompactFilterBarProps) {
  return (
    <div className="compact-filter-bar">
      <div className="compact-filter-row">
        {searchField}
        {children}
        <div className="compact-filter-actions">
          {submitControl}
          {disclosure}
        </div>
      </div>
      {appliedFilters.length > 0 ? (
        <div className="compact-filter-chips" aria-label="Applied filters">
          <div className="facet-pills">
            {appliedFilters.map((filter) => (
              <a
                aria-label={filter.removeLabel}
                className="status-pill compact-filter-chip"
                href={filter.href}
                key={filter.key}
                title={filter.removeLabel}
              >
                {filter.label}
                <span aria-hidden="true">×</span>
              </a>
            ))}
          </div>
          {clearHref ? (
            <a className="asset-clear-filters compact-filter-clear" href={clearHref}>
              {clearLabel ?? "Clear filters"}
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
