"""Config flow for Proton Link."""

from __future__ import annotations

import secrets
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import ProtonLinkApiError, ProtonLinkAuthError, ProtonLinkClient
from .const import API_DEVICE_ID_LENGTH, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

CONF_MOBILE_PHONE = "mobile_phone"
CONF_DEVICE_ID = "device_id"


class NoVehicleError(ProtonLinkApiError):
    """The credentials are valid but there is no Proton vehicle on the account."""

    def __init__(self) -> None:
        super().__init__("no-vehicle", "account has no vehicle", "app/v1/vehicle")


def _generate_device_id() -> str:
    """Generate a stable Android-ID-style device identifier (32 hex chars)."""
    return secrets.token_hex(API_DEVICE_ID_LENGTH // 2)


def normalise_mobile(value: str) -> str | None:
    """Normalise a phone number into the service's expected format.

    Accepts ``0123456789``, ``60123456789`` and ``+60123456789`` and returns
    ``60123456789``.  Returns ``None`` when the value cannot be a valid mobile
    number.  The service rejects a leading ``+`` outright.
    """
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None

    if digits.startswith("60"):
        national = digits[2:]
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        national = digits

    if not (9 <= len(national) <= 10):
        return None

    return "60" + national


class ProtonLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for the account credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            normalised = normalise_mobile(user_input.get(CONF_MOBILE_PHONE, ""))
            password = user_input.get(CONF_PASSWORD) or ""

            if normalised is None:
                errors["base"] = "invalid_phone"
            else:
                device_id = _generate_device_id()
                try:
                    result = await self._async_validate(normalised, password, device_id)
                except ProtonLinkAuthError:
                    errors["base"] = "invalid_auth"
                except NoVehicleError:
                    errors["base"] = "no_vehicle"
                except aiohttp.ClientError:
                    errors["base"] = "cannot_connect"
                except ProtonLinkApiError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001 - surface as a generic form error
                    errors["base"] = "unknown"
                else:
                    # Unique per account, so the same account cannot be added twice.
                    await self.async_set_unique_id(normalised)
                    self._abort_if_unique_id_configured()

                    vehicle = (result.get("vehicles") or [{}])[0]
                    return self.async_create_entry(
                        title=vehicle.get("plateNum")
                        or vehicle.get("matName")
                        or "Proton Link",
                        data={
                            CONF_MOBILE_PHONE: normalised,
                            CONF_PASSWORD: password,
                            CONF_DEVICE_ID: device_id,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MOBILE_PHONE): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEL
                        )
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_validate(
        self, mobile: str, password: str, device_id: str
    ) -> dict[str, Any]:
        """Log in and confirm the account has at least one vehicle."""
        async with aiohttp.ClientSession() as session:
            client = ProtonLinkClient(session, mobile, password, device_id)
            result = await client.async_validate_credentials()

        if not result.get("vehicles"):
            raise NoVehicleError()
        return result

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return ProtonLinkOptionsFlow(config_entry)


class ProtonLinkOptionsFlow(OptionsFlow):
    """Allow the polling interval to be tuned after setup.

    ``CONF_SCAN_INTERVAL`` is stored as a whole number of minutes.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(CONF_SCAN_INTERVAL)
        if current is None:
            minutes = int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60)
        else:
            minutes = int(current)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=minutes): vol.All(
                        int, vol.Range(min=5, max=120)
                    )
                }
            ),
        )
