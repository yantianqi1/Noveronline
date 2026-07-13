BEGIN;

LOCK TABLE llm_platform_module_defaults IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM llm_platform_module_defaults LIMIT 1) THEN
    RAISE EXCEPTION '0014 rollback requires an empty llm_platform_module_defaults table';
  END IF;
END
$$;

DROP TABLE IF EXISTS llm_platform_module_defaults;
DROP FUNCTION IF EXISTS enforce_llm_platform_default_target();

DROP POLICY IF EXISTS platform_select_llm_channels ON llm_channels;
DROP POLICY IF EXISTS platform_select_llm_models ON llm_models;
DROP INDEX IF EXISTS llm_module_bindings_tenant_default_key;

COMMIT;
