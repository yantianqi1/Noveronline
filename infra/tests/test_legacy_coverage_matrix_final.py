from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


MATRIX = Path(__file__).resolve().parents[2] / "docs" / "refactor-saas" / "18-legacy-coverage-matrix.md"
PROGRESS = Path(__file__).resolve().parents[2] / "docs" / "refactor-saas" / "24-current-development-progress.md"
ALLOWED = ("verified replacement", "verified", "non-restored", "blocked")
FORBIDDEN = re.compile(r"^(planned|implemented|in_progress|pending)(?:\b|:)")


def _status_rows() -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    in_status_table = False
    for number, line in enumerate(MATRIX.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|"):
            in_status_table = False
            continue
        if re.match(r"^\|[-:| ]+\|$", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        status = cells[-1]
        if status in {"状态", "Status"}:
            in_status_table = True
            continue
        if not in_status_table:
            continue
        if not any(status.startswith(value) for value in ALLOWED):
            if FORBIDDEN.match(status):
                raise AssertionError(f"line {number} retains forbidden coverage status: {status}")
            raise AssertionError(f"line {number} has no final coverage status: {status}")
        rows.append((number, cells[0], status))
    return rows


def test_final_coverage_matrix_has_only_final_statuses_and_exact_counts() -> None:
    rows = _status_rows()
    counts = Counter(
        next(value for value in ALLOWED if status.startswith(value))
        for _, _, status in rows
    )
    assert counts == {
        "verified": 90,
        "verified replacement": 25,
        "non-restored": 5,
        "blocked": 1,
    }
    encoded = MATRIX.read_text(encoding="utf-8")
    assert "`verified=90`" in encoded
    assert "`verified replacement=25`" in encoded
    assert "`non-restored=5`" in encoded
    assert "`blocked=1`" in encoded


def test_non_restored_rows_name_a_release_replacement_or_decision() -> None:
    for number, label, status in _status_rows():
        if not status.startswith("non-restored"):
            continue
        normalized = status.lower()
        assert "owner:" not in normalized, f"line {number} kept obsolete owner/wave state"
        assert any(term in normalized for term in ("replacement", "替代", "410", "outside this release")), (
            f"line {number} non-restored row has no explicit replacement/decision: {label}"
        )


def test_only_real_legacy_input_remains_blocked() -> None:
    blocked = [(label, status) for _, label, status in _status_rows() if status.startswith("blocked")]
    assert [label for label, _ in blocked] == ["Legacy import real cutover"]
    assert "non-empty selected legacy project source" in blocked[0][1]
    assert "correctly remains partial" in blocked[0][1]


def test_external_https_provider_certificate_records_full_sanitized_success_chain() -> None:
    statuses = {label: status for _, label, status in _status_rows()}
    status = statuses["external HTTPS provider release certificate"]
    assert status.startswith("verified:")
    for literal in (
        "`api.aiwanai.cc/v1`",
        "HTTP 200 from `/models`",
        "`gpt-5.5` present",
        "strict Seed external-provider tests passed (2/2)",
        "project binding",
        "encrypted credential resolution",
        "quota reservation/finalization",
        "2 correlated usage rows",
        "completed `llm_activity`",
        "private full-redaction trace",
        "JSON and tools probes returned HTTP 200",
        "formally opted in",
        "provider health returned HTTP 200",
        "26 non-embedding project module bindings",
        "public privacy scan",
        "does not claim every per-domain cluster/browser E2E",
    ):
        assert literal in status, f"external provider certificate omitted {literal!r}"
    for forbidden in ("api_key", "encrypted_api_key", "credential_ref", "sk-"):
        assert forbidden not in status, f"external provider certificate exposed private field marker {forbidden!r}"


def test_status_normalization_preserves_protocol_and_state_machine_identifiers() -> None:
    encoded = MATRIX.read_text(encoding="utf-8")
    required = (
        "LLM model sync ok/failed/pending counts",
        "explicit pending `events` contract",
        "server-side object upload API with pending-only write-status guard",
        "allows only `pending` / `uploaded` rows",
        "sanitized pending/completed/failed stage events",
        "pending uploads fail with `SOURCE_FILE_NOT_UPLOADED`",
        "sanitized `seed.stage.pending`",
        "pending `GET /v1/character-interactions/{interactionId}/events`",
    )
    for literal in required:
        assert literal in encoded, f"coverage normalization corrupted protocol literal: {literal}"

    corrupted = (
        "LLM model sync ok/failed/not restored in this release counts",
        "explicit not restored in this release `events` contract",
        "not restored in this release-only write-status guard",
        "allows only `not restored in this release` / `uploaded` rows",
        "`seed.stage.not restored in this release`",
        "not restored in this release uploads fail with `SOURCE_FILE_NOT_UPLOADED`",
    )
    for literal in corrupted:
        assert literal not in encoded, f"coverage matrix retains mechanically rewritten identifier: {literal}"


def test_writer_planning_coverage_names_security_ledgers_and_candidate_boundaries() -> None:
    encoded = MATRIX.read_text(encoding="utf-8")
    required = (
        "`POST /v1/projects/{projectId}/book-plans/{bookPlanId}/generations`",
        "`POST /v1/projects/{projectId}/manuscript-workspace/dedup-extractions`",
        "cookie CSRF",
        "invalid bearer",
        "`writer_book_planner` / `writer_dedup_extractor` LLM Facility binding",
        "quota reservation/finalization",
        "`usage_events`",
        "`llm_activity`",
        "private `agent_trace_events`",
        "book-plan 输出保持 `draft`",
        "dedup 输出保持 disabled `candidate`",
        "原 browser 功能/隐私证书已通过（1/1，18.8s）",
        "book workflow 到 `completed` 且计划保持 `draft` v2",
        "dedup workflow 到 `completed` 且模式保持 `candidate` / `enabled=false`",
        "2 条 planning `llm_activity` 均为 completed",
        "token 与 cost usage 均落盘",
        "full private traces 可审计且 public sentinel leak count = 0",
        "旧蓝色长页截图已撤销并删除",
        "fresh desktop/mobile browser evidence",
        "compose app-role `Admit -> Replay -> Compensate` live contract 同样 PASS",
    )
    for literal in required:
        assert literal in encoded, f"writer-planning coverage omitted required evidence: {literal}"
    assert "/tmp/p6-writer-planning-certification" not in encoded
    assert "本轮没有当前 live/browser 执行证书" not in encoded


def test_production_ops_rows_match_current_verified_evidence_without_stale_non_restored_claims() -> None:
    statuses = {label: status for _, label, status in _status_rows()}
    expected = {
        "配额/计费": (
            "verified:",
            ("provider_call_id", "billing_ready", "pricing_unavailable", "app-role PostgreSQL live quota coverage"),
        ),
        "文件对象存储": (
            "verified replacement:",
            ("enable bucket versioning", "metadata-only `/readyz`", "object SHA-256 inventory", "destructive disposable restore"),
        ),
        "Agent 可恢复": (
            "verified:",
            ("current compose recovery certificate", "persistent volumes", "queued workflow completion after poller recovery"),
        ),
        "审计": (
            "verified:",
            ("Asset/Archive", "Story Graph", "Character", "Writer", "collaboration/invitation", "LLM provider-health"),
        ),
    }
    for label, (prefix, evidence) in expected.items():
        status = statuses[label]
        assert status.startswith(prefix), f"{label} lost its current final status: {status}"
        for literal in evidence:
            assert literal in status, f"{label} omitted current evidence {literal!r}"

    stale_claims = (
        "billing aggregation not restored in this release",
        "production object storage hardening remain not restored in this release",
        "live cluster recovery semantics not restored in this release",
        "broader audit coverage not restored in this release",
    )
    for literal in stale_claims:
        assert literal not in MATRIX.read_text(encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    assert "compose health/restart/recovery/backup+restore/observability/alerts | `verified_current`" in progress
