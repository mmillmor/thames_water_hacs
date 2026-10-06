"""Test Thames Water DataUpdateCoordinator."""
from datetime import datetime, timezone, date, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.thames_water.api import UsageRecord
from custom_components.thames_water.coordinator import ThamesWaterDataUpdateCoordinator


@pytest.mark.asyncio
async def test_coordinator_update_data():
    """Test coordinator update process and historical statistics injection."""
    hass = MagicMock()
    mock_api = AsyncMock()
    mock_api.async_login.return_value = True

    dt1 = datetime(2024, 10, 1, 10, 0, tzinfo=timezone.utc)
    dt2 = datetime(2024, 10, 1, 11, 0, tzinfo=timezone.utc)

    records = [
        UsageRecord(timestamp=dt1, volume_m3=0.015, cumulative_m3=100.015, is_actual=True),
        UsageRecord(timestamp=dt2, volume_m3=0.020, cumulative_m3=100.035, is_actual=True),
    ]

    mock_api.async_get_consumption.return_value = records

    coordinator = ThamesWaterDataUpdateCoordinator(
        hass=hass,
        api=mock_api,
        meters=["WM123456"],
        update_interval_hours=6,
    )

    with patch.object(coordinator, "_async_import_historical_statistics") as mock_import:
        data = await coordinator._async_update_data()

        assert "WM123456" in data
        meter_info = data["WM123456"]
        assert meter_info["latest_cumulative_m3"] == 100.035
        assert meter_info["latest_interval_usage_m3"] == 0.020
        assert meter_info["latest_daily_usage_l"] == 35.0  # (0.015 + 0.020) * 1000
        assert meter_info["total_records_synced"] == 2
        mock_import.assert_called_once_with("WM123456", records)
