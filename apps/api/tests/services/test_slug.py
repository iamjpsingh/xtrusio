"""Unit tests for slug helpers — pure functions, no DB."""

from __future__ import annotations

import pytest
from xtrusio_api.services.slug import slugify, unique_slug_from_taken


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Acme Corp", "acme-corp"),
        ("  Acme  Corp  ", "acme-corp"),
        ("ACME!!! Corp™", "acme-corp"),
        ("Über Glühwein", "uber-gluhwein"),
        (
            "123 Numbers Then Letters",
            "n123-numbers-then-letters",
        ),  # leading digit forbidden by schema regex
        ("------", "tenant"),  # all hyphens stripped → fallback
        ("a", "tenant-a"),  # below min length 3, padded by fallback
        ("x" * 200, "x" * 64),  # truncated to schema max
    ],
)
def test_slugify_known_cases(name: str, expected: str) -> None:
    assert slugify(name) == expected


def test_unique_slug_no_collision() -> None:
    assert unique_slug_from_taken("acme", taken=set()) == "acme"


def test_unique_slug_first_collision() -> None:
    assert unique_slug_from_taken("acme", taken={"acme"}) == "acme-2"


def test_unique_slug_multiple_collisions() -> None:
    assert unique_slug_from_taken("acme", taken={"acme", "acme-2", "acme-3"}) == "acme-4"
