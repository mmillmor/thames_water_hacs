"""Test Thames Water DataUpdateCoordinator."""
from datetime import datetime, timezone, date, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.thames_water.api import UsageRecord
from custom_components.thames_water.coordinator import ThamesWaterDataUpdateCoordinator


@pytest.mark.asyncio
async def test_coordinator_initial_and_subsequent_pulls():
    """Test initial pull (365 days) vs subsequent daily pull (30 days)."""
    hass = MagicMock()
    mock_api = AsyncMock()
    mock_api.async_login.return_value = True

    dt1 = datetime(2024, 10, 1, 10, 0, tzinfo=timezone.utc)
    records = [
        UsageRecord(timestamp=dt1, volume_m3=0.015, cumulative_m3=100.015, is_actual=True),
    ]
    mock_api.async_get_consumption.return_value = records

    coordinator = ThamesWaterDataUpdateCoordinator(
        hass=hass,
        api=mock_api,
        meters=["WM123456"],
        schedule_hour=6,
        schedule_minute=0,
    )

    with patch.object(coordinator, "_async_import_historical_statistics"):
        # First pull: should request past 365 days
        await coordinator._async_update_data()
        assert coordinator._initial_fetch_done is True
        call_args_1 = mock_api.async_get_consumption.call_args[1]
        assert (date.today() - call_args_1["start_date"]).days == 365

        # Second pull: should request past 7 days
        await coordinator._async_update_data()
        call_args_2 = mock_api.async_get_consumption.call_args[1]
        assert (date.today() - call_args_2["start_date"]).days == 7


@pytest.mark.asyncio
async def test_coordinator_schedule_setup():
    """Test daily schedule registration at 06:00 AM."""
    hass = MagicMock()
    mock_api = AsyncMock()

    coordinator = ThamesWaterDataUpdateCoordinator(
        hass=hass,
        api=mock_api,
        meters=["WM123456"],
        schedule_hour=6,
        schedule_minute=0,
    )

    with patch("custom_components.thames_water.coordinator.async_track_time_change") as mock_track:
        mock_track.return_value = MagicMock()
        coordinator.async_setup_schedule()

        mock_track.assert_called_once()
        _, kwargs = mock_track.call_args
        assert kwargs["hour"] == 6
        assert kwargs["minute"] == 0
        assert kwargs["second"] == 0
