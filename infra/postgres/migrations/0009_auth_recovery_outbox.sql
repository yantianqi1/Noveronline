BEGIN;

CREATE TABLE IF NOT EXISTS password_reset_delivery_outbox (
  outbox_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reset_token_id UUID NOT NULL UNIQUE REFERENCES password_reset_tokens(reset_token_id) ON DELETE CASCADE,
  token_ciphertext BYTEA NOT NULL CHECK (octet_length(token_ciphertext) >= 32),
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'delivered', 'dead')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((status = 'processing') = (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_password_reset_delivery_outbox_claim
  ON password_reset_delivery_outbox (status, next_attempt_at, lease_expires_at, created_at);

CREATE OR REPLACE FUNCTION reject_manuscript_block_version_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
    RETURN OLD;
  END IF;
  IF TG_OP = 'UPDATE' AND pg_trigger_depth() > 1
     AND (to_jsonb(NEW) - 'source_draft_id' - 'source_writer_run_id')
         = (to_jsonb(OLD) - 'source_draft_id' - 'source_writer_run_id')
     AND (NEW.source_draft_id IS NULL OR NEW.source_draft_id IS NOT DISTINCT FROM OLD.source_draft_id)
     AND (NEW.source_writer_run_id IS NULL OR NEW.source_writer_run_id IS NOT DISTINCT FROM OLD.source_writer_run_id)
  THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'manuscript block versions are immutable';
END;
$$;

ALTER TABLE manuscript_blocks
  DROP CONSTRAINT IF EXISTS manuscript_blocks_source_writer_run_scope_fk,
  DROP CONSTRAINT IF EXISTS manuscript_blocks_source_draft_scope_fk,
  ADD CONSTRAINT manuscript_blocks_source_writer_run_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_writer_run_id)
    REFERENCES writer_runs(tenant_id, project_id, run_id)
    ON DELETE SET NULL (source_writer_run_id) NOT VALID,
  ADD CONSTRAINT manuscript_blocks_source_draft_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_draft_id)
    REFERENCES writer_drafts(tenant_id, project_id, draft_id)
    ON DELETE SET NULL (source_draft_id) NOT VALID;

ALTER TABLE manuscript_block_versions
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_source_writer_run_scope_fk,
  DROP CONSTRAINT IF EXISTS manuscript_block_versions_source_draft_scope_fk,
  ADD CONSTRAINT manuscript_block_versions_source_writer_run_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_writer_run_id)
    REFERENCES writer_runs(tenant_id, project_id, run_id)
    ON DELETE SET NULL (source_writer_run_id) NOT VALID,
  ADD CONSTRAINT manuscript_block_versions_source_draft_scope_fk
    FOREIGN KEY (tenant_id, project_id, source_draft_id)
    REFERENCES writer_drafts(tenant_id, project_id, draft_id)
    ON DELETE SET NULL (source_draft_id) NOT VALID;

ALTER TABLE manuscript_blocks
  VALIDATE CONSTRAINT manuscript_blocks_source_writer_run_scope_fk,
  VALIDATE CONSTRAINT manuscript_blocks_source_draft_scope_fk;
ALTER TABLE manuscript_block_versions
  VALIDATE CONSTRAINT manuscript_block_versions_source_writer_run_scope_fk,
  VALIDATE CONSTRAINT manuscript_block_versions_source_draft_scope_fk;

CREATE OR REPLACE FUNCTION auth_recovery_request(
  p_email_normalized TEXT,
  p_token_hash TEXT,
  p_token_ciphertext BYTEA,
  p_request_id TEXT,
  p_expires_at TIMESTAMPTZ
)
RETURNS TABLE(account_matched BOOLEAN, reset_token_id UUID)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $request$
DECLARE
  matched_user_id UUID;
  created_reset_id UUID;
BEGIN
  IF p_email_normalized IS NULL OR p_email_normalized <> lower(btrim(p_email_normalized))
     OR p_email_normalized = '' OR p_token_hash !~ '^[0-9a-f]{64}$'
     OR p_token_ciphertext IS NULL OR octet_length(p_token_ciphertext) < 32
     OR p_expires_at <= now() THEN
    RAISE EXCEPTION 'invalid recovery request';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_email_normalized, 0));
  SELECT user_id INTO matched_user_id
  FROM users
  WHERE lower(btrim(email)) = p_email_normalized AND status = 'active'
  LIMIT 1;
  IF matched_user_id IS NULL THEN
    INSERT INTO auth_security_audit_logs(action, resource_type, request_id, metadata_jsonb)
    VALUES ('auth.password_reset.requested', 'password_reset', NULLIF(p_request_id, ''), '{"account_matched":false}'::JSONB);
    RETURN QUERY SELECT FALSE, NULL::UUID;
    RETURN;
  END IF;
  UPDATE password_reset_delivery_outbox AS queued
  SET status = 'dead', lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
  WHERE queued.reset_token_id IN (
    SELECT token.reset_token_id FROM password_reset_tokens AS token
    WHERE token.user_id = matched_user_id AND token.status = 'pending'
  ) AND queued.status IN ('queued', 'processing');
  UPDATE password_reset_tokens
  SET status = 'revoked', updated_at = now()
  WHERE user_id = matched_user_id AND status = 'pending';
  INSERT INTO password_reset_tokens(user_id, token_hash, request_id, expires_at)
  VALUES (matched_user_id, p_token_hash, NULLIF(p_request_id, ''), p_expires_at)
  RETURNING password_reset_tokens.reset_token_id INTO created_reset_id;
  INSERT INTO password_reset_delivery_outbox(reset_token_id, token_ciphertext)
  VALUES (created_reset_id, p_token_ciphertext);
  INSERT INTO auth_security_audit_logs(user_id, action, resource_type, resource_id, request_id, metadata_jsonb)
  VALUES (matched_user_id, 'auth.password_reset.requested', 'password_reset', created_reset_id,
          NULLIF(p_request_id, ''), jsonb_build_object('account_matched', TRUE, 'expires_at', p_expires_at));
  RETURN QUERY SELECT TRUE, created_reset_id;
