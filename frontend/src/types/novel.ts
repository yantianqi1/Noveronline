export interface ArchiveCandidate {
  entity_name: string;
  entity_type: string;
  importance_tier: string;
  evidence_count: number;
  selected?: boolean;
  tier_override?: string;
}

export interface SeedAnalysis {
  project_id: string;
  entities: SeedEntity[];
  relationships: SeedRelationship[];
  plot_threads: SeedPlotThread[];
  world_rules: SeedWorldRule[];
}

export interface SeedEntity {
  name: string;
  type: string;
  description: string;
  importance: string;
}

export interface SeedRelationship {
  source: string;
  target: string;
  type: string;
  description: string;
}

export interface SeedPlotThread {
  name: string;
  description: string;
  status: string;
}

export interface SeedWorldRule {
  name: string;
  description: string;
  category: string;
}

export interface ChapterContextOptions {
  chapters: { id: string; title: string; order_index: number }[];
  entity_types: string[];
}
