"""Tests that pin the reverse-engineered API contract.

These guard the hard-won details: the login body shape, the MD5 password
transform, the deviceId binding and the raw (non-Bearer) AUTHORIZATION header.
A regression in any of these breaks authentication silently, so they are
asserted explicitly.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from aiohttp import ClientSession

from custom_components.protonlink.api import (
    ProtonLinkApiError,
    ProtonLinkAuthError,
    ProtonLinkClient,
)

MOBILE = "60123456789"
PASSWORD = "hunter2"
DEVICE = "067ecdf9a1b2c3d4e5f60718293a4b5c"


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def text(self) -> str:
        return json.dumps(self._payload)


class FakeSession:
    """Records every request and replays canned envelopes in order."""

    def __init__(self, *payloads: dict) -> None:
        self.payloads = list(payloads)
        self.requests: list[dict] = []

    def request(self, method, url, params=None, data=None, headers=None, timeout=None):
        self.requests.append(
            {"method": method, "url": url, "params": params, "data": data, "headers": headers}
        )
        payload = self.payloads.pop(0) if self.payloads else {"code": 200, "data": {}}
        return FakeResponse(payload)

    @property
    def last(self) -> dict:
        return self.requests[-1]


def make_client(session) -> ProtonLinkClient:
    return ProtonLinkClient(session, MOBILE, PASSWORD, DEVICE)


def login_ok(token: str = "TOKEN-1") -> dict:
    return {
        "code": 200,
        "msg": "Operation successful",
        "data": {"accessToken": token, "refreshToken": "R", "userId": "999"},
    }


async def test_login_sends_documented_body_and_headers():
    session = FakeSession(login_ok())
    client = make_client(session)
    await client.async_login()

    req = session.last
    assert req["method"] == "POST"
    assert req["url"].endswith("app/v1/member/login")

    body = json.loads(req["data"])
    assert set(body) == {"mobilePhone", "password", "type", "clientType", "deviceId"}
    assert body["mobilePhone"] == MOBILE
    assert body["type"] == "1"
    assert body["clientType"] == "phone"
    assert body["deviceId"] == DEVICE
    # Password must be sent as lower-case hex MD5, never in clear text.
    assert body["password"] == hashlib.md5(PASSWORD.encode()).hexdigest().lower()
    assert PASSWORD not in req["data"].decode()

    headers = req["headers"]
    assert headers["APP-NAME"] == "Proton Link"
    assert headers["X-APP-ID"] == "protonlink_01"
    # The service is case-sensitive about this value.
    assert headers["X-EQUIPMENT-TYPE"] == "proton link"


async def test_access_token_is_sent_raw_not_bearer():
    """AUTHORIZATION carries the raw token; a Bearer prefix is rejected."""
    session = FakeSession(login_ok("RAW-TOKEN"), {"code": 200, "data": []})
    client = make_client(session)
    await client.async_login()
    await client.async_get_vehicles()

    assert session.last["headers"]["AUTHORIZATION"] == "RAW-TOKEN"


async def test_login_rejects_missing_token():
    session = FakeSession({"code": 200, "msg": "Operation successful", "data": {}})
    with pytest.raises(ProtonLinkAuthError):
        await make_client(session).async_login()


async def test_bad_credentials_raise_auth_error():
    session = FakeSession({"code": 7177, "msg": "Incorrect username or password"})
    with pytest.raises(ProtonLinkApiError) as err:
        await make_client(session).async_login()
    assert err.value.code == 7177


async def test_token_timeout_triggers_one_relogin():
    """40006 means the single-session token was rotated; retry transparently."""
    session = FakeSession(
        login_ok("OLD"),                                  # initial login
        {"code": 40006, "msg": "Token time out"},          # first attempt
        login_ok("NEW"),                                   # re-login
        {"code": 200, "data": [{"vin": "V"}]},             # retry succeeds
    )
    client = make_client(session)
    await client.async_login()
    vehicles = await client.async_get_vehicles()

    assert vehicles == [{"vin": "V"}]
    assert len(session.requests) == 4
    assert session.last["headers"]["AUTHORIZATION"] == "NEW"


async def test_device_changed_is_recovered_by_one_relogin():
    """40009 (device binding changed) recovers the same way the app does."""
    session = FakeSession(
        login_ok("T1"),
        {"code": 40009, "msg": "DEVICE IS CHANGED"},   # first attempt
        login_ok("T2"),                                 # re-login with same deviceId
        {"code": 200, "data": [{"vin": "V"}]},          # retry succeeds
    )
    client = make_client(session)
    await client.async_login()
    assert await client.async_get_vehicles() == [{"vin": "V"}]
    assert len(session.requests) == 4
    assert session.last["headers"]["AUTHORIZATION"] == "T2"
    # The re-login must reuse the identical device binding.
    assert json.loads(session.requests[2]["data"])["deviceId"] == DEVICE


async def test_persistent_device_changed_surfaces_after_one_retry():
    """40009 must not loop forever: it retries once, then raises."""
    session = FakeSession(
        login_ok("T1"),
        {"code": 40009, "msg": "DEVICE IS CHANGED"},
        login_ok("T2"),
        {"code": 40009, "msg": "DEVICE IS CHANGED"},
    )
    client = make_client(session)
    await client.async_login()
    with pytest.raises(ProtonLinkApiError) as err:
        await client.async_get_vehicles()
    assert str(err.value.code) == "40009"
    assert len(session.requests) == 4  # initial + retry, not unbounded


async def test_entitlement_error_surfaces_cleanly():
    """The gated realtimeData code must not be mistaken for an auth failure."""
    session = FakeSession(
        login_ok("T"),
        {"code": 150001006, "msg": "The basic benefits for your car have expired"},
    )
    client = make_client(session)
    await client.async_login()
    with pytest.raises(ProtonLinkApiError) as err:
        await client.async_get_parking_status("VIN")
    assert str(err.value.code) == "150001006"


def test_real_aiohttp_session_is_compatible():
    """Guard the fake against drift from aiohttp's real interface."""
    assert hasattr(ClientSession, "request")
