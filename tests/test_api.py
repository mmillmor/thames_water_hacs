"""Test Thames Water API client."""
from datetime import date, datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.thames_water.api import (
    ThamesWaterAPI,
    ThamesWaterAuthError,
    ThamesWaterConnectionError,
    UsageRecord,
)


def create_mock_session(resp_status=200, json_data=None, text_data=""):
    """Helper to create a properly mocked aiohttp ClientSession and response."""
    mock_resp = MagicMock()
    mock_resp.status = resp_status
    mock_resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    mock_resp.text = AsyncMock(return_value=text_data)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

    return mock_session, mock_resp


@pytest.mark.asyncio
async def test_login_success():
    """Test successful login."""
    mock_session, _ = create_mock_session(
        resp_status=200, json_data={"success": True, "accountNumber": "12345678"}
    )

    api = ThamesWaterAPI("test@example.com", "password", session=mock_session)
    result = await api.async_login()

    assert result is True
    assert api.account_number == "12345678"


@pytest.mark.asyncio
async def test_login_invalid_auth():
    """Test login with invalid credentials."""
    mock_session, _ = create_mock_session(
        resp_status=401, text_data="Unauthorized"
    )

    api = ThamesWaterAPI("test@example.com", "wrong_password", session=mock_session)

    with pytest.raises(ThamesWaterAuthError):
        await api.async_login()


@pytest.mark.asyncio
async def test_get_meters():
    """Test retrieving meters."""
    mock_session, _ = create_mock_session(
        resp_status=200,
        json_data={
            "meters": [
                {
                    "meterId": "WM123456",
                    "accountNumber": "ACC999",
                    "address": "10 Downing Street",
                },
                {
                    "meterId": "WM654321",
                    "accountNumber": "ACC999",
                    "address": "11 Downing Street",
                },
            ]
        },
    )

    api = ThamesWaterAPI("test@example.com", "password", session=mock_session)
    meters = await api.async_get_meters()

    assert len(meters) == 2
    assert meters[0].meter_id == "WM123456"
    assert meters[0].address == "10 Downing Street"
    assert meters[1].meter_id == "WM654321"


@pytest.mark.asyncio
async def test_get_consumption_parsing():
    """Test fetching and parsing historical consumption records."""
    mock_session, _ = create_mock_session(
        resp_status=200,
        json_data={
            "Lines": [
                {
                    "ReadingDateTime": "2024-10-01T00:00:00Z",
                    "Volume": 0.025,
                    "Cumulative": 150.025,
                    "readType": "ACTUAL",
                },
                {
                    "ReadingDateTime": "2024-10-01T01:00:00Z",
                    "Volume": 0.010,
                    "Cumulative": 150.035,
                    "readType": "ACTUAL",
                },
            ]
        },
    )

    api = ThamesWaterAPI("test@example.com", "password", session=mock_session)
    records = await api.async_get_consumption(
        "WM123456", date(2024, 10, 1), date(2024, 10, 2)
    )

    assert len(records) == 2
    assert records[0].volume_m3 == 0.025
    assert records[0].cumulative_m3 == 150.025
    assert records[1].volume_m3 == 0.010
    assert records[1].cumulative_m3 == 150.035
