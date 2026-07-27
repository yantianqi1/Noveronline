BEGIN;

REVOKE UPDATE ON writer_thread_messages FROM mirofish_app;

DELETE FROM mirofish_schema_migrations
WHERE version = '0030_writer_thread_message_adoption';

COMMIT;
