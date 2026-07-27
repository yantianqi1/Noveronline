BEGIN;

-- Draft adoption records the adopted manuscript block on the originating
-- thread message. Keep DELETE revoked while granting the one mutation needed
-- by the adoption transaction.
GRANT UPDATE ON writer_thread_messages TO mirofish_app;

COMMIT;
