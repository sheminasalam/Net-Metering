"""
Net Metering – Coordinator.

Owns:
  - Fixed wall-clock scheduling (Asia/Kolkata)
  - Source sensor reading
  - Midnight / self-reset handling
  - Delegation to calculation_engine
  - Persistent state via GridBalanceStore
  - Diagnostic snapshot
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .calculation_engine import CalculationResult, run_calculation
from .const import (
    CONF_ENERGY_SELF_RESET,
    CONF_ENERGY_SENSOR,
    CONF_SOLAR_SELF_RESET,
    CONF_SOLAR_SENSOR,
    DOMAIN,
    SCHEDULE_MINUTES,
    TIMEZONE,
)
from .store import GridBalanceStore

_LOGGER = logging.getLogger(__name__)
_TZ = ZoneInfo(TIMEZONE)


class GridBalanceMeterCoordinator(DataUpdateCoordinator):
    """Central coordinator for the Net Metering integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: GridBalanceStore,
        config_options: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # No automatic polling interval – we drive scheduling ourselves.
            update_interval=None,
        )
        self._store = store
        self._options = config_options

        # In-memory diagnostics / latest result (reset on each cycle)
        self._last_result: CalculationResult | None = None
        self._fault: bool = False  # Energy Consumption Fault

        # Unsubscribe handles
        self._unsub_schedule: list[Any] = []

        # Prevent duplicate callbacks for the same wall-clock slot while
        # an asynchronous calculation is still running.
        self._processing_slot: str | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cumulative_import(self) -> float:
        return self._store.cumulative_import

    @property
    def cumulative_export(self) -> float:
        return self._store.cumulative_export

    @property
    def energy_fault(self) -> bool:
        return self._fault

    @property
    def last_result(self) -> CalculationResult | None:
        return self._last_result

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Load persistent state and register the schedule listener."""
        await self._store.async_load()

        # Restore the fault indication immediately from the current source
        # state so entities do not briefly report a false healthy state after
        # a Home Assistant restart.
        energy_entity = self._options.get(CONF_ENERGY_SENSOR)
        self._fault = _read_numeric_state(self.hass, energy_entity) is None

        # Publish restored cumulative totals immediately rather than waiting
        # for the next scheduled calculation slot.
        self.async_set_updated_data(self._build_data())

        self._register_schedule()
        _LOGGER.info("Net Metering coordinator set up.")

    def _register_schedule(self) -> None:
        """Register one time-change listener per scheduled minute."""
        self._unsub_schedule = []
        for minute in SCHEDULE_MINUTES:
            unsub = async_track_time_change(
                self.hass,
                self._handle_scheduled_tick,
                second=0,
                minute=minute,
            )
            self._unsub_schedule.append(unsub)
        _LOGGER.debug("Registered schedule for minutes: %s", sorted(SCHEDULE_MINUTES))

    def async_unload(self) -> None:
        """Cancel all scheduled listeners."""
        for unsub in self._unsub_schedule:
            unsub()
        self._unsub_schedule = []

    # ------------------------------------------------------------------
    # Configuration update (called from options flow)
    # ------------------------------------------------------------------

    async def async_update_options(
        self,
        new_options: dict[str, Any],
        sensors_changed: bool,
    ) -> None:
        """Apply new configuration options.

        If the source sensors changed the existing references are discarded so
        that no spurious delta is calculated against the old sensor's value.
        Cumulative totals are NEVER reset.
        """
        self._options = new_options

        if sensors_changed:
            _LOGGER.info(
                "Source sensors changed; discarding references. "
                "Cumulative totals are preserved."
            )
            self._store.previous_solar = None
            self._store.previous_energy = None
            self._store.initialized = False
            self._store.solar_ref_valid = False
            await self._store.async_save()

    # ------------------------------------------------------------------
    # Scheduled tick handler
    # ------------------------------------------------------------------

    @callback
    def _handle_scheduled_tick(self, now: datetime) -> None:
        """Called by HA at each scheduled wall-clock minute."""
        local_now = now.astimezone(_TZ)
        # Guard: deduplicate if HA fires the callback more than once per slot
        slot_key = local_now.strftime("%Y-%m-%d %H:%M")
        if (
            self._store.last_scheduled_minute == slot_key
            or self._processing_slot == slot_key
        ):
            _LOGGER.debug("Duplicate tick for slot %s – skipped.", slot_key)
            return

        # Claim this slot synchronously before creating the asynchronous task.
        # This prevents two callbacks for the same wall-clock minute from
        # starting concurrent calculations against the same references.
        self._processing_slot = slot_key

        _LOGGER.debug("Scheduled tick: %s", slot_key)
        self.hass.async_create_task(self._async_calculate(local_now, slot_key))

    # ------------------------------------------------------------------
    # Core calculation
    # ------------------------------------------------------------------

    async def _async_calculate(self, local_now: datetime, slot_key: str) -> None:
        """Read sensors, run the engine, persist state, notify listeners."""
        try:
            await self._async_calculate_impl(local_now, slot_key)
        finally:
            if self._processing_slot == slot_key:
                self._processing_slot = None

    async def _async_calculate_impl(self, local_now: datetime, slot_key: str) -> None:
        """Perform one scheduled calculation cycle."""

        solar_entity = self._options.get(CONF_SOLAR_SENSOR)
        energy_entity = self._options.get(CONF_ENERGY_SENSOR)
        solar_self_reset = self._options.get(CONF_SOLAR_SELF_RESET, True)
        energy_self_reset = self._options.get(CONF_ENERGY_SELF_RESET, False)

        current_date_str = local_now.strftime("%Y-%m-%d")

        # ------ Read source sensors ------

        current_solar = _read_numeric_state(self.hass, solar_entity)
        current_energy = _read_numeric_state(self.hass, energy_entity)

        # ------ Energy Consumption Fault ------

        if current_energy is None:
            if not self._fault:
                _LOGGER.warning(
                    "Energy Consumption Sensor (%s) is unavailable/invalid. "
                    "Grid calculations suspended.",
                    energy_entity,
                )
            self._fault = True
            # Invalidate energy reference so the first valid reading after
            # recovery sets a fresh reference (Section 7 of spec).
            self._store.previous_energy = None
            self._store.initialized = False
            self._store.last_scheduled_minute = slot_key
            await self._store.async_save()
            self.async_set_updated_data(self._build_data())
            return

        # Energy is valid – clear fault
        if self._fault:
            _LOGGER.info(
                "Energy Consumption Sensor recovered. Resuming calculations."
            )
        self._fault = False

        # ------ Midnight / self-reset handling ------

        last_date = self._store.last_date
        is_new_day = last_date is not None and last_date != current_date_str

        midnight_reference_cycle = False

        if is_new_day:
            if solar_self_reset:
                _LOGGER.debug(
                    "New calendar day. Solar sensor is self-resetting; "
                    "solar reference reset to 0."
                )
                # Establish reference at 0. The midnight reset cycle itself
                # must not calculate or add any grid energy.
                self._store.previous_solar = 0.0
                self._store.solar_ref_valid = True
                midnight_reference_cycle = True

            if energy_self_reset:
                _LOGGER.debug(
                    "New calendar day. Energy sensor is self-resetting; "
                    "energy reference reset to 0."
                )
                # Establish reference at 0. The midnight reset cycle itself
                # must not calculate or add any grid energy.
                self._store.previous_energy = 0.0
                midnight_reference_cycle = True

            # If the source that is NOT configured as self-resetting rolls
            # backward at the same boundary, preserve the normal rollback
            # rule by establishing its current reading as the new reference.
            # The entire midnight cycle remains reference-only.
            if (
                not energy_self_reset
                and self._store.previous_energy is not None
                and current_energy < self._store.previous_energy
            ):
                _LOGGER.warning(
                    "Energy Consumption counter rollback detected at midnight; "
                    "new reference established at %.6f kWh.",
                    current_energy,
                )
                self._store.previous_energy = current_energy

            if (
                not solar_self_reset
                and current_solar is not None
                and self._store.previous_solar is not None
                and math.isfinite(self._store.previous_solar)
                and current_solar < self._store.previous_solar
            ):
                _LOGGER.warning(
                    "Solar Production counter rollback detected at midnight; "
                    "new reference established at %.6f kWh.",
                    current_solar,
                )
                self._store.previous_solar = current_solar
                self._store.solar_ref_valid = True

        # ------ Determine if this is a reference-only cycle ------

        prev_energy = self._store.previous_energy
        is_reference_cycle = (
            midnight_reference_cycle
            or not self._store.initialized
            or prev_energy is None
        )

        # Capture the exact references that will be supplied to the
        # calculation engine AFTER any midnight/reference handling. These
        # values are diagnostic-only and never alter the calculation engine's
        # inputs or outputs.
        calculation_previous_solar = self._store.previous_solar
        calculation_previous_energy = self._store.previous_energy
        self._store.last_calculation_previous_solar = calculation_previous_solar
        self._store.last_calculation_previous_energy = calculation_previous_energy
        self._store.last_calculation_time = local_now.isoformat()

        # ------ Run engine ------

        result = run_calculation(
            current_solar=current_solar,
            current_energy=current_energy,
            previous_solar=self._store.previous_solar,
            previous_energy=prev_energy,
            solar_ref_valid=self._store.solar_ref_valid,
            cumulative_import=self._store.cumulative_import,
            cumulative_export=self._store.cumulative_export,
            is_reference_cycle=is_reference_cycle,
        )

        self._last_result = result

        # ------ Update persistent state ------

        # On a deliberate midnight self-reset, preserve the references
        # established above through this reference-only cycle. The following
        # scheduled cycle must calculate from those reset/preserved references.
        if not midnight_reference_cycle:
            # Always advance energy reference
            self._store.previous_energy = current_energy

            # Update solar reference only when solar is currently valid
            if current_solar is not None and math.isfinite(current_solar):
                self._store.previous_solar = current_solar
                self._store.solar_ref_valid = True
            # else: preserve existing solar reference (spec §6)

        self._store.initialized = True
        self._store.last_date = current_date_str
        self._store.last_scheduled_minute = slot_key

        # Persist updated cumulative totals from engine result
        self._store.cumulative_import = result.cumulative_import
        self._store.cumulative_export = result.cumulative_export

        await self._store.async_save()

        _LOGGER.debug(
            "Cycle complete: import_delta=%.6f export_delta=%.6f "
            "cumulative_import=%.6f cumulative_export=%.6f notes=%s",
            result.interval_import,
            result.interval_export,
            result.cumulative_import,
            result.cumulative_export,
            result.notes,
        )

        self.async_set_updated_data(self._build_data())

    # ------------------------------------------------------------------
    # DataUpdateCoordinator overrides
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Satisfy the coordinator contract; actual updates are event-driven."""
        return self._build_data()

    def _build_data(self) -> dict[str, Any]:
        return {
            "cumulative_import": self._store.cumulative_import,
            "cumulative_export": self._store.cumulative_export,
            "energy_fault": self._fault,
            "last_result": self._last_result,
            "diagnostics": self._build_diagnostic_data(),
        }

    def _build_diagnostic_data(self) -> dict[str, Any]:
        """Return entity-safe diagnostic attributes for the latest cycle."""
        r = self._last_result
        return {
            "current_solar_kwh": r.current_solar if r else None,
            "current_energy_kwh": r.current_energy if r else None,
            "previous_solar_reference_kwh": self._store.last_calculation_previous_solar,
            "previous_energy_reference_kwh": self._store.last_calculation_previous_energy,
            "delta_solar_kwh": r.delta_solar if r else None,
            "delta_energy_kwh": r.delta_energy if r else None,
            "net_kwh": r.net if r else None,
            "interval_import_kwh": r.interval_import if r else None,
            "interval_export_kwh": r.interval_export if r else None,
            "cumulative_import_kwh": self._store.cumulative_import,
            "cumulative_export_kwh": self._store.cumulative_export,
            "reference_only": r.reference_only if r else None,
            "rollback_detected": r.rollback_detected if r else None,
            "solar_unavailable": r.solar_unavailable if r else None,
            "energy_consumption_fault": self._fault,
            "last_calculation_time": self._store.last_calculation_time,
            "last_scheduled_slot": self._store.last_scheduled_minute,
            "last_processed_date": self._store.last_date,
            "solar_reference_valid": self._store.solar_ref_valid,
            "notes": list(r.notes) if r else [],
        }

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> dict[str, Any]:
        """Return a full diagnostic snapshot."""
        r = self._last_result
        opts = self._options
        store_dict = self._store.as_dict()

        return {
            "configuration": {
                "solar_production_sensor": opts.get(CONF_SOLAR_SENSOR),
                "energy_consumption_sensor": opts.get(CONF_ENERGY_SENSOR),
                "solar_self_resetting_at_midnight": opts.get(CONF_SOLAR_SELF_RESET),
                "energy_self_resetting_at_midnight": opts.get(CONF_ENERGY_SELF_RESET),
            },
            "state": {
                "initialized": self._store.initialized,
                "last_processed_date": self._store.last_date,
                "last_scheduled_slot": self._store.last_scheduled_minute,
                "previous_solar_reference_kwh": self._store.previous_solar,
                "previous_energy_reference_kwh": self._store.previous_energy,
                "last_calculation_previous_solar_reference_kwh": self._store.last_calculation_previous_solar,
                "last_calculation_previous_energy_reference_kwh": self._store.last_calculation_previous_energy,
                "last_calculation_time": self._store.last_calculation_time,
                "solar_reference_valid": self._store.solar_ref_valid,
                "cumulative_grid_import_kwh": self._store.cumulative_import,
                "cumulative_grid_export_kwh": self._store.cumulative_export,
                "energy_consumption_fault": self._fault,
            },
            "last_calculation": {
                "current_solar_kwh": (r.current_solar if r else None),
                "current_energy_kwh": (r.current_energy if r else None),
                "solar_unavailable": (r.solar_unavailable if r else None),
                "delta_solar_kwh": (r.delta_solar if r else None),
                "delta_energy_kwh": (r.delta_energy if r else None),
                "net_kwh": (r.net if r else None),
                "interval_import_kwh": (r.interval_import if r else None),
                "interval_export_kwh": (r.interval_export if r else None),
                "reference_only": (r.reference_only if r else None),
                "rollback_detected": (r.rollback_detected if r else None),
                "notes": (r.notes if r else []),
            },
            "raw_store": store_dict,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_numeric_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return the numeric state of an entity, or None if unavailable."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", ""):
        return None
    try:
        val = float(state.state)
        if math.isfinite(val):
            return val
        return None
    except (ValueError, TypeError):
        return None
