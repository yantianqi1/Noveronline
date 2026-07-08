BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_app') THEN
    CREATE ROLE mirofish_app NOLOGIN;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION app_set_tenant_context(
  p_tenant_id UUID,
  p_user_id UUID,
  p_is_service_role BOOLEAN DEFAULT FALSE
) RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_tenant_id IS NULL THEN
    RAISE EXCEPTION 'tenant context is required';
  END IF;
  PERFORM set_config('app.current_tenant_id', p_tenant_id::TEXT, true);
  PERFORM set_config('app.current_user_id', COALESCE(p_user_id::TEXT, ''), true);
  PERFORM set_config('app.current_service_role', CASE WHEN p_is_service_role THEN 'true' ELSE 'false' END, true);
END;
$$;

-- Example transaction setup for application code:
-- BEGIN;
-- SET LOCAL app.current_tenant_id = '00000000-0000-0000-0000-000000000000';
-- SET LOCAL app.current_user_id = '00000000-0000-0000-0000-000000000000';
-- COMMIT;

CREATE TABLE IF NOT EXISTS users (
  user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  avatar_url TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_password_credentials (
  user_id UUID PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  password_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'reset_required')),
  password_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_sessions (
  user_session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  tenant_type TEXT NOT NULL CHECK (tenant_type IN ('personal', 'organization')),
  plan TEXT NOT NULL DEFAULT 'free',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_memberships (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'editor', 'writer', 'viewer', 'billing')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'invited', 'suspended')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  joined_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS projects (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT,
  genre TEXT,
  language TEXT NOT NULL DEFAULT 'zh-CN',
  status TEXT NOT NULL DEFAULT 'active',
  default_worldline_id UUID,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS project_members (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('project_owner', 'editor', 'writer', 'analyst', 'viewer')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, project_id, user_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_files (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  upload_id UUID NOT NULL DEFAULT gen_random_uuid(),
  object_key TEXT NOT NULL,
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
  sha256 TEXT NOT NULL,
  purpose TEXT NOT NULL,
  parse_status TEXT NOT NULL DEFAULT 'pending' CHECK (parse_status IN ('pending', 'uploaded', 'parsing', 'parsed', 'failed', 'cancelled')),
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, upload_id),
  UNIQUE (tenant_id, project_id, object_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_text_artifacts (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  source_file_id UUID REFERENCES source_files(file_id) ON DELETE SET NULL,
  run_id UUID,
  artifact_type TEXT NOT NULL CHECK (artifact_type IN ('extracted_text', 'normalized_text', 'segment_text')),
  object_key TEXT NOT NULL,
  char_count INTEGER NOT NULL DEFAULT 0 CHECK (char_count >= 0),
  line_count INTEGER NOT NULL DEFAULT 0 CHECK (line_count >= 0),
  sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, artifact_type, object_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id UUID REFERENCES users(user_id),
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  project_id UUID,
  run_id UUID,
  request_id TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  usage_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID,
  run_id UUID,
  module_key TEXT,
  usage_type TEXT NOT NULL,
  quantity NUMERIC NOT NULL DEFAULT 0,
  unit TEXT NOT NULL,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resource_locks (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  lock_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_type TEXT NOT NULL,
  resource_id UUID NOT NULL,
  owner_run_id UUID,
  lock_mode TEXT NOT NULL DEFAULT 'exclusive',
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, resource_type, resource_id, lock_mode)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_type TEXT NOT NULL,
  project_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  message TEXT,
  started_by UUID REFERENCES users(user_id),
  temporal_workflow_id TEXT,
  temporal_run_id TEXT,
  result_jsonb JSONB,
  error_code TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workflow_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  workflow_type TEXT NOT NULL,
  project_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_id, sequence),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS text_segments (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  segment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID REFERENCES workflow_runs(run_id) ON DELETE SET NULL,
  source_file_id UUID REFERENCES source_files(file_id) ON DELETE SET NULL,
  segment_order INTEGER NOT NULL CHECK (segment_order >= 0),
  chapter_guess TEXT,
  title_guess TEXT,
  start_offset INTEGER CHECK (start_offset IS NULL OR start_offset >= 0),
  end_offset INTEGER CHECK (end_offset IS NULL OR end_offset >= 0),
  content_excerpt TEXT,
  object_key TEXT,
  summary TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_order),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reading_passes (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  pass_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  pass_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
  module_key TEXT,
  model_id TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reading_segment_notes (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  note_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  pass_id UUID REFERENCES reading_passes(pass_id) ON DELETE SET NULL,
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_id, segment_id, pass_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entities (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  source_run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  canonical_name TEXT NOT NULL,
  entity_type TEXT NOT NULL DEFAULT 'character',
  importance TEXT,
  state_summary TEXT,
  first_seen_segment_id UUID REFERENCES text_segments(segment_id) ON DELETE SET NULL,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, canonical_name),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entity_aliases (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  entity_id UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, entity_id, alias),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entity_labels (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  label_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  entity_id UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  label_type TEXT NOT NULL DEFAULT 'tag',
  source_kind TEXT NOT NULL DEFAULT 'sequential_reading',
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, entity_id, run_id, segment_id, label, source_kind),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entity_evidence (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  entity_id UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  evidence_text TEXT NOT NULL,
  source_kind TEXT NOT NULL DEFAULT 'sequential_reading',
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, entity_id, run_id, segment_id, source_kind, evidence_text),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationships (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  source_entity_name TEXT NOT NULL,
  target_entity_name TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  summary TEXT,
  source_run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  first_seen_segment_id UUID REFERENCES text_segments(segment_id) ON DELETE SET NULL,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, source_entity_name, target_entity_name, relationship_type),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationship_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  relationship_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  source_entity_name TEXT NOT NULL,
  target_entity_name TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  event_summary TEXT NOT NULL,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, source_entity_name, target_entity_name, relationship_type, event_summary),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS character_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  character_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  entity_name TEXT NOT NULL,
  event_summary TEXT NOT NULL,
  event_kind TEXT,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, entity_name, event_summary),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS world_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  world_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  event_summary TEXT NOT NULL,
  event_kind TEXT,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, event_summary),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plot_threads (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  thread_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  source_run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  summary TEXT,
  first_seen_segment_id UUID REFERENCES text_segments(segment_id) ON DELETE SET NULL,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, title),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS thread_lifecycle (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  thread_lifecycle_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  thread_id UUID NOT NULL REFERENCES plot_threads(thread_id) ON DELETE CASCADE,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  summary TEXT,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, thread_id, run_id, segment_id, status),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS narrative_arcs (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  narrative_arc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  arc_type TEXT,
  summary TEXT,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, title),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS volume_summaries (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  volume_summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  volume_key TEXT NOT NULL,
  title TEXT,
  summary TEXT NOT NULL,
  evidence_text TEXT,
  source_kind TEXT NOT NULL DEFAULT 'sequential_reading',
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, volume_key, source_kind),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS world_rule_evidence (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  rule_evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  rule_text TEXT NOT NULL,
  evidence_text TEXT,
  category TEXT,
  confidence NUMERIC,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, rule_text),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consistency_notes (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  consistency_note_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  note_type TEXT NOT NULL DEFAULT 'general',
  severity TEXT NOT NULL DEFAULT 'info',
  summary TEXT NOT NULL,
  evidence_text TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, note_type, summary),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS segment_summaries (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  segment_summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  segment_id UUID NOT NULL REFERENCES text_segments(segment_id) ON DELETE CASCADE,
  summary TEXT NOT NULL,
  source_kind TEXT NOT NULL DEFAULT 'sequential_reading',
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, segment_id, source_kind),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seed_analysis_snapshots (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  seed_analysis_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  module_key TEXT NOT NULL,
  model_id TEXT,
  analysis_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  summary_count INTEGER NOT NULL DEFAULT 0 CHECK (summary_count >= 0),
  segment_count INTEGER NOT NULL DEFAULT 0 CHECK (segment_count >= 0),
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, module_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seed_ontology_snapshots (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  seed_ontology_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  module_key TEXT NOT NULL,
  model_id TEXT,
  ontology_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  entity_type_count INTEGER NOT NULL DEFAULT 0 CHECK (entity_type_count >= 0),
  relationship_type_count INTEGER NOT NULL DEFAULT 0 CHECK (relationship_type_count >= 0),
  world_rule_type_count INTEGER NOT NULL DEFAULT 0 CHECK (world_rule_type_count >= 0),
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, module_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seed_entity_resolution_snapshots (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  seed_entity_resolution_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  module_key TEXT NOT NULL,
  model_id TEXT,
  resolution_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  merged_entity_count INTEGER NOT NULL DEFAULT 0 CHECK (merged_entity_count >= 0),
  alias_count INTEGER NOT NULL DEFAULT 0 CHECK (alias_count >= 0),
  conflict_count INTEGER NOT NULL DEFAULT 0 CHECK (conflict_count >= 0),
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id, module_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_readiness_snapshots (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_readiness_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  ready_asset_count INTEGER NOT NULL DEFAULT 0 CHECK (ready_asset_count >= 0),
  ready_entity_count INTEGER NOT NULL DEFAULT 0 CHECK (ready_entity_count >= 0),
  ready_relationship_count INTEGER NOT NULL DEFAULT 0 CHECK (ready_relationship_count >= 0),
  ready_world_rule_count INTEGER NOT NULL DEFAULT 0 CHECK (ready_world_rule_count >= 0),
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, run_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assets (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID,
  scope TEXT NOT NULL DEFAULT 'project' CHECK (scope IN ('tenant', 'project', 'system')),
  asset_type TEXT NOT NULL,
  category TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'seed' CHECK (
    lifecycle IN ('seed', 'candidate', 'canon', 'material', 'simulation', 'draft', 'manuscript', 'archived')
  ),
  title TEXT NOT NULL,
  summary TEXT,
  content_text TEXT,
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  tags_jsonb JSONB NOT NULL DEFAULT '[]'::JSONB,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  pinned BOOLEAN NOT NULL DEFAULT FALSE,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, asset_id),
  UNIQUE (tenant_id, project_id, source_kind, source_ref, asset_type, title),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_versions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  asset_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  version_number INTEGER NOT NULL CHECK (version_number > 0),
  title TEXT,
  summary TEXT,
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_kind TEXT,
  source_ref TEXT,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, asset_id, version_number),
  FOREIGN KEY (tenant_id, project_id, asset_id) REFERENCES assets(tenant_id, project_id, asset_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_collections (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  collection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'material' CHECK (
    lifecycle IN ('seed', 'candidate', 'canon', 'material', 'simulation', 'draft', 'manuscript', 'archived')
  ),
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, collection_id),
  UNIQUE (tenant_id, project_id, title),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_collection_items (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  collection_id UUID NOT NULL REFERENCES asset_collections(collection_id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  added_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, project_id, collection_id, asset_id),
  FOREIGN KEY (tenant_id, project_id, collection_id) REFERENCES asset_collections(tenant_id, project_id, collection_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, asset_id) REFERENCES assets(tenant_id, project_id, asset_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS archive_memories (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  memory_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'canon', 'rejected', 'archived')),
  summary TEXT,
  body_text TEXT,
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, asset_id, source_kind, source_ref, memory_type),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS archive_memory_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_id UUID NOT NULL REFERENCES archive_memories(memory_id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'recorded' CHECK (status IN ('recorded', 'candidate', 'accepted', 'rejected', 'failed')),
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  actor_user_id UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS global_search_index (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  search_document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  project_id UUID,
  entity_type TEXT,
  title TEXT NOT NULL,
  body TEXT,
  tags_jsonb JSONB NOT NULL DEFAULT '[]'::JSONB,
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, source, source_ref),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_snapshots (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  graph_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  version INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'building' CHECK (status IN ('building', 'ready', 'failed', 'archived')),
  build_run_id UUID,
  source_version_hash TEXT,
  node_count INTEGER NOT NULL DEFAULT 0 CHECK (node_count >= 0),
  edge_count INTEGER NOT NULL DEFAULT 0 CHECK (edge_count >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, version),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_nodes (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  graph_id UUID NOT NULL REFERENCES story_graph_snapshots(graph_id) ON DELETE CASCADE,
  canonical_entity_id UUID,
  node_type TEXT NOT NULL CHECK (
    node_type IN ('character', 'organization', 'faction', 'location', 'artifact', 'plot_event', 'plot_thread', 'world_rule', 'concept', 'manuscript_scene')
  ),
  title TEXT NOT NULL,
  summary TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'seed' CHECK (lifecycle IN ('seed', 'candidate', 'canon', 'simulation', 'manuscript', 'archived')),
  importance NUMERIC NOT NULL DEFAULT 0,
  cluster_id UUID,
  attributes_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, graph_id, node_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_node_aliases (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  graph_id UUID NOT NULL REFERENCES story_graph_snapshots(graph_id) ON DELETE CASCADE,
  node_id UUID NOT NULL REFERENCES story_graph_nodes(node_id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  source_type TEXT,
  confidence NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, graph_id, node_id, alias),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_node_labels (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  label_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  graph_id UUID NOT NULL REFERENCES story_graph_snapshots(graph_id) ON DELETE CASCADE,
  node_id UUID NOT NULL REFERENCES story_graph_nodes(node_id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  label_type TEXT NOT NULL DEFAULT 'tag',
  confidence NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, graph_id, node_id, label_type, label),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_edges (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  graph_id UUID NOT NULL REFERENCES story_graph_snapshots(graph_id) ON DELETE CASCADE,
  source_node_id UUID NOT NULL REFERENCES story_graph_nodes(node_id) ON DELETE CASCADE,
  target_node_id UUID NOT NULL REFERENCES story_graph_nodes(node_id) ON DELETE CASCADE,
  edge_type TEXT NOT NULL CHECK (
    edge_type IN ('relationship', 'participates_in', 'belongs_to', 'opposes', 'constrained_by', 'causes', 'reveals', 'foreshadows', 'located_in', 'mentions')
  ),
  label TEXT,
  summary TEXT,
  weight NUMERIC NOT NULL DEFAULT 1,
  lifecycle TEXT NOT NULL DEFAULT 'seed' CHECK (lifecycle IN ('seed', 'candidate', 'canon', 'simulation', 'manuscript', 'archived')),
  attributes_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, graph_id, edge_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_evidence (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  graph_id UUID NOT NULL REFERENCES story_graph_snapshots(graph_id) ON DELETE CASCADE,
  owner_type TEXT NOT NULL CHECK (owner_type IN ('node', 'edge')),
  owner_id UUID NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  chapter_id UUID,
  segment_id UUID,
  snippet TEXT,
  confidence NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_layouts (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  layout_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  graph_id UUID NOT NULL REFERENCES story_graph_snapshots(graph_id) ON DELETE CASCADE,
  view_id TEXT NOT NULL,
  layout_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, graph_id, view_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_graph_clusters (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  cluster_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  graph_id UUID NOT NULL REFERENCES story_graph_snapshots(graph_id) ON DELETE CASCADE,
  cluster_key TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  node_count INTEGER NOT NULL DEFAULT 0 CHECK (node_count >= 0),
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, graph_id, cluster_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worldline_sessions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'paused', 'completed', 'failed', 'cancelled')),
  lifecycle TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle IN ('active', 'saved', 'archived', 'cancelled')),
  goal_summary TEXT NOT NULL DEFAULT '',
  anchor_path_id UUID,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, session_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worldline_preparations (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  prepare_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
  lifecycle TEXT NOT NULL DEFAULT 'preparing' CHECK (lifecycle IN ('preparing', 'ready', 'started', 'archived', 'cancelled')),
  goal_summary TEXT NOT NULL DEFAULT '',
  anchor_path_id UUID,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, prepare_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worldline_prepared_agents (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  agent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prepare_id UUID NOT NULL REFERENCES worldline_preparations(prepare_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'ready', 'failed', 'archived')),
  source_asset_id UUID,
  summary TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, prepare_id, agent_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worldline_variables (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  variable_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES worldline_sessions(session_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  impact_axis TEXT NOT NULL DEFAULT '',
  locked BOOLEAN NOT NULL DEFAULT false,
  source TEXT NOT NULL DEFAULT 'author',
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, session_id, variable_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worldline_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES worldline_sessions(session_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  step INTEGER NOT NULL DEFAULT 0 CHECK (step >= 0),
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'director',
  status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'canon', 'rejected')),
  lifecycle TEXT NOT NULL DEFAULT 'simulation' CHECK (lifecycle IN ('simulation', 'material', 'canon_reference', 'archived')),
  confidence NUMERIC(5,4),
  involved_agent_ids_jsonb JSONB NOT NULL DEFAULT '[]'::JSONB,
  state_changes_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_run_id UUID,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, session_id, event_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worldline_event_adoptions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  adoption_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID NOT NULL REFERENCES worldline_events(event_id) ON DELETE CASCADE,
  session_id UUID NOT NULL REFERENCES worldline_sessions(session_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  from_status TEXT NOT NULL CHECK (from_status IN ('candidate')),
  to_status TEXT NOT NULL CHECK (to_status IN ('canon')),
  note TEXT NOT NULL DEFAULT '',
  adopted_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worldline_saved_paths (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  path_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL,
  project_id UUID NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'saved',
  selected_event_ids_jsonb JSONB NOT NULL DEFAULT '[]'::JSONB,
  writer_instruction TEXT,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, path_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS character_interaction_sessions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  interaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  worldline_session_id UUID,
  anchor_type TEXT NOT NULL DEFAULT '' CHECK (anchor_type IN ('', 'worldline_session', 'worldline_event', 'saved_path', 'chapter', 'scene', 'graph_node', 'plot_thread')),
  anchor_id TEXT NOT NULL DEFAULT '',
  pov_agent_id TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT 'first_person' CHECK (mode IN ('first_person', 'director_assisted', 'dialogue', 'replay')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'saved', 'archived')),
  title TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, interaction_id),
  FOREIGN KEY (tenant_id, project_id, worldline_session_id) REFERENCES worldline_sessions(tenant_id, project_id, session_id) ON DELETE SET NULL (worldline_session_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS character_interaction_turns (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  turn_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  interaction_id UUID NOT NULL,
  project_id UUID NOT NULL,
  turn_order INTEGER NOT NULL CHECK (turn_order > 0),
  actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'agent', 'director', 'system')),
  actor_id TEXT NOT NULL DEFAULT '',
  turn_kind TEXT NOT NULL DEFAULT 'action' CHECK (turn_kind IN ('action', 'dialogue', 'thought', 'director_note', 'system_note')),
  summary TEXT NOT NULL DEFAULT '',
  action_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  world_state_delta_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  trace_id TEXT NOT NULL DEFAULT '',
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, interaction_id, turn_order),
  FOREIGN KEY (tenant_id, project_id, interaction_id) REFERENCES character_interaction_sessions(tenant_id, project_id, interaction_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_traces (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  trace_id TEXT NOT NULL,
  run_id UUID,
  project_id UUID NOT NULL,
  module_key TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, trace_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_trace_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  trace_id TEXT NOT NULL,
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_order INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  redaction_level TEXT NOT NULL DEFAULT 'summary' CHECK (redaction_level IN ('public', 'summary', 'full')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, trace_id, event_order),
  FOREIGN KEY (tenant_id, trace_id) REFERENCES agent_traces(tenant_id, trace_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS llm_channels (
  tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  channel_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  provider TEXT NOT NULL,
  base_url TEXT NOT NULL,
  encrypted_api_key TEXT NOT NULL,
  max_concurrency INTEGER NOT NULL DEFAULT 1 CHECK (max_concurrency > 0),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  last_sync_at TIMESTAMPTZ,
  last_sync_status TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_models (
  tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  channel_id UUID NOT NULL REFERENCES llm_channels(channel_id) ON DELETE CASCADE,
  model_id TEXT NOT NULL,
  owned_by TEXT,
  context_window INTEGER,
  supports_tools BOOLEAN NOT NULL DEFAULT FALSE,
  supports_json BOOLEAN NOT NULL DEFAULT FALSE,
  input_cost NUMERIC,
  output_cost NUMERIC,
  raw_payload_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (channel_id, model_id)
);

CREATE TABLE IF NOT EXISTS llm_module_bindings (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID,
  module_key TEXT NOT NULL,
  channel_id UUID NOT NULL REFERENCES llm_channels(channel_id) ON DELETE RESTRICT,
  model_id TEXT NOT NULL,
  settings_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  updated_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, module_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS llm_activity (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID,
  run_id UUID,
  module_key TEXT NOT NULL,
  channel_id UUID,
  model_id TEXT,
  status TEXT NOT NULL,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  latency_ms INTEGER,
  cost_estimate NUMERIC,
  error_jsonb JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS writer_runs (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id UUID REFERENCES workflow_runs(run_id) ON DELETE SET NULL,
  project_id UUID NOT NULL,
  chapter_id UUID,
  scene_id UUID,
  mode TEXT NOT NULL CHECK (mode IN ('draft', 'continue', 'outline', 'review')),
  status TEXT NOT NULL DEFAULT 'queued',
  module_key TEXT NOT NULL DEFAULT 'writer_composer',
  instruction TEXT NOT NULL,
  options_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  error_code TEXT,
  error_message TEXT,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS writer_drafts (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  draft_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES writer_runs(run_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  chapter_id UUID,
  scene_id UUID,
  content_text TEXT NOT NULL,
  word_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'adopted', 'rejected')),
  adopted_block_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS draft_reviews (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
  draft_id UUID NOT NULL REFERENCES writer_drafts(draft_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
  module_key TEXT NOT NULL DEFAULT 'writer_reviewer',
  note TEXT,
  options_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  error_code TEXT,
  error_message TEXT,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  UNIQUE (tenant_id, project_id, draft_id, review_id)
);

CREATE TABLE IF NOT EXISTS draft_review_issues (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  issue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  review_id UUID NOT NULL REFERENCES draft_reviews(review_id) ON DELETE CASCADE,
  draft_id UUID NOT NULL REFERENCES writer_drafts(draft_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  category TEXT NOT NULL,
  summary TEXT NOT NULL,
  suggestion TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'dismissed', 'resolved')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, draft_id, review_id) REFERENCES draft_reviews(tenant_id, project_id, draft_id, review_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS manuscript_blocks (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  block_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  chapter_id UUID,
  source_draft_id UUID REFERENCES writer_drafts(draft_id) ON DELETE SET NULL,
  block_order INTEGER NOT NULL,
  content_text TEXT NOT NULL,
  word_count INTEGER NOT NULL DEFAULT 0,
  pov_entity_id UUID,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, block_order),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_status ON user_sessions (user_id, status, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions (token_hash);
CREATE INDEX IF NOT EXISTS idx_user_password_credentials_status ON user_password_credentials (user_id, status);
CREATE INDEX IF NOT EXISTS idx_projects_tenant_status ON projects (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_source_files_tenant_project ON source_files (tenant_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_files_upload ON source_files (tenant_id, project_id, upload_id);
CREATE INDEX IF NOT EXISTS idx_project_text_artifacts_tenant_project ON project_text_artifacts (tenant_id, project_id, artifact_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_text_segments_tenant_project_run_order ON text_segments (tenant_id, project_id, run_id, segment_order);
CREATE INDEX IF NOT EXISTS idx_text_segments_source_file_order ON text_segments (tenant_id, source_file_id, segment_order);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'project_text_artifacts'
      AND indexdef LIKE '%UNIQUE INDEX%'
      AND indexdef LIKE '%(tenant_id, project_id, run_id, artifact_type, object_key)%'
  ) THEN
    CREATE UNIQUE INDEX idx_project_text_artifacts_upsert_unique
    ON project_text_artifacts (tenant_id, project_id, run_id, artifact_type, object_key);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'text_segments'
      AND indexdef LIKE '%UNIQUE INDEX%'
      AND indexdef LIKE '%(tenant_id, project_id, run_id, segment_order)%'
  ) THEN
    CREATE UNIQUE INDEX idx_text_segments_upsert_unique
    ON text_segments (tenant_id, project_id, run_id, segment_order);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_reading_passes_tenant_project_run ON reading_passes (tenant_id, project_id, run_id, pass_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reading_segment_notes_tenant_run_segment ON reading_segment_notes (tenant_id, run_id, segment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reading_segment_notes_pass ON reading_segment_notes (tenant_id, pass_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_tenant_project_name ON entities (tenant_id, project_id, canonical_name);
CREATE INDEX IF NOT EXISTS idx_entity_labels_tenant_project_entity ON entity_labels (tenant_id, project_id, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entity_evidence_tenant_project_entity ON entity_evidence (tenant_id, project_id, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_relationships_tenant_project_source ON relationships (tenant_id, project_id, source_entity_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_relationship_events_tenant_project_run ON relationship_events (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_character_events_tenant_project_run ON character_events (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_world_events_tenant_project_run ON world_events (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plot_threads_tenant_project_status ON plot_threads (tenant_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_thread_lifecycle_tenant_project_run ON thread_lifecycle (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_narrative_arcs_tenant_project_run ON narrative_arcs (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_volume_summaries_tenant_project_run ON volume_summaries (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_world_rule_evidence_tenant_project_run ON world_rule_evidence (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consistency_notes_tenant_project_run ON consistency_notes (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_segment_summaries_tenant_project_run ON segment_summaries (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_seed_analysis_snapshots_tenant_project_run ON seed_analysis_snapshots (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_seed_ontology_snapshots_tenant_project_run ON seed_ontology_snapshots (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_seed_entity_resolution_snapshots_tenant_project_run ON seed_entity_resolution_snapshots (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_readiness_snapshots_tenant_project_run ON project_readiness_snapshots (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assets_tenant_project_type ON assets (tenant_id, project_id, asset_type, lifecycle, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assets_tenant_project_source ON assets (tenant_id, project_id, source_kind, source_ref);
CREATE INDEX IF NOT EXISTS idx_asset_versions_tenant_project_asset ON asset_versions (tenant_id, project_id, asset_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_asset_collections_tenant_project_lifecycle ON asset_collections (tenant_id, project_id, lifecycle, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_asset_collection_items_tenant_project_asset ON asset_collection_items (tenant_id, project_id, asset_id, collection_id);
CREATE INDEX IF NOT EXISTS idx_archive_memories_tenant_project_asset ON archive_memories (tenant_id, project_id, asset_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_archive_memory_events_tenant_project_asset ON archive_memory_events (tenant_id, project_id, asset_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_global_search_index_tenant_project ON global_search_index (tenant_id, project_id, source, entity_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_graph_snapshots_current ON story_graph_snapshots (tenant_id, project_id, status, version DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_graph_nodes_tenant_project_graph ON story_graph_nodes (tenant_id, project_id, graph_id, node_type, lifecycle);
CREATE INDEX IF NOT EXISTS idx_story_graph_nodes_title ON story_graph_nodes (tenant_id, project_id, title);
CREATE INDEX IF NOT EXISTS idx_story_graph_node_aliases_node ON story_graph_node_aliases (tenant_id, project_id, graph_id, node_id, alias);
CREATE INDEX IF NOT EXISTS idx_story_graph_node_labels_node ON story_graph_node_labels (tenant_id, project_id, graph_id, node_id, label_type, label);
CREATE INDEX IF NOT EXISTS idx_story_graph_edges_tenant_project_graph ON story_graph_edges (tenant_id, project_id, graph_id, edge_type, lifecycle);
CREATE INDEX IF NOT EXISTS idx_story_graph_edges_source_target ON story_graph_edges (tenant_id, project_id, graph_id, source_node_id, target_node_id);
CREATE INDEX IF NOT EXISTS idx_story_graph_evidence_owner ON story_graph_evidence (tenant_id, project_id, graph_id, owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_story_graph_layouts_view ON story_graph_layouts (tenant_id, project_id, graph_id, view_id);
CREATE INDEX IF NOT EXISTS idx_story_graph_clusters_graph ON story_graph_clusters (tenant_id, project_id, graph_id, cluster_key);
CREATE INDEX IF NOT EXISTS idx_worldline_sessions_tenant_project ON worldline_sessions (tenant_id, project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_sessions_run ON worldline_sessions (tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS idx_worldline_preparations_tenant_project ON worldline_preparations (tenant_id, project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_preparations_run ON worldline_preparations (tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS idx_worldline_prepared_agents_prepare ON worldline_prepared_agents (tenant_id, project_id, prepare_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_variables_session ON worldline_variables (tenant_id, project_id, session_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_variables_project ON worldline_variables (tenant_id, project_id, source, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_events_session_status ON worldline_events (tenant_id, project_id, session_id, status, step, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_events_project ON worldline_events (tenant_id, project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_event_adoptions_event ON worldline_event_adoptions (tenant_id, project_id, event_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_event_adoptions_session ON worldline_event_adoptions (tenant_id, project_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_saved_paths_tenant_project ON worldline_saved_paths (tenant_id, project_id, lifecycle, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_worldline_saved_paths_session ON worldline_saved_paths (tenant_id, project_id, session_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_character_interaction_sessions_project ON character_interaction_sessions (tenant_id, project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_character_interaction_sessions_worldline ON character_interaction_sessions (tenant_id, project_id, worldline_session_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_character_interaction_turns_interaction ON character_interaction_turns (tenant_id, project_id, interaction_id, turn_order);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_tenant_project ON workflow_runs (tenant_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_events_run_sequence ON workflow_events (tenant_id, run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_agent_traces_tenant_project_run ON agent_traces (tenant_id, project_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_trace_events_trace_order ON agent_trace_events (tenant_id, trace_id, event_order);
CREATE INDEX IF NOT EXISTS idx_llm_channels_tenant_enabled ON llm_channels (tenant_id, enabled);
CREATE INDEX IF NOT EXISTS idx_llm_models_tenant_channel ON llm_models (tenant_id, channel_id);
CREATE INDEX IF NOT EXISTS idx_llm_module_bindings_tenant_project ON llm_module_bindings (tenant_id, project_id, module_key);
CREATE INDEX IF NOT EXISTS idx_llm_activity_tenant_project_run ON llm_activity (tenant_id, project_id, run_id, module_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_writer_runs_tenant_project ON writer_runs (tenant_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_writer_drafts_run ON writer_drafts (tenant_id, run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_draft_reviews_draft ON draft_reviews (tenant_id, draft_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_draft_review_issues_review ON draft_review_issues (tenant_id, review_id, created_at);
CREATE INDEX IF NOT EXISTS idx_manuscript_blocks_project_order ON manuscript_blocks (tenant_id, project_id, block_order);
CREATE INDEX IF NOT EXISTS idx_resource_locks_expiry ON resource_locks (tenant_id, expires_at);

GRANT USAGE ON SCHEMA public TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON user_password_credentials TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON user_sessions TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_snapshots TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_nodes TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_node_aliases TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_node_labels TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_edges TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_evidence TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_layouts TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON story_graph_clusters TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON seed_ontology_snapshots TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON seed_entity_resolution_snapshots TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_sessions TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_preparations TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_prepared_agents TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_variables TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_events TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_event_adoptions TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_saved_paths TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON character_interaction_sessions TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON character_interaction_turns TO mirofish_app;
GRANT EXECUTE ON FUNCTION app_set_tenant_context(UUID, UUID, BOOLEAN) TO mirofish_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mirofish_app;

ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_memberships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_tenant_memberships ON tenant_memberships;
CREATE POLICY tenant_isolation_tenant_memberships
ON tenant_memberships
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_members FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_project_members ON project_members;
CREATE POLICY tenant_isolation_project_members
ON project_members
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_projects ON projects;
CREATE POLICY tenant_isolation_projects
ON projects
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE source_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_files FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_source_files ON source_files;
CREATE POLICY tenant_isolation_source_files
ON source_files
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE project_text_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_text_artifacts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_project_text_artifacts ON project_text_artifacts;
CREATE POLICY tenant_isolation_project_text_artifacts
ON project_text_artifacts
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE text_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE text_segments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_text_segments ON text_segments;
CREATE POLICY tenant_isolation_text_segments
ON text_segments
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE reading_passes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reading_passes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_reading_passes ON reading_passes;
CREATE POLICY tenant_isolation_reading_passes
ON reading_passes
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE reading_segment_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reading_segment_notes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_reading_segment_notes ON reading_segment_notes;
CREATE POLICY tenant_isolation_reading_segment_notes
ON reading_segment_notes
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_entities ON entities;
CREATE POLICY tenant_isolation_entities
ON entities
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE entity_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_aliases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_entity_aliases ON entity_aliases;
CREATE POLICY tenant_isolation_entity_aliases
ON entity_aliases
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE entity_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_labels FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_entity_labels ON entity_labels;
CREATE POLICY tenant_isolation_entity_labels
ON entity_labels
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE entity_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_entity_evidence ON entity_evidence;
CREATE POLICY tenant_isolation_entity_evidence
ON entity_evidence
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_relationships ON relationships;
CREATE POLICY tenant_isolation_relationships
ON relationships
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE relationship_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationship_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_relationship_events ON relationship_events;
CREATE POLICY tenant_isolation_relationship_events
ON relationship_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE character_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE character_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_character_events ON character_events;
CREATE POLICY tenant_isolation_character_events
ON character_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE world_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE world_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_world_events ON world_events;
CREATE POLICY tenant_isolation_world_events
ON world_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE plot_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE plot_threads FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_plot_threads ON plot_threads;
CREATE POLICY tenant_isolation_plot_threads
ON plot_threads
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE thread_lifecycle ENABLE ROW LEVEL SECURITY;
ALTER TABLE thread_lifecycle FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_thread_lifecycle ON thread_lifecycle;
CREATE POLICY tenant_isolation_thread_lifecycle
ON thread_lifecycle
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE narrative_arcs ENABLE ROW LEVEL SECURITY;
ALTER TABLE narrative_arcs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_narrative_arcs ON narrative_arcs;
CREATE POLICY tenant_isolation_narrative_arcs
ON narrative_arcs
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE volume_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE volume_summaries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_volume_summaries ON volume_summaries;
CREATE POLICY tenant_isolation_volume_summaries
ON volume_summaries
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE world_rule_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE world_rule_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_world_rule_evidence ON world_rule_evidence;
CREATE POLICY tenant_isolation_world_rule_evidence
ON world_rule_evidence
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE consistency_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE consistency_notes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_consistency_notes ON consistency_notes;
CREATE POLICY tenant_isolation_consistency_notes
ON consistency_notes
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE segment_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE segment_summaries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_segment_summaries ON segment_summaries;
CREATE POLICY tenant_isolation_segment_summaries
ON segment_summaries
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE seed_analysis_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE seed_analysis_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_seed_analysis_snapshots ON seed_analysis_snapshots;
CREATE POLICY tenant_isolation_seed_analysis_snapshots
ON seed_analysis_snapshots
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE seed_ontology_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE seed_ontology_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_seed_ontology_snapshots ON seed_ontology_snapshots;
CREATE POLICY tenant_isolation_seed_ontology_snapshots
ON seed_ontology_snapshots
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE seed_entity_resolution_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE seed_entity_resolution_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_seed_entity_resolution_snapshots ON seed_entity_resolution_snapshots;
CREATE POLICY tenant_isolation_seed_entity_resolution_snapshots
ON seed_entity_resolution_snapshots
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE project_readiness_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_readiness_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_project_readiness_snapshots ON project_readiness_snapshots;
CREATE POLICY tenant_isolation_project_readiness_snapshots
ON project_readiness_snapshots
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_assets ON assets;
CREATE POLICY tenant_isolation_assets
ON assets
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE asset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_asset_versions ON asset_versions;
CREATE POLICY tenant_isolation_asset_versions
ON asset_versions
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE asset_collections ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_collections FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_asset_collections ON asset_collections;
CREATE POLICY tenant_isolation_asset_collections
ON asset_collections
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE asset_collection_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_collection_items FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_asset_collection_items ON asset_collection_items;
CREATE POLICY tenant_isolation_asset_collection_items
ON asset_collection_items
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE archive_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE archive_memories FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_archive_memories ON archive_memories;
CREATE POLICY tenant_isolation_archive_memories
ON archive_memories
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE archive_memory_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE archive_memory_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_archive_memory_events ON archive_memory_events;
CREATE POLICY tenant_isolation_archive_memory_events
ON archive_memory_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE global_search_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_search_index FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_global_search_index ON global_search_index;
CREATE POLICY tenant_isolation_global_search_index
ON global_search_index
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_snapshots ON story_graph_snapshots;
CREATE POLICY tenant_isolation_story_graph_snapshots
ON story_graph_snapshots
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_nodes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_nodes ON story_graph_nodes;
CREATE POLICY tenant_isolation_story_graph_nodes
ON story_graph_nodes
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_node_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_node_aliases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_node_aliases ON story_graph_node_aliases;
CREATE POLICY tenant_isolation_story_graph_node_aliases
ON story_graph_node_aliases
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_node_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_node_labels FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_node_labels ON story_graph_node_labels;
CREATE POLICY tenant_isolation_story_graph_node_labels
ON story_graph_node_labels
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_edges FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_edges ON story_graph_edges;
CREATE POLICY tenant_isolation_story_graph_edges
ON story_graph_edges
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_evidence ON story_graph_evidence;
CREATE POLICY tenant_isolation_story_graph_evidence
ON story_graph_evidence
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_layouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_layouts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_layouts ON story_graph_layouts;
CREATE POLICY tenant_isolation_story_graph_layouts
ON story_graph_layouts
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE story_graph_clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_graph_clusters FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_story_graph_clusters ON story_graph_clusters;
CREATE POLICY tenant_isolation_story_graph_clusters
ON story_graph_clusters
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE worldline_saved_paths ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_saved_paths FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_worldline_saved_paths ON worldline_saved_paths;
CREATE POLICY tenant_isolation_worldline_saved_paths
ON worldline_saved_paths
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE character_interaction_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE character_interaction_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_character_interaction_sessions ON character_interaction_sessions;
CREATE POLICY tenant_isolation_character_interaction_sessions
ON character_interaction_sessions
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE character_interaction_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE character_interaction_turns FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_character_interaction_turns ON character_interaction_turns;
CREATE POLICY tenant_isolation_character_interaction_turns
ON character_interaction_turns
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE worldline_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_worldline_sessions ON worldline_sessions;
CREATE POLICY tenant_isolation_worldline_sessions
ON worldline_sessions
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE worldline_preparations ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_preparations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_worldline_preparations ON worldline_preparations;
CREATE POLICY tenant_isolation_worldline_preparations
ON worldline_preparations
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE worldline_prepared_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_prepared_agents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_worldline_prepared_agents ON worldline_prepared_agents;
CREATE POLICY tenant_isolation_worldline_prepared_agents
ON worldline_prepared_agents
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE worldline_variables ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_variables FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_worldline_variables ON worldline_variables;
CREATE POLICY tenant_isolation_worldline_variables
ON worldline_variables
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE worldline_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_worldline_events ON worldline_events;
CREATE POLICY tenant_isolation_worldline_events
ON worldline_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE worldline_event_adoptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE worldline_event_adoptions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_worldline_event_adoptions ON worldline_event_adoptions;
CREATE POLICY tenant_isolation_worldline_event_adoptions
ON worldline_event_adoptions
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_audit_logs ON audit_logs;
CREATE POLICY tenant_isolation_audit_logs
ON audit_logs
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_usage_events ON usage_events;
CREATE POLICY tenant_isolation_usage_events
ON usage_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE resource_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE resource_locks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_resource_locks ON resource_locks;
CREATE POLICY tenant_isolation_resource_locks
ON resource_locks
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_workflow_runs ON workflow_runs;
CREATE POLICY tenant_isolation_workflow_runs
ON workflow_runs
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE workflow_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_workflow_events ON workflow_events;
CREATE POLICY tenant_isolation_workflow_events
ON workflow_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE agent_traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_traces FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_agent_traces ON agent_traces;
CREATE POLICY tenant_isolation_agent_traces
ON agent_traces
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE agent_trace_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_trace_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_agent_trace_events ON agent_trace_events;
CREATE POLICY tenant_isolation_agent_trace_events
ON agent_trace_events
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE llm_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_channels FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_llm_channels ON llm_channels;
CREATE POLICY tenant_isolation_llm_channels
ON llm_channels
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE llm_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_models FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_llm_models ON llm_models;
CREATE POLICY tenant_isolation_llm_models
ON llm_models
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE llm_module_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_module_bindings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_llm_module_bindings ON llm_module_bindings;
CREATE POLICY tenant_isolation_llm_module_bindings
ON llm_module_bindings
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE llm_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_activity FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_llm_activity ON llm_activity;
CREATE POLICY tenant_isolation_llm_activity
ON llm_activity
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE writer_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE writer_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_writer_runs ON writer_runs;
CREATE POLICY tenant_isolation_writer_runs
ON writer_runs
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE writer_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE writer_drafts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_writer_drafts ON writer_drafts;
CREATE POLICY tenant_isolation_writer_drafts
ON writer_drafts
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE draft_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_reviews FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_draft_reviews ON draft_reviews;
CREATE POLICY tenant_isolation_draft_reviews
ON draft_reviews
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE draft_review_issues ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_review_issues FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_draft_review_issues ON draft_review_issues;
CREATE POLICY tenant_isolation_draft_review_issues
ON draft_review_issues
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE manuscript_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE manuscript_blocks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_manuscript_blocks ON manuscript_blocks;
CREATE POLICY tenant_isolation_manuscript_blocks
ON manuscript_blocks
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

COMMIT;
