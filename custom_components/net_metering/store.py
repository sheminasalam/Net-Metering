"""Persistent state storage for Net Metering."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    STORAGE_KEY,
    STORAGE_VERSION,
    STATE_CUMULATIVE_IMPORT,
    STATE_CUMULATIVE_EXPORT,
    STATE_PREV_SOLAR,
    STATE_PREV_ENERGY,
    STATE_LAST_DATE,
    STATE_INITIALIZED,
    STATE_LAST_SCHEDULED_MINUTE,
    STATE_SOLAR_REF_VALID,
    STATE_LAST_CALCULATION_TIME,
    STATE_LAST_CALCULATION_PREV_SOLAR,
    STATE_LAST_CALCULATION_PREV_ENERGY,
)

_LOGGER = logging.getLogger(__name__)


class GridBalanceStore:
    """Manages reading and writing of persistent integration state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}_{entry_id}",
        )
        self._data: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load persisted state from storage."""
        stored = await self._store.async_load()
        if stored and isinstance(stored, dict):
            self._data = stored
            _LOGGER.debug("Loaded persisted state: %s", self._data)
        else:
            self._data = {}
            _LOGGER.debug("No persisted state found; starting fresh.")

    async def async_save(self) -> None:
        """Persist current state to storage."""
        await self._store.async_save(self._data)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, updates: dict[str, Any]) -> None:
        self._data.update(updates)

    # ------------------------------------------------------------------
    # Typed helpers
    # ------------------------------------------------------------------

    @property
    def cumulative_import(self) -> float:
        val = self._data.get(STATE_CUMULATIVE_IMPORT, 0.0)
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    @cumulative_import.setter
    def cumulative_import(self, value: float) -> None:
        self._data[STATE_CUMULATIVE_IMPORT] = value

    @property
    def cumulative_export(self) -> float:
        val = self._data.get(STATE_CUMULATIVE_EXPORT, 0.0)
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    @cumulative_export.setter
    def cumulative_export(self, value: float) -> None:
        self._data[STATE_CUMULATIVE_EXPORT] = value

    @property
    def previous_solar(self) -> float | None:
        val = self._data.get(STATE_PREV_SOLAR)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @previous_solar.setter
    def previous_solar(self, value: float | None) -> None:
        self._data[STATE_PREV_SOLAR] = value

    @property
    def previous_energy(self) -> float | None:
        val = self._data.get(STATE_PREV_ENERGY)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @previous_energy.setter
    def previous_energy(self, value: float | None) -> None:
        self._data[STATE_PREV_ENERGY] = value

    @property
    def last_date(self) -> str | None:
        return self._data.get(STATE_LAST_DATE)

    @last_date.setter
    def last_date(self, value: str | None) -> None:
        self._data[STATE_LAST_DATE] = value

    @property
    def initialized(self) -> bool:
        return bool(self._data.get(STATE_INITIALIZED, False))

    @initialized.setter
    def initialized(self, value: bool) -> None:
        self._data[STATE_INITIALIZED] = value

    @property
    def last_scheduled_minute(self) -> str | None:
        """ISO-like key 'YYYY-MM-DD HH:MM' of the last executed schedule slot."""
        return self._data.get(STATE_LAST_SCHEDULED_MINUTE)

    @last_scheduled_minute.setter
    def last_scheduled_minute(self, value: str | None) -> None:
        self._data[STATE_LAST_SCHEDULED_MINUTE] = value

    @property
    def solar_ref_valid(self) -> bool:
        return bool(self._data.get(STATE_SOLAR_REF_VALID, False))

    @solar_ref_valid.setter
    def solar_ref_valid(self, value: bool) -> None:
        self._data[STATE_SOLAR_REF_VALID] = value

    @property
    def last_calculation_time(self) -> str | None:
        return self._data.get(STATE_LAST_CALCULATION_TIME)

    @last_calculation_time.setter
    def last_calculation_time(self, value: str | None) -> None:
        self._data[STATE_LAST_CALCULATION_TIME] = value

    @property
    def last_calculation_previous_solar(self) -> float | None:
        val = self._data.get(STATE_LAST_CALCULATION_PREV_SOLAR)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @last_calculation_previous_solar.setter
    def last_calculation_previous_solar(self, value: float | None) -> None:
        self._data[STATE_LAST_CALCULATION_PREV_SOLAR] = value

    @property
    def last_calculation_previous_energy(self) -> float | None:
        val = self._data.get(STATE_LAST_CALCULATION_PREV_ENERGY)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @last_calculation_previous_energy.setter
    def last_calculation_previous_energy(self, value: float | None) -> None:
        self._data[STATE_LAST_CALCULATION_PREV_ENERGY] = value

    # ------------------------------------------------------------------
    # Bulk snapshot (for diagnostics)
    # ------------------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
