"use client";

import { useMemo, useState } from "react";

import { Bi, FailureText } from "./bilingual-text";
import {
  AssetPreviewDialog,
  assetRecordToPreview,
  searchItemToPreview,
  type AssetPreviewModel,
} from "./asset-preview-dialog";
import { EmptyState } from "./empty-state";
import type {
  AssetListSummary,
  AssetRecord,
  AssetSearchSummary,
} from "../lib/api";
import { displayAssetTitle } from "../lib/asset-display";
import { type Locale, tx } from "../lib/locale";

export type AssetBrowseFilters = {
  asset_types: string[];
  categories: string[];
  lifecycles: string[];
  sources: string[];
  tags: string[];
  pinned?: boolean;
};

type AssetBrowseClientProps = {
  assets: AssetListSummary;
  filters?: AssetBrowseFilters;
  locale: Locale;
  searchResults: AssetSearchSummary | null;
};

type BrowseRow = {
  key: string;
  title: string;
  assetType: string;
  summary: string;
  pinned: boolean;
  lifecycle: string;
  source: string;
  createdAt: string;
  preview: AssetPreviewModel | null;
};

/**
 * Card-grid asset browse + in-page preview dialog (no full-page catalog navigation).
 * Facet filters apply client-side when browsing without a search query.
 * Uniform status/source/type across the current page are collapsed so cards stay title-first.
 */
export function AssetBrowseClient({
  assets,
  filters,
  locale,
  searchResults,
}: AssetBrowseClientProps) {
  const [selected, setSelected] = useState<AssetPreviewModel | null>(null);

  if (searchResults !== null) {
    return (
      <>
        <SearchResultsGrid
          locale={locale}
          onSelect={setSelected}
          searchResults={searchResults}
        />
        <AssetPreviewDialog
          asset={selected}
          locale={locale}
          onClose={() => setSelected(null)}
          open={selected !== null}
        />
      </>
    );
  }

  return (
    <>
      <AssetBrowseGrid assets={assets} filters={filters} locale={locale} onSelect={setSelected} />
      <AssetPreviewDialog
        asset={selected}
        locale={locale}
        onClose={() => setSelected(null)}
        open={selected !== null}
      />
    </>
  );
}

function AssetBrowseGrid({
  assets,
  filters,
  locale,
  onSelect,
}: {
  assets: AssetListSummary;
  filters?: AssetBrowseFilters;
  locale: Locale;
  onSelect: (asset: AssetPreviewModel) => void;
}) {
  const rows = useMemo(() => {
    if (!assets.ok) {
      return [] as BrowseRow[];
    }
    const filtered = filterAssets(assets.items, filters);
    return filtered
      .slice()
      .sort((a, b) => {
        const pinnedDiff = Number(b.pinned) - Number(a.pinned);
        if (pinnedDiff !== 0) {
          return pinnedDiff;
        }
        return (b.created_at || "").localeCompare(a.created_at || "");
      })
      .map((asset) => ({
        key: asset.asset_id,
        title: displayAssetTitle(asset) || "",
        assetType: asset.asset_type,
        summary: distinctCardSummary(asset.summary, displayAssetTitle(asset) || ""),
        pinned: asset.pinned,
        lifecycle: asset.lifecycle,
        source: asset.source_kind,
        createdAt: asset.created_at,
        preview: assetRecordToPreview(asset),
      }));
  }, [assets, filters]);

  if (!assets.ok) {
    return <PublicFailureNotice />;
  }
  if (assets.items.length === 0) {
    return (
      <EmptyState
        action={(
          <a data-tone="primary" href="#asset-operations">
            <Bi zh="+ 创建资产" en="+ Create asset" />
          </a>
        )}
        className="asset-library-empty"
        description={<Bi zh="创建资产或导入素材后会出现在这里。世界规则、角色与风格都会出现在此列表。" en="Created or ingested materials will appear here—rules, characters, and style." />}
        title={<Bi zh="项目资产" en="Project assets" />}
      />
    );
  }
  if (rows.length === 0) {
    return (
      <div className="asset-search-empty asset-type-groups" data-testid="asset-type-groups">
        <p className="form-hint">
          <Bi zh="当前筛选下没有资产，请调整或清除筛选。" en="No assets match the current filters. Adjust or clear filters." />
        </p>
      </div>
    );
  }

  return (
    <AssetCardGrid
      locale={locale}
      onSelect={onSelect}
      rows={rows}
      testId="asset-type-groups"
    />
  );
}

