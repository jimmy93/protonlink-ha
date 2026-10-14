"""Contract tests for pure logic: phone normalisation and GPS decoding."""

from __future__ import annotations

import pytest

from custom_components.protonlink.config_flow import normalise_mobile
from custom_components.protonlink.coordinator import _decode_position


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("60123456789", "60123456789"),
        ("+60123456789", "60123456789"),
        ("0123456789", "60123456789"),
        ("123456789", "60123456789"),
        ("60 12-345 6789", "60123456789"),
    ],
)
def test_normalise_mobile_accepts(raw, expected):
    assert normalise_mobile(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "hello", "12345", "60123", "00123456789012", "6012345678"]
)
def test_normalise_mobile_rejects(raw):
    assert normalise_mobile(raw) is None


def test_gps_decode_matches_known_location():
    """Raw arc-millisecond values decode to WGS-84 degrees."""
    lat, lon = _decode_position({"latitude": 10243839, "longitude": 366557025})
    assert lat == pytest.approx(2.845510, abs=1e-5)
    assert lon == pytest.approx(101.821395, abs=1e-5)


def test_gps_decode_rejects_null_island():
    """0/0 is the service's 'no fix' value, not a position off Ghana."""
    assert _decode_position({"latitude": 0, "longitude": 0}) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"latitude": "x", "longitude": "y"},
        {"latitude": 999999999999, "longitude": 0},
    ],
)
def test_gps_decode_rejects_bad_input(payload):
    assert _decode_position(payload) is None
