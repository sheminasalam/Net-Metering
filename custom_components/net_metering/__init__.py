"""Net Metering – custom Home Assistant integration.

Calculates cumulative Grid Import and Grid Export from:
  - Solar Production Sensor  (SolarMan / inverter day-total)
  - Energy Consumption Sensor (ESP32/ESPHome cumulative total)

No grid meter hardware is required.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GridBalanceMeterCoordinator
from .store import GridBalanceStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Net Metering from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    store = GridBalanceStore(hass, entry.entry_id)
    coordinator = GridBalanceMeterCoordinator(hass, store, dict(entry.options))

    await coordinator.async_setup()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "store": store,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Re-register listener so options changes propagate without full reload
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info("Net Metering integration loaded (entry_id=%s).", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        coordinator: GridBalanceMeterCoordinator | None = entry_data.get("coordinator")
        if coordinator is not None:
            coordinator.async_unload()
        _LOGGER.info(
            "Net Metering integration unloaded (entry_id=%s).", entry.entry_id
        )
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when options are saved via the options flow."""
    # The options flow already calls coordinator.async_update_options directly.
    # This listener exists as a safety net to trigger a reload if needed.
    await hass.config_entries.async_reload(entry.entry_id)
