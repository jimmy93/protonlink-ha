"""Sensor platform for Proton Link.

Entity values come from the coordinator's normalised snapshot.  Where the
gated ``realtimeData`` endpoint would normally supply a value, the equivalent
is derived from the trip log and the state vector; see coordinator.py.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfSpeed,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import (
    ENGINE_STATE,
    IMMOBILIZATION_STATE,
    JOURNAL_LOG_STATES,
    POSITION_UPLOAD_STATE,
    POWER_MODE,
    SV_STATE,
    ProtonLinkCoordinator,
)
from .entity import ProtonLinkEntity

_LOGGER = logging.getLogger(__name__)


def _vehicle(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("vehicle") or {}


def _last_trip(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("last_trip") or {}


def _state(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("state") or {}


def _pick_odometer(snapshot: dict[str, Any]) -> float | None:
    """Odometer from the newest trip, falling back to the vehicle record."""
    odometer = _last_trip(snapshot).get("odometer")
    if odometer is None:
        odometer = _vehicle(snapshot).get("drivenDistance")
    try:
        return round(float(odometer), 1) if odometer is not None else None
    except (TypeError, ValueError):
        return None


def _pick_fuel(snapshot: dict[str, Any]) -> float | None:
    """Most recent known fuel level (percentage)."""
    trip = _last_trip(snapshot)
    level = trip.get("end_fuel_level")
    if level is None:
        level = trip.get("start_fuel_level")
    try:
        return round(float(level), 1) if level is not None else None
    except (TypeError, ValueError):
        return None


def _flow_gib(snapshot: dict[str, Any], key: str) -> float | None:
    """Convert the service's kibibyte data allowance into GiB."""
    flow = snapshot.get("flow") or {}
    try:
        return round(float(flow[key]) * 1024 / (1024**3), 3)
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True, kw_only=True)
class ProtonLinkSensorDescription(SensorEntityDescription):
    """Describes one Proton Link sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[ProtonLinkSensorDescription, ...] = (
    # --- vehicle identity -------------------------------------------------
    ProtonLinkSensorDescription(
        key="vin",
        translation_key="vin",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _vehicle(s).get("vin"),
    ),
    ProtonLinkSensorDescription(
        key="model",
        translation_key="model",
        icon="mdi:car",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _vehicle(s).get("matName") or _vehicle(s).get("modelName"),
    ),
    ProtonLinkSensorDescription(
        key="plate",
        translation_key="plate",
        icon="mdi:card-text",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _vehicle(s).get("plateNum"),
    ),
    ProtonLinkSensorDescription(
        key="colour",
        translation_key="colour",
        icon="mdi:palette",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _vehicle(s).get("colorName"),
    ),
    # --- mileage ----------------------------------------------------------
    ProtonLinkSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=_pick_odometer,
    ),
    ProtonLinkSensorDescription(
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fuel",
        value_fn=_pick_fuel,
    ),
    # --- most recent trip -------------------------------------------------
    ProtonLinkSensorDescription(
        key="last_trip_distance",
        translation_key="last_trip_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-distance",
        value_fn=lambda s: _last_trip(s).get("distance_km"),
    ),
    ProtonLinkSensorDescription(
        key="last_trip_avg_speed",
        translation_key="last_trip_avg_speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        value_fn=lambda s: _last_trip(s).get("avg_speed_kmh"),
    ),
    ProtonLinkSensorDescription(
        key="last_trip_started",
        translation_key="last_trip_started",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        value_fn=lambda s: _last_trip(s).get("start_time"),
    ),
    ProtonLinkSensorDescription(
        key="last_trip_ended",
        translation_key="last_trip_ended",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-end",
        value_fn=lambda s: _last_trip(s).get("end_time"),
    ),
    ProtonLinkSensorDescription(
        key="trips_recorded",
        translation_key="trips_recorded",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:format-list-numbered",
        value_fn=lambda s: s.get("trip_total"),
    ),
    # --- vehicle state vector (journeyLog/resetEnable) --------------------
    ProtonLinkSensorDescription(
        key="engine_state",
        translation_key="engine_state",
        icon="mdi:engine",
        value_fn=lambda s: ENGINE_STATE.get(_state(s).get("engineState")),
    ),
    ProtonLinkSensorDescription(
        key="power_mode",
        translation_key="power_mode",
        icon="mdi:power",
        value_fn=lambda s: POWER_MODE.get(_state(s).get("powerMode")),
    ),
    ProtonLinkSensorDescription(
        key="immobilization",
        translation_key="immobilization",
        icon="mdi:shield-car",
        value_fn=lambda s: IMMOBILIZATION_STATE.get(
            _state(s).get("immobilizationState")
        ),
    ),
    ProtonLinkSensorDescription(
        key="svt_state",
        translation_key="svt_state",
        icon="mdi:crosshairs-gps",
        value_fn=lambda s: SV_STATE.get(_state(s).get("svtState")),
    ),
    ProtonLinkSensorDescription(
        key="position_upload",
        translation_key="position_upload",
        icon="mdi:upload-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: POSITION_UPLOAD_STATE.get(
            _state(s).get("positionUploadState")
        ),
    ),
    ProtonLinkSensorDescription(
        key="trip_log_state",
        translation_key="trip_log_state",
        icon="mdi:notebook-check",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: JOURNAL_LOG_STATES.get(_state(s).get("journalLogState")),
    ),
    # --- connectivity -----------------------------------------------------
    ProtonLinkSensorDescription(
        key="data_remaining",
        translation_key="data_remaining",
        icon="mdi:signal-cellular-3",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _flow_gib(s, "residueFlow"),
    ),
    ProtonLinkSensorDescription(
        key="data_used",
        translation_key="data_used",
        icon="mdi:signal-cellular-1",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _flow_gib(s, "usedFlow"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator: ProtonLinkCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities(
        ProtonLinkSensor(coordinator, description) for description in SENSORS
    )


class ProtonLinkSensor(ProtonLinkEntity, SensorEntity):
    """A sensor backed by the coordinator snapshot."""

    entity_description: ProtonLinkSensorDescription

    def __init__(
        self,
        coordinator: ProtonLinkCoordinator,
        description: ProtonLinkSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def native_value(self) -> Any:
        try:
            return self.entity_description.value_fn(self.coordinator.data or {})
        except Exception:  # noqa: BLE001 - never let a bad field kill the entity
            _LOGGER.debug(
                "failed to read %s", self.entity_description.key, exc_info=True
            )
            return None
