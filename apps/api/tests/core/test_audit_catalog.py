"""Unit tests for the event catalog (`core/audit_catalog.py`).

Pure data + helpers — no DB, no fixtures. Covers ``describe_action`` for known
actions and the unknown-action fallback, plus the category/action accessors and
the empty-category contract used by the list-endpoint filter.
"""

from __future__ import annotations

from xtrusio_api.core.audit_catalog import (
    actions,
    actions_in_category,
    categories,
    category_keys,
    describe_action,
)


def test_describe_action_known() -> None:
    label, category = describe_action("platform_role.grant")
    assert label == "Granted platform role"
    assert category == "grants"


def test_describe_action_every_known_action_resolves() -> None:
    # Every action in the catalog resolves to its declared (label, category) and
    # never falls through to "other".
    for action, label, category in actions():
        got_label, got_category = describe_action(action)
        assert got_label == label
        assert got_category == category
        assert got_category != "other"


def test_describe_action_unknown_falls_back_to_other() -> None:
    label, category = describe_action("totally_unknown.action")
    assert category == "other"
    # Title-cased fallback: dots/underscores -> spaces, Title Case.
    assert label == "Totally Unknown Action"


def test_describe_action_empty_string_fallback() -> None:
    label, category = describe_action("")
    assert category == "other"
    assert label == "Unknown action"


def test_categories_stable_and_include_reserved_and_other() -> None:
    keys = [k for k, _ in categories()]
    # Reserved-empty future categories + the catch-all are always present.
    for required in ("auth", "system", "other", "grants", "invites"):
        assert required in keys
    # Stable order (declaration order) — first is roles, last is other.
    assert keys[0] == "roles"
    assert keys[-1] == "other"


def test_category_keys_matches_categories() -> None:
    assert category_keys() == frozenset(k for k, _ in categories())


def test_actions_in_category_groups_correctly() -> None:
    grants = set(actions_in_category("grants"))
    assert grants == {
        "platform_role.grant",
        "platform_role.revoke",
        "workspace_role.grant",
        "workspace_role.revoke",
    }


def test_reserved_category_has_no_actions() -> None:
    # ``auth``/``system`` are declared but empty for now → the filter yields
    # zero rows (= ANY('{}')), it does NOT disable the filter.
    assert actions_in_category("auth") == []
    assert actions_in_category("system") == []


def test_unknown_category_has_no_actions() -> None:
    assert actions_in_category("does_not_exist") == []
