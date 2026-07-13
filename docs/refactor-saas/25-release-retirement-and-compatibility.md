# Release Retirement and Compatibility Decisions

This document is the authoritative Phase 7 decision record for the current SaaS release.
Compatibility source may remain in `backend/` for import/reference tests, but the production
runtime is only `apps/*` plus `infra/*`. The root legacy `frontend/` has been deleted; only
`apps/web` may provide a Web surface. A retained backend source file is not a retained public
SaaS capability.

## Identity

| Legacy or deferred capability | Release decision | Supported replacement |
|---|---|---|
| Self-service signup | Not restored in this release | Administrators provision password accounts; users use production password login and password recovery. |
| OAuth login | Not restored in this release | Admin-provisioned password accounts and recovery. |
| MFA enrollment/challenge | Not restored in this release | Admin-provisioned password accounts and recovery. |

The release does not expose `POST /v1/auth/signup`, `/v1/auth/oauth*`, or `/v1/auth/mfa*`.
These are explicit product decisions, not silent missing implementations.

## Writer Compatibility

| Exact legacy API | Release decision | Supported replacement |
|---|---|---|
| `GET /api/v2/chapter-context/options` | Legacy-only; not mounted by SaaS | Writer tool references and tenant/project-scoped context loaders. |
| `POST /api/v2/chapter-context/builds` | Legacy-only; not mounted by SaaS | Writer tool references and workspace context assembly. |
| `POST /api/v2/drafts` | Legacy-only; not mounted by SaaS | Writer workspace run and candidate draft lifecycle. |
| `POST /api/v2/drafts/{draftId}/events` | Legacy-only; not mounted by SaaS | Writer workflow events and reviewer issue actions. |
| `POST /api/v2/drafts/{draftId}/revisions` | Legacy-only; not mounted by SaaS | Candidate drafts plus explicit review/adoption. |
| `POST /api/v2/drafts/{draftId}/revisions/{revisionId}/events` | Legacy-only; not mounted by SaaS | Writer workflow/reviewer events. |
| `POST /api/v2/drafts/{draftId}/finalizations` | Legacy-only; not mounted by SaaS | Explicit draft adoption into manuscript workspace. |
| `POST /api/writer-agent/world-update` | Retired; not mounted by SaaS | Candidate world changes followed by explicit user adoption. |

The production API must return ordinary `404 NOT_FOUND` for these unmounted compatibility
paths. It must not proxy to FastAPI, read legacy local files, or fabricate compatibility success.

## Worldline

The product has exactly one `current_world`. Multi-branch creation and comparison are not
restored. Legacy compatibility endpoints
`GET /api/v2/worldlines/sessions/{sessionId}/branches` and
`GET /api/v2/worldlines/sessions/{sessionId}/comparison` return `410 Gone`; SaaS does not
mount branch/comparison routes and rejects branch/comparison payload fields.

## LLM Facility

The module registry is the versioned static SaaS registry for this release. Dynamic registry
administration is deferred and is not required for release completion. Activity and usage use
polling/read APIs; realtime activity push is deferred. Neither decision permits provider
credentials from environment variables: every provider call still requires a tenant/project
module binding and encrypted credential resolved through LLM Facility.

## Runtime and Data Truth

- `backend/` FastAPI is not a production service, build context, mount, reverse-proxy target,
  or fallback runtime. The retired root `frontend/` must remain absent and must never be
  recreated as a compatibility surface.
- Postgres is the SaaS business-data truth source. S3-compatible object storage is the binary
  object truth source. Runtime reads do not fall back to legacy SQLite, `backend/data`, uploads,
  project artifact directories, or arbitrary local files.
- `LLM_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, legacy model variables, and equivalent
  single-provider environment fallback are forbidden in base, staging, and production runtime.
- Legacy SQLite/project artifacts are accepted only by the explicit read-only Legacy Import
  workflow. Partial or empty imports remain partial and never become success.

## Remaining External Gates

This decision record does not claim an external-provider certificate or a real-data cutover.
Release-wide completion still requires the separately tracked explicit external HTTPS provider
success and a non-empty selected legacy source for real cutover/verify/rollback evidence.
