"""Test Thames Water API client."""
from datetime import date, datetime, timezone
import pytest
from unittest.mock import MagicMock, patch

from thameswaterapi import AuthenticationError, Line, MeterUsage, MetersResponse

from custom_components.thames_water.api import (
    ThamesWaterAPI,
    ThamesWaterAuthError,
    ThamesWaterConnectionError,
    UsageRecord,
)


@pytest.mark.asyncio
async def test_login_success():
    """Test successful login."""
    with patch("custom_components.thames_water.api.ThamesWater") as mock_cls:
        mock_client = MagicMock()
        mock_client.account_number = 12345678
        mock_cls.return_value = mock_client

        api = ThamesWaterAPI("test@example.com", "password")
        result = await api.async_login()

        assert result is True
        assert api.account_number == "12345678"
        mock_client.authenticate.assert_called_once()


@pytest.mark.asyncio
async def test_login_invalid_auth():
    """Test login with invalid credentials."""
    with patch("custom_components.thames_water.api.ThamesWater") as mock_cls:
        mock_client = MagicMock()
        mock_client.authenticate.side_effect = AuthenticationError("Invalid login")
        mock_cls.return_value = mock_client

        api = ThamesWaterAPI("test@example.com", "wrong_password")

        with pytest.raises(ThamesWaterAuthError):
            await api.async_login()


@pytest.mark.asyncio
async def test_login_connection_error():
    """Test login with network/connection error."""
    with patch("custom_components.thames_water.api.ThamesWater") as mock_cls:
        mock_client = MagicMock()
        mock_client.authenticate.side_effect = ConnectionError("Network down")
        mock_cls.return_value = mock_client

        api = ThamesWaterAPI("test@example.com", "password")

        with pytest.raises(ThamesWaterConnectionError):
            await api.async_login()


@pytest.mark.asyncio
async def test_get_meters():
    """Test retrieving meters."""
    with patch("custom_components.thames_water.api.ThamesWater") as mock_cls:
        mock_client = MagicMock()
        mock_client.account_number = 12345678
        mock_client.get_meters.return_value = MagicMock(
            Meters=["WM123456", "WM654321"],
            Lines=[],
        )
        mock_cls.return_value = mock_client

        api = ThamesWaterAPI("test@example.com", "password")
        meters = await api.async_get_meters()

        assert len(meters) == 2
        assert meters[0].meter_id == "WM123456"
        assert meters[0].account_number == "12345678"
        assert meters[1].meter_id == "WM654321"


@pytest.mark.asyncio
async def test_get_consumption_parsing():
    """Test fetching and parsing historical consumption records."""
    with patch("custom_components.thames_water.api.ThamesWater") as mock_cls:
        mock_client = MagicMock()
        mock_client.account_number = 12345678

        # Mock hourly meter usage lines for 2026-10-01
        line1 = Line(
            Label="0:00",
            Usage=25.0,  # 25 L = 0.025 m3
            Read=150025.0,  # 150025 L = 150.025 m3
            IsEstimated=False,
            MeterSerialNumberHis="WM123456",
        )
        line2 = Line(
            Label="1:00",
            Usage=10.0,  # 10 L = 0.010 m3
            Read=150035.0,  # 150035 L = 150.035 m3
            IsEstimated=False,
            MeterSerialNumberHis="WM123456",
        )

        mock_usage = MagicMock(Lines=[line1, line2])
        mock_client.get_meter_usage.return_value = mock_usage
        mock_client.get_meters.return_value = MagicMock(Meters=["WM123456"], Lines=[])
        mock_cls.return_value = mock_client

        api = ThamesWaterAPI("test@example.com", "password")
        records = await api.async_get_consumption(
            "WM123456", date(2026, 10, 1), date(2026, 10, 1)
        )

        assert len(records) == 2
        assert records[0].volume_m3 == 0.025
        assert records[0].cumulative_m3 == 150.025
        assert records[1].volume_m3 == 0.010
        assert records[1].cumulative_m3 == 150.035


@pytest.mark.asyncio
async def test_get_consumption_skips_when_no_data_available():
    """Test that days with IsDataAvailable=False are skipped."""
    with patch("custom_components.thames_water.api.ThamesWater") as mock_cls:
        mock_client = MagicMock()
        mock_client.account_number = 12345678

        # Mock day with placeholder lines but IsDataAvailable=False
        line1 = Line(
            Label="0:00",
            Usage=0.0,
            Read=0.0,
            IsEstimated=True,
            MeterSerialNumberHis="WM123456",
        )
        mock_usage = MagicMock(
            Lines=[line1],
            IsError=False,
            IsDataAvailable=False,
            IsConsumptionAvailable=False,
        )
        mock_client.get_meter_usage.return_value = mock_usage
        mock_client.get_meters.return_value = MagicMock(Meters=["WM123456"], Lines=[])
        mock_cls.return_value = mock_client

        api = ThamesWaterAPI("test@example.com", "password")
        records = await api.async_get_consumption(
            "WM123456", date(2026, 10, 14), date(2026, 10, 14)
        )

        # Because IsDataAvailable is False, no records should be ingested
        assert len(records) == 0


@pytest.mark.asyncio
async def test_get_consumption_monotonic_cumulative_repair():
    """Test that fluctuating or 0 Read values are repaired to be strictly monotonic."""
    with patch("custom_components.thames_water.api.ThamesWater") as mock_cls:
        mock_client = MagicMock()
        mock_client.account_number = 12345678

        # Line 1: Normal read 1000L
        # Line 2: Glitched read 0L (dropped!) but 20L usage
        # Line 3: Read returns to 1030L
        line1 = Line(Label="0:00", Usage=10.0, Read=1000.0, IsEstimated=False, MeterSerialNumberHis="WM123456")
        line2 = Line(Label="1:00", Usage=20.0, Read=0.0, IsEstimated=False, MeterSerialNumberHis="WM123456")
        line3 = Line(Label="2:00", Usage=10.0, Read=1030.0, IsEstimated=False, MeterSerialNumberHis="WM123456")

        mock_usage = MagicMock(Lines=[line1, line2, line3], IsError=False, IsDataAvailable=True, IsConsumptionAvailable=True)
        mock_client.get_meter_usage.return_value = mock_usage
        mock_client.get_meters.return_value = MagicMock(Meters=["WM123456"], Lines=[])
        mock_cls.return_value = mock_client

        api = ThamesWaterAPI("test@example.com", "password")
        records = await api.async_get_consumption(
            "WM123456", date(2026, 10, 1), date(2026, 10, 1)
        )

        assert len(records) == 3
        # First reading: 1000L = 1.0 m3
        assert records[0].cumulative_m3 == 1.0
        # Second reading: should advance by volume (0.02 m3) to 1.02 m3, NOT drop to 0.0
        assert records[1].cumulative_m3 == 1.02
        # Third reading: syncs with valid read 1.03 m3
        assert records[2].cumulative_m3 == 1.03

