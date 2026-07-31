#!/bin/sh
set -eu
export LC_ALL=C

required="MIROFISH_DEPLOYMENT_ENV COMPOSE_PROJECT_NAME POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD REDIS_PASSWORD APP_DATABASE_USER APP_DATABASE_PASSWORD DATABASE_URL MIROFISH_AUTH_SESSION_SECRET MIROFISH_RECOVERY_CLIENT_PROOF_SECRET MIROFISH_TRUSTED_CLIENT_IP_HEADER AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY MIROFISH_AUTH_RATE_LIMIT_REDIS_URL MIROFISH_RATE_LIMIT_KEY_SECRET MIROFISH_RATE_LIMIT_POLICIES_JSON LLM_CREDENTIAL_ENCRYPTION_KEY MINIO_ROOT_USER MINIO_ROOT_PASSWORD MIROFISH_OBJECT_STORAGE_ENDPOINT MIROFISH_OBJECT_STORAGE_BUCKET MIROFISH_OBJECT_STORAGE_ACCESS_KEY MIROFISH_OBJECT_STORAGE_SECRET_KEY MIROFISH_OBJECT_STORAGE_USE_SSL MIROFISH_OBJECT_STORAGE_REGION TEMPORAL_NAMESPACE SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD SMTP_FROM SMTP_TLS_MODE AUTH_RECOVERY_RESET_BASE_URL COLLABORATION_ACCEPT_BASE_URL API_PORT WEB_PORT"
for name in $required; do
  eval "value=\${$name-}"
  [ -n "$value" ] || { echo "configuration error: $name is required" >&2; exit 1; }
  case "$value" in
    *replace-with*|*change_me*|*dev_password*|mirofish_local_*)
      echo "configuration error: $name contains a placeholder or development default" >&2
      exit 1
      ;;
  esac
done

case "$MIROFISH_DEPLOYMENT_ENV" in staging|production) ;; *)
  echo "configuration error: MIROFISH_DEPLOYMENT_ENV must be staging or production" >&2
  exit 1
esac
[ "${#MIROFISH_AUTH_SESSION_SECRET}" -ge 32 ] || {
  echo "configuration error: MIROFISH_AUTH_SESSION_SECRET must be at least 32 characters" >&2
  exit 1
}
[ "${#MIROFISH_RECOVERY_CLIENT_PROOF_SECRET}" -ge 32 ] || {
  echo "configuration error: MIROFISH_RECOVERY_CLIENT_PROOF_SECRET must be at least 32 bytes" >&2
  exit 1
}
decoded_outbox_key_bytes="$(printf '%s' "$AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY" | openssl base64 -d -A 2>/dev/null | wc -c | tr -d ' ')"
[ "$decoded_outbox_key_bytes" -eq 32 ] || {
  echo "configuration error: AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY must decode to exactly 32 bytes" >&2
  exit 1
}
[ "${#MIROFISH_RATE_LIMIT_KEY_SECRET}" -ge 32 ] || {
  echo "configuration error: MIROFISH_RATE_LIMIT_KEY_SECRET must be at least 32 bytes" >&2
  exit 1
}
case "$MIROFISH_TRUSTED_CLIENT_IP_HEADER" in
  X-Real-IP|CF-Connecting-IP) ;;
  *)
    echo "configuration error: trusted client IP header must be edge-overwritten X-Real-IP or CF-Connecting-IP" >&2
    exit 1
    ;;
esac
[ "$MIROFISH_RECOVERY_CLIENT_PROOF_SECRET" != "$MIROFISH_AUTH_SESSION_SECRET" ] &&
[ "$MIROFISH_RATE_LIMIT_KEY_SECRET" != "$MIROFISH_AUTH_SESSION_SECRET" ] &&
[ "$MIROFISH_RATE_LIMIT_KEY_SECRET" != "$MIROFISH_RECOVERY_CLIENT_PROOF_SECRET" ] &&
[ "$AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY" != "$(printf '%s' "$MIROFISH_AUTH_SESSION_SECRET" | openssl base64 -A)" ] &&
[ "$AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY" != "$(printf '%s' "$MIROFISH_RECOVERY_CLIENT_PROOF_SECRET" | openssl base64 -A)" ] &&
[ "$AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY" != "$(printf '%s' "$MIROFISH_RATE_LIMIT_KEY_SECRET" | openssl base64 -A)" ] || {
  echo "configuration error: authentication and recovery secrets must be distinct" >&2
  exit 1
}
[ "$POSTGRES_PASSWORD" != "$APP_DATABASE_PASSWORD" ] || {
  echo "configuration error: admin and runtime database passwords must differ" >&2
  exit 1
}
[ "$MINIO_ROOT_PASSWORD" != "$POSTGRES_PASSWORD" ] || {
  echo "configuration error: storage and database passwords must differ" >&2
  exit 1
}
case "$DATABASE_URL" in postgresql://*|postgres://*) ;; *)
  echo "configuration error: DATABASE_URL must be a PostgreSQL DSN" >&2
  exit 1
