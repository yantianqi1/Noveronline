# Postgres SaaS Schema

This directory contains the target SaaS Postgres schema baseline for Phase 3.
It is intentionally separate from the current FastAPI/SQLite Alembic chain:
the compatibility backend keeps running on SQLite while the Go control plane,
Temporal workers, and RLS-backed SaaS data model are introduced.

Apply order:

```bash
psql "$DATABASE_URL" -f infra/postgres/migrations/0001_core_saas.sql
```

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
