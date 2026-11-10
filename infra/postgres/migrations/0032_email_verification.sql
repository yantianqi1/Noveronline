-- Self-service signup stores no account or session until the email challenge is consumed.
CREATE TABLE IF NOT EXISTS pending_email_registrations (
  pending_registration_id UUID PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  project_title TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pending_email_registrations_active
  ON pending_email_registrations (email, expires_at)
  WHERE consumed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_pending_email_registrations_token
  ON pending_email_registrations (token_hash, expires_at)
  WHERE consumed_at IS NULL;

REVOKE ALL ON pending_email_registrations FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON pending_email_registrations TO mirofish_app;

-- The migration runner records the checksum and execution kind after applying this file.