function SearchResultsGrid({
  locale,
  onSelect,
  searchResults,
}: {
  locale: Locale;
  onSelect: (asset: AssetPreviewModel) => void;
  searchResults: AssetSearchSummary;
}) {
  if (!searchResults.ok) {
    return <PublicFailureNotice />;
  }
  if (searchResults.items.length === 0) {
    return (
      <div className="asset-search-empty asset-type-groups" data-testid="asset-type-groups">
        <p className="form-hint">
          <Bi zh="未找到匹配资产，请调整关键词或清除筛选。" en="No matching assets. Adjust the wording or clear the filters." />
        </p>
      </div>
    );
  }

  const rows: BrowseRow[] = searchResults.items.map((item) => {
    const preview = searchItemToPreview(item);
    const readableTitle = displayAssetTitle({
      title: item.title,
      asset_type: item.entity_type || item.source,
      payload: item.payload,
    });
    const title = readableTitle || item.title;
    const lifecycle = item.collections[0]?.lifecycle
      || (typeof item.payload?.lifecycle === "string" ? item.payload.lifecycle : "");
    const source = typeof item.payload?.source_kind === "string" && item.payload.source_kind.trim()
      ? item.payload.source_kind
      : item.source;
    const summaryRaw = typeof item.payload?.summary === "string" ? item.payload.summary : "";
    return {
      key: item.search_document_id,
      title,
      assetType: item.entity_type || "",
      summary: distinctCardSummary(summaryRaw, title),
      pinned: Boolean(item.payload?.pinned),
      lifecycle,
      source,
      createdAt: item.created_at,
      preview,
    };
  });

  return <AssetCardGrid locale={locale} onSelect={onSelect} rows={rows} testId="asset-type-groups" />;
}

