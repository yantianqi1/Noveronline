/**
 * Asset library domain types — the unified read model over a project's story
 * knowledge (roles, settings, relationships, foreshadowing, world rules,
 * archives) plus the catalog that versions and organizes individual assets.
 *
 * Two backend surfaces shape these types:
 *  - the list/facets/search read model (`internal/httpapi` → `internal/assets`),
 *    which is flat (strings, not null) and powers browsing + filtering;
 *  - the catalog (`internal/assetcatalog`), which owns detail, private content,
 *    versions, restore, and collections.
 */

// ── Unified list / facets / search (internal/assets) ───────────────────────

/** One row of the unified asset list. Flat — strings, never null. */
export type AssetRecord = {
  asset_id: string;
  project_id: string;
  scope: string;
  asset_type: string;
  category: string;
  lifecycle: string;
  title: string;
  summary: string;
  source_kind: string;
  source_ref: string;
  enabled: boolean;
  pinned: boolean;
  tags: string[];
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type FacetBucket = { value: string; count: number };

export type Facets = {
  asset_types: FacetBucket[];
  categories: FacetBucket[];
  lifecycles: FacetBucket[];
  sources: FacetBucket[];
  tags: FacetBucket[];
};

/** Whether keyword / vector / hybrid search is actually available. */
export type SearchCapabilities = {
  keyword: boolean;
  vector: boolean;
  hybrid: boolean;
  reason?: string;
  config_href?: string;
};

export type SearchFilters = {
  asset_types?: string[];
  categories?: string[];
  lifecycles?: string[];
  sources?: string[];
  tags?: string[];
  pinned?: boolean;
};

/** A cross-entity search hit. `source_ref` points back at the asset id. */
export type SearchRecord = {
  search_document_id: string;
  source: string;
  source_ref: string;
  project_id: string;
  entity_type: string;
  title: string;
  tags: string[];
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ListResponse<T> = { items: T[] };

// ── Catalog: detail / versions / collections (internal/assetcatalog) ───────

export type AssetSource = { kind: string; ref: string };

export type CollectionRef = {
  collection_id: string;
  title: string;
  lifecycle: string;
  position: number;
};

export type AssetCapabilities = {
  read_private: boolean;
  mutate: boolean;
  manage_collections: boolean;
};

/** The catalog's rich asset detail. Nullable fields stay nullable here. */
export type CatalogAsset = {
  asset_id: string;
  project_id: string;
  asset_type: string;
  category: string | null;
  lifecycle: string;
  title: string;
  summary: string | null;
  payload?: unknown;
  tags: string[];
  source: AssetSource;
  enabled: boolean;
  pinned: boolean;
  /** Constant-injection flag (doc 41 §4.2): present on every writing run. */
  always_on: boolean;
  /** Spoiler gate (doc 41 §4.5): hidden from writer recall until this chapter. */
  reveal_after_chapter_order: number | null;
  current_version: number;
  collections: CollectionRef[];
  created_at: string;
  updated_at: string;
  private?: { content_text: string | null };
  capabilities: AssetCapabilities;
};

export type AssetVersion = {
  version_id: string;
  version_number: number;
  title: string | null;
  summary: string | null;
  source: AssetSource;
  created_by: string | null;
  created_at: string;
  snapshot?: {
    asset_type: string;
    category: string | null;
    title: string;
    summary: string | null;
    tags: string[];
    enabled: boolean;
    pinned: boolean;
    always_on?: boolean;
    content_text?: string | null;
  };
};

export type CollectionItem = {
  asset_id: string;
  title: string;
  asset_type: string;
  position: number;
  created_at: string;
};

export type Collection = {
  collection_id: string;
  project_id: string;
  title: string;
  summary: string | null;
  lifecycle: string;
  metadata?: unknown;
  items: CollectionItem[];
  created_at: string;
  updated_at: string;
};