esac
case "$MIROFISH_OBJECT_STORAGE_BUCKET" in *"$MIROFISH_DEPLOYMENT_ENV"*) ;; *)
  echo "configuration error: object bucket must include the deployment environment" >&2
  exit 1
esac
case "$MIROFISH_OBJECT_STORAGE_ENDPOINT" in
  *://*|*/*|*[[:space:]]*|'')
    echo "configuration error: object storage endpoint must be host:port without a scheme or path" >&2
    exit 1
    ;;
esac
case "$MIROFISH_OBJECT_STORAGE_USE_SSL" in true|false) ;; *)
  echo "configuration error: MIROFISH_OBJECT_STORAGE_USE_SSL must be true or false" >&2
  exit 1
esac
case "$TEMPORAL_NAMESPACE" in *"$MIROFISH_DEPLOYMENT_ENV"*) ;; *)
  echo "configuration error: Temporal namespace must include the deployment environment" >&2
  exit 1
esac
case "$MIROFISH_AUTH_RATE_LIMIT_REDIS_URL" in redis://:*@*|rediss://:*@*) ;; *)
  echo "configuration error: MIROFISH_AUTH_RATE_LIMIT_REDIS_URL must use redis:// or rediss://" >&2
  exit 1
esac
for policy_class in auth_login auth_signup auth_session_mutation collaboration_invite_create collaboration_invite_accept llm_admin_mutation llm_provider_health; do
  case "$MIROFISH_RATE_LIMIT_POLICIES_JSON" in *\"$policy_class\"*) ;; *)
    echo "configuration error: MIROFISH_RATE_LIMIT_POLICIES_JSON is missing a required policy class" >&2
    exit 1
  esac
done
case "$MIROFISH_RATE_LIMIT_POLICIES_JSON" in *\"limit\"*\"window_seconds\"*) ;; *)
  echo "configuration error: MIROFISH_RATE_LIMIT_POLICIES_JSON must define limit and window_seconds" >&2
  exit 1
esac
case "$SMTP_PORT" in *[!0-9]*|'')
  echo "configuration error: SMTP_PORT must be an integer from 1 to 65535" >&2
  exit 1
esac
[ "$SMTP_PORT" -ge 1 ] && [ "$SMTP_PORT" -le 65535 ] || {
  echo "configuration error: SMTP_PORT must be an integer from 1 to 65535" >&2
  exit 1
}
case "$SMTP_HOST" in *://*|*/*|*[[:space:]]*)
  echo "configuration error: SMTP_HOST must be a hostname without a scheme or path" >&2
  exit 1
esac
case "$SMTP_FROM" in
  *[[:space:]]*|*@*@*|@*|*@)
    echo "configuration error: SMTP_FROM must be an email address" >&2
    exit 1
    ;;
  *@*.*) ;;
  *)
    echo "configuration error: SMTP_FROM must be an email address" >&2
    exit 1
    ;;
esac
case "$AUTH_RECOVERY_RESET_BASE_URL" in https://*) ;; *)
  echo "configuration error: public password reset URL must use HTTPS" >&2
  exit 1
esac
case "$COLLABORATION_ACCEPT_BASE_URL" in https://*) ;; *)
  echo "configuration error: public invitation URL must use HTTPS" >&2
  exit 1
esac
for public_url in "$AUTH_RECOVERY_RESET_BASE_URL" "$COLLABORATION_ACCEPT_BASE_URL"; do
  case "${public_url#https://}" in *@*|*\?*|*\#*|'')
    echo "configuration error: public recovery and invitation URLs must not contain credentials, query, or fragment" >&2
    exit 1
  esac
done
[ "$AUTH_RECOVERY_RESET_BASE_URL" != "$COLLABORATION_ACCEPT_BASE_URL" ] || {
  echo "configuration error: recovery and invitation URLs must be distinct" >&2
  exit 1
}
case "$SMTP_TLS_MODE" in implicit_tls|starttls) ;; *)
  echo "configuration error: SMTP TLS mode must be implicit_tls or starttls" >&2
  exit 1
esac
if [ "$MIROFISH_DEPLOYMENT_ENV" = "production" ] && [ "$SMTP_TLS_MODE" != "implicit_tls" ]; then
  echo "configuration error: production SMTP must use implicit_tls" >&2
  exit 1
fi

echo "deployment configuration accepted for $MIROFISH_DEPLOYMENT_ENV (secret values not printed)"
