"""DataUpdateCoordinator for Proton Link.

Responsibilities:
  * hold exactly one authenticated session (the service is single-session, so
    concurrent logins would invalidate each other)
  * poll the read-only endpoints on a schedule
  * normalise the raw envelopes into a flat snapshot the entities can consume
  * translate the gated ``realtimeData`` endpoint into graceful degradation

Data sourcing note
------------------
``app/v1/vehicle/realtimeData`` is behind a per-vehicle entitlement that is
currently inactive for this vehicle (error ``150001006``).  The coordinator
therefore derives the equivalent values from endpoints that are *not* gated:

  odometer   <- newest trip record's ``endOdometer``, falling back to the
                vehicle list's ``drivenDistance``
  fuel level <- newest trip record's ``endFuelLevel``
  position   <- last GPS point of the newest trip's ``trackpoints``
  engine etc <- ``app/v1/journeyLog/resetEnable`` state vector
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ProtonLinkApiError,
    ProtonLinkAuthError,
    ProtonLinkClient,
    ProtonLinkSessionError,
)
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FLOW_UNIT_FACTOR,
    GPS_SCALE,
    TRIPS_PER_POLL,
)

_LOGGER = logging.getLogger(__name__)

# Interpretation of the state vector returned by journeyLog/resetEnable.
# The values are small enums; we surface them as readable states rather than
# guessing beyond what the app's own labels imply.
JOURNAL_LOG_STATES = {0: "disabled", 1: "enabled"}
SV_STATE = {0: "off", 1: "on"}
ENGINE_STATE = {0: "off", 1: "on"}
POWER_MODE = {0: "off", 1: "on"}
IMMOBILIZATION_STATE = {0: "released", 1: "immobilized"}
POSITION_UPLOAD_STATE = {0: "off", 1: "on"}
PARKING_STATE = {"0": "off", "1": "on"}


def _ms_to_dt(value: Any) -> datetime | None:
    """Convert an epoch-millisecond value to an aware UTC datetime."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _decode_position(pos: dict[str, Any] | None) -> tuple[float, float] | None:
    """Decode a raw arc-millisecond position into WGS-84 degrees."""
    if not isinstance(pos, dict):
        return None
    try:
        lat = float(pos["latitude"]) / GPS_SCALE
        lon = float(pos["longitude"]) / GPS_SCALE
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    # A position of 0/0 is the service's "no fix" value, not the Gulf of Guinea.
    if lat == 0.0 and lon == 0.0:
        return None
    return lat, lon


class ProtonLinkCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the Proton Link service and keep one normalised snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        *,
        mobile: str,
        password: str,
        device_id: str,
        scan_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )
        self.client = ProtonLinkClient(session, mobile, password, device_id)
        self.mobile = mobile
        self.device_id = device_id

    # ------------------------------------------------------------- snapshot --

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch everything and return the normalised snapshot."""
        if not self.client.user_id:
            try:
                await self.client.async_login()
            except ProtonLinkAuthError as err:
                raise UpdateFailed(f"authentication failed: {err}") from err

        try:
            return await self._async_collect()
        except ProtonLinkAuthError as err:
            # Credentials are wrong or the login was rejected outright.
            raise UpdateFailed(f"authentication failed: {err}") from err
        except ProtonLinkSessionError as err:
            raise UpdateFailed(f"session rejected: {err}") from err
        except ProtonLinkApiError as err:
            # A server-side outage should not wipe the coordinator's history.
            raise UpdateFailed(str(err)) from err

    async def _async_collect(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "vehicle": {},
            "capabilities": {},
            "trips": [],
            "last_trip": None,
            "position": None,
            "state": {},
            "flow": {},
            "fences": [],
        }

        vehicles = await self.client.async_get_vehicles()
        if not vehicles:
            raise UpdateFailed("no vehicles on this account")
        vehicle = vehicles[0]
        snapshot["vehicle"] = vehicle
        vin = vehicle.get("vin")
        if not vin:
            raise UpdateFailed("vehicle record has no VIN")

        # Live vehicle state vector.
        try:
            snapshot["state"] = await self.client.async_get_vehicle_state(vin)
        except ProtonLinkApiError as err:
            _LOGGER.debug("state vector unavailable: %s", err)

        # Parking status.
        try:
            parking = await self.client.async_get_parking_status(vin)
            snapshot["state"]["parkingStatus"] = parking.get("parkingStatus")
        except ProtonLinkApiError as err:
            _LOGGER.debug("parking status unavailable: %s", err)

        # Data allowance.
        try:
            snapshot["flow"] = await self.client.async_get_flow(vin)
        except ProtonLinkApiError as err:
            _LOGGER.debug("flow unavailable: %s", err)

        # Electronic fences (geofences the user configured in the app).
        try:
            snapshot["fences"] = await self.client.async_get_electronic_fences(vin)
        except ProtonLinkApiError as err:
            _LOGGER.debug("electronic fences unavailable: %s", err)

        # Capability matrix — static, but cheap to refresh with the vehicle.
        try:
            caps = await self.client.async_get_capabilities(vin)
            snapshot["capabilities"] = caps
        except ProtonLinkApiError as err:
            _LOGGER.debug("capabilities unavailable: %s", err)

        # Trips: this is the source of odometer, fuel level and position.
        try:
            trips_response = await self.client.async_get_trips(
                vin, page=1, page_size=TRIPS_PER_POLL
            )
            trips = trips_response.get("list") or []
            snapshot["trips"] = trips
            snapshot["trip_total"] = (
                (trips_response.get("pagination") or {}).get("totleSize")
                or (trips_response.get("pagination") or {}).get("totalSize")
            )
            if trips:
                snapshot["last_trip"] = self._async_normalise_trip(trips[0])
                snapshot["position"] = self._async_latest_position(trips[0])
        except ProtonLinkApiError as err:
            _LOGGER.debug("trip list unavailable: %s", err)
            snapshot["trip_total"] = None

        snapshot["telematics_available"] = False  # realtimeData is entitlement-gated
        snapshot["last_updated"] = datetime.now(timezone.utc)
        return snapshot

    # ------------------------------------------------------------ normalise --

    @staticmethod
    def _async_latest_position(trip: dict[str, Any]) -> dict[str, Any] | None:
        """Last trusted GPS fix in a trip record."""
        points = trip.get("trackpoints") or []
        for point in reversed(points):
            pos = point.get("position") if isinstance(point, dict) else None
            decoded = _decode_position(pos)
            if decoded:
                lat, lon = decoded
                return {
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": pos.get("altitude"),
                    "trusted": pos.get("posCanBeTrusted"),
                    "timestamp": _ms_to_dt(trip.get("endTime")),
                }
        return None

    @staticmethod
    def _async_normalise_trip(trip: dict[str, Any]) -> dict[str, Any]:
        """Flatten one trip record into the fields the sensors expose."""
        start_odo = trip.get("startOdometer")
        end_odo = trip.get("endOdometer")
        return {
            "start_time": _ms_to_dt(trip.get("startTime")),
            "end_time": _ms_to_dt(trip.get("endTime")),
            "distance_km": trip.get("traveledDistance"),
            "avg_speed_kmh": trip.get("avgSpeed"),
            "fuel_consumption": trip.get("fuelConsumption"),
            "start_odometer": start_odo,
            "end_odometer": end_odo,
            "start_fuel_level": trip.get("startFuelLevel"),
            "end_fuel_level": trip.get("endFuelLevel"),
            "odometer": end_odo if end_odo is not None else start_odo,
        }

    # --------------------------------------------------------------- helpers --

    @staticmethod
    def _flow_kb_to_mb(key: str, flow: dict[str, Any]) -> float | None:
        """The service reports data allowance in kibibytes."""
        try:
            kb = float(flow[key])
        except (KeyError, TypeError, ValueError):
            return None
        # kibibytes -> gibibytes, matching how the app displays the allowance
        return round(kb * FLOW_UNIT_FACTOR / (1024**3), 3)
