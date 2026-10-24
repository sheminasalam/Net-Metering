"""Sensor entities for Net Metering (Grid Import & Grid Export)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTEGRATION_NAME, UNIQUE_ID_EXPORT, UNIQUE_ID_IMPORT
from .coordinator import GridBalanceMeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GridBalanceMeterCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    async_add_entities(
        [
            GridImportSensor(coordinator, entry),
            GridExportSensor(coordinator, entry),
        ]
    )


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------


class _GridEnergySensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Grid Import / Export sensors."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GridBalanceMeterCoordinator,
        entry: ConfigEntry,
        uid_suffix: str,
        name: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{uid_suffix}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry.entry_id)},
            name=INTEGRATION_NAME,
            manufacturer="Net Metering",
            model="Virtual Grid Meter",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the exact latest calculation inputs and results for debugging."""
        if self.coordinator.data is None:
            return None
        diagnostics = self.coordinator.data.get("diagnostics")
        if not diagnostics:
            return None
        return dict(diagnostics)


class GridImportSensor(_GridEnergySensorBase):
    def __init__(
        self,
        coordinator: GridBalanceMeterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            uid_suffix=UNIQUE_ID_IMPORT,
            name="Grid Import",
            key="cumulative_import",
        )
        self._attr_icon = "mdi:transmission-tower-import"


class GridExportSensor(_GridEnergySensorBase):
    def __init__(
        self,
        coordinator: GridBalanceMeterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            uid_suffix=UNIQUE_ID_EXPORT,
            name="Grid Export",
            key="cumulative_export",
        )
        self._attr_icon = "mdi:transmission-tower-export"
