export interface Asset {
  id: string;
  scope: string;
  project_id?: string;
  asset_type: string;
  name: string;
  category?: string;
  summary?: string;
  payload: Record<string, unknown>;
  enabled: boolean;
  source_label?: string;
  created_at: string;
  updated_at: string;
}

export interface AssetFacets {
  sources: FacetBucket[];
  entity_types: FacetBucket[];
  projects: FacetBucket[];
}

export interface FacetBucket {
  key: string;
  label: string;
  count: number;
}

export interface UnifiedAsset {
  id: string;
  source: string;
  entity_type: string;
  name: string;
  summary?: string;
  project_id?: string;
  project_name?: string;
  detail?: Record<string, unknown>;
  created_at: string;
}

export interface SearchResult {
  items: UnifiedAsset[];
  total: number;
  query: string;
}
