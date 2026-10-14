"""Integration tests: set the component up inside a real Home Assistant.

The cloud client is replaced with a fake that replays the recorded fixtures,
so these tests exercise the genuine Home Assistant plumbing: config entry
setup, the coordinator's normalisation, entity creation and entity state.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.protonlink.const import DOMAIN

from .conftest import load_fixture

ENTRY_DATA = {
    "mobile_phone": "60123456789",
    CONF_PASSWORD: "hunter2",
    "device_id": "067ecdf9a1b2c3d4e5f60718293a4b5c",
}

VIN = "PL1DG2FVRMG000000"


class FakeClient:
    """Replays recorded fixtures through the client interface."""

    def __init__(self, session, mobile, password, device_id) -> None:
        self.session = session
        self.user_id = None

    async def async_login(self) -> None:
        self.user_id = "100000000000000000000000"

    async def async_get_vehicles(self):
        return load_fixture("vehicles.json")["data"]

    async def async_get_vehicle_state(self, vin):
        return load_fixture("reset_enable.json")["data"]

    async def async_get_parking_status(self, vin):
        return load_fixture("parking_status.json")["data"]

    async def async_get_flow(self, vin):
        return load_fixture("flow.json")["data"]

    async def async_get_electronic_fences(self, vin):
        return load_fixture("electronic_fence.json")["data"]

    async def async_get_capabilities(self, vin):
        return load_fixture("capabilities.json")["data"]

    async def async_get_trips(self, vin, **kwargs):
        return load_fixture("log_list.json")["data"]

    async def async_get_track(self, vin, **kwargs):
        return []


@pytest.fixture
def fake_client():
    with patch(
        "custom_components.protonlink.coordinator.ProtonLinkClient", FakeClient
    ) as mocked:
        yield mocked


async def _setup(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="60123456789")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state_of(hass, key: str):
    """Look an entity up by unique_id suffix, then return its state object."""
    registry = er.async_get(hass)
    for entity in registry.entities.values():
        if entity.platform == DOMAIN and entity.unique_id == f"{VIN}_{key}":
            return hass.states.get(entity.entity_id)
    return None


async def test_setup_entry_creates_the_expected_entities(hass, fake_client):
    """A valid entry loads and produces one entity per description."""
    entry = await _setup(hass)

    registry = er.async_get(hass)
    uids = {
        e.unique_id for e in registry.entities.values() if e.platform == DOMAIN
    }

    for key in (
        "vin",
        "model",
        "odometer",
        "fuel_level",
        "engine_state",
        "trips_recorded",
        "location",
        "parked",
        "immobilized",
    ):
        assert f"{VIN}_{key}" in uids, f"missing entity {key}"

    assert entry.state is ConfigEntryState.LOADED


async def test_odometer_and_fuel_come_from_the_trip_log(hass, fake_client):
    """The gated realtimeData endpoint is bypassed; values come from trips."""
    await _setup(hass)

    odometer = _state_of(hass, "odometer")
    assert odometer is not None
    assert float(odometer.state) == pytest.approx(114834.2, abs=0.1)

    fuel = _state_of(hass, "fuel_level")
    assert float(fuel.state) == pytest.approx(27.5, abs=0.1)


async def test_state_vector_is_exposed(hass, fake_client):
    """journeyLog/resetEnable is decoded into readable states."""
    await _setup(hass)

    assert _state_of(hass, "engine_state").state == "off"
    assert _state_of(hass, "power_mode").state == "off"
    assert _state_of(hass, "trip_log_state").state == "enabled"
    assert _state_of(hass, "parked").state == "on"


async def test_device_tracker_uses_decoded_wgs84(hass, fake_client):
    """Coordinates are decoded from arc-milliseconds, not passed through raw."""
    await _setup(hass)

    tracker = _state_of(hass, "location")
    assert tracker is not None
    lat = tracker.attributes["latitude"]
    lon = tracker.attributes["longitude"]
    # Sanity: inside Malaysia, and nowhere near the raw integer values.
    assert 1.0 < lat < 7.5
    assert 99.5 < lon < 119.5


async def test_vehicle_identity_and_diagnostics(hass, fake_client):
    await _setup(hass)

    assert _state_of(hass, "vin").state == VIN
    assert _state_of(hass, "model").state == "X50"
    # Data allowance is reported in KiB and must be converted to GiB.
    remaining = _state_of(hass, "data_remaining")
    assert remaining is not None
    assert 0 < float(remaining.state) < 100


async def test_every_entity_shows_its_own_name(hass, fake_client):
    """Regression: entities must not all collapse to the device name.

    Without ``has_entity_name`` the translation keys are never consulted and
    every entity falls back to the device name, so the device page showed a
    column of identical rows all reading "X50".
    """
    await _setup(hass)

    expectations = {
        "odometer": "Odometer",
        "fuel_level": "Fuel level",
        "last_trip_distance": "Last trip distance",
        "last_trip_avg_speed": "Last trip average speed",
        "trips_recorded": "Trips recorded",
        "engine_state": "Engine",
        "data_remaining": "Data allowance remaining",
        "vin": "VIN",
        "parked": "Parked",
        "immobilized": "Immobilised",
    }

    seen: dict[str, str] = {}
    for key, label in expectations.items():
        state = _state_of(hass, key)
        assert state is not None, f"entity {key!r} was never created"
        friendly = state.attributes.get("friendly_name")
        assert friendly, f"entity {key!r} has no friendly_name"
        assert label in friendly, (
            f"entity {key!r} is shown as {friendly!r}; expected label {label!r}"
        )
        assert friendly not in seen, (
            f"entities {seen.get(friendly)!r} and {key!r} share the name {friendly!r}"
        )
        seen[friendly] = key


async def test_all_platforms_attach_to_one_named_device(hass, fake_client):
    """Sensors, binary sensors and the tracker all hang off the car."""
    await _setup(hass)

    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    all_entities = {
        e.unique_id for e in registry.entities.values() if e.platform == DOMAIN
    }
    assert all_entities, "no entities were registered"

    # Every entity must point at one and the same device, and that device must
    # be the car.  Look the device up by id -- stable across HA versions, and
    # avoids iterating the registry (deprecated in newer releases).
    device_ids = {
        e.device_id
        for e in registry.entities.values()
        if e.platform == DOMAIN
    }
    assert None not in device_ids, "some entities are orphaned (no device)"
    assert len(device_ids) == 1, f"entities split across devices: {device_ids}"

    device = device_registry.async_get(device_ids.pop())
    assert device is not None
    assert (DOMAIN, VIN) in device.identifiers
    assert device.name == "Proton X50"
    assert device.manufacturer == "Proton"
    assert device.serial_number == VIN

    linked = {
        e.unique_id
        for e in registry.entities.values()
        if e.platform == DOMAIN and e.device_id == device.id
    }
    assert linked == all_entities, (
        f"orphaned entities not linked to the device: {sorted(all_entities - linked)}"
    )


async def test_device_tracker_takes_the_vehicle_name(hass, fake_client):
    """The tracker is labelled with the car's own name plus a role."""
    await _setup(hass)

    state = _state_of(hass, "location")
    assert state is not None
    assert state.attributes["friendly_name"] == "Proton X50 Location"


async def test_unload_entry_closes_cleanly(hass, fake_client):
    entry = await _setup(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_fails_gracefully_when_service_is_down(hass):
    """A failing API yields a retryable setup failure, not a crash."""

    class BrokenClient(FakeClient):
        async def async_login(self) -> None:
            from custom_components.protonlink.api import ProtonLinkApiError

            raise ProtonLinkApiError("network", "connection refused", "login")

    with patch(
        "custom_components.protonlink.coordinator.ProtonLinkClient", BrokenClient
    ):
        entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="60123456789")
        entry.add_to_hass(hass)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
