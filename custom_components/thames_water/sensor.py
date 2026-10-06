"""Sensor platform for Thames Water integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_METERS, DOMAIN, STATISTIC_SOURCE
from .coordinator import ThamesWaterDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Thames Water sensors based on a config entry."""
    coordinator: ThamesWaterDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    meters = entry.data.get(CONF_METERS, [])

    entities: list[SensorEntity] = []
    for meter_id in meters:
        entities.append(ThamesWaterConsumptionSensor(coordinator, meter_id))
        entities.append(ThamesWaterLatestDailyUsageSensor(coordinator, meter_id))

    async_add_entities(entities)


class ThamesWaterBaseSensor(CoordinatorEntity[ThamesWaterDataUpdateCoordinator], SensorEntity):
    """Base class for Thames Water sensors."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ThamesWaterDataUpdateCoordinator,
        meter_id: str,
    ) -> None:
        """Initialize the base sensor."""
        super().__init__(coordinator)
        self.meter_id = meter_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, meter_id)},
            "name": f"Thames Water Meter {meter_id}",
            "manufacturer": "Thames Water",
            "model": "Smart Water Meter",
        }

    @property
    def meter_data(self) -> Dict[str, Any]:
        """Get coordinator data for this meter."""
        if self.coordinator.data and self.meter_id in self.coordinator.data:
            return self.coordinator.data[self.meter_id]
        return {}


class ThamesWaterConsumptionSensor(ThamesWaterBaseSensor):
    """Sensor tracking Thames Water cumulative consumption (m3)."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS

    def __init__(
        self,
        coordinator: ThamesWaterDataUpdateCoordinator,
        meter_id: str,
    ) -> None:
        """Initialize cumulative consumption sensor."""
        super().__init__(coordinator, meter_id)
        self._attr_name = "Cumulative Consumption"
        self._attr_unique_id = f"{DOMAIN}_{meter_id}_cumulative_consumption"

    @property
    def native_value(self) -> Optional[float]:
        """Return the latest cumulative meter reading in m3."""
        val = self.meter_data.get("latest_cumulative_m3")
        return round(val, 3) if val is not None else None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        data = self.meter_data
        reading_time = data.get("latest_reading_time")
        return {
            "meter_id": self.meter_id,
            "last_reading_time": reading_time.isoformat() if reading_time else None,
            "data_lag_days": data.get("data_lag_days", 3),
            "latest_interval_usage_m3": data.get("latest_interval_usage_m3"),
            "is_actual_reading": data.get("is_actual", True),
            "historical_statistics_id": f"{STATISTIC_SOURCE}:{self.meter_id}_water_consumption",
            "total_historical_records_synced": data.get("total_records_synced", 0),
            "note": "Historical past values are populated automatically in Home Assistant Energy/Water statistics.",
        }


class ThamesWaterLatestDailyUsageSensor(ThamesWaterBaseSensor):
    """Sensor tracking Thames Water daily usage (Liters) for the latest available reported day."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS

    def __init__(
        self,
        coordinator: ThamesWaterDataUpdateCoordinator,
        meter_id: str,
    ) -> None:
        """Initialize latest daily usage sensor."""
        super().__init__(coordinator, meter_id)
        self._attr_name = "Latest Daily Usage"
        self._attr_unique_id = f"{DOMAIN}_{meter_id}_latest_daily_usage"

    @property
    def native_value(self) -> Optional[float]:
        """Return latest reported daily usage in Liters."""
        val = self.meter_data.get("latest_daily_usage_l")
        return round(val, 1) if val is not None else None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        data = self.meter_data
        return {
            "meter_id": self.meter_id,
            "reading_date": data.get("latest_reading_date"),
            "data_lag_days": data.get("data_lag_days", 3),
            "daily_usage_m3": data.get("latest_daily_usage_m3"),
            "note": "Data lag is typically ~3 days from Thames Water.",
        }
