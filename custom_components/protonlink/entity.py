"""Shared entity plumbing for the Proton Link integration.

Every platform attaches to the same device and opts into ``has_entity_name``,
which is what tells Home Assistant to label each row with the entity's own
translated name rather than the device name.  Both are centralised here because
forgetting either one fails *silently*: without ``has_entity_name`` every entity
renders as a duplicate of the device name, and without ``device_info`` the
entities are not attached to the car at all.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtonLinkCoordinator

MANUFACTURER = "Proton"


def vehicle_name(vehicle: dict[str, Any]) -> str:
    """Return a human-readable device name, e.g. ``Proton X50``."""
    model = str(vehicle.get("matName") or vehicle.get("modelName") or "").strip()
    return f"{MANUFACTURER} {model}" if model else MANUFACTURER


def build_device_info(vehicle: dict[str, Any]) -> dict[str, Any]:
    """Describe the car as one Home Assistant device.

    ``brandName`` from the API is the platform vendor (acotech), not the marque,
    so the manufacturer is fixed to Proton.
    """
    vin = vehicle.get("vin") or "unknown"
    model = str(vehicle.get("matName") or vehicle.get("modelName") or "").strip()
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, vin)},
        "manufacturer": MANUFACTURER,
        "name": vehicle_name(vehicle),
        "serial_number": vin,
    }
    if model:
        info["model"] = model
    return info


class ProtonLinkEntity(CoordinatorEntity[ProtonLinkCoordinator]):
    """Base entity: one device per car, each entity labelled with its own name."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ProtonLinkCoordinator) -> None:
        """Bind to the coordinator and the vehicle device."""
        super().__init__(coordinator)
        vehicle = (coordinator.data or {}).get("vehicle") or {}
        self._vin: str = vehicle.get("vin") or "unknown"
        self._attr_device_info = build_device_info(vehicle)

    @property
    def vin(self) -> str:
        """The vehicle identification number this entity belongs to."""
        return self._vin
