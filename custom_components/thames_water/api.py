"""API client for Thames Water using thameswaterapi library."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from thameswaterapi import (
    Account,
    AuthenticationError,
    MeterUsage,
    MetersResponse,
    Tariff,
    ThamesWater,
    get_tariff,
    lines_to_timeseries,
    meter_usage_lines_to_timeseries,
)

_LOGGER = logging.getLogger(__name__)

LONDON_TZ = ZoneInfo("Europe/London")


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
    """API Client for Thames Water portal using thameswaterapi."""

    def __init__(
        self,
        username: str,
        password: str,
        account_number: Optional[str] = None,
        session: Optional[Any] = None,
    ) -> None:
        """Initialize the API client."""
        self.username = username
        self.password = password
        self.account_number = account_number
        self._session = session  # kept for signature compatibility
        self._client: Optional[ThamesWater] = None
        self._meters_response: Optional[MetersResponse] = None

    def _get_or_create_client(self) -> ThamesWater:
        """Return or instantiate the ThamesWater client."""
        if self._client is None:
            acc_num = int(self.account_number) if self.account_number and self.account_number.isdigit() else None
            self._client = ThamesWater(
                email=self.username,
                password=self.password,
                account_number=acc_num,
            )
        return self._client

    async def close(self) -> None:
        """Close/reset client session."""
        if self._client is not None:
            try:
                await asyncio.to_thread(self._client.logout)
            except Exception:
                pass
            self._client = None
        self._meters_response = None

    async def async_login(self) -> bool:
        """Authenticate with Thames Water B2C portal."""
        client = self._get_or_create_client()
        _LOGGER.debug("Authenticating with Thames Water for user %s", self.username)

        try:
            await asyncio.to_thread(client.authenticate)
        except AuthenticationError as err:
            _LOGGER.error("Thames Water authentication rejected credentials: %s", err)
            raise ThamesWaterAuthError(f"Invalid credentials: {err}") from err
        except Exception as err:
            _LOGGER.error("Failed to connect to Thames Water during login: %s", err)
            raise ThamesWaterConnectionError(f"Connection failed: {err}") from err

        if not self.account_number and client.account_number:
            self.account_number = str(client.account_number)

        _LOGGER.info(
            "Successfully authenticated with Thames Water for user %s (Account: %s)",
            self.username,
            self.account_number,
        )
        return True

    async def async_get_meters(self) -> List[MeterInfo]:
        """Fetch list of active meters for the account."""
        client = self._get_or_create_client()

        try:
            meters_resp: MetersResponse = await asyncio.to_thread(client.get_meters)
            self._meters_response = meters_resp
        except AuthenticationError as err:
            raise ThamesWaterAuthError(f"Authentication expired: {err}") from err
        except Exception as err:
            raise ThamesWaterConnectionError(f"Failed to fetch meters: {err}") from err

        acc_str = str(client.account_number or self.account_number or "")
        meters: List[MeterInfo] = []

        for meter_id in meters_resp.Meters:
            meters.append(
                MeterInfo(
                    meter_id=str(meter_id),
                    account_number=acc_str,
                    address=None,
                    serial_number=str(meter_id),
                )
            )

        # Fallback if meter list was empty in MetersResponse
        if not meters:
            try:
                meter_numbers = await asyncio.to_thread(client.get_meter_numbers)
                for m_id in meter_numbers:
                    meters.append(
                        MeterInfo(
                            meter_id=str(m_id),
                            account_number=acc_str,
                            address=None,
                            serial_number=str(m_id),
                        )
                    )
            except Exception as err:
                _LOGGER.debug("Could not fetch meter numbers fallback: %s", err)

        return meters

    async def async_get_consumption(
        self,
        meter_id: str,
        start_date: date,
        end_date: date,
        granularity: str = "H",
    ) -> List[UsageRecord]:
        """Fetch historical water consumption records.

        Attempts hourly resolution for recent dates (which Thames Water supports
        at single-day granularity), and supplements with daily measurements
        for older dates or where hourly data is not available.
        """
        client = self._get_or_create_client()
        records: List[UsageRecord] = []
        covered_dates: set[date] = set()

        # Step 1: Hourly records for days in range (up to 7 days back)
        hourly_start = max(start_date, end_date - timedelta(days=7))
        current_day = hourly_start

        while current_day <= end_date:
            try:
                usage: MeterUsage = await asyncio.to_thread(
                    client.get_meter_usage, meter_id, current_day, current_day, "H"
                )
                if usage.Lines:
                    hourly_measurements = meter_usage_lines_to_timeseries(
                        current_day, usage.Lines
                    )
                    for m in hourly_measurements:
                        utc_ts = m.hour_start.astimezone(timezone.utc)
                        records.append(
                            UsageRecord(
                                timestamp=utc_ts,
                                volume_m3=round(m.usage / 1000.0, 5),
                                cumulative_m3=round(m.total / 1000.0, 5),
                                is_actual=True,
                            )
                        )
                    covered_dates.add(current_day)
            except Exception as err:
                _LOGGER.debug("Could not fetch hourly usage for %s: %s", current_day, err)

            current_day += timedelta(days=1)

        # Step 2: Daily records for dates not covered by hourly
        try:
            if self._meters_response is None:
                self._meters_response = await asyncio.to_thread(client.get_meters)

            if self._meters_response and self._meters_response.Lines:
                daily_measurements = lines_to_timeseries(self._meters_response.Lines)
                for dm in daily_measurements:
                    if dm.start in covered_dates:
                        continue
                    if start_date <= dm.start <= end_date:
                        local_dt = datetime(
                            dm.start.year, dm.start.month, dm.start.day, tzinfo=LONDON_TZ
                        )
                        utc_ts = local_dt.astimezone(timezone.utc)
                        records.append(
                            UsageRecord(
                                timestamp=utc_ts,
                                volume_m3=round(dm.usage / 1000.0, 5),
                                cumulative_m3=round(dm.total / 1000.0, 5),
                                is_actual=True,
                            )
                        )
                        covered_dates.add(dm.start)
        except Exception as err:
            _LOGGER.debug("Could not parse daily measurements from get_meters: %s", err)

        # Step 3: For older history if requested and not covered yet
        if start_date < end_date - timedelta(days=7):
            try:
                older_usage: MeterUsage = await asyncio.to_thread(
                    client.get_meter_usage,
                    meter_id,
                    start_date,
                    min(end_date, start_date + timedelta(days=30)),
                    "D",
                )
                if older_usage.Lines:
                    older_measurements = lines_to_timeseries(older_usage.Lines)
                    for dm in older_measurements:
                        if dm.start not in covered_dates and start_date <= dm.start <= end_date:
                            local_dt = datetime(
                                dm.start.year, dm.start.month, dm.start.day, tzinfo=LONDON_TZ
                            )
                            utc_ts = local_dt.astimezone(timezone.utc)
                            records.append(
                                UsageRecord(
                                    timestamp=utc_ts,
                                    volume_m3=round(dm.usage / 1000.0, 5),
                                    cumulative_m3=round(dm.total / 1000.0, 5),
                                    is_actual=True,
                                )
                            )
                            covered_dates.add(dm.start)
            except Exception as err:
                _LOGGER.debug("Could not fetch older daily usage: %s", err)

        # Sort all records chronologically
        records.sort(key=lambda r: r.timestamp)
        return records

    async def async_get_account(self) -> Account:
        """Fetch account information."""
        client = self._get_or_create_client()
        return await asyncio.to_thread(client.get_account)

    async def async_get_tariff(self) -> Tariff:
        """Fetch current water tariff."""
        return await asyncio.to_thread(get_tariff)
