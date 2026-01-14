from __future__ import annotations

import voluptuous as vol
import logging
from homeassistant import config_entries

from .const import DOMAIN, UPDATE_INTERVAL, BASE_API

_LOGGER = logging.getLogger(__name__)


class KeskkonnateenusedFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            contract = str(user_input["contract_number"])
            # attempt to fetch API to extract address for confirmation
            address = None
            # import network helpers lazily to avoid import-time errors
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            import async_timeout
            import asyncio

            session = async_get_clientsession(self.hass)
            url = f"{BASE_API}{contract}"
            try:
                async with async_timeout.timeout(10):
                    resp = await session.get(url)
                    resp.raise_for_status()
                    data = await resp.json()
                    # try to extract first address field from response
                    items = None
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        for k in ("data", "items", "upcomingDischarges", "discharges"):
                            v = data.get(k)
                            if isinstance(v, list):
                                items = v
                                break
                    if items and len(items) > 0 and isinstance(items[0], dict):
                        raw = items[0]
                        for ak in ("address", "addressText", "street", "streetAddress", "location", "addr", "address_line"):
                            if ak in raw and raw[ak]:
                                address = str(raw[ak]).strip()
                                break
            except Exception:
                _LOGGER.debug("Could not fetch/parse API for contract %s", contract)

            # If we found an address, show a confirmation form prefilled; otherwise proceed to create entry
            if address:
                schema = vol.Schema(
                    {
                        vol.Required("contract_number", default=contract): str,
                        vol.Required("address", default=address): str,
                        vol.Optional("update_interval", default=UPDATE_INTERVAL): int,
                    }
                )
                return self.async_show_form(step_id="confirm", data_schema=schema, errors=errors)

            data = {"contract_number": contract}
            options = {"update_interval": user_input.get("update_interval", UPDATE_INTERVAL)}
            return self.async_create_entry(title="Keskonnateenused", data=data, options=options)

        # show initial user form when no input provided
        schema = vol.Schema(
            {
                vol.Required("contract_number"): str,
                vol.Optional("update_interval", default=UPDATE_INTERVAL): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_confirm(self, user_input=None):
        """Handle the confirmation step where user confirms extracted address."""
        errors = {}
        if user_input is not None:
            data = {"contract_number": str(user_input.get("contract_number")), "address": str(user_input.get("address"))}
            options = {"update_interval": user_input.get("update_interval", UPDATE_INTERVAL)}
            return self.async_create_entry(title="Keskonnateenused", data=data, options=options)

        # Shouldn't reach here; show empty form defensively
        schema = vol.Schema(
            {
                vol.Required("contract_number"): str,
                vol.Required("address"): str,
                vol.Optional("update_interval", default=UPDATE_INTERVAL): int,
            }
        )
        return self.async_show_form(step_id="confirm", data_schema=schema, errors=errors)


    @staticmethod
    def async_get_options_flow(config_entry):
        try:
            return OptionsFlowHandler(config_entry)
        except Exception:
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
                vol.Required("update_interval", default=self._config_entry.options.get("update_interval", UPDATE_INTERVAL)): int,
                vol.Optional("address", default=self._config_entry.data.get("address")): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
