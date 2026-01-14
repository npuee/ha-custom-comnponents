from __future__ import annotations

import voluptuous as vol
import logging
from homeassistant import config_entries

from .const import DOMAIN, DEFAULT_API, UPDATE_INTERVAL


class FuelEstoniaFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # store api_url and update_interval in the config entry
            data = {"api_url": user_input["api_url"]}
            options = {"update_interval": user_input.get("update_interval", UPDATE_INTERVAL)}
            return self.async_create_entry(title="Fuel Estonia", data=data, options=options)

        schema = vol.Schema(
            {
                vol.Required("api_url", default=DEFAULT_API): str,
                vol.Optional("update_interval", default=UPDATE_INTERVAL): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


    @staticmethod
    def async_get_options_flow(config_entry):
        try:
            return OptionsFlowHandler(config_entry)
        except Exception:  # defensive: do not allow options flow errors to crash HA
            _LOGGER = logging.getLogger(__name__)
            _LOGGER.exception("Failed to create options flow handler")
            return None


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required("api_url", default=self._config_entry.data.get("api_url", DEFAULT_API)): str,
                vol.Required("update_interval", default=self._config_entry.options.get("update_interval", UPDATE_INTERVAL)): int,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
