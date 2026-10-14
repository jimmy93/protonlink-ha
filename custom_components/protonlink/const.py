"""Constants for the Proton Link integration.

The API contract here was derived by reverse-engineering the official
``cn.com.ecarx.protonlink`` Android application and then verified against the
live service.  See README.md for the evidence trail.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "protonlink"

# --- Service -----------------------------------------------------------------
API_BASE_URL: Final = "https://app.acotech.my:8443"
API_APP_ID: Final = "protonlink_01"
API_ENV_TYPE: Final = "production"
API_TIMEOUT: Final = 30

# The app identifies the handset with Android's ANDROID_ID (a 64-bit value
# rendered as 16 hex characters).  The value is *not* sent as a header; it is
# sent in the login body and the server binds the session to it.  We therefore
# generate a stable per-installation identifier and persist it in the config
# entry.  Omitting it makes every subsequent call fail with
# 40009 "DEVICE IS CHANGED".
API_DEVICE_ID_LENGTH: Final = 32

# Request headers.  Header values are case-insensitive on the wire but the
# service is picky about the *values*: "proton link" must be lower case.
API_HEADERS: Final = {
    "Accept-Language": "en",
    "APP-NAME": "Proton Link",
    "X-APP-ID": API_APP_ID,
    "X-EQUIPMENT-TYPE": "proton link",
    "X-AGENT-TYPE": "android",
    "X-AGENT-VERSION": "34",
    "Version-Name": "2.1.0",
    "Version-Code": "1441",
    "Content-Type": "application/json",
}

# --- Error codes -------------------------------------------------------------
CODE_OK: Final = 200
CODE_TOKEN_TIMEOUT: Final = "40006"
CODE_DEVICE_CHANGED: Final = "40009"
CODE_ENTITLEMENT: Final = "150001006"

# Codes that mean "our session is no longer usable" -> re-authenticate.
RELOGIN_CODES: Final = {CODE_TOKEN_TIMEOUT, CODE_DEVICE_CHANGED}

# --- Defaults ----------------------------------------------------------------
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 120

CONF_SCAN_INTERVAL: Final = "scan_interval"

# How many trips to request per poll.  One is enough for the "latest known
# odometer/fuel" sensors; a few more lets the extra sensors be useful without
# making the payload large.
TRIPS_PER_POLL: Final = 1

# Number of trips fetched for the "recent trips" history sensor set.
TRIPS_HISTORY: Final = 10

# --- GPS ---------------------------------------------------------------------
# Raw coordinates are arc-milliseconds: divide by 3_600_000 to get degrees.
# `marsCoordinates: false` in the payload confirms the values are already
# WGS-84, i.e. what Home Assistant's device_tracker expects.
GPS_SCALE: Final = 3_600_000

# --- Units -------------------------------------------------------------------
# `residueFlow` / `usedFlow` are reported in kibibytes by the service; the app
# multiplies by 1024 to display bytes.
FLOW_UNIT_FACTOR: Final = 1024
