#!/bin/sh
set -eu

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${APP_DATABASE_USER:?APP_DATABASE_USER is required}"
: "${APP_DATABASE_PASSWORD:?APP_DATABASE_PASSWORD is required}"

export PGPASSWORD="$POSTGRES_PASSWORD"
psql -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL' >/dev/null
CREATE TABLE IF NOT EXISTS mirofish_schema_migrations (
  version TEXT PRIMARY KEY,
  checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  execution_kind TEXT NOT NULL CHECK (execution_kind IN ('applied', 'baselined'))
);
REVOKE ALL ON mirofish_schema_migrations FROM PUBLIC;
SQL

migration_marker_present() {
  case "$1" in
    0001_*) marker="
      4 = (SELECT count(*) FROM pg_class WHERE relname IN ('projects','workflow_runs','assets','writer_runs') AND relkind = 'r')
      AND to_regprocedure('app_set_tenant_context(uuid,uuid,boolean)') IS NOT NULL
      AND 4 = (SELECT count(*) FROM pg_class WHERE relname IN ('source_files','entities','assets','writer_runs') AND relrowsecurity AND relforcerowsecurity)" ;;
    0002_*) marker="
      to_regclass('public.asset_embeddings') IS NOT NULL
      AND to_regclass('public.idx_global_search_index_search_vector') IS NOT NULL
      AND to_regclass('public.idx_asset_embeddings_reindex_batch') IS NOT NULL
      AND EXISTS (SELECT 1 FROM pg_class WHERE relname = 'asset_embeddings' AND relrowsecurity AND relforcerowsecurity)" ;;
    0003_*) marker="
      2 = (SELECT count(*) FROM pg_class WHERE relname IN ('llm_quota_policies','llm_quota_reservations') AND relkind = 'r')
      AND to_regclass('public.idx_llm_quota_policies_scope') IS NOT NULL
      AND 2 = (SELECT count(*) FROM pg_class WHERE relname IN ('llm_quota_policies','llm_quota_reservations') AND relrowsecurity AND relforcerowsecurity)" ;;
    0004_*) marker="
      5 = (SELECT count(*) FROM pg_class WHERE relname IN ('chapters','scenes','outline_versions','book_plans','book_run_events') AND relkind = 'r')
      AND 5 = (SELECT count(*) FROM pg_class WHERE relname IN ('chapters','scenes','outline_versions','book_plans','book_run_events') AND relrowsecurity AND relforcerowsecurity)
      AND EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_outline_versions_immutable' AND NOT tgisinternal)" ;;
    0005_*) marker="
      4 = (SELECT count(*) FROM pg_class WHERE relname IN ('manuscript_block_versions','manuscript_exports','writer_command_runs','writer_dedup_patterns') AND relkind = 'r')
      AND 4 = (SELECT count(*) FROM pg_class WHERE relname IN ('manuscript_block_versions','manuscript_exports','writer_command_runs','writer_dedup_patterns') AND relrowsecurity AND relforcerowsecurity)
      AND EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'manuscript_block_versions_immutable' AND NOT tgisinternal)" ;;
    0006_*) marker="
      4 = (SELECT count(*) FROM pg_class WHERE relname IN ('collaboration_invitations','collaboration_delivery_attempts','password_reset_tokens','password_reset_delivery_attempts') AND relkind = 'r')
      AND 2 = (SELECT count(*) FROM pg_class WHERE relname IN ('collaboration_invitations','collaboration_delivery_attempts') AND relrowsecurity AND relforcerowsecurity)
      AND to_regprocedure('collaboration_invitation_tenant_for_token(text)') IS NOT NULL" ;;
    0007_*) marker="
      to_regclass('public.auth_abuse_rate_limits') IS NOT NULL
      AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'llm_models' AND column_name = 'enabled')
      AND 6 = (SELECT count(*) FROM pg_constraint WHERE conname IN ('writer_runs_scope_key','writer_drafts_scope_key','manuscript_blocks_source_writer_run_scope_fk','manuscript_blocks_source_draft_scope_fk','collaboration_invitations_tenant_invitation_key','collaboration_delivery_attempts_invitation_scope_fk'))" ;;
    0008_*) marker="
      to_regclass('public.chapters_project_active_order_key') IS NOT NULL
      AND to_regclass('public.scenes_chapter_active_order_key') IS NOT NULL
      AND 6 = (SELECT count(*) FROM pg_constraint WHERE conname IN ('manuscript_blocks_location_check','manuscript_blocks_chapter_fk','manuscript_blocks_scene_fk','manuscript_block_versions_location_check','manuscript_block_versions_chapter_fk','manuscript_block_versions_scene_fk') AND convalidated)" ;;
    0009_*) marker="to_regclass('public.password_reset_delivery_outbox') IS NOT NULL
      AND EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'auth_recovery_complete')
      AND NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE grantee = 'mirofish_app'
          AND table_name IN ('password_reset_tokens','password_reset_delivery_attempts','password_reset_delivery_outbox','auth_security_audit_logs')
      )
      AND 4 = (
        SELECT count(*) FROM pg_class
        WHERE relname IN ('password_reset_tokens','password_reset_delivery_attempts','password_reset_delivery_outbox','auth_security_audit_logs')
          AND relrowsecurity AND relforcerowsecurity
      )
      AND 4 = (
        SELECT count(*) FROM pg_constraint
        WHERE conname IN ('manuscript_blocks_source_writer_run_scope_fk','manuscript_blocks_source_draft_scope_fk','manuscript_block_versions_source_writer_run_scope_fk','manuscript_block_versions_source_draft_scope_fk')
          AND confdeltype = 'n'
      )" ;;
    0010_*) marker="
      5 = (SELECT count(*) FROM pg_proc WHERE oid IN (
        to_regprocedure('auth_recovery_request(text,text,bytea,text,timestamptz)'),
        to_regprocedure('auth_recovery_claim_delivery(text,integer)'),
        to_regprocedure('auth_recovery_finish_delivery(uuid,text,text,text,text,timestamptz)'),
        to_regprocedure('auth_recovery_complete(text,text,timestamptz,text)'),
        to_regprocedure('auth_recovery_expire(timestamptz)')
      ) AND prosecdef)
      AND NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE grantee IN ('PUBLIC','mirofish_app') AND table_schema = 'public'
          AND table_name IN ('password_reset_tokens','password_reset_delivery_attempts','password_reset_delivery_outbox','auth_security_audit_logs')
      )
      AND has_function_privilege('mirofish_app', 'auth_recovery_request(text,text,bytea,text,timestamptz)', 'EXECUTE')
      AND has_function_privilege('mirofish_app', 'auth_recovery_complete(text,text,timestamptz,text)', 'EXECUTE')" ;;
    0011_*) marker="
      to_regclass('public.legacy_artifact_imports') IS NOT NULL
      AND to_regclass('public.idx_legacy_artifact_imports_import_status') IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM pg_class
        WHERE relname = 'legacy_artifact_imports' AND relrowsecurity AND relforcerowsecurity
      )
      AND EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'legacy_artifact_imports'
          AND policyname = 'tenant_isolation_legacy_artifact_imports'
      )
      AND has_table_privilege('mirofish_app', 'legacy_artifact_imports', 'SELECT,INSERT,UPDATE,DELETE')
      AND NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE grantee = 'PUBLIC' AND table_schema = 'public'
          AND table_name = 'legacy_artifact_imports'
      )" ;;
    0012_*) marker="
      EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'legacy_artifact_imports'
          AND column_name = 'created_version_id'
      )
      AND EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'legacy_artifact_imports_created_version_id_check'
      )" ;;
    0013_*) marker="
      EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'legacy_artifact_imports_version_ownership_check'
          AND convalidated
      )" ;;
    0014_*) marker="
      to_regclass('public.llm_platform_module_defaults') IS NOT NULL
      AND to_regclass('public.llm_module_bindings_tenant_default_key') IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM pg_class
        WHERE relname = 'llm_platform_module_defaults'
          AND relrowsecurity AND relforcerowsecurity
      )
      AND 3 = (
        SELECT count(*) FROM pg_policies
        WHERE schemaname = 'public'
          AND (tablename, policyname) IN (
            ('llm_channels', 'platform_select_llm_channels'),
            ('llm_models', 'platform_select_llm_models'),
            ('llm_platform_module_defaults', 'select_llm_platform_module_defaults')
          )
      )
      AND to_regprocedure('enforce_llm_platform_default_target()') IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_llm_platform_default_target' AND NOT tgisinternal
      )
      AND has_table_privilege('mirofish_app', 'llm_platform_module_defaults', 'SELECT')
	      AND NOT has_table_privilege('mirofish_app', 'llm_platform_module_defaults', 'INSERT')
	      AND NOT has_table_privilege('mirofish_app', 'llm_platform_module_defaults', 'UPDATE')
	      AND NOT has_table_privilege('mirofish_app', 'llm_platform_module_defaults', 'DELETE')" ;;
	    0015_*) marker="
	      EXISTS (
	        SELECT 1 FROM information_schema.columns
	        WHERE table_schema = 'public'
	          AND table_name = 'tenant_memberships'
	          AND column_name = 'access_scope'
	          AND is_nullable = 'NO'
	      )
	      AND EXISTS (
	        SELECT 1 FROM pg_constraint
	        WHERE conname = 'tenant_memberships_access_scope_check'
	          AND convalidated
	      )
	      AND to_regclass('public.idx_tenant_memberships_user_scope') IS NOT NULL
	      AND EXISTS (
	        SELECT 1 FROM pg_policies
	        WHERE schemaname = 'public'
	          AND tablename = 'projects'
	          AND policyname = 'current_user_membership_select_projects'
	          AND qual LIKE '%access_scope%'
	          AND qual LIKE '%project_members%'
	      )" ;;
	    0016_*) marker="
	      to_regclass('public.workspace_membership_scope_backfill_audit') IS NOT NULL
	      AND EXISTS (
	        SELECT 1 FROM pg_constraint
	        WHERE conname = 'workspace_membership_scope_backfill_audit_check'
	          AND convalidated
	      )
	      AND NOT EXISTS (
	        SELECT 1 FROM information_schema.role_table_grants
	        WHERE grantee = 'mirofish_app'
	          AND table_schema = 'public'
	          AND table_name = 'workspace_membership_scope_backfill_audit'
	      )" ;;
	    0017_*) marker="
	      NOT EXISTS (
	        SELECT 1
	        FROM tenants AS tenant
	        WHERE NOT EXISTS (
	          SELECT 1
	          FROM llm_quota_policies AS policy
	          WHERE policy.tenant_id = tenant.tenant_id
	            AND policy.scope_type = 'tenant'
	            AND policy.enabled = TRUE
	        )
	      )" ;;
	    0018_*) marker="
	      to_regclass('public.project_asset_distillation_settings') IS NOT NULL
	      AND to_regclass('public.manuscript_asset_distillation_requests') IS NOT NULL
	      AND to_regclass('public.asset_candidate_proposals') IS NOT NULL
	      AND to_regclass('public.asset_candidate_evidence') IS NOT NULL
	      AND EXISTS (
	        SELECT 1 FROM pg_constraint
	        WHERE conname = 'manuscript_block_versions_snapshot_reason_check'
	          AND pg_get_constraintdef(oid) LIKE '%adopt%'
	      )
	      AND EXISTS (
	        SELECT 1 FROM pg_policies
	        WHERE schemaname = 'public'
	          AND tablename = 'asset_candidate_evidence'
	          AND policyname = 'tenant_isolation_asset_candidate_evidence'
	      )
	      AND NOT EXISTS (
	        SELECT 1 FROM information_schema.role_table_grants
	        WHERE grantee = 'mirofish_app'
	          AND table_schema = 'public'
	          AND table_name = 'asset_candidate_evidence'
	          AND privilege_type = 'DELETE'
	      )" ;;
	    0019_*) marker="
	      to_regclass('public.writer_threads') IS NOT NULL
	      AND to_regclass('public.writer_thread_messages') IS NOT NULL
	      AND to_regclass('public.writer_approvals') IS NOT NULL
	      AND EXISTS (
	        SELECT 1 FROM pg_constraint
	        WHERE conname = 'writer_runs_mode_check'
	          AND pg_get_constraintdef(oid) LIKE '%revise%'
	      )
	      AND EXISTS (
	        SELECT 1 FROM pg_policies
	        WHERE schemaname = 'public'
	          AND tablename = 'writer_threads'
	          AND policyname = 'tenant_isolation_writer_threads'
	      )
	      AND EXISTS (
	        SELECT 1 FROM pg_policies
	        WHERE schemaname = 'public'
	          AND tablename = 'writer_thread_messages'
	          AND policyname = 'tenant_isolation_writer_thread_messages'
	      )
	      AND NOT EXISTS (
	        SELECT 1 FROM information_schema.role_table_grants
	        WHERE grantee = 'mirofish_app'
	          AND table_schema = 'public'
	          AND table_name = 'writer_thread_messages'
	          AND privilege_type = 'DELETE'
	      )" ;;
	    0020_*) marker="
	      to_regclass('public.analysis_runs') IS NOT NULL
	      AND to_regclass('public.analysis_workspace_files') IS NOT NULL
	      AND to_regclass('public.analysis_candidates') IS NOT NULL
	      AND EXISTS (
	        SELECT 1 FROM pg_policies
	        WHERE schemaname = 'public'
	          AND tablename = 'analysis_runs'
	          AND policyname = 'tenant_isolation_analysis_runs'
	      )
	      AND EXISTS (
	        SELECT 1 FROM pg_policies
	        WHERE schemaname = 'public'
	          AND tablename = 'analysis_workspace_files'
	          AND policyname = 'tenant_isolation_analysis_workspace_files'
	      )
	      AND EXISTS (
	        SELECT 1 FROM pg_policies
	        WHERE schemaname = 'public'
	          AND tablename = 'analysis_candidates'
	          AND policyname = 'tenant_isolation_analysis_candidates'
	      )
	      AND 3 = (
	        SELECT count(*) FROM pg_class
	        WHERE relname IN ('analysis_runs','analysis_workspace_files','analysis_candidates')
	          AND relrowsecurity AND relforcerowsecurity
	      )" ;;
	    *) return 1 ;;
  esac
  [ "$(psql -At -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT $marker")" = "t" ]
}

