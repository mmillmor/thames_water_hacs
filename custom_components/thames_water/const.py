"""Constants for the Thames Water integration."""

DOMAIN = "thames_water"
DEFAULT_NAME = "Thames Water"
ATTRIBUTION = "Data provided by Thames Water"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_METERS = "meters"
CONF_ACCOUNT_NUMBER = "account_number"

# Schedule daily pull at 06:00 AM local time
DEFAULT_SCHEDULE_HOUR = 6
DEFAULT_SCHEDULE_MINUTE = 0

# Sensor device classes & units
UNIT_CUBIC_METERS = "m³"
UNIT_LITERS = "L"

# Historical Statistics constants
STATISTIC_SOURCE = DOMAIN
