"""The Thames Water integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ThamesWaterAPI
from .const import CONF_METERS, CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .coordinator import ThamesWaterDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thames Water from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    meters = entry.data.get(CONF_METERS, [])

    session = async_get_clientsession(hass)
    api = ThamesWaterAPI(username, password, session=session)

    coordinator = ThamesWaterDataUpdateCoordinator(
        hass,
        api=api,
        meters=meters,
    )

    # Schedule daily pull at 06:00 AM local time
    coordinator.async_setup_schedule()

    # Perform initial data fetch & historical statistics import upon setup/restart
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: ThamesWaterDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.unload()
        await coordinator.api.close()

    return unload_ok
