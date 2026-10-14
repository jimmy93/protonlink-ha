"""Shared test fixtures for the Proton Link integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations in every test."""
    yield


@pytest.fixture(autouse=True)
def expected_lingering_timers():
    """The coordinator schedules a refresh timer; that is expected."""
    return True


@pytest.fixture
def fake_client():
    """Replace the cloud client with one that replays recorded fixtures."""
    from .test_setup import FakeClient

    with patch(
        "custom_components.protonlink.coordinator.ProtonLinkClient", FakeClient
    ) as mocked:
        yield mocked
