from __future__ import annotations

from mirofish_agents.legacy_import.completion import (
    has_unresolved_families,
    unresolved_reason_codes,
)
from mirofish_agents.legacy_import.models import FamilyPlan


def test_approved_unsupported_is_complete_but_remains_visible() -> None:
    family = FamilyPlan(
        "worldline",
        unsupported_count=3,
        reason_codes=["APPROVED_LEGACY_MULTI_BRANCH_UNSUPPORTED"],
    )

    assert not has_unresolved_families({"worldline": family})
    assert unresolved_reason_codes({"worldline": family}) == []
    assert family.public_dict()["unsupported"] == 3
    assert family.public_dict()["reason_codes"] == [
        "APPROVED_LEGACY_MULTI_BRANCH_UNSUPPORTED"
    ]


def test_unknown_unsupported_remains_partial() -> None:
    family = FamilyPlan(
        "writer",
        unsupported_count=1,
        reason_codes=["UNKNOWN_WRITER_HISTORY_UNSUPPORTED"],
    )

    assert has_unresolved_families({"writer": family})
    assert unresolved_reason_codes({"writer": family}) == [
        "UNKNOWN_WRITER_HISTORY_UNSUPPORTED"
    ]


def test_unsupported_without_reason_and_deferred_remain_partial() -> None:
    unsupported = FamilyPlan("source", unsupported_count=1)
    deferred = FamilyPlan("graph", deferred_count=1)

    families = {"source": unsupported, "graph": deferred}
    assert has_unresolved_families(families)
    assert unresolved_reason_codes(families) == [
        "DEFERRED_RECORDS_REMAIN",
        "UNAPPROVED_UNSUPPORTED_RECORDS",
    ]