function AssetCardGrid({
  locale,
  onSelect,
  rows,
  testId,
}: {
  locale: Locale;
  onSelect: (asset: AssetPreviewModel) => void;
  rows: BrowseRow[];
  testId?: string;
}) {
  const showType = !isUniformField(rows, (row) => row.assetType);
  const showLifecycle = !isUniformField(rows, (row) => row.lifecycle);
  const showSource = !isUniformField(rows, (row) => row.source);
  const showTime = !isUniformField(rows, (row) => formatCardDate(locale, row.createdAt));

  return (
    <div className="asset-type-groups asset-browse-grid" data-testid={testId}>
      <ul className="asset-browse-card-list">
        {rows.map((row) => {
          const title = row.title || tx(locale, "未命名资产", "Untitled asset");
          const metaBits: string[] = [];
          if (showSource && row.source) {
            metaBits.push(assetValueLabel(locale, row.source));
          }
          if (showTime && row.createdAt) {
            metaBits.push(formatCardDate(locale, row.createdAt));
          }
          const card = (
            <>
              <span className="asset-browse-card-top">
                {showType && row.assetType ? (
                  <span className="asset-browse-card-type">{assetValueLabel(locale, row.assetType)}</span>
                ) : (
                  <span className="asset-browse-card-type is-spacer" aria-hidden="true" />
                )}
                {row.pinned ? (
                  <span className="asset-pin-flag" title={tx(locale, "已置顶", "Pinned")}>★</span>
                ) : null}
              </span>
              <strong className="asset-browse-card-title">{title}</strong>
              {row.summary ? <span className="asset-browse-card-summary">{row.summary}</span> : null}
              <span className="asset-browse-card-footer">
                {showLifecycle && row.lifecycle ? (
                  <span className={`asset-lifecycle-chip is-${row.lifecycle}`}>
                    {assetLifecycleLabel(locale, row.lifecycle)}
                  </span>
                ) : null}
                {metaBits.length > 0 ? (
                  <span className="asset-browse-card-meta">{metaBits.join(" · ")}</span>
                ) : null}
              </span>
            </>
          );

          return (
            <li key={row.key}>
              {row.preview ? (
                <button
                  className="asset-browse-card asset-title-link"
                  onClick={() => onSelect(row.preview!)}
                  type="button"
                >
                  {card}
                </button>
              ) : (
                <div className="asset-browse-card is-static">{card}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function isUniformField(rows: BrowseRow[], pick: (row: BrowseRow) => string) {
  if (rows.length <= 1) {
    return true;
  }
  const first = pick(rows[0]!);
  return rows.every((row) => pick(row) === first);
}

function distinctCardSummary(summary: string, title: string) {
  const trimmed = summary.trim();
  if (!trimmed) {
    return "";
  }
  if (trimmed === title.trim()) {
    return "";
  }
  if (trimmed.length <= 72) {
    return trimmed;
  }
  return `${trimmed.slice(0, 72)}…`;
}

function filterAssets(items: AssetRecord[], filters?: AssetBrowseFilters) {
  if (!filters) {
    return items;
  }
  return items.filter((asset) => {
    if (filters.asset_types.length > 0 && !filters.asset_types.includes(asset.asset_type)) {
      return false;
    }
    if (filters.categories.length > 0 && !filters.categories.includes(asset.category)) {
      return false;
    }
    if (filters.lifecycles.length > 0 && !filters.lifecycles.includes(asset.lifecycle)) {
      return false;
    }
    if (filters.sources.length > 0 && !filters.sources.includes(asset.source_kind)) {
      return false;
    }
    if (filters.tags.length > 0 && !filters.tags.some((tag) => asset.tags.includes(tag))) {
      return false;
    }
    if (filters.pinned !== undefined && asset.pinned !== filters.pinned) {
      return false;
    }
    return true;
  });
}

function formatCardDate(locale: Locale, value: string) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : "en", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function assetLifecycleLabel(locale: Locale, lifecycle: string) {
  const labels: Record<string, [string, string]> = {
    archived: ["已归档", "Archived"],
    candidate: ["候选", "Candidate"],
    canon: ["正史", "Canon"],
    material: ["素材", "Material"],
  };
  const label = labels[lifecycle];
  return label ? tx(locale, label[0], label[1]) : assetValueLabel(locale, lifecycle);
}

function assetValueLabel(locale: Locale, value: string) {
  const labels: Record<string, [string, string]> = {
    archive: ["档案", "Archive"],
    character: ["角色", "Character"],
    character_archetype: ["角色原型", "Character archetype"],
    clue: ["伏笔", "Clue"],
    graph: ["故事图谱", "Story graph"],
    manual: ["手动创建", "Created here"],
    note: ["笔记", "Note"],
    organization: ["组织", "Organization"],
    plot_template: ["剧情模板", "Plot template"],
    relationship: ["关系", "Relationship"],
    seed: ["种子分析", "Seed analysis"],
    seed_canon: ["种子正史", "Seed canon"],
    style: ["风格", "Style"],
    writing_style: ["写作风格", "Writing style"],
    world_rule: ["世界规则", "World rule"],
    "pi analysis": ["Pi Analysis", "Pi Analysis"],
    pi_analysis: ["Pi Analysis", "Pi Analysis"],
  };
  const normalized = value.trim().toLowerCase();
  const label = labels[normalized];
  if (label) {
    return tx(locale, label[0], label[1]);
  }
  return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function PublicFailureNotice() {
  return <p className="form-status error-box" role="alert"><FailureText /></p>;
}
