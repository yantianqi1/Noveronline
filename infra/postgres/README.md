# Postgres SaaS Schema

This directory contains the target SaaS Postgres schema baseline for Phase 3.
It is intentionally separate from the current FastAPI/SQLite Alembic chain:
the compatibility backend keeps running on SQLite while the Go control plane,
Temporal workers, and RLS-backed SaaS data model are introduced.

Shared, upgraded, staging, production, and compose databases must be migrated by
the checksum-ledger bootstrap only:

```bash
docker compose -f infra/docker-compose.yml run --rm schema-init
```

`schema-init` validates the contiguous migration set, verifies every recorded
SHA-256 checksum, applies only missing revisions in order, and checks the schema
sentinels before application startup. Never replay a raw revision on a database
that already contains the `mirofish_schema_migrations` ledger, and never apply
`0001_core_saas.sql` directly to a shared compose database.

Raw `0001_core_saas.sql` execution is permitted only for a deliberately fresh,
disposable database whose public schema is empty. Test harnesses must fail
closed when a non-empty database has no migration ledger.

Every request or worker transaction must set tenant context before touching
tenant-scoped tables:

```sql
BEGIN;
SELECT app_set_tenant_context(
  'tenant-uuid-here',
  'user-uuid-here',
  false
);
-- tenant-scoped queries here
COMMIT;
```

Do not grant bypass-RLS roles to application code. Service jobs still set an
explicit tenant and write audit logs.
