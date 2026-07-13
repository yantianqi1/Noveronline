BEGIN;

LOCK TABLE llm_module_bindings IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM llm_module_bindings
    WHERE project_id IS NULL
    GROUP BY tenant_id, module_key
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'duplicate tenant-default LLM module bindings must be resolved before 0014';
  END IF;
END
$$;

CREATE UNIQUE INDEX llm_module_bindings_tenant_default_key
  ON llm_module_bindings (tenant_id, module_key)
  WHERE project_id IS NULL;

DROP POLICY IF EXISTS platform_select_llm_channels ON llm_channels;
CREATE POLICY platform_select_llm_channels
ON llm_channels FOR SELECT
USING (tenant_id IS NULL);

DROP POLICY IF EXISTS platform_select_llm_models ON llm_models;
CREATE POLICY platform_select_llm_models
ON llm_models FOR SELECT
USING (tenant_id IS NULL);

CREATE TABLE llm_platform_module_defaults (
  module_key TEXT PRIMARY KEY CHECK (btrim(module_key) <> ''),
  channel_id UUID NOT NULL,
  model_id TEXT NOT NULL CHECK (btrim(model_id) <> ''),
  settings_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  updated_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (channel_id, model_id)
    REFERENCES llm_models(channel_id, model_id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION enforce_llm_platform_default_target()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM llm_channels AS channel
    JOIN llm_models AS model
      ON model.channel_id = channel.channel_id
     AND model.model_id = NEW.model_id
    WHERE channel.channel_id = NEW.channel_id
      AND channel.tenant_id IS NULL
      AND model.tenant_id IS NULL
  ) THEN
    RAISE EXCEPTION 'LLM platform default must reference a platform channel and model';
  END IF;
  RETURN NEW;
END
$$;

REVOKE ALL ON FUNCTION enforce_llm_platform_default_target() FROM PUBLIC;

CREATE TRIGGER trg_llm_platform_default_target
BEFORE INSERT OR UPDATE OF channel_id, model_id
ON llm_platform_module_defaults
FOR EACH ROW
EXECUTE FUNCTION enforce_llm_platform_default_target();

REVOKE ALL ON llm_platform_module_defaults FROM PUBLIC, mirofish_app;
GRANT SELECT ON llm_platform_module_defaults TO mirofish_app;

ALTER TABLE llm_platform_module_defaults ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_platform_module_defaults FORCE ROW LEVEL SECURITY;
CREATE POLICY select_llm_platform_module_defaults
ON llm_platform_module_defaults FOR SELECT
USING (true);

COMMIT;
