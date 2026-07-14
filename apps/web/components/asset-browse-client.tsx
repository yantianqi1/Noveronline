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

type AssetBrowseClientProps = {
  assets: AssetListSummary;
  locale: Locale;
  searchResults: AssetSearchSummary | null;
};

/**
 * Grouped asset list + in-page preview dialog (no full-page catalog navigation).
 */
export function AssetBrowseClient({ assets, locale, searchResults }: AssetBrowseClientProps) {
  const [selected, setSelected] = useState<AssetPreviewModel | null>(null);

  if (searchResults !== null) {
    return (
      <>
        <SearchResultsList
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
      <GroupedAssetList assets={assets} locale={locale} onSelect={setSelected} />
      <AssetPreviewDialog
        asset={selected}
        locale={locale}
        onClose={() => setSelected(null)}
        open={selected !== null}
      />
    </>
  );
}

function GroupedAssetList({
  assets,
  locale,
  onSelect,
}: {
  assets: AssetListSummary;
  locale: Locale;
  onSelect: (asset: AssetPreviewModel) => void;
}) {
  const groups = useMemo(() => {
    if (!assets.ok) {
      return [];
    }
    return groupAssetsByType(assets.items);
  }, [assets]);

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

  return (
    <div className="asset-type-groups" data-testid="asset-type-groups">
      {groups.map((group) => (
        <details className="asset-type-group" key={group.type} open>
          <summary className="asset-type-group-summary">
            <span className="asset-type-group-title">
              <strong>{assetValueLabel(locale, group.type)}</strong>
              <span className="asset-type-group-count">{group.items.length}</span>
            </span>
          </summary>
          <ul className="asset-type-group-list">
            {group.items.map((asset) => (
              <li key={asset.asset_id}>
                <button
                  className="asset-title-link asset-row-button"
                  onClick={() => onSelect(assetRecordToPreview(asset))}
                  type="button"
                >
                  <span className="asset-row-main">
                    <strong>
                      {displayAssetTitle(asset) || <Bi zh="未命名资产" en="Untitled asset" />}
                    </strong>
                    {asset.pinned ? (
                      <span className="asset-pin-flag" title={tx(locale, "已置顶", "Pinned")}>★</span>
                    ) : null}
                  </span>
                  <span className="asset-row-meta">
                    <span className={`asset-lifecycle-chip is-${asset.lifecycle}`}>
                      {assetLifecycleLabel(locale, asset.lifecycle)}
                    </span>
                    <span className="asset-cell-muted">{assetValueLabel(locale, asset.source_kind)}</span>
                    <span className="asset-cell-muted">{formatAuthorTimestamp(locale, asset.updated_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

function SearchResultsList({
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
      <div className="asset-search-empty">
        <p className="form-hint">
          <Bi zh="未找到匹配资产，请调整关键词或清除筛选。" en="No matching assets. Adjust the wording or clear the filters." />
        </p>
      </div>
    );
  }

  return (
    <div className="trace-list asset-search-results asset-type-groups" style={{ marginTop: 12 }}>
      {searchResults.items.map((item) => {
        const preview = searchItemToPreview(item);
        const readableTitle = displayAssetTitle({
          title: item.title,
          asset_type: item.entity_type || item.source,
          payload: item.payload,
        });
        const title = <strong>{readableTitle || item.title}</strong>;
        return (
          <article className="trace-event asset-search-card" key={item.search_document_id}>
            <div className="trace-event-header">
              {preview ? (
                <button
                  className="asset-title-link asset-row-button asset-search-title-button"
                  onClick={() => onSelect(preview)}
                  type="button"
                >
                  {title}
                </button>
              ) : title}
              <span className="trace-redaction">
                {assetValueLabel(locale, item.entity_type || item.source)}
              </span>
            </div>
            {item.tags.length > 0 ? (
              <p className="trace-meta"><Bi zh="标签" en="Tags" />: {item.tags.join(", ")}</p>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}

function groupAssetsByType(items: AssetRecord[]): Array<{ type: string; items: AssetRecord[] }> {
  const order: string[] = [];
  const map = new Map<string, AssetRecord[]>();
  for (const asset of items) {
    const type = (asset.asset_type || "unknown").trim() || "unknown";
    if (!map.has(type)) {
      map.set(type, []);
      order.push(type);
    }
    map.get(type)!.push(asset);
  }
  order.sort((a, b) => {
    const rank = (type: string) => TYPE_PRIORITY[type.toLowerCase()] ?? 50;
    const diff = rank(a) - rank(b);
    if (diff !== 0) {
      return diff;
    }
    return a.localeCompare(b);
  });
  return order.map((type) => ({ type, items: map.get(type)! }));
}

const TYPE_PRIORITY: Record<string, number> = {
  character: 1,
  character_archetype: 2,
  world_rule: 3,
  organization: 4,
  relationship: 5,
  clue: 6,
  note: 7,
  style: 8,
  writing_style: 9,
  plot_template: 10,
  archive: 11,
  graph: 12,
  seed: 13,
  seed_canon: 14,
};

function formatAuthorTimestamp(locale: Locale, value: string) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
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
