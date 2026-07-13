from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


APPROVED_UNSUPPORTED_REASON_CODES = frozenset(
    {
        "APPROVED_LEGACY_MULTI_BRANCH_UNSUPPORTED",
        "APPROVED_LEGACY_SOURCE_PATH_UNSUPPORTED",
        "APPROVED_PRIVATE_PREPARATION_STATE_UNSUPPORTED",
        "APPROVED_TRANSIENT_WRITER_EVENT_HISTORY_UNSUPPORTED",
    }
)


class FamilyCompletion(Protocol):
    deferred_count: int
    unsupported_count: int
    reason_codes: list[str]


def has_unresolved_families(families: Mapping[str, FamilyCompletion]) -> bool:
    return any(family_is_unresolved(family) for family in families.values())


def family_is_unresolved(family: FamilyCompletion) -> bool:
    if family.deferred_count:
        return True
    if not family.unsupported_count:
        return False
    unsupported_reasons = _unsupported_reasons(family)
    return not unsupported_reasons or not unsupported_reasons.issubset(
        APPROVED_UNSUPPORTED_REASON_CODES
    )


def unresolved_reason_codes(families: Mapping[str, FamilyCompletion]) -> list[str]:
    reasons: set[str] = set()
    for family in families.values():
        if family.deferred_count:
            deferred_reasons = set(family.reason_codes) - APPROVED_UNSUPPORTED_REASON_CODES
            reasons.update(deferred_reasons or {"DEFERRED_RECORDS_REMAIN"})
        if family.unsupported_count:
            unsupported_reasons = _unsupported_reasons(family)
            unresolved = unsupported_reasons - APPROVED_UNSUPPORTED_REASON_CODES
            if not unsupported_reasons:
                unresolved.add("UNAPPROVED_UNSUPPORTED_RECORDS")
            reasons.update(unresolved)
    return sorted(reasons)


def _unsupported_reasons(family: FamilyCompletion) -> set[str]:
    return {
        reason
        for reason in family.reason_codes
        if reason.startswith("APPROVED_") or reason.endswith("_UNSUPPORTED")
    }
