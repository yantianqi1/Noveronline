"use client";

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { Bi } from "./bilingual-text";
import type { AssetRecord } from "../lib/api";
import {
  displayAssetTitle,
  formatRawPayloadJson,
  structureAssetBody,
} from "../lib/asset-display";
import { type Locale, tx } from "../lib/locale";

export type AssetPreviewModel = {
  asset_id: string;
  title: string;
  summary?: string;
  asset_type?: string;
  category?: string;
  lifecycle?: string;
  source_kind?: string;
  source_ref?: string;
  enabled?: boolean;
  pinned?: boolean;
  tags?: string[];
  payload?: Record<string, unknown>;
  content_text?: string;
  updated_at?: string;
  created_at?: string;
};

type AssetPreviewDialogProps = {
  asset: AssetPreviewModel | null;
  locale: Locale;
  onClose: () => void;
  open: boolean;
};

/**
 * In-page asset preview: list data first, no navigation to the catalog detail page.
 */
export function AssetPreviewDialog({ asset, locale, onClose, open }: AssetPreviewDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (open && asset) {
      previousFocusRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      if (!dialog.open) {
        dialog.showModal();
      }
      closeRef.current?.focus();
      return;
    }

    if (dialog.open) {
      dialog.close();
    }
    previousFocusRef.current?.focus();
  }, [open, asset]);

  if (!open || !asset) {
    return null;
  }

  const tags = asset.tags ?? [];
  const displayTitle = displayAssetTitle(asset);
  const structured = structureAssetBody(asset);
  const rawJson = formatRawPayloadJson(structured.rawPayload);
  const updated = formatAuthorTimestamp(locale, asset.updated_at ?? "");
  const summaryText = structured.summaryDistinct
    && !isBoringSummary(structured.summaryDistinct, displayTitle)
    ? structured.summaryDistinct
    : "";
  const bodyText = structured.prose
    || (asset.summary?.trim() && !isBoringSummary(asset.summary, displayTitle) && !summaryText
      ? asset.summary.trim()
      : "");

  return (
    <dialog
      aria-describedby={descriptionId}
      aria-labelledby={titleId}
      className="asset-preview-dialog"
      data-testid="asset-preview-dialog"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) {
          onClose();
        }
      }}
      ref={dialogRef}
    >
      <div className="asset-preview-dialog-panel">
        <header className="asset-preview-dialog-header">
          <div className="asset-preview-dialog-heading">
            <p className="eyebrow">
              <Bi zh="资产详情" en="Asset detail" />
            </p>
            <h2 id={titleId}>{displayTitle || tx(locale, "未命名资产", "Untitled asset")}</h2>
            <p className="form-hint" id={descriptionId}>
              <Bi zh="当前页预览，无需离开资产库。" en="In-page preview — stay in the asset library." />
            </p>
          </div>
          <button
            className="submit-button asset-preview-close"
            data-tone="secondary"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            <X aria-hidden="true" size={16} strokeWidth={1.9} />
            <Bi zh="关闭" en="Close" />
          </button>
        </header>

        <div className="asset-preview-dialog-body">
          <div className="asset-preview-chips" aria-label={tx(locale, "元数据", "Metadata")}>
            {asset.asset_type ? (
              <span className="asset-type-chip">{assetValueLabel(locale, asset.asset_type)}</span>
            ) : null}
            {asset.lifecycle ? (
              <span className={`asset-lifecycle-chip is-${asset.lifecycle}`}>
                {assetLifecycleLabel(locale, asset.lifecycle)}
              </span>
            ) : null}
            {asset.pinned ? (
              <span className="status-pill"><Bi zh="已置顶" en="Pinned" /></span>
            ) : null}
            {asset.enabled === false ? (
              <span className="status-pill"><Bi zh="已停用" en="Disabled" /></span>
            ) : null}
          </div>

          <dl className="asset-preview-meta">
            {asset.source_kind ? (
              <div>
                <dt><Bi zh="来源" en="Source" /></dt>
                <dd>{assetValueLabel(locale, asset.source_kind)}</dd>
              </div>
            ) : null}
            {asset.category ? (
              <div>
                <dt><Bi zh="分类" en="Category" /></dt>
                <dd>{assetValueLabel(locale, asset.category)}</dd>
              </div>
            ) : null}
            {updated !== "—" ? (
              <div>
                <dt><Bi zh="更新时间" en="Updated" /></dt>
                <dd>{updated}</dd>
              </div>
            ) : null}
            {asset.source_ref ? (
              <div>
                <dt><Bi zh="来源引用" en="Source ref" /></dt>
                <dd className="asset-preview-mono">{asset.source_ref}</dd>
              </div>
            ) : null}
          </dl>

          {summaryText ? (
            <section className="asset-preview-section" aria-labelledby={`${titleId}-summary`}>
              <h3 id={`${titleId}-summary`}><Bi zh="摘要" en="Summary" /></h3>
              <p className="asset-preview-summary">{summaryText}</p>
            </section>
          ) : null}

          {tags.length > 0 ? (
            <section className="asset-preview-section" aria-labelledby={`${titleId}-tags`}>
              <h3 id={`${titleId}-tags`}><Bi zh="标签" en="Tags" /></h3>
              <div className="asset-preview-tags">
                {tags.map((tag) => (
                  <span className="status-pill" key={tag}>{tag}</span>
                ))}
              </div>
            </section>
          ) : null}

          {structured.fields.length > 0 ? (
            <section
              className="asset-preview-section asset-preview-structured"
              aria-labelledby={`${titleId}-structured`}
              data-testid="asset-preview-structured"
            >
              <h3 id={`${titleId}-structured`}><Bi zh="结构化信息" en="Structured details" /></h3>
              <dl className="asset-preview-fields">
                {structured.fields.map((item) => (
                  <div key={item.key}>
                    <dt>{tx(locale, item.labelZh, item.labelEn)}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ) : null}

          {bodyText ? (
            <section className="asset-preview-section" aria-labelledby={`${titleId}-body`}>
              <h3 id={`${titleId}-body`}><Bi zh="正文" en="Body" /></h3>
              <p className="asset-preview-summary asset-preview-prose" data-testid="asset-preview-prose">
                {bodyText}
              </p>
            </section>
          ) : null}

          {!summaryText && structured.fields.length === 0 && !bodyText ? (
            <section className="asset-preview-section">
              <p className="asset-preview-summary">
                <Bi zh="暂无可读正文。可展开下方原始结构查看完整字段。" en="No readable body yet. Expand raw structure below for full fields." />
              </p>
            </section>
          ) : null}

          {rawJson ? (
            <details className="asset-preview-raw" data-testid="asset-preview-raw">
              <summary className="asset-preview-raw-summary">
                <span className="asset-preview-raw-label">
                  <Bi zh="原始结构" en="Raw structure" />
                </span>
                <span className="asset-preview-raw-hint">
                  <Bi zh="可点开 · 默认收起" en="Tap to expand · collapsed by default" />
                </span>
              </summary>
              <pre className="asset-preview-payload">{rawJson}</pre>
            </details>
          ) : null}

          <p className="form-hint asset-preview-ops-hint">
            <Bi
              zh="需要创建、更新或批量处理时，请使用右侧「资产检视」操作区。"
              en="Use the Asset inspector on the right for create, update, or bulk actions."
            />
            {" "}
            <a className="asset-preview-ops-link" href="#asset-operations" onClick={onClose}>
              <Bi zh="前往操作区" en="Open operations" />
            </a>
          </p>
        </div>
      </div>
    </dialog>
  );
}

export function assetRecordToPreview(asset: AssetRecord): AssetPreviewModel {
  return {
    asset_id: asset.asset_id,
    title: asset.title,
    summary: asset.summary,
    asset_type: asset.asset_type,
    category: asset.category,
    lifecycle: asset.lifecycle,
    source_kind: asset.source_kind,
    source_ref: asset.source_ref,
    enabled: asset.enabled,
    pinned: asset.pinned,
    tags: asset.tags,
    payload: asset.payload,
    updated_at: asset.updated_at,
    created_at: asset.created_at,
  };
}

export function searchItemToPreview(item: {
  source_ref: string;
  title: string;
  entity_type?: string;
  source?: string;
  tags?: string[];
  payload?: Record<string, unknown>;
  updated_at?: string;
  created_at?: string;
}): AssetPreviewModel | null {
  const fromPayload = item.payload?.asset_id;
  const assetId = typeof fromPayload === "string" && fromPayload.trim()
    ? fromPayload.trim()
    : (item.source_ref?.trim() ?? "");
  if (!assetId) {
    return null;
  }
  const summary = typeof item.payload?.summary === "string" ? item.payload.summary : undefined;
  const lifecycle = typeof item.payload?.lifecycle === "string" ? item.payload.lifecycle : undefined;
  const category = typeof item.payload?.category === "string" ? item.payload.category : undefined;
  return {
    asset_id: assetId,
    title: item.title,
    summary,
    asset_type: item.entity_type || item.source,
    category,
    lifecycle,
    source_kind: item.source,
    source_ref: item.source_ref,
    tags: item.tags ?? [],
    payload: item.payload,
    updated_at: item.updated_at,
    created_at: item.created_at,
  };
}

function isBoringSummary(summary: string, displayTitle: string): boolean {
  const s = summary.trim();
  if (!s) return true;
  if (s === displayTitle) return true;
  const keys = new Set([
    "character", "relationship", "world_rule", "plot_thread",
    "ontology", "note_summary", "note", "story_ontology",
  ]);
  return keys.has(s.toLowerCase());
}

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

function assetValueLabel(locale: Locale, value: string): ReactNode {
  const labels: Record<string, [string, string]> = {
    archive: ["档案", "Archive"],
    character: ["角色", "Character"],
    character_archetype: ["角色原型", "Character archetype"],
    clue: ["伏笔", "Clue"],
    graph: ["故事图谱", "Story graph"],
    manual: ["手动创建", "Created here"],
    note: ["笔记", "Note"],
    note_summary: ["笔记", "Note"],
    organization: ["组织", "Organization"],
    plot_template: ["剧情模板", "Plot template"],
    plot_thread: ["情节线索", "Plot thread"],
    relationship: ["关系", "Relationship"],
    seed: ["种子分析", "Seed analysis"],
    seed_canon: ["种子正史", "Seed canon"],
    style: ["风格", "Style"],
    writing_style: ["写作风格", "Writing style"],
    world_rule: ["世界规则", "World rule"],
    pi_analysis: ["分析导入", "Analysis import"],
    story_ontology: ["故事本体", "Story ontology"],
    ontology: ["本体", "Ontology"],
  };
  const normalized = value.trim().toLowerCase();
  const label = labels[normalized];
  if (label) {
    return tx(locale, label[0], label[1]);
  }
  return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
