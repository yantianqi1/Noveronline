#!/bin/sh
set -eu

: "${PUBLIC_HOST:?PUBLIC_HOST is required}"

output_path="${1:-.env}"
image_tag="${MIROFISH_IMAGE_TAG:-latest}"
web_port="${WEB_PORT:-3999}"

postgres_password="$(openssl rand -hex 24)"
runtime_password="$(openssl rand -hex 24)"
storage_password="$(openssl rand -hex 24)"
auth_session_secret="$(openssl rand -hex 32)"
recovery_proof_secret="$(openssl rand -hex 32)"
rate_limit_secret="$(openssl rand -hex 32)"
outbox_key="$(openssl rand -base64 32 | tr -d '\n')"
llm_key="$(openssl rand -base64 32 | tr -d '\n')"

umask 077
{
  printf '%s\n' \
    'MIROFISH_DEPLOYMENT_ENV=production' \
    'COMPOSE_PROJECT_NAME=mirofish-production' \
    'POSTGRES_DB=mirofish' \
    'POSTGRES_USER=mirofish_admin' \
    "POSTGRES_PASSWORD=$postgres_password" \
    'APP_DATABASE_USER=mirofish_runtime' \
    "APP_DATABASE_PASSWORD=$runtime_password" \
    "DATABASE_URL=postgresql://mirofish_runtime:$runtime_password@postgres:5432/mirofish?sslmode=disable" \
    "MIROFISH_AUTH_SESSION_SECRET=$auth_session_secret" \
    "MIROFISH_RECOVERY_CLIENT_PROOF_SECRET=$recovery_proof_secret" \
    'MIROFISH_TRUSTED_CLIENT_IP_HEADER=X-Real-IP' \
    "AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY=$outbox_key" \
    "LLM_CREDENTIAL_ENCRYPTION_KEY=$llm_key" \
    'MINIO_ROOT_USER=mirofish_storage' \
    "MINIO_ROOT_PASSWORD=$storage_password" \
    'MIROFISH_OBJECT_STORAGE_BUCKET=mirofish-production-uploads' \
    'MIROFISH_OBJECT_STORAGE_ENDPOINT=minio:9000' \
    'MIROFISH_OBJECT_STORAGE_ACCESS_KEY=mirofish_storage' \
    "MIROFISH_OBJECT_STORAGE_SECRET_KEY=$storage_password" \
    'MIROFISH_OBJECT_STORAGE_USE_SSL=false' \
    'MIROFISH_OBJECT_STORAGE_REGION=us-east-1' \
    'TEMPORAL_NAMESPACE=mirofish-production' \
    'MIROFISH_AUTH_RATE_LIMIT_REDIS_URL=redis://redis:6379/0' \
    "MIROFISH_RATE_LIMIT_KEY_SECRET=$rate_limit_secret" \
    'MIROFISH_RATE_LIMIT_POLICIES_JSON='"'"'{"auth_login":{"limit":10,"window_seconds":60},"auth_signup":{"limit":5,"window_seconds":300},"auth_session_mutation":{"limit":20,"window_seconds":60},"collaboration_invite_create":{"limit":10,"window_seconds":60},"collaboration_invite_accept":{"limit":20,"window_seconds":60},"llm_admin_mutation":{"limit":20,"window_seconds":60},"llm_provider_health":{"limit":30,"window_seconds":60}}'"'"'' \
    'SMTP_HOST=127.0.0.1' \
    'SMTP_PORT=465' \
    'SMTP_USERNAME=unconfigured' \
    "SMTP_PASSWORD=$(openssl rand -hex 24)" \
    'SMTP_FROM=no-reply@localhost.invalid' \
    'SMTP_TLS_MODE=implicit_tls' \
    "AUTH_RECOVERY_RESET_BASE_URL=https://$PUBLIC_HOST:$web_port/recovery/reset" \
    "COLLABORATION_ACCEPT_BASE_URL=https://$PUBLIC_HOST:$web_port/invitations/accept" \
    'API_PORT=3888' \
    "WEB_PORT=$web_port" \
    'PUBLIC_BIND_ADDRESS=0.0.0.0' \
    'MIROFISH_DATA_ROOT=/data/mirofish-saas' \
    "MIROFISH_API_IMAGE=mirofish/api:$image_tag" \
    "MIROFISH_WEB_IMAGE=mirofish/web:$image_tag" \
    "MIROFISH_AGENT_RUNTIME_IMAGE=mirofish/agent-runtime:$image_tag" \
    "MIROFISH_PI_AGENT_RUNTIME_IMAGE=mirofish/pi-agent-runtime:$image_tag"
} >"$output_path"

chmod 600 "$output_path"
printf 'Created %s with generated deployment secrets.\n' "$output_path"
