BEGIN;

DROP INDEX IF EXISTS idx_worldline_variables_session_locked;

DELETE FROM mirofish_schema_migrations
WHERE version = '0028_worldline_variable_lock_and_canon';

COMMIT;
