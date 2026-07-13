BEGIN;

CREATE TABLE chapters (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  chapter_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_order INTEGER NOT NULL CHECK (chapter_order >= 0),
  title TEXT NOT NULL CHECK (btrim(title) <> ''),
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','drafting','review','completed','archived')),
  brief TEXT,
  outline TEXT,
  content_text TEXT,
  optimistic_version BIGINT NOT NULL DEFAULT 1 CHECK (optimistic_version > 0),
  created_by UUID REFERENCES users(user_id),
  updated_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, chapter_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE chapter_versions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  chapter_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_id UUID NOT NULL,
  version_number BIGINT NOT NULL CHECK (version_number > 0),
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  brief TEXT,
  outline TEXT,
  content_text TEXT,
  change_kind TEXT NOT NULL DEFAULT 'update' CHECK (change_kind IN ('update','restore','delete')),
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, chapter_id, version_number),
  FOREIGN KEY (tenant_id, project_id, chapter_id)
    REFERENCES chapters(tenant_id, project_id, chapter_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE scenes (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  scene_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_id UUID NOT NULL,
  scene_order INTEGER NOT NULL CHECK (scene_order >= 0),
  title TEXT NOT NULL CHECK (btrim(title) <> ''),
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','drafting','review','completed','archived')),
  brief TEXT,
  outline TEXT,
  content_text TEXT,
  optimistic_version BIGINT NOT NULL DEFAULT 1 CHECK (optimistic_version > 0),
  created_by UUID REFERENCES users(user_id),
  updated_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, scene_id),
  UNIQUE (tenant_id, project_id, chapter_id, scene_id),
  FOREIGN KEY (tenant_id, project_id, chapter_id)
    REFERENCES chapters(tenant_id, project_id, chapter_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE scene_versions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  scene_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scene_id UUID NOT NULL,
  chapter_id UUID NOT NULL,
  version_number BIGINT NOT NULL CHECK (version_number > 0),
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  brief TEXT,
  outline TEXT,
  content_text TEXT,
  change_kind TEXT NOT NULL DEFAULT 'update' CHECK (change_kind IN ('update','restore','delete')),
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, scene_id, version_number),
  FOREIGN KEY (tenant_id, project_id, chapter_id, scene_id)
    REFERENCES scenes(tenant_id, project_id, chapter_id, scene_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE outline_versions (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  outline_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type TEXT NOT NULL CHECK (scope_type IN ('project','chapter','scene')),
  scope_id UUID,
  version_number BIGINT NOT NULL CHECK (version_number > 0),
  lifecycle TEXT NOT NULL DEFAULT 'candidate' CHECK (lifecycle IN ('candidate','active','superseded')),
  title TEXT NOT NULL CHECK (btrim(title) <> ''),
  outline_text TEXT NOT NULL,
  restored_from_version_id UUID,
  created_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((scope_type = 'project' AND scope_id IS NULL) OR (scope_type <> 'project' AND scope_id IS NOT NULL)),
  UNIQUE (tenant_id, project_id, scope_type, scope_id, version_number),
  UNIQUE (tenant_id, project_id, outline_version_id),
  FOREIGN KEY (tenant_id, project_id, restored_from_version_id)
    REFERENCES outline_versions(tenant_id, project_id, outline_version_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_outline_versions_project_version
  ON outline_versions (tenant_id, project_id, scope_type, version_number) WHERE scope_id IS NULL;
CREATE UNIQUE INDEX idx_outline_versions_one_active
  ON outline_versions (tenant_id, project_id, scope_type, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::UUID))
  WHERE lifecycle = 'active';
CREATE UNIQUE INDEX idx_outline_versions_restore_once
  ON outline_versions (tenant_id, project_id, restored_from_version_id)
  WHERE restored_from_version_id IS NOT NULL;

CREATE UNIQUE INDEX idx_workflow_runs_writer_workspace_identity
  ON workflow_runs (tenant_id, project_id, run_id);

CREATE TABLE book_plans (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  book_plan_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL CHECK (btrim(title) <> ''),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','completed','archived')),
  premise TEXT,
  target_chapter_count INTEGER CHECK (target_chapter_count IS NULL OR target_chapter_count > 0),
  planning_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  optimistic_version BIGINT NOT NULL DEFAULT 1 CHECK (optimistic_version > 0),
  last_run_id UUID,
  last_run_status TEXT,
  created_by UUID REFERENCES users(user_id),
  updated_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, book_plan_id),
  FOREIGN KEY (tenant_id, project_id, last_run_id)
    REFERENCES workflow_runs(tenant_id, project_id, run_id) ON DELETE SET NULL,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE book_run_events (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  book_run_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_plan_id UUID NOT NULL,
  run_id UUID,
  sequence INTEGER NOT NULL CHECK (sequence > 0),
  event_type TEXT NOT NULL CHECK (btrim(event_type) <> ''),
  status TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
  warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, book_plan_id, sequence),
  FOREIGN KEY (tenant_id, project_id, book_plan_id)
    REFERENCES book_plans(tenant_id, project_id, book_plan_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES workflow_runs(tenant_id, project_id, run_id) ON DELETE SET NULL,
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE writer_presets (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID,
  writer_preset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL CHECK (btrim(name) <> ''),
  description TEXT,
  settings_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(user_id),
  updated_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, project_id, name),
  UNIQUE (tenant_id, project_id, writer_preset_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE forbidden_lexicon_entries (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  lexicon_entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  term TEXT NOT NULL CHECK (btrim(term) <> ''),
  category TEXT NOT NULL CHECK (btrim(category) <> ''),
  severity TEXT NOT NULL DEFAULT 'warning' CHECK (severity IN ('info','warning','error')),
  replacement_guidance TEXT,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(user_id),
  updated_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, term),
  UNIQUE (tenant_id, project_id, lexicon_entry_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX idx_chapters_project ON chapters (tenant_id, project_id, chapter_order);
CREATE UNIQUE INDEX chapters_project_active_order_key
  ON chapters (tenant_id, project_id, chapter_order)
  WHERE status <> 'archived';
CREATE INDEX idx_chapter_versions_history ON chapter_versions (tenant_id, project_id, chapter_id, version_number DESC);
CREATE INDEX idx_scenes_chapter ON scenes (tenant_id, project_id, chapter_id, scene_order);
CREATE UNIQUE INDEX scenes_chapter_active_order_key
  ON scenes (tenant_id, project_id, chapter_id, scene_order)
  WHERE status <> 'archived';
CREATE INDEX idx_scene_versions_history ON scene_versions (tenant_id, project_id, scene_id, version_number DESC);
CREATE INDEX idx_outline_versions_scope ON outline_versions (tenant_id, project_id, scope_type, scope_id, version_number DESC);
CREATE INDEX idx_book_plans_project ON book_plans (tenant_id, project_id, status, updated_at DESC);
CREATE INDEX idx_book_run_events_replay ON book_run_events (tenant_id, project_id, book_plan_id, sequence);
CREATE INDEX idx_writer_presets_scope ON writer_presets (tenant_id, project_id, enabled, name);
CREATE INDEX idx_forbidden_lexicon_project ON forbidden_lexicon_entries (tenant_id, project_id, enabled, category, term);

DO $rls$
DECLARE table_name TEXT;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['chapters','chapter_versions','scenes','scene_versions','outline_versions','book_plans','book_run_events','writer_presets','forbidden_lexicon_entries'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I FOR ALL USING (tenant_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::UUID) WITH CHECK (tenant_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::UUID)', table_name, table_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO mirofish_app', table_name);
  END LOOP;
END
$rls$;

REVOKE UPDATE, DELETE ON chapter_versions, scene_versions, book_run_events FROM mirofish_app;
REVOKE DELETE ON outline_versions FROM mirofish_app;

CREATE OR REPLACE FUNCTION enforce_outline_version_immutability()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.project_id IS DISTINCT FROM OLD.project_id
     OR NEW.outline_version_id IS DISTINCT FROM OLD.outline_version_id
     OR NEW.scope_type IS DISTINCT FROM OLD.scope_type
     OR NEW.scope_id IS DISTINCT FROM OLD.scope_id
     OR NEW.version_number IS DISTINCT FROM OLD.version_number
     OR NEW.title IS DISTINCT FROM OLD.title
     OR NEW.outline_text IS DISTINCT FROM OLD.outline_text
     OR NEW.restored_from_version_id IS DISTINCT FROM OLD.restored_from_version_id
     OR NEW.created_by IS DISTINCT FROM OLD.created_by
     OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'outline version snapshots are immutable';
  END IF;
  IF NOT (
    NEW.lifecycle = OLD.lifecycle OR
    (OLD.lifecycle = 'candidate' AND NEW.lifecycle IN ('active','superseded')) OR
    (OLD.lifecycle = 'active' AND NEW.lifecycle = 'superseded')
  ) THEN
    RAISE EXCEPTION 'invalid outline lifecycle transition';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_outline_versions_immutable
BEFORE UPDATE ON outline_versions
FOR EACH ROW EXECUTE FUNCTION enforce_outline_version_immutability();

COMMIT;
