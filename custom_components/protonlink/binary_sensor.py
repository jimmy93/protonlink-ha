"""Binary sensor platform for Proton Link."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PARKING_STATE, ProtonLinkCoordinator
from .entity import ProtonLinkEntity

_LOGGER = logging.getLogger(__name__)


def _parking_on(snapshot: dict[str, Any]) -> bool | None:
    """True when the vehicle reports itself as parked/ignition-off."""
    raw = (snapshot.get("state") or {}).get("parkingStatus")
    if raw is None:
        return None
    return PARKING_STATE.get(str(raw)) == "on"


def _trip_log_on(snapshot: dict[str, Any]) -> bool | None:
    value = (snapshot.get("state") or {}).get("journalLogState")
    if value is None:
        return None
    return bool(value)


def _immobilized_on(snapshot: dict[str, Any]) -> bool | None:
    value = (snapshot.get("state") or {}).get("immobilizationState")
    if value is None:
        return None
    return bool(value)


@dataclass(frozen=True, kw_only=True)
class ProtonLinkBinaryDescription(BinarySensorEntityDescription):
    """Describes one Proton Link binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[ProtonLinkBinaryDescription, ...] = (
    ProtonLinkBinaryDescription(
        key="parked",
        translation_key="parked",
        icon="mdi:parking",
        value_fn=_parking_on,
    ),
    ProtonLinkBinaryDescription(
        key="trip_logging",
        translation_key="trip_logging",
        icon="mdi:notebook-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_trip_log_on,
    ),
    ProtonLinkBinaryDescription(
        key="immobilized",
        translation_key="immobilized",
        icon="mdi:shield-lock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_immobilized_on,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator: ProtonLinkCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities(
        ProtonLinkBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class ProtonLinkBinarySensor(ProtonLinkEntity, BinarySensorEntity):
    """A binary sensor backed by the coordinator snapshot."""

    entity_description: ProtonLinkBinaryDescription

    def __init__(
        self,
        coordinator: ProtonLinkCoordinator,
        description: ProtonLinkBinaryDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        try:
            return self.entity_description.value_fn(self.coordinator.data or {})
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "failed to read %s", self.entity_description.key, exc_info=True
            )
            return None