expected_number=1
migration_count=0
for migration in /migrations/[0-9][0-9][0-9][0-9]_*.sql; do
  [ -f "$migration" ] || { echo "no numbered migrations found" >&2; exit 1; }
  version="$(basename "$migration" .sql)"
  sequence_text="${version%%_*}"
  sequence_number="$(printf '%s' "$sequence_text" | sed 's/^0*//')"
  [ -n "$sequence_number" ] || sequence_number=0
  [ "$sequence_number" -eq "$expected_number" ] || {
    echo "migration sequence gap: expected $(printf '%04d' "$expected_number"), found $sequence_text" >&2
    exit 1
  }
  expected_number=$((expected_number + 1))
  migration_count=$((migration_count + 1))
  checksum="$(sha256sum "$migration" | awk '{print $1}')"
  case "$version:$checksum" in
    *[!a-zA-Z0-9_.:-]*) echo "invalid migration identity" >&2; exit 1 ;;
  esac
  recorded="$(psql -At -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT checksum FROM mirofish_schema_migrations WHERE version = '$version'")"
  if [ -n "$recorded" ]; then
    [ "$recorded" = "$checksum" ] || { echo "migration checksum mismatch: $version" >&2; exit 1; }
    migration_marker_present "$version" || { echo "migration sentinel incomplete: $version" >&2; exit 1; }
    continue
  fi
  if migration_marker_present "$version"; then
    execution_kind=baselined
  else
    psql -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$migration" >/dev/null
    execution_kind=applied
  fi
  psql -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "INSERT INTO mirofish_schema_migrations(version, checksum, execution_kind) VALUES ('$version', '$checksum', '$execution_kind')" >/dev/null
done

ledger_count="$(psql -At -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT count(*) FROM mirofish_schema_migrations')"
[ "$ledger_count" -eq "$migration_count" ] || {
  echo "migration ledger mismatch: expected $migration_count entries, found $ledger_count" >&2
  exit 1
}

psql -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --set=app_database_user="$APP_DATABASE_USER" \
  --set=app_database_password="$APP_DATABASE_PASSWORD" <<'SQL' >/dev/null
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L IN ROLE mirofish_app',
  :'app_database_user',
  :'app_database_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'app_database_user'
)
\gexec
SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L',
  :'app_database_user',
  :'app_database_password'
)
\gexec
SELECT format('GRANT mirofish_app TO %I', :'app_database_user')
\gexec
SQL

echo "compose database schema and runtime role ready"
