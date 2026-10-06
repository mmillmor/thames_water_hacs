"""DataUpdateCoordinator for Thames Water integration."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any, Callable, Dict, List, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ThamesWaterAPI, ThamesWaterError, UsageRecord
from .const import DEFAULT_SCHEDULE_HOUR, DEFAULT_SCHEDULE_MINUTE, DOMAIN, STATISTIC_SOURCE

_LOGGER = logging.getLogger(__name__)


class ThamesWaterDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching Thames Water data and importing historical statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ThamesWaterAPI,
        meters: List[str],
        schedule_hour: int = DEFAULT_SCHEDULE_HOUR,
        schedule_minute: int = DEFAULT_SCHEDULE_MINUTE,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # Scheduled at specific time of day rather than polling interval
        )
        self.api = api
        self.meters = meters
        self.schedule_hour = schedule_hour
        self.schedule_minute = schedule_minute
        self._unsub_time_track: Optional[Callable[[], None]] = None
        self._initial_fetch_done: bool = False

    def async_setup_schedule(self) -> None:
        """Schedule coordinator to refresh daily at fixed time (default 06:00 AM)."""
        if self._unsub_time_track:
            self._unsub_time_track()
            self._unsub_time_track = None

        @callback
        async def _async_scheduled_update(*_: Any) -> None:
            _LOGGER.info(
                "Executing scheduled daily Thames Water update at %02d:%02d",
                self.schedule_hour,
                self.schedule_minute,
            )
            await self.async_request_refresh()

        try:
            self._unsub_time_track = async_track_time_change(
                self.hass,
                _async_scheduled_update,
                hour=self.schedule_hour,
                minute=self.schedule_minute,
                second=0,
            )
            _LOGGER.info(
                "Thames Water daily update scheduled for %02d:%02d local time",
                self.schedule_hour,
                self.schedule_minute,
            )
        except Exception as err:
            _LOGGER.warning("Could not register time change tracker: %s", err)

    def unload(self) -> None:
        """Unsubscribe from schedule timer when integration is unloaded."""
        if self._unsub_time_track:
            self._unsub_time_track()
            self._unsub_time_track = None

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Thames Water API and import past values to HA statistics."""
        data: Dict[str, Any] = {}
        end_date = date.today()

        if not self._initial_fetch_done:
            # First run: fetch past 365 days (1 year) to backfill historical statistics
            start_date = end_date - timedelta(days=365)
            self._initial_fetch_done = True
            _LOGGER.info("Performing initial Thames Water backfill for past 365 days")
        else:
            # Subsequent daily pulls: fetch past 7 days to cover publication lag and adjustments
            start_date = end_date - timedelta(days=7)

        try:
            # Ensure API is authenticated
            await self.api.async_login()
        except ThamesWaterError as err:
            _LOGGER.error("Authentication failed during coordinator update: %s", err)
            raise UpdateFailed(f"Authentication failed: {err}") from err

        for meter_id in self.meters:
            try:
                _LOGGER.debug(
                    "Fetching past readings for meter %s from %s to %s",
                    meter_id,
                    start_date,
                    end_date,
                )
                records = await self.api.async_get_consumption(
                    meter_id=meter_id,
                    start_date=start_date,
                    end_date=end_date,
                    granularity="H",
                )

                if records:
                    # Import historical readings into HA Recorder Statistics
                    await self._async_import_historical_statistics(meter_id, records)

                    latest_record = records[-1]
                    today_utc = datetime.now(timezone.utc).date()
                    latest_date = latest_record.timestamp.date()
                    lag_days = (today_utc - latest_date).days

                    # Calculate latest complete day total in Liters
                    latest_day_records = [
                        r for r in records if r.timestamp.date() == latest_date
                    ]
                    latest_day_total_m3 = sum(r.volume_m3 for r in latest_day_records)
                    latest_day_total_l = round(latest_day_total_m3 * 1000.0, 2)

                    data[meter_id] = {
                        "latest_reading_time": latest_record.timestamp,
                        "latest_cumulative_m3": latest_record.cumulative_m3,
                        "latest_interval_usage_m3": latest_record.volume_m3,
                        "latest_daily_usage_l": latest_day_total_l,
                        "latest_daily_usage_m3": round(latest_day_total_m3, 4),
                        "latest_reading_date": latest_date.isoformat(),
                        "data_lag_days": max(0, lag_days),
                        "total_records_synced": len(records),
                        "is_actual": latest_record.is_actual,
                    }
                else:
                    _LOGGER.warning("No consumption records returned for meter %s", meter_id)
                    data[meter_id] = {
                        "latest_reading_time": None,
                        "latest_cumulative_m3": 0.0,
                        "latest_interval_usage_m3": 0.0,
                        "latest_daily_usage_l": 0.0,
                        "latest_daily_usage_m3": 0.0,
                        "latest_reading_date": None,
                        "data_lag_days": 3,
                        "total_records_synced": 0,
                        "is_actual": False,
                    }

            except ThamesWaterError as err:
                _LOGGER.error("Failed to update meter %s: %s", meter_id, err)
                # Retain existing data if available
                if self.data and meter_id in self.data:
                    data[meter_id] = self.data[meter_id]
                else:
                    data[meter_id] = {}

        return data

    async def _async_import_historical_statistics(
        self, meter_id: str, records: List[UsageRecord]
    ) -> None:
        """Inject historical consumption data points into Home Assistant long-term statistics."""
        if not records:
            return

        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.models import (
                StatisticData,
                StatisticMetaData,
                StatisticMeanType,
            )
            mean_type = StatisticMeanType.NONE
        except (ImportError, AttributeError):
            try:
                from homeassistant.components.recorder.models import (
                    StatisticData,
                    StatisticMetaData,
                )
                mean_type = 0  # type: ignore
            except ImportError:
                _LOGGER.debug(
                    "Recorder component not loaded or available; skipping statistic import."
                )
                return

        # Prepare StatisticData objects for each historical timestamp
        statistic_data_list: List[StatisticData] = []
        for rec in records:
            stat_entry: Dict[str, Any] = {
                "start": rec.timestamp,
                "state": rec.volume_m3,        # Incremental usage in m3
                "sum": rec.cumulative_m3,      # Running total meter reading in m3
            }
            statistic_data_list.append(stat_entry)  # type: ignore

        statistic_id = f"{STATISTIC_SOURCE}:{meter_id}_water_consumption"
        entity_statistic_id = f"sensor.thames_water_meter_{meter_id.lower()}_cumulative_consumption"

        # Build StatisticMetaData for external statistics (used by HA Energy Dashboard)
        meta: Dict[str, Any] = {
            "has_mean": False,
            "has_sum": True,
            "mean_type": mean_type,
            "unit_of_measurement": "m³",
            "unit_class": "volume",
            "source": STATISTIC_SOURCE,
            "statistic_id": statistic_id,
            "name": f"Thames Water Meter {meter_id} Consumption",
        }

        # Build StatisticMetaData for entity statistics (used by entity More Info graph)
        entity_meta: Dict[str, Any] = {
            "has_mean": False,
            "has_sum": True,
            "mean_type": mean_type,
            "unit_of_measurement": "m³",
            "unit_class": "volume",
            "source": "recorder",
            "statistic_id": entity_statistic_id,
            "name": f"Thames Water Meter {meter_id} Cumulative Consumption",
        }

        _LOGGER.info(
            "Importing %d historical statistic data points for meter %s (ID: %s)",
            len(statistic_data_list),
            meter_id,
            statistic_id,
        )

        try:
            from homeassistant.components.recorder.statistics import (
                async_add_external_statistics,
                async_import_statistics,
            )
        except ImportError:
            return

        # 1. Add as external statistic source (available to HA Energy/Water dashboard)
        try:
            async_add_external_statistics(self.hass, meta, statistic_data_list)
            _LOGGER.debug("External statistics successfully injected for %s", statistic_id)
        except Exception as err:
            _LOGGER.warning(
                "Failed to import external statistics for %s: %s",
                statistic_id,
                err,
            )

        # 2. Also import directly to the sensor entity's statistics if recorder is active
        try:
            async_import_statistics(self.hass, entity_meta, statistic_data_list)
            _LOGGER.debug("Entity statistics successfully injected for %s", entity_statistic_id)
        except Exception as err:
            _LOGGER.warning(
                "Failed to import entity statistics for %s: %s",
                entity_statistic_id,
                err,
            )
