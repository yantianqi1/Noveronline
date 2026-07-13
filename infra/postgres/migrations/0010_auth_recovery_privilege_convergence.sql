BEGIN;

DO $$
DECLARE
  function_signature REGPROCEDURE;
BEGIN
  FOREACH function_signature IN ARRAY ARRAY[
    to_regprocedure('auth_recovery_request(text,text,bytea,text,timestamptz)'),
    to_regprocedure('auth_recovery_claim_delivery(text,integer)'),
    to_regprocedure('auth_recovery_finish_delivery(uuid,text,text,text,text,timestamptz)'),
    to_regprocedure('auth_recovery_complete(text,text,timestamptz,text)'),
    to_regprocedure('auth_recovery_expire(timestamptz)')
  ] LOOP
    IF function_signature IS NULL OR NOT EXISTS (
      SELECT 1 FROM pg_proc WHERE oid = function_signature AND prosecdef
    ) THEN
      RAISE EXCEPTION 'auth recovery privilege convergence requires SECURITY DEFINER functions';
    END IF;
  END LOOP;
END;
$$;

REVOKE ALL PRIVILEGES ON TABLE password_reset_tokens FROM PUBLIC, mirofish_app;
REVOKE ALL PRIVILEGES ON TABLE password_reset_delivery_attempts FROM PUBLIC, mirofish_app;
REVOKE ALL PRIVILEGES ON TABLE password_reset_delivery_outbox FROM PUBLIC, mirofish_app;
REVOKE ALL PRIVILEGES ON TABLE auth_security_audit_logs FROM PUBLIC, mirofish_app;

REVOKE ALL ON FUNCTION auth_recovery_request(TEXT, TEXT, BYTEA, TEXT, TIMESTAMPTZ) FROM PUBLIC, mirofish_app;
REVOKE ALL ON FUNCTION auth_recovery_claim_delivery(TEXT, INTEGER) FROM PUBLIC, mirofish_app;
REVOKE ALL ON FUNCTION auth_recovery_finish_delivery(UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ) FROM PUBLIC, mirofish_app;
REVOKE ALL ON FUNCTION auth_recovery_complete(TEXT, TEXT, TIMESTAMPTZ, TEXT) FROM PUBLIC, mirofish_app;
REVOKE ALL ON FUNCTION auth_recovery_expire(TIMESTAMPTZ) FROM PUBLIC, mirofish_app;

GRANT EXECUTE ON FUNCTION auth_recovery_request(TEXT, TEXT, BYTEA, TEXT, TIMESTAMPTZ) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_claim_delivery(TEXT, INTEGER) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_finish_delivery(UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_complete(TEXT, TEXT, TIMESTAMPTZ, TEXT) TO mirofish_app;
GRANT EXECUTE ON FUNCTION auth_recovery_expire(TIMESTAMPTZ) TO mirofish_app;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.role_table_grants
    WHERE grantee IN ('PUBLIC', 'mirofish_app')
      AND table_schema = 'public'
      AND table_name IN (
        'password_reset_tokens',
        'password_reset_delivery_attempts',
        'password_reset_delivery_outbox',
        'auth_security_audit_logs'
      )
  ) THEN
    RAISE EXCEPTION 'auth recovery sensitive table privileges remain exposed';
  END IF;
  IF NOT (
    has_function_privilege('mirofish_app', 'auth_recovery_request(text,text,bytea,text,timestamptz)', 'EXECUTE')
    AND has_function_privilege('mirofish_app', 'auth_recovery_claim_delivery(text,integer)', 'EXECUTE')
    AND has_function_privilege('mirofish_app', 'auth_recovery_finish_delivery(uuid,text,text,text,text,timestamptz)', 'EXECUTE')
    AND has_function_privilege('mirofish_app', 'auth_recovery_complete(text,text,timestamptz,text)', 'EXECUTE')
    AND has_function_privilege('mirofish_app', 'auth_recovery_expire(timestamptz)', 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'auth recovery safe function privileges are incomplete';
  END IF;
END;
$$;

COMMIT;
