# Legacy Import Cutover

This contract covers the explicit migration of a legacy SQLite project into one SaaS tenant/project. The source database is always opened read-only. Reports contain counts, stable reason/error codes, hashes, and durations only; they must not contain original text, prompts, provider responses, credentials, absolute paths, or object keys.

## Family Decisions

| Legacy family | Target behavior |
| --- | --- |
| `project_artifacts` | Existing normalized legacy business tables continue to map to their structured SaaS targets. Every valid JSON payload is also preserved byte-for-byte in private object storage and recorded in `legacy_artifact_imports`; arbitrary JSON is never inserted into public `assets`. |
| `archive_sources` | Sanitized provenance is recorded in `legacy_artifact_imports`. Relative files explicitly authorized beneath `artifact_root` may be copied to private object storage. Absolute, missing, or unmapped machine-local paths are metadata-only and use `APPROVED_LEGACY_SOURCE_PATH_UNSUPPORTED`; raw paths are never persisted. |
| `entity_evidence` | Entity-owned rows map to SaaS `entity_evidence`. Rows explicitly owned by a Legacy relationship map to `relationship_events` using the resolved source/target entities and relationship type. Missing owners or unknown owner types remain deferred; they are never silently adopted as entity evidence. |
| `graph_meta` | Current legacy `project_id + key + value` rows describe one overwrite-only graph. They are aggregated into one deterministic imported snapshot. Conflicting duplicate keys fail closed. Nodes and edges are never presented as reconstructed historical snapshots. |
| `prepare_runs` and `prepared_agent_dossiers` | Public identity/profile fields become archived preparation and prepared-agent rows. Private profile/runtime/provider/memory/evidence state is not made runnable and uses `APPROVED_PRIVATE_PREPARATION_STATE_UNSUPPORTED`. |
| `writer_run_events` | Only ordered lifecycle/status/tool/count/error-code metadata becomes `workflow_events`. Text, arguments, results, tokens, prompts, responses, and error messages are discarded. |
| `writer_draft_events` | Draft/manuscript/version rows remain the content truth source. Transient event payload/history uses `APPROVED_TRANSIENT_WRITER_EVENT_HISTORY_UNSUPPORTED`. |
| metadata-only chapters | A deterministic `planned` chapter shell is created with no body and no manuscript block. Summary and outline metadata remain private chapter planning fields. |
| multi-branch runtime | The product remains one `current_world`; branch/runtime state uses `APPROVED_LEGACY_MULTI_BRANCH_UNSUPPORTED` and is never restored as runnable state. |

Approved unsupported rows remain visible in family counts and reason codes. They do not make an otherwise resolved report partial. Any deferred row, missing dependency, unknown `*_UNSUPPORTED` reason, object mismatch, target conflict, or privacy/RLS failure keeps the report partial or failed.

## Object Contract

Object keys are deterministic and private:

```text
projects/{project_id}/legacy-imports/{import_id}/{kind}/{source_key_hash}/{sha256}
```

`legacy_artifact_imports` stores tenant/project/import scope, hashed source identity/path, sanitized provenance, optional private object reference, SHA-256, byte size, media type, lifecycle status, ownership, and the exact object version created by the import. The table uses enabled and forced tenant RLS. No public API or report returns its object reference or version identifier.

The importer requires the standard object-storage endpoint, bucket, access key, secret key, SSL mode, and region contract. The private bucket must have object versioning enabled; rollback deletes only the exact version it verified, so a concurrent replacement survives. Missing version identifiers fail closed. Partial configuration fails closed; there is no environment credential fallback. Temporal execution also requires `LEGACY_IMPORT_SOURCE_ROOT`; source and artifact paths must resolve beneath that read-only root, and symlinks are rejected. Missing root configuration is an error, not an unrestricted local-path mode.

Apply verifies an existing deterministic object before reuse and records whether the import created it. The exact S3 version returned by PUT is persisted before visibility verification; an ownership-write failure triggers exact-version compensation, and a failed compensation retries durable ownership recording. Temporal and CLI apply, verify, and rollback bind to the exact source fingerprint and plan hash produced by plan; a changed source is rejected before any write. Verify re-reads every owned object version and checks size/SHA-256 plus the ledger row. Rollback rechecks and deletes only that owned version; pre-existing or later matching versions are retained. A mismatch or failed delete is recorded as an orphan/partial cleanup and never reported as successful rollback.

## Cutover Order

1. Run `inspect` and `plan`; archive the sanitized reports and source fingerprint.
2. Confirm the target tenant/project exists, is disposable or approved for cutover, and contains no conflicting current graph.
3. Run `apply --execute` with the app-role DSN and complete object-storage configuration.
4. Run `verify`; require complete status or only approved unsupported counts, cross-tenant invisibility, matching DB row hashes, and matching object hashes.
5. Stop legacy writes, repeat inspect/plan, and reject cutover if the source fingerprint changed unexpectedly.
6. Run the final apply/verify pair, then switch traffic.
7. For rollback, stop SaaS writes first, run guarded DB rollback, then object rollback. Any later reference, modified imported row, object mismatch, or cleanup failure blocks or leaves an explicit partial result.

Schema downgrade is a separate final step. `0011` rollback fails while `legacy_artifact_imports` contains any row; complete and verify the importer rollback first, then remove the empty ledger table. This preserves object ownership and prevents orphaning private MinIO data.

Upgrading an installation that used `0011` before exact object-version ownership was available is also fail closed. `0013` refuses active import-created rows that lack a version identifier; reconcile or roll back those imports before upgrade. Pending/orphaned rows require explicit exact-version reconciliation and are never repaired by guessing the current version.

If both the initial ownership write and exact-version delete compensation fail, ordinary retry never guesses ownership from the current object, even when the bytes match. An operator must obtain the original PUT version ID from private MinIO audit/version history and run `reconcile-version --execute` with the approved source fingerprint and plan hash. The command reads that exact version, verifies its size/SHA-256 against the frozen plan, and records ownership without returning the object key or version ID in its report. A subsequent bound apply/verify may then continue.

Migration order is `0001` through `0016_workspace_membership_scope_backfill`. Production startup must verify the complete checksum ledger, the `0011` table/index/RLS sentinel, the `0012` version-ownership column, the `0013` convergence constraint, the `0014` platform-default LLM sentinel, the `0015` workspace membership-scope sentinel, and the `0016` historical project-invitation backfill audit sentinel before serving traffic.
