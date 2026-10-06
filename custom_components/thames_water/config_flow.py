"""Config flow for Thames Water integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ThamesWaterAPI, ThamesWaterAuthError, ThamesWaterConnectionError, MeterInfo
from .const import CONF_PASSWORD, CONF_SESSION_COOKIE, CONF_USERNAME, CONF_METERS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ThamesWaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thames Water."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        self._session_cookie: Optional[str] = None
        self._available_meters: List[MeterInfo] = []

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle initial step: user enters credentials or session cookie."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            self._password = user_input.get(CONF_PASSWORD, "").strip()
            self._session_cookie = user_input.get(CONF_SESSION_COOKIE, "").strip() or None

            await self.async_set_unique_id(self._username.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = ThamesWaterAPI(
                self._username,
                self._password,
                session_cookie=self._session_cookie,
                session=session,
            )

            try:
                await api.async_login()
                meters = await api.async_get_meters()
                self._available_meters = meters

                if not meters:
                    default_meter = MeterInfo(
                        meter_id=f"meter_{abs(hash(self._username)) % 10000000:08d}",
                        account_number="Primary Account",
                    )
                    self._available_meters = [default_meter]

                if len(self._available_meters) == 1:
                    selected_meter = self._available_meters[0].meter_id
                    return self.async_create_entry(
                        title=f"Thames Water ({self._username})",
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                            CONF_SESSION_COOKIE: self._session_cookie,
                            CONF_METERS: [selected_meter],
                        },
                    )

                return await self.async_step_meters()

            except ThamesWaterAuthError:
                errors["base"] = "invalid_auth"
            except ThamesWaterConnectionError:
                errors["base"] = "cannot_connect"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error during Thames Water authentication: %s", err)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_SESSION_COOKIE, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_meters(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle step 2: User selects which meters to add."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            selected_meters = user_input.get(CONF_METERS, [])
            if selected_meters:
                return self.async_create_entry(
                    title=f"Thames Water ({self._username})",
                    data={
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                        CONF_SESSION_COOKIE: self._session_cookie,
                        CONF_METERS: selected_meters,
                    },
                )
            errors["base"] = "no_meters_selected"

        meter_options = {
            m.meter_id: f"Meter {m.meter_id} ({m.address or m.account_number})"
            for m in self._available_meters
        }

        return self.async_show_form(
            step_id="meters",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_METERS, default=list(meter_options.keys())
                    ): cv_multi_select(meter_options)
                }
            ),
            errors=errors,
        )


def cv_multi_select(options: Dict[str, str]):
    """Helper validator for multi-select options in HA UI."""
    return vol.All(vol.Coerce(list), [vol.In(options)])
