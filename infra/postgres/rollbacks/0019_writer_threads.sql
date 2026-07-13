BEGIN;

DROP TABLE IF EXISTS writer_approvals;
DROP TABLE IF EXISTS writer_thread_messages;
DROP TABLE IF EXISTS writer_threads;

ALTER TABLE writer_runs
  DROP CONSTRAINT IF EXISTS writer_runs_mode_check;

ALTER TABLE writer_runs
  ADD CONSTRAINT writer_runs_mode_check
    CHECK (mode IN ('draft', 'continue', 'outline', 'review'));

DELETE FROM mirofish_schema_migrations
WHERE version = '0019_writer_threads';

COMMIT;
