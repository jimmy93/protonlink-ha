"""The Proton Link integration.

Read-only Home Assistant integration for Proton vehicles (Malaysia) that use
the ECARX "Atlas" connected-car platform.

Setup is via the UI: the user supplies the phone number and password of their
own Proton Link account, plus a device identifier.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import ProtonLinkCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Proton Link from a config entry."""
    session = aiohttp.ClientSession()
    # Options store whole minutes; fall back to the default when unset.
    options_interval = entry.options.get(CONF_SCAN_INTERVAL)
    scan_interval = (
        timedelta(minutes=int(options_interval))
        if options_interval is not None
        else DEFAULT_SCAN_INTERVAL
    )
    coordinator = ProtonLinkCoordinator(
        hass,
        session,
        mobile=entry.data["mobile_phone"],
        password=entry.data[CONF_PASSWORD],
        device_id=entry.data["device_id"],
        scan_interval=scan_interval,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001 - reported to the user as not-ready
        # Never leave the aiohttp session dangling on a failed setup.
        await session.close()
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        stored = hass.data[DOMAIN].pop(entry.entry_id, {})
        session: aiohttp.ClientSession | None = stored.get("session")
        if session is not None and not session.closed:
            await session.close()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
