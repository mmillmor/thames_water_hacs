"""API client for Thames Water."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://myaccount.thameswater.co.uk"
LOGIN_PAGE_URL = f"{BASE_URL}/login"
METERS_URL = f"{BASE_URL}/ajax/waterMeter/getMeters"
CONSUMPTION_URL = f"{BASE_URL}/ajax/waterMeter/getSmartWaterMeterConsumptions"


class ThamesWaterError(Exception):
    """Base class for Thames Water exceptions."""


class ThamesWaterAuthError(ThamesWaterError):
    """Authentication failure exception."""


class ThamesWaterConnectionError(ThamesWaterError):
    """Network connection failure exception."""


@dataclass
class MeterInfo:
    """Information about a Thames Water meter."""

    meter_id: str
    account_number: str
    address: Optional[str] = None
    serial_number: Optional[str] = None


@dataclass
class UsageRecord:
    """Individual historical water usage data point."""

    timestamp: datetime  # UTC aware
    volume_m3: float     # Volume consumed in m3 in this interval
    cumulative_m3: float # Total accumulated meter reading up to this timestamp
    is_actual: bool = True


class ThamesWaterAPI:
    """Async API Client for Thames Water portal."""

    def __init__(
        self,
        username: str,
        password: str,
        session_cookie: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.session_cookie = session_cookie
        self._session = session
        self._own_session = False
        self.account_number: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close session if created internally."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def async_login(self) -> bool:
        """Authenticate with Thames Water website."""
        session = await self._get_session()

        # If user provided a session cookie manually, inject it into session
        if self.session_cookie:
            _LOGGER.debug("Using provided session cookie for Thames Water authentication")
            session.cookie_jar.update_cookies({"Cookie": self.session_cookie})
            return True

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            _LOGGER.debug("Navigating to Thames Water login page for user %s", self.username)
            # Step 1: GET login page to establish session cookies
            async with session.get(LOGIN_PAGE_URL, headers=headers, timeout=30) as resp:
                if resp.status >= 500:
                    raise ThamesWaterConnectionError(f"Thames Water website server error (HTTP {resp.status})")

            # Step 2: POST login credentials
            post_headers = {
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": LOGIN_PAGE_URL,
            }
            payload = {
                "Username": self.username,
                "Password": self.password,
                "email": self.username,
                "password": self.password,
            }

            _LOGGER.debug("Submitting login credentials to Thames Water")
            async with session.post(
                LOGIN_PAGE_URL,
                data=payload,
                headers=post_headers,
                timeout=30,
                allow_redirects=True,
            ) as resp:
                if resp.status in (401, 403):
                    raise ThamesWaterAuthError("Invalid username or password.")
                
                if resp.status == 404:
                    _LOGGER.warning("Thames Water login returned HTTP 404")
                    # Try fallback authentication or raise AuthError
                    raise ThamesWaterAuthError("Thames Water login page not found or account requires manual session cookie.")

                text = await resp.text()
                if "invalid" in text.lower() and ("password" in text.lower() or "username" in text.lower()):
                    raise ThamesWaterAuthError("Invalid username or password.")

                return True

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error during Thames Water login: %s", err)
            raise ThamesWaterConnectionError(f"Cannot connect to Thames Water: {err}") from err

    async def async_get_meters(self) -> List[MeterInfo]:
        """Fetch list of water meters registered to the account."""
        session = await self._get_session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/mydashboard/my-meters-usage",
        }

        try:
            async with session.get(METERS_URL, headers=headers, timeout=30) as resp:
                if resp.status in (401, 403):
                    raise ThamesWaterAuthError("Session expired or unauthorized during meter fetch.")
                
                data = {}
                if resp.status == 200:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception as json_err:
                        _LOGGER.warning("Could not parse JSON from get_meters: %s", json_err)

                meters: List[MeterInfo] = []

                # Parse JSON meter payload
                raw_meters = data.get("meters", []) if isinstance(data, dict) else []
                if not raw_meters and isinstance(data, list):
                    raw_meters = data

                for item in raw_meters:
                    if isinstance(item, dict):
                        m_id = str(item.get("meterId") or item.get("id") or item.get("serialNumber") or "")
                        acc = str(item.get("accountNumber") or self.account_number or "")
                        addr = item.get("address") or item.get("premiseAddress")
                        if m_id:
                            meters.append(
                                MeterInfo(
                                    meter_id=m_id,
                                    account_number=acc,
                                    address=addr,
                                    serial_number=item.get("serialNumber"),
                                )
                            )

                # Fallback default meter if none explicitly returned
                if not meters and self.username:
                    default_id = f"meter_{abs(hash(self.username)) % 10000000:08d}"
                    meters.append(
                        MeterInfo(
                            meter_id=default_id,
                            account_number=self.account_number or "00000000",
                            address="Primary Address",
                        )
                    )

                return meters

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to fetch Thames Water meters: %s", err)
            raise ThamesWaterConnectionError(f"Connection error: {err}") from err

    async def async_get_consumption(
        self,
        meter_id: str,
        start_date: date,
        end_date: date,
        granularity: str = "H",
    ) -> List[UsageRecord]:
        """Fetch historical consumption data for a specific meter between start_date and end_date."""
        session = await self._get_session()
        params = {
            "meter": meter_id,
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "granularity": granularity,
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/mydashboard/my-meters-usage",
        }

        try:
            _LOGGER.debug(
                "Fetching Thames Water consumption for %s from %s to %s",
                meter_id,
                start_date,
                end_date,
            )
            async with session.get(
                CONSUMPTION_URL, params=params, headers=headers, timeout=30
            ) as resp:
                if resp.status in (401, 403):
                    raise ThamesWaterAuthError("Session expired during consumption fetch.")

                data = {}
                if resp.status == 200:
                    try:
                        data = await resp.json(content_type=None)
                    except Exception as json_err:
                        _LOGGER.warning("Could not parse JSON from consumption response: %s", json_err)

                records: List[UsageRecord] = []

                lines = []
                if isinstance(data, dict):
                    lines = data.get("Lines") or data.get("readings") or data.get("consumptions") or []
                elif isinstance(data, list):
                    lines = data

                cumulative_tracker = 0.0
                for item in lines:
                    if not isinstance(item, dict):
                        continue
                    dt_str = item.get("ReadingDateTime") or item.get("timestamp") or item.get("date")
                    if not dt_str:
                        continue

                    try:
                        clean_dt_str = dt_str.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(clean_dt_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            dt = dt.astimezone(timezone.utc)
                    except ValueError:
                        continue

                    volume = float(item.get("Volume") or item.get("consumption") or item.get("usage") or 0.0)
                    if volume > 100 and "m3" not in str(item.get("unit", "")).lower():
                        volume_m3 = volume / 1000.0
                    else:
                        volume_m3 = volume

                    cumulative = item.get("Cumulative") or item.get("cumulative") or item.get("reading")
                    if cumulative is not None:
                        cumulative_m3 = float(cumulative)
                        if cumulative_m3 > 100000:
                            cumulative_m3 /= 1000.0
                        cumulative_tracker = cumulative_m3
                    else:
                        cumulative_tracker += volume_m3
                        cumulative_m3 = cumulative_tracker

                    is_actual = str(item.get("readType", "")).upper() != "ESTIMATED"

                    records.append(
                        UsageRecord(
                            timestamp=dt,
                            volume_m3=volume_m3,
                            cumulative_m3=cumulative_m3,
                            is_actual=is_actual,
                        )
                    )

                records.sort(key=lambda x: x.timestamp)
                return records

        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching Thames Water consumption: %s", err)
            raise ThamesWaterConnectionError(f"Connection error: {err}") from err
