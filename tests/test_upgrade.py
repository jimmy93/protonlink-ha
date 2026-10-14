"""Upgrade-path test: does an existing install's entity_id get cleaned up?

Jimmy's live install (v1.0.0) has four orphaned entities whose entity_ids were
derived from ``platform_name + unique_id`` because ``entity_namespace`` is set
on the platform, e.g.:

    binary_sensor.protonlink_pl1dg2fvrmg014771_immobilized

This test registers exactly that legacy state, then loads the *current* code and
reports whether Home Assistant rewrites the entity_id to the new suggestion.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.protonlink.const import DOMAIN

from .test_setup import VIN, _setup

LEGACY = {
    f"{VIN}_immobilized": (
        "binary_sensor",
        "binary_sensor.protonlink_pl1dg2fvrmg014771_immobilized",
    ),
    f"{VIN}_parked": (
        "binary_sensor",
        "binary_sensor.protonlink_pl1dg2fvrmg014771_parked",
    ),
    f"{VIN}_trip_logging": (
        "binary_sensor",
        "binary_sensor.protonlink_pl1dg2fvrmg014771_trip_logging",
    ),
    f"{VIN}_location": (
        "device_tracker",
        "device_tracker.protonlink_pl1dg2fvrmg014771_location",
    ),
    # A sensor whose entity_id was derived from the old device name "X50".
    f"{VIN}_odometer": ("sensor", "sensor.x50_5"),
    f"{VIN}_vin": ("sensor", "sensor.x50"),
}


@pytest.mark.usefixtures("fake_client")
async def test_legacy_entity_ids_are_cleaned_up_on_upgrade(
    hass: HomeAssistant,
) -> None:
    """An upgraded install should not keep the unwieldy generated ids."""
    registry = er.async_get(hass)

    # 1. Recreate the legacy registry entries exactly as v1.0.0 left them.
    for unique_id, (domain, legacy_id) in LEGACY.items():
        entry = registry.async_get_or_create(
            domain=domain,
            platform=DOMAIN,
            unique_id=unique_id,
            suggested_object_id=None,
            has_entity_name=True,
        )
        registry.async_update_entity(entry.entity_id, new_entity_id=legacy_id)

    before = {
        e.unique_id: e.entity_id
        for e in registry.entities.values()
        if e.platform == DOMAIN
    }
    assert len(before) == len(LEGACY)

    # 2. Now set up the integration with the fixed code.
    await _setup(hass)

    after = {
        e.unique_id: e.entity_id
        for e in registry.entities.values()
        if e.platform == DOMAIN
    }
    print("\n  unique_id                          before -> after")
    for unique_id in LEGACY:
        print(f"  {unique_id.replace(VIN, '<VIN>'):<33} "
              f"{before[unique_id]} -> {after.get(unique_id)}")

    renamed = {
        u: (before[u], after[u])
        for u in LEGACY
        if after.get(u) != before[u]
    }
    print(f"\n  renamed on upgrade: {len(renamed)}/{len(LEGACY)}")
