"""Device tracker platform for Proton Link.

Reports the vehicle's last known position.  Coordinates in the API payload are
arc-milliseconds and are already WGS-84 (the payload sets
``marsCoordinates: false``), so they can be passed to Home Assistant directly
after dividing by 3,600,000.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ProtonLinkCoordinator
from .entity import ProtonLinkEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the device tracker."""
    coordinator: ProtonLinkCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([ProtonLinkTracker(coordinator)])


class ProtonLinkTracker(ProtonLinkEntity, TrackerEntity):
    """Last known vehicle position, from the trip log's GPS breadcrumbs.

    Named "Location" like the sibling Geely integration, so it renders as
    "Proton X50 Location" -- the vehicle name comes from the device, which
    ``ProtonLinkEntity`` already attaches.
    """

    _attr_name = "Location"
    _attr_icon = "mdi:car-connected"

    def __init__(self, coordinator: ProtonLinkCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.vin}_location"

    @property
    def _position(self) -> dict[str, Any] | None:
        position = (self.coordinator.data or {}).get("position")
        return position if isinstance(position, dict) else None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        position = self._position
        return position.get("latitude") if position else None

    @property
    def longitude(self) -> float | None:
        position = self._position
        return position.get("longitude") if position else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        position = self._position
        if not position:
            return None
        return {
            "altitude_m": position.get("altitude"),
            "position_trusted": position.get("trusted"),
            "fix_timestamp": position.get("timestamp"),
        }
