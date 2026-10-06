"""Pytest configuration and mocks for Home Assistant modules."""
import sys
from unittest.mock import AsyncMock, MagicMock

# Mock homeassistant packages
ha_mock = MagicMock()

# Set up submodule attributes
ha_mock.config_entries = MagicMock()
ha_mock.core = MagicMock()
ha_mock.const = MagicMock()
ha_mock.data_entry_flow = MagicMock()
ha_mock.helpers = MagicMock()
ha_mock.components = MagicMock()

sys.modules["homeassistant"] = ha_mock
sys.modules["homeassistant.config_entries"] = ha_mock.config_entries
sys.modules["homeassistant.core"] = ha_mock.core
sys.modules["homeassistant.const"] = ha_mock.const
sys.modules["homeassistant.data_entry_flow"] = ha_mock.data_entry_flow
sys.modules["homeassistant.helpers"] = ha_mock.helpers
sys.modules["homeassistant.helpers.aiohttp_client"] = ha_mock.helpers.aiohttp_client
sys.modules["homeassistant.helpers.update_coordinator"] = ha_mock.helpers.update_coordinator
sys.modules["homeassistant.components"] = ha_mock.components
sys.modules["homeassistant.components.sensor"] = ha_mock.components.sensor
sys.modules["homeassistant.components.recorder"] = ha_mock.components.recorder
sys.modules["homeassistant.components.recorder.models"] = ha_mock.components.recorder.models
sys.modules["homeassistant.components.recorder.statistics"] = ha_mock.components.recorder.statistics


class MockConfigFlow:
    """Mock ConfigFlow base class."""

    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self):
        self.hass = None

    async def async_set_unique_id(self, unique_id, raise_on_progress=True):
        pass

    def _abort_if_unique_id_configured(self, updates=None, reload_on_update=True):
        pass

    def async_create_entry(self, *, title, data, options=None):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id, data_schema=None, errors=None, description_placeholders=None):
        return {"type": "form", "step_id": step_id, "errors": errors}


ha_mock.config_entries.ConfigFlow = MockConfigFlow


class MockDataUpdateCoordinator:
    """Mock DataUpdateCoordinator base class."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, name, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = {}

    async def async_config_entry_first_refresh(self):
        pass


ha_mock.helpers.update_coordinator.DataUpdateCoordinator = MockDataUpdateCoordinator
ha_mock.helpers.update_coordinator.UpdateFailed = Exception
