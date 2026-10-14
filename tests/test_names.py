"""Dump the entity names Home Assistant actually generates.

Run as a test so the real EN translation catalogue is loaded (translation
lookups do not resolve outside the config-entry setup path).

    pytest tests/test_names.py -q -s
"""

from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.protonlink.const import DOMAIN

from .test_setup import _setup


@pytest.mark.usefixtures("fake_client")
async def test_dump_entity_names(hass):
    """Print every entity id and friendly name, for eyeballing."""
    await _setup(hass)

    registry = er.async_get(hass)
    rows = []
    for entity in registry.entities.values():
        if entity.platform != DOMAIN:
            continue
        state = hass.states.get(entity.entity_id)
        friendly = state.attributes.get("friendly_name") if state else None
        rows.append((entity.entity_id, friendly))

    rows.sort()
    print(f"\n{'entity_id':<48} {'friendly_name'}")
    print("-" * 92)
    for entity_id, friendly in rows:
        print(f"{entity_id:<48} {friendly}")

    names = [f for _, f in rows]
    assert len(names) == len(set(names)), f"duplicate names: {names}"
