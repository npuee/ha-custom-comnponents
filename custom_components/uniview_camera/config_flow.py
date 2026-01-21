import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    pass


class InvalidAuth(Exception):
    pass


class UniviewConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._caps = []
        self._caps_raw = None
        self._device_info = None

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required("host"): str,
                        vol.Required("username", default="admin"): str,
                        vol.Required("password", default=""): str,
                    }
                ),
            )

        host = user_input["host"]
        username = user_input.get("username")
        password = user_input.get("password")

        try:
            caps_raw = await self._fetch_with_digest(self.hass, f"http://{host}/LAPI/V1.0/Smart/Capabilities", username, password)
            device_info = await self._fetch_with_digest(self.hass, f"http://{host}/LAPI/V1.0/System/DeviceInfo", username, password)
        except InvalidAuth:
            errors["base"] = "invalid_auth"
            return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("host"): str, vol.Required("username", default="admin"): str, vol.Required("password", default=""): str}), errors=errors)
        except CannotConnect:
            errors["base"] = "cannot_connect"
            return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("host"): str, vol.Required("username", default="admin"): str, vol.Required("password", default=""): str}), errors=errors)
        except Exception as exc:
            _LOGGER.exception("Unexpected error testing connection: %s", exc)
            errors["base"] = "unknown"
            return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("host"): str, vol.Required("username", default="admin"): str, vol.Required("password", default=""): str}), errors=errors)

        # parse capability names from JSON structure
        caps = []
        try:
            import json

            obj = json.loads(caps_raw) if caps_raw else {}
            if isinstance(obj, dict) and "Response" in obj and isinstance(obj["Response"], dict):
                resp = obj["Response"]
                if "Data" in resp and isinstance(resp["Data"], dict):
                    caps = list(resp["Data"].keys())
        except Exception:
            _LOGGER.debug("Failed parsing capabilities JSON")

        self._caps = caps
        self._caps_raw = caps_raw
        self._device_info = device_info

        # store submitted host/credentials in flow context for second step
        self.context["source_data"] = {"host": host, "username": username, "password": password}

        if len(caps) == 0:
            # No capabilities found, create entry but no smart entities
            return self.async_create_entry(title=host, data={
                "host": host,
                "username": username,
                "password": password,
                "capabilities": caps_raw,
                "selected_capability": None,
                "device_info": device_info,
            })

        if len(caps) == 1:
            return self.async_create_entry(title=f"{host} - {caps[0]}", data={
                "host": host,
                "username": username,
                "password": password,
                "capabilities": caps_raw,
                "selected_capability": caps[0],
                "device_info": device_info,
            })

        # Multiple capabilities: ask user to select one
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema({vol.Required("capability"): vol.In({c: c for c in caps})}),
        )

    async def async_step_select(self, user_input=None):
        # finalize with selected capability
        if user_input is None:
            return self.async_show_form(step_id="select", data_schema=vol.Schema({vol.Required("capability"): vol.In({c: c for c in self._caps})}))

        src = self.context.get("source_data", {})
        host = src.get("host")
        username = src.get("username")
        password = src.get("password")
        selected = user_input.get("capability")
        return self.async_create_entry(title=f"{host} - {selected}", data={
            "host": host,
            "username": username,
            "password": password,
            "capabilities": self._caps_raw,
            "selected_capability": selected,
            "device_info": self._device_info,
        })

    async def _fetch_with_digest(self, hass: HomeAssistant, url: str, username: str, password: str) -> str | None:
        """Fetch URL using HTTP Digest (requests in executor). Return text or raise exceptions."""

        def _sync():
            try:
                import requests
                from requests.auth import HTTPDigestAuth

                resp = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
                return resp.status_code, resp.text
            except Exception as exc:
                _LOGGER.debug("Sync Digest request error: %s", exc)
                return None, None

        status_text = await hass.async_add_executor_job(_sync)
        if not status_text:
            raise CannotConnect()
        status, text = status_text
        if status == 200:
            return text
        if status == 401:
            raise InvalidAuth()
        raise CannotConnect()
