"""Constants for the Net Metering integration."""

DOMAIN = "net_metering"
INTEGRATION_NAME = "Net Metering"

# Config / options keys
CONF_SOLAR_SENSOR = "solar_production_sensor"
CONF_ENERGY_SENSOR = "energy_consumption_sensor"
CONF_SOLAR_SELF_RESET = "solar_self_resetting_at_midnight"
CONF_ENERGY_SELF_RESET = "energy_self_resetting_at_midnight"

# Storage keys (written to HA storage)
STORAGE_KEY = f"{DOMAIN}_state"
STORAGE_VERSION = 1

# State dict keys
STATE_CUMULATIVE_IMPORT = "cumulative_grid_import"
STATE_CUMULATIVE_EXPORT = "cumulative_grid_export"
STATE_PREV_SOLAR = "previous_solar_reference"
STATE_PREV_ENERGY = "previous_energy_reference"
STATE_LAST_DATE = "last_processed_date"
STATE_INITIALIZED = "initialized"
STATE_LAST_SCHEDULED_MINUTE = "last_scheduled_minute"
STATE_SOLAR_REF_VALID = "solar_reference_valid"
STATE_LAST_CALCULATION_TIME = "last_calculation_time"
STATE_LAST_CALCULATION_PREV_SOLAR = "last_calculation_previous_solar_reference"
STATE_LAST_CALCULATION_PREV_ENERGY = "last_calculation_previous_energy_reference"

# Timezone
TIMEZONE = "Asia/Kolkata"

# Fixed wall-clock minute schedule
# :00 :05 :10 :15 :20 :25 :29 :30 :35 :40 :45 :50 :55
SCHEDULE_MINUTES = {0, 5, 10, 15, 20, 25, 29, 30, 35, 40, 45, 50, 55}

# Entity unique ID suffixes
UNIQUE_ID_IMPORT = "grid_import"
UNIQUE_ID_EXPORT = "grid_export"
UNIQUE_ID_FAULT = "energy_consumption_fault"

# Precision
PRECISION = 6
