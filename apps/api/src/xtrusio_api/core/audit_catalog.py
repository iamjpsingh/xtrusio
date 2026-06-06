"""Event catalog — single source of truth mapping each audit ``action`` string
to a human-readable label + a filter category.

Pure data + helpers, NO I/O. The audit feed (`AuditEventOut` computed fields,
the `GET /api/audit/catalog` endpoint, and the `category` filter on both
audit-log list endpoints) all derive from this one table, so a new mutation's
action only needs registering here once.

Categories are declared up front — including the two reserved-empty future
ones (``auth`` for GoTrue login/logout/password, ``system`` for worker/job
runs) — so the filter dropdown is forward-ready and old/unknown rows stay
filterable via the ``other`` catch-all.
"""

from __future__ import annotations

# --- categories ------------------------------------------------------------
# (key, human label). Stable order = the order the filter dropdown renders.
# ``auth`` + ``system`` are reserved (no action maps to them yet — Slice C /
# GoTrue ingestion fills them later with zero schema churn). ``other`` is the
# catch-all for any legacy/unknown action so old rows remain filterable.
_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("roles", "Roles"),
    ("grants", "Role grants"),
    ("invites", "Invites"),
    ("members", "Members"),
    ("workspaces", "Workspaces"),
    ("users", "Platform users"),
    ("settings", "Settings"),
    ("auth", "Authentication"),
    ("system", "System"),
    ("other", "Other"),
)

# Catch-all category key for unknown/legacy actions.
_OTHER = "other"

# --- action -> (label, category) -------------------------------------------
# EVERY action string the codebase emits (existing + the ones the Slice A
# coverage backfill adds) must appear here. Labels are imperative/human.
_ACTIONS: dict[str, tuple[str, str]] = {
    # roles (platform + workspace role CRUD)
    "platform_role.create": ("Created platform role", "roles"),
    "platform_role.update": ("Updated platform role", "roles"),
    "platform_role.delete": ("Deleted platform role", "roles"),
    "workspace_role.create": ("Created workspace role", "roles"),
    "workspace_role.update": ("Updated workspace role", "roles"),
    "workspace_role.delete": ("Deleted workspace role", "roles"),
    # grants (role grant/revoke)
    "platform_role.grant": ("Granted platform role", "grants"),
    "platform_role.revoke": ("Revoked platform role", "grants"),
    "workspace_role.grant": ("Granted workspace role", "grants"),
    "workspace_role.revoke": ("Revoked workspace role", "grants"),
    # invites (platform + tenant invite create/revoke/accept)
    "platform_invite.create": ("Invited platform user", "invites"),
    "platform_invite.revoke": ("Revoked platform invite", "invites"),
    "platform_invite.accept": ("Accepted platform invite", "invites"),
    "tenant_invite.create": ("Invited workspace member", "invites"),
    "tenant_invite.revoke": ("Revoked workspace invite", "invites"),
    "tenant_invite.accept": ("Accepted workspace invite", "invites"),
    # workspaces
    "tenant.create": ("Created workspace", "workspaces"),
    # users (direct platform-user provisioning)
    "platform_user.create": ("Created platform user", "users"),
    # settings
    "platform.settings.updated": ("Updated platform settings", "settings"),
    "workspace.settings.updated": ("Updated workspace settings", "settings"),
}


def describe_action(action: str) -> tuple[str, str]:
    """Return ``(label, category)`` for an action string.

    Unknown action → a title-cased fallback label + the ``other`` category, so
    legacy/unrecognised rows still render and stay filterable.
    """
    known = _ACTIONS.get(action)
    if known is not None:
        return known
    return _fallback_label(action), _OTHER


def _fallback_label(action: str) -> str:
    """Title-case an unknown action into a passable label, e.g.
    ``foo_bar.baz`` -> ``Foo Bar Baz``."""
    cleaned = action.replace(".", " ").replace("_", " ").strip()
    if not cleaned:
        return "Unknown action"
    return cleaned.title()


def categories() -> list[tuple[str, str]]:
    """``[(key, label), ...]`` for the filter dropdown, in stable order."""
    return list(_CATEGORIES)


def actions() -> list[tuple[str, str, str]]:
    """``[(action, label, category), ...]`` for the full catalog, in the
    table's declaration order."""
    return [(action, label, cat) for action, (label, cat) in _ACTIONS.items()]


def actions_in_category(category: str) -> list[str]:
    """Action strings belonging to ``category``.

    Unknown category → ``[]`` (the caller treats that as "no rows": a
    well-formed but empty category, e.g. the reserved ``auth``/``system``,
    yields zero matches rather than disabling the filter). The list endpoints
    distinguish *unknown* from *empty* by checking membership in
    :func:`category_keys` first.
    """
    return [action for action, (_label, cat) in _ACTIONS.items() if cat == category]


def category_keys() -> frozenset[str]:
    """The set of valid category keys (declared in :func:`categories`)."""
    return frozenset(key for key, _label in _CATEGORIES)