END;
$request$;

CREATE OR REPLACE FUNCTION auth_recovery_claim_delivery(p_worker_id TEXT, p_lease_seconds INTEGER)
RETURNS TABLE(
  outbox_id UUID,
  reset_token_id UUID,
  token_ciphertext BYTEA,
  email TEXT,
  expires_at TIMESTAMPTZ,
  attempt_count INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $claim$
BEGIN
  IF btrim(COALESCE(p_worker_id, '')) = '' OR p_lease_seconds < 1 OR p_lease_seconds > 3600 THEN
    RAISE EXCEPTION 'invalid recovery delivery lease';
  END IF;
  RETURN QUERY
  WITH candidate AS (
    SELECT queued.outbox_id
    FROM password_reset_delivery_outbox AS queued
    JOIN password_reset_tokens AS token ON token.reset_token_id = queued.reset_token_id
    WHERE token.status = 'pending' AND token.expires_at > now()
      AND queued.next_attempt_at <= now()
      AND (queued.status = 'queued' OR (queued.status = 'processing' AND queued.lease_expires_at <= now()))
    ORDER BY queued.created_at
    LIMIT 1
    FOR UPDATE OF queued SKIP LOCKED
  ), claimed AS (
    UPDATE password_reset_delivery_outbox AS queued
    SET status = 'processing', attempt_count = queued.attempt_count + 1,
        lease_owner = p_worker_id, lease_expires_at = now() + make_interval(secs => p_lease_seconds),
        updated_at = now()
    FROM candidate
    WHERE queued.outbox_id = candidate.outbox_id
    RETURNING queued.outbox_id, queued.reset_token_id, queued.token_ciphertext, queued.attempt_count
  )
  SELECT claimed.outbox_id, claimed.reset_token_id, claimed.token_ciphertext, account.email, token.expires_at,
         claimed.attempt_count
  FROM claimed
  JOIN password_reset_tokens AS token ON token.reset_token_id = claimed.reset_token_id
  JOIN users AS account ON account.user_id = token.user_id;
END;
$claim$;

CREATE OR REPLACE FUNCTION auth_recovery_finish_delivery(
  p_outbox_id UUID,
  p_worker_id TEXT,
  p_status TEXT,
  p_error_code TEXT,
  p_provider_message_id TEXT,
  p_next_attempt_at TIMESTAMPTZ
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $finish$
DECLARE
  target_reset_id UUID;
  attempt_status TEXT;
  token_delivery_status TEXT;
BEGIN
  IF p_status NOT IN ('delivered', 'queued', 'dead') OR btrim(COALESCE(p_worker_id, '')) = '' THEN
    RAISE EXCEPTION 'invalid recovery delivery result';
  END IF;
  UPDATE password_reset_delivery_outbox
  SET status = p_status,
      lease_owner = NULL,
      lease_expires_at = NULL,
      next_attempt_at = CASE WHEN p_status = 'queued' THEN COALESCE(p_next_attempt_at, now()) ELSE next_attempt_at END,
      last_error_code = NULLIF(p_error_code, ''),
      updated_at = now()
  WHERE outbox_id = p_outbox_id AND status = 'processing' AND lease_owner = p_worker_id
  RETURNING reset_token_id INTO target_reset_id;
  IF target_reset_id IS NULL THEN
    RETURN FALSE;
  END IF;
  attempt_status := CASE WHEN p_status = 'delivered' THEN 'delivered' ELSE 'failed' END;
  token_delivery_status := CASE WHEN p_status = 'delivered' THEN 'delivered' ELSE 'failed' END;
  UPDATE password_reset_tokens
  SET delivery_status = token_delivery_status,
      delivery_attempts = delivery_attempts + 1,
      last_delivery_error_code = NULLIF(p_error_code, ''),
      updated_at = now()
  WHERE password_reset_tokens.reset_token_id = target_reset_id;
  INSERT INTO password_reset_delivery_attempts(reset_token_id, status, provider_message_id, error_code)
  VALUES (target_reset_id, attempt_status, NULLIF(p_provider_message_id, ''), NULLIF(p_error_code, ''));
  RETURN TRUE;
END;
$finish$;

CREATE OR REPLACE FUNCTION auth_recovery_complete(
  p_token_hash TEXT,
  p_password_hash TEXT,
  p_now TIMESTAMPTZ,
  p_request_id TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $complete$
DECLARE
  target_reset_id UUID;
  target_user_id UUID;
  target_status TEXT;
  target_expires_at TIMESTAMPTZ;
BEGIN
  SELECT reset_token_id, user_id, status, expires_at
  INTO target_reset_id, target_user_id, target_status, target_expires_at
  FROM password_reset_tokens
  WHERE token_hash = p_token_hash
  FOR UPDATE;
  IF target_reset_id IS NULL THEN RETURN 'invalid'; END IF;
  IF target_status <> 'pending' THEN RETURN 'consumed'; END IF;
  IF target_expires_at <= p_now THEN
    UPDATE password_reset_tokens SET status = 'expired', updated_at = now() WHERE reset_token_id = target_reset_id;
    UPDATE password_reset_delivery_outbox SET status = 'dead', lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
    WHERE reset_token_id = target_reset_id AND status IN ('queued', 'processing');
    INSERT INTO auth_security_audit_logs(user_id, actor_user_id, action, resource_type, resource_id, request_id, metadata_jsonb)
    VALUES (target_user_id, target_user_id, 'auth.password_reset.expired', 'password_reset', target_reset_id,
            NULLIF(p_request_id, ''), '{"status_before":"pending","status_after":"expired"}'::JSONB);
    RETURN 'expired';
  END IF;
  UPDATE user_password_credentials
  SET password_hash = p_password_hash, status = 'active', password_updated_at = p_now, updated_at = now()
  WHERE user_id = target_user_id;
  IF NOT FOUND THEN RETURN 'backend_failed'; END IF;
  UPDATE password_reset_tokens SET status = 'consumed', consumed_at = p_now, updated_at = now()
  WHERE reset_token_id = target_reset_id AND status = 'pending';
  IF NOT FOUND THEN RETURN 'consumed'; END IF;
  UPDATE user_sessions SET status = 'revoked', revoked_at = p_now, updated_at = now()
  WHERE user_id = target_user_id AND status = 'active' AND revoked_at IS NULL;
  UPDATE password_reset_delivery_outbox SET status = 'dead', lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
  WHERE reset_token_id = target_reset_id AND status IN ('queued', 'processing');
  INSERT INTO auth_security_audit_logs(user_id, actor_user_id, action, resource_type, resource_id, request_id, metadata_jsonb)
  VALUES (target_user_id, target_user_id, 'auth.password_reset.completed', 'password_reset', target_reset_id,
          NULLIF(p_request_id, ''), '{"credential_replaced":true,"all_sessions_revoked":true}'::JSONB);
  RETURN 'completed';
END;
$complete$;

CREATE OR REPLACE FUNCTION auth_recovery_expire(p_now TIMESTAMPTZ)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $expire$
DECLARE
  expired_count BIGINT;
BEGIN
  WITH expired AS (
    UPDATE password_reset_tokens
    SET status = 'expired', updated_at = now()
    WHERE status = 'pending' AND expires_at <= p_now
    RETURNING reset_token_id, user_id
  ), dead_outbox AS (
    UPDATE password_reset_delivery_outbox AS queued
    SET status = 'dead', lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
    FROM expired
    WHERE queued.reset_token_id = expired.reset_token_id AND queued.status IN ('queued', 'processing')
  ), audited AS (
    INSERT INTO auth_security_audit_logs(user_id, action, resource_type, resource_id, metadata_jsonb)
    SELECT user_id, 'auth.password_reset.expired', 'password_reset', reset_token_id,
           '{"status_before":"pending","status_after":"expired"}'::JSONB
    FROM expired
    RETURNING 1
  )
  SELECT count(*) INTO expired_count FROM audited;
  RETURN expired_count;
END;
$expire$;

ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_reset_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE password_reset_delivery_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_reset_delivery_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE password_reset_delivery_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_reset_delivery_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE auth_security_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_security_audit_logs FORCE ROW LEVEL SECURITY;

REVOKE ALL ON password_reset_tokens FROM mirofish_app;
REVOKE ALL ON password_reset_delivery_attempts FROM mirofish_app;
REVOKE ALL ON password_reset_delivery_outbox FROM mirofish_app;
REVOKE ALL ON auth_security_audit_logs FROM mirofish_app;

REVOKE ALL ON FUNCTION auth_recovery_request(TEXT, TEXT, BYTEA, TEXT, TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION auth_recovery_claim_delivery(TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION auth_recovery_finish_delivery(UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION auth_recovery_complete(TEXT, TEXT, TIMESTAMPTZ, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION auth_recovery_expire(TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_recovery_request(TEXT, TEXT, BYTEA, TEXT, TIMESTAMPTZ) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_claim_delivery(TEXT, INTEGER) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_finish_delivery(UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_complete(TEXT, TEXT, TIMESTAMPTZ, TEXT) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_expire(TIMESTAMPTZ) TO mirofish_app;

COMMIT;
