BEGIN;

-- 0027: Asset-to-asset relationship links for 1-hop recall expansion
-- ("召回一个、带出相关一串"). Projected from seed `relationships` by resolving
-- entity names → entity assets, and writable by manuscript distillation
-- acceptance. Additive only.

CREATE TABLE IF NOT EXISTS asset_links (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  asset_link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  asset_a_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  asset_b_id UUID NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  -- direction: a_to_b (A is source), b_to_a (B is source), undirected
  direction TEXT NOT NULL DEFAULT 'undirected'
    CHECK (direction IN ('a_to_b', 'b_to_a', 'undirected')),
  -- provenance: which pipeline wrote this link (seed_pipeline | manuscript_distillation)
  source_kind TEXT NOT NULL DEFAULT 'seed_pipeline',
  source_ref TEXT,
  summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, asset_a_id, asset_b_id, relation_type),
  CHECK (asset_a_id <> asset_b_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS asset_links_a_idx
  ON asset_links (tenant_id, project_id, asset_a_id);
CREATE INDEX IF NOT EXISTS asset_links_b_idx
  ON asset_links (tenant_id, project_id, asset_b_id);

-- Grants and FORCE RLS, matching the 0018 distillation tables.
REVOKE ALL ON asset_links FROM PUBLIC, mirofish_app;
GRANT SELECT, INSERT, UPDATE ON asset_links TO mirofish_app;

ALTER TABLE asset_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_links FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_asset_links ON asset_links;
CREATE POLICY tenant_isolation_asset_links
ON asset_links
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

COMMIT;
