"""Config flow and options flow for Net Metering."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ENERGY_SELF_RESET,
    CONF_ENERGY_SENSOR,
    CONF_SOLAR_SELF_RESET,
    CONF_SOLAR_SENSOR,
    DOMAIN,
    INTEGRATION_NAME,
)

_LOGGER = logging.getLogger(__name__)

_YES_NO = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="true", label="Yes"),
            selector.SelectOptionDict(value="false", label="No"),
        ],
        mode=selector.SelectSelectorMode.LIST,
    )
)

_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
)


def _bool_to_str(val: bool) -> str:
    return "true" if val else "false"


def _str_to_bool(val: str) -> bool:
    return str(val).lower() == "true"


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SOLAR_SENSOR,
                default=defaults.get(CONF_SOLAR_SENSOR, ""),
            ): _ENTITY_SELECTOR,
            vol.Required(
                CONF_ENERGY_SENSOR,
                default=defaults.get(CONF_ENERGY_SENSOR, ""),
            ): _ENTITY_SELECTOR,
            vol.Required(
                CONF_SOLAR_SELF_RESET,
                default=_bool_to_str(defaults.get(CONF_SOLAR_SELF_RESET, True)),
            ): _YES_NO,
            vol.Required(
                CONF_ENERGY_SELF_RESET,
                default=_bool_to_str(defaults.get(CONF_ENERGY_SELF_RESET, False)),
            ): _YES_NO,
        }
    )


def _normalise_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Convert string booleans from the selector back to real booleans."""
    out = dict(user_input)
    out[CONF_SOLAR_SELF_RESET] = _str_to_bool(user_input[CONF_SOLAR_SELF_RESET])
    out[CONF_ENERGY_SELF_RESET] = _str_to_bool(user_input[CONF_ENERGY_SELF_RESET])
    return out


class GridBalanceMeterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _normalise_user_input(user_input)
            return self.async_create_entry(
                title=INTEGRATION_NAME,
                data={},
                options=data,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_options_schema({}),
            description_placeholders={
                "solar_label": "Solar Production Sensor",
                "energy_label": "Energy Consumption Sensor",
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "GridBalanceMeterOptionsFlow":
        return GridBalanceMeterOptionsFlow(config_entry)


class GridBalanceMeterOptionsFlow(OptionsFlow):
    """Handle options (reconfiguration) flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        errors: dict[str, str] = {}

        current_options = dict(self._config_entry.options)

        if user_input is not None:
            new_options = _normalise_user_input(user_input)

            # Detect if source sensors changed so coordinator can discard refs
            sensors_changed = (
                new_options.get(CONF_SOLAR_SENSOR) != current_options.get(CONF_SOLAR_SENSOR)
                or new_options.get(CONF_ENERGY_SENSOR) != current_options.get(CONF_ENERGY_SENSOR)
            )

            # Notify the coordinator of the change
            from homeassistant.helpers import entity_registry  # noqa: PLC0415
            entry_data = self.hass.data.get(DOMAIN, {}).get(
                self._config_entry.entry_id
            )
            if entry_data is not None:
                coordinator = entry_data.get("coordinator")
                if coordinator is not None:
                    await coordinator.async_update_options(new_options, sensors_changed)

            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(current_options),
            description_placeholders={
                "solar_label": "Solar Production Sensor",
                "energy_label": "Energy Consumption Sensor",
            },
            errors=errors,
        )
