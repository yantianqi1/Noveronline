DROP TABLE IF EXISTS pending_email_registrations;

DELETE FROM mirofish_schema_migrations
WHERE version = '0032_email_verification';
