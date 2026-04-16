export interface Chapter {
  id: string;
  project_id: string;
  title: string;
  outline: string;
  order_index: number;
  scene_count?: number;
  word_count?: number;
  created_at: string;
  updated_at: string;
}

export interface Scene {
  id: string;
  chapter_id: string;
  project_id: string;
  title: string;
  summary: string;
  pov: string;
  setting: string;
  characters: string;
  notes: string;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface Preset {
  id: string;
  project_id: string;
  name: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ManuscriptBlock {
  id: string;
  project_id: string;
  chapter_id: string;
  scene_id?: string;
  content: string;
  block_type: string;
  order_index: number;
  tags: string[];
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface OutlineVersion {
  id: string;
  chapter_id: string;
  project_id: string;
  outline_text: string;
  label?: string;
  created_at: string;
}

export interface WriterEvent {
  type: string;
  [key: string]: unknown;
}

export interface ContinuationContext {
  fragments: ContinuationFragment[];
  total_tokens: number;
  budget: number;
}

export interface ContinuationFragment {
  source: string;
  content: string;
  token_count: number;
}
