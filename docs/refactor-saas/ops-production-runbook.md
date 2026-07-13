# Production Operations Runbook

This runbook covers the standalone production assets that MAIN-100 can layer onto the base compose file. It does not change the base compose topology.

## Configuration gate

Load secrets from the deployment secret manager, then run:

```bash
set -a
. infra/deployment/production.env
set +a
infra/scripts/validate-deployment-config.sh
docker compose -f infra/docker-compose.yml -f infra/compose.production.yml config --quiet
```

The gate rejects missing values, documented placeholders, reused database/storage passwords, short session secrets, and staging/production namespace or bucket collisions. It never prints secret values.

Readiness is fail-closed in staging and production. The API receives the same explicit `TEMPORAL_NAMESPACE` used by workers and explicit object-storage endpoint, bucket, access key, secret key and TLS mode; production overrides do not allow those probes to inherit local development credentials. `/readyz` returns only dependency names, readiness states and stable error codes.

Production SMTP is fail-closed: host, port, username, password, From address, `implicit_tls`, and both HTTPS public reset/invitation URLs are mandatory. The platform limiter is also fail-closed in staging and production: `MIROFISH_AUTH_RATE_LIMIT_REDIS_URL`, a dedicated 32-byte `MIROFISH_RATE_LIMIT_KEY_SECRET`, and `MIROFISH_RATE_LIMIT_POLICIES_JSON` covering all six production policy classes are required. Redis failure must prevent the API from silently starting without the limiter.

The edge proxy must delete any incoming `X-Real-IP` / `CF-Connecting-IP` value and write the authenticated client address itself. Set `MIROFISH_TRUSTED_CLIENT_IP_HEADER` to that edge-owned header on Web, and inject the same non-public `MIROFISH_RECOVERY_CLIENT_PROOF_SECRET` into Web and API. Never trust a browser-provided forwarding header.

Both staging and production require `AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY` as strict standard base64 that decodes to exactly 32 bytes. The API has no legacy raw-key fallback: a missing production key or any malformed/wrong-length supplied key fails startup. Run `authrecovery.NewDeliveryDispatcher` with a unique worker id and continuously call `DispatchOne`; every returned error must increment a stable metric and produce a redacted structured log. Drain queued/processing recovery outbox rows before rotating this key unless multi-key decryption has been deployed.

## Start and readiness

```bash
docker compose -f infra/docker-compose.yml -f infra/compose.production.yml up -d
MIROFISH_COMPOSE_OVERRIDE=infra/compose.production.yml infra/scripts/check-compose-health.sh
```

`schema-init` now rejects numbering gaps, applies migrations in filename order, and records checksum plus applied/baselined state in `mirofish_schema_migrations`. Every startup revalidates multi-object completion sentinels for recorded migrations and requires the ledger count to exactly match the on-disk migration set. A changed checksum or incomplete sentinel fails closed. MAIN-100 must keep API startup dependent on successful schema initialization and verify the ledger reaches the current maximum migration before serving traffic.

Live and browser fixtures must never run against the runtime `mirofish` database. Use `infra/scripts/run-live-test-stack.sh -- <command>` (or `--app` when API/Web are required). The runner creates a unique Compose project, `mirofish_test_*` database, `mirofish.live_test=on` database marker, ports and volumes, then always destroys them with `down -v`. Go/Python/Web fixture guards reject the runtime database or a missing marker before fixture writes.

Migration `0010_auth_recovery_privilege_convergence` is a security convergence and has no privilege-widening SQL rollback. Rolling it back by granting direct sensitive-table access would recreate the vulnerability it closes. A production rollback therefore requires restoring the pre-upgrade full database snapshot into an isolated target, verifying its manifest/content hashes, and atomically rolling the application back with that database. Do not run the older `0009` rollback after `0010`.

Enable the standalone Prometheus target and alert rules with `--profile monitoring`. Route Prometheus alerts to the platform's managed Alertmanager; receiver credentials must stay in the platform secret manager.

## Backup and restore drill

The operational target is RPO 24 hours and RTO 4 hours until a managed Postgres PITR/object-versioning policy establishes stricter values. Every backup contains a custom-format Postgres dump, a MinIO object archive, a metadata manifest, and SHA-256 checksums.

```bash
export BACKUP_ROOT=/secure/mirofish-backups
export MIROFISH_COMPOSE_OVERRIDE=infra/compose.staging.yml
infra/scripts/backup-postgres-minio.sh

# Only against an isolated disposable staging compose project.
export RESTORE_DRILL_DISPOSABLE=1
infra/scripts/verify-backup-restore.sh
```

`restore-postgres-minio.sh` refuses production targets and requires both `RESTORE_CONFIRM=destroy-disposable-state` and `RESTORE_DRILL_DISPOSABLE=1`. Before restoration it terminates connections, drops the disposable database, and recreates it, proving the dump is sufficient rather than overlaying existing state. Backup preserves ACLs and captures canonical SHA-256 content hashes and counts for every user table both before and after `pg_dump`, refusing a drifting source. After restore it recomputes all table counts/content hashes, compares the anonymized object inventory, then authenticates over TCP as `APP_DATABASE_USER` to exercise `app_set_tenant_context`, an RLS-protected `projects` SELECT, and zero direct DML privilege on the four recovery-sensitive tables.

## Restart recovery

Run `infra/scripts/run-compose-recovery.sh` on staging after deploy and after stateful service upgrades. It verifies persisted sessions, CSRF, tenant denial, session rotation/revocation, password revocation, and Temporal recovery. Do not run its disposable fixture against production.

The current base `worker-readiness` container is unhealthy because its central task-queue probe is not aligned with all standalone workers. MAIN-100 must add the standalone `legacy-import` queue and final reviewer/character queues to the central readiness contract, then require readiness to become healthy before release. These overrides intentionally do not modify the central worker or base readiness script.

## Privacy and incident response

Only emit request/run identifiers, tenant/project identifiers, hashed user identifiers, status, duration and stable error codes. Never log tokens, cookies, credentials, object keys, prompts, provider responses, source text, drafts or manuscripts. Pipe diagnostic output through `infra/scripts/redact-compose-diagnostics.sh` before attaching it to an incident.

For suspected tenant leakage, disable the affected route, preserve sanitized audit evidence, validate the app-role RLS path, rotate exposed credentials, and notify affected tenants. For provider outages, mark provider health unavailable and fail requests explicitly; do not synthesize success.

## Legacy import cutover

The override starts a dedicated `legacy-import-worker` on `LEGACY_IMPORT_TASK_QUEUE`. Before cutover, run CLI `inspect`, `plan`, `apply --execute`, and `verify`, archive the sanitized report, stop legacy writes, repeat `inspect` to prove a stable source fingerprint, then perform final apply/verify. Rollback is allowed only while the importer proves every imported row is unchanged and has no later references.
