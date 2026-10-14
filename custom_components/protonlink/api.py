"""Thin async client for the Proton Link (ECARX / Atlas) cloud API.

Every method is read-only.  No endpoint here can start, stop, lock or otherwise
command the vehicle.

Authentication model (established by reverse engineering the Android app and
confirmed against the live service):

* ``POST app/v1/member/login`` is sent as **JSON** with
  ``{mobilePhone, password, type: "1", clientType: "phone", deviceId}``.
* ``password`` must be the **lower-case hex MD5** of the account password.
* ``deviceId`` is an Android-ID-style value that the server binds the session
  to.  It is only sent at login.  If it is missing, or if a different value is
  used than the one the session was created with, the service answers
  ``40009 DEVICE IS CHANGED`` on *every* endpoint.
* The access token is sent in a header literally named ``AUTHORIZATION`` with
  the **raw** token value (no ``Bearer`` prefix).
* The service is effectively single-session: a new login invalidates the
  previous access token.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import aiohttp

from .const import (
    API_APP_ID,
    API_BASE_URL,
    API_ENV_TYPE,
    API_HEADERS,
    API_TIMEOUT,
    CODE_OK,
    CODE_TOKEN_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class ProtonLinkError(Exception):
    """Base error."""


class ProtonLinkAuthError(ProtonLinkError):
    """Credentials rejected, or the session could not be established."""


class ProtonLinkSessionError(ProtonLinkError):
    """The session was invalidated (e.g. the account was used elsewhere)."""


class ProtonLinkApiError(ProtonLinkError):
    """The service returned an unexpected error."""

    def __init__(self, code: Any, message: str, endpoint: str) -> None:
        self.code = code
        self.endpoint = endpoint
        super().__init__(f"{endpoint}: [{code}] {message}")


class ProtonLinkClient:
    """Read-only client.  One instance per config entry."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        mobile: str,
        password: str,
        device_id: str,
    ) -> None:
        self._session = session
        self._mobile = mobile.strip()
        self._password_md5 = hashlib.md5(password.encode()).hexdigest().lower()
        self._device_id = device_id

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self.user_id: str | None = None

    # ------------------------------------------------------------------ auth --

    async def async_login(self) -> None:
        """Authenticate and store the session token.

        Raises ProtonLinkAuthError on bad credentials.
        """
        payload = {
            "mobilePhone": self._mobile,
            "password": self._password_md5,
            "type": "1",
            "clientType": "phone",
            "deviceId": self._device_id,
        }
        data = await self._async_request(
            "POST", "app/v1/member/login", payload=payload, authenticated=False
        )

        token = (data or {}).get("accessToken")
        if not token:
            raise ProtonLinkAuthError("login succeeded but no accessToken returned")

        self._access_token = token
        self._refresh_token = data.get("refreshToken")
        self.user_id = str(data.get("userId") or "") or None
        _LOGGER.debug("Proton Link login OK (userId present: %s)", bool(self.user_id))

    async def async_validate_credentials(self) -> dict[str, Any]:
        """Login and immediately fetch the account profile (used by the flow)."""
        await self.async_login()
        me = await self.async_get_user()
        vehicles = await self.async_get_vehicles()
        return {"user": me, "vehicles": vehicles}

    async def _async_relogin(self) -> None:
        _LOGGER.debug("Proton Link session expired; re-authenticating")
        self._access_token = None
        await self.async_login()

    # ------------------------------------------------------------------ http --

    async def _async_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
        retry_on_session_error: bool = True,
    ) -> Any:
        """Perform one request and unwrap the ``{code, msg, data}`` envelope."""
        url = f"{API_BASE_URL}/{endpoint}"
        headers = dict(API_HEADERS)
        headers["AUTHORIZATION"] = self._access_token or ""

        body = None
        if payload is not None:
            body = json.dumps(payload).encode()

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                data=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                raw = await resp.text()
        except asyncio.TimeoutError as err:
            raise ProtonLinkApiError("timeout", "request timed out", endpoint) from err
        except aiohttp.ClientError as err:
            raise ProtonLinkApiError("network", str(err), endpoint) from err

        try:
            envelope = json.loads(raw)
        except ValueError as err:
            raise ProtonLinkApiError(
                "invalid-json", f"non-JSON response ({raw[:120]!r})", endpoint
            ) from err

        if not isinstance(envelope, dict):
            raise ProtonLinkApiError("invalid-envelope", repr(envelope)[:120], endpoint)

        code = envelope.get("code")
        message = str(envelope.get("msg") or envelope.get("message") or "")

        if code == CODE_OK:
            return envelope.get("data")

        # Session no longer valid -> one transparent re-login.
        if (
            authenticated
            and retry_on_session_error
            and str(code) == CODE_TOKEN_TIMEOUT
        ):
            await self._async_relogin()
            return await self._async_request(
                method,
                endpoint,
                params=params,
                payload=payload,
                authenticated=True,
                retry_on_session_error=False,
            )

        if authenticated and not self._access_token:
            raise ProtonLinkAuthError(f"[{code}] {message}")

        raise ProtonLinkApiError(code, message, endpoint)

    # ---------------------------------------------------------------- reads --

    async def async_get_user(self) -> dict[str, Any]:
        """GET app/v1/me/user"""
        return await self._async_request(
            "GET", "app/v1/me/user", params={"userId": self.user_id}
        ) or {}

    async def async_get_vehicles(self) -> list[dict[str, Any]]:
        """GET app/v1/vehicle -> the account's vehicle list."""
        data = await self._async_request(
            "GET",
            "app/v1/vehicle",
            params={
                "userId": self.user_id,
                "onlySearchDefault": "true",
                "isPage": "false",
            },
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("items") or data.get("list") or []
        return []

    async def async_get_parking_status(self, vin: str) -> dict[str, Any]:
        """GET app/v1/vehicle/parkingStatus -> {'parkingStatus': '1'}"""
        return await self._async_request(
            "GET",
            "app/v1/vehicle/parkingStatus",
            params={"userId": self.user_id, "vin": vin, "envType": API_ENV_TYPE},
        ) or {}

    async def async_get_capabilities(self, vin: str) -> dict[str, Any]:
        """GET app/v1/vehicle/capability/service/app -> capability matrix."""
        return await self._async_request(
            "GET",
            "app/v1/vehicle/capability/service/app",
            params={"userId": self.user_id, "vin": vin},
        ) or {}

    async def async_get_flow(self, vin: str) -> dict[str, Any]:
        """GET app/v1/vehicle/flow -> data allowance (kibibytes)."""
        return await self._async_request(
            "GET",
            "app/v1/vehicle/flow",
            params={"userId": self.user_id, "vin": vin},
        ) or {}

    async def async_get_vehicle_state(self, vin: str) -> dict[str, Any]:
        """GET app/v1/journeyLog/resetEnable -> live vehicle state vector.

        Despite the name this is a read-only status endpoint and is *not*
        behind the expiring-benefits entitlement that blocks ``realtimeData``.
        Returns: svtState, activateState, engineState, powerMode,
        positionUploadState, journalLogState, immobilizationState.
        """
        return await self._async_request(
            "GET", "app/v1/journeyLog/resetEnable", params={"vin": vin}
        ) or {}

    async def async_get_electronic_fences(self, vin: str) -> list[dict[str, Any]]:
        """GET app/v1/vehicle/electronicFence"""
        data = await self._async_request(
            "GET",
            "app/v1/vehicle/electronicFence",
            params={"userId": self.user_id, "vin": vin, "isPage": "false"},
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("list") or []
        return []

    async def async_get_trips(
        self,
        vin: str,
        *,
        start_ms: int = 0,
        end_ms: int = 4_102_444_800_000,
        page: int = 1,
        page_size: int = 1,
    ) -> dict[str, Any]:
        """POST app/v1/journeyLog/logList -> trip records (newest first).

        Each record carries start/end odometer, fuel level and (optionally)
        GPS track points, which is how the integration derives the current
        odometer and fuel level without the gated ``realtimeData`` endpoint.
        """
        return await self._async_request(
            "POST",
            "app/v1/journeyLog/logList",
            payload={
                "vin": vin,
                "userId": self.user_id,
                "startTime": start_ms,
                "endTime": end_ms,
                "pageNo": page,
                "pageSize": page_size,
            },
        ) or {}

    async def async_get_track(
        self,
        vin: str,
        *,
        start_ms: int,
        end_ms: int,
    ) -> list[dict[str, Any]]:
        """POST app/v1/journeyLog/trackList -> GPS breadcrumb track."""
        data = await self._async_request(
            "POST",
            "app/v1/journeyLog/trackList",
            payload={"vin": vin, "startTime": start_ms, "endTime": end_ms},
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("list") or []
        return []
