"""Diagnostics support for Net Metering."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GridBalanceMeterCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: GridBalanceMeterCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    return coordinator.get_diagnostics()
