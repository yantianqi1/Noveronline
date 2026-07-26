BEGIN;

DROP POLICY IF EXISTS tenant_isolation_asset_links ON asset_links;

DROP TABLE IF EXISTS asset_links;

DELETE FROM mirofish_schema_migrations
WHERE version = '0027_asset_links';

COMMIT;
