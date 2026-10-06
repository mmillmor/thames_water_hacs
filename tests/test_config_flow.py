"""Test Thames Water Config Flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.thames_water.api import MeterInfo, ThamesWaterAuthError
from custom_components.thames_water.config_flow import ThamesWaterConfigFlow
from custom_components.thames_water.const import (
    CONF_METERS,
    CONF_PASSWORD,
    CONF_SESSION_COOKIE,
    CONF_USERNAME,
)


@pytest.mark.asyncio
async def test_flow_user_single_meter_success():
    """Test user step with single meter auto-selection."""
    flow = ThamesWaterConfigFlow()
    flow.hass = MagicMock()

    meter = MeterInfo(meter_id="WM123", account_number="ACC1")

    with patch(
        "custom_components.thames_water.config_flow.ThamesWaterAPI"
    ) as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.async_login = AsyncMock(return_value=True)
        mock_api.async_get_meters = AsyncMock(return_value=[meter])

        result = await flow.async_step_user(
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "password"}
        )

        assert result["type"] == "create_entry"
        assert result["title"] == "Thames Water (test@example.com)"
        assert result["data"] == {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "password",
            CONF_SESSION_COOKIE: None,
            CONF_METERS: ["WM123"],
        }


@pytest.mark.asyncio
async def test_flow_user_invalid_auth():
    """Test user step with invalid authentication."""
    flow = ThamesWaterConfigFlow()
    flow.hass = MagicMock()

    with patch(
        "custom_components.thames_water.config_flow.ThamesWaterAPI"
    ) as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.async_login.side_effect = ThamesWaterAuthError("Invalid credentials")

        result = await flow.async_step_user(
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "wrong_password"}
        )

        assert result["type"] == "form"
        assert result["errors"] == {"base": "invalid_auth"}
