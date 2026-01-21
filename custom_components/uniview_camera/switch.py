import logging
import json
from typing import Any

import requests
from requests.auth import HTTPDigestAuth

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    data = entry.data
    host = data.get("host")
    username = data.get("username")
    password = data.get("password")
    capabilities_raw = data.get("capabilities")
    selected = data.get("selected_capability")

    caps = _parse_capabilities(capabilities_raw)
    entities = []
    # If user selected a capability, only create that one
    if selected:
        if selected in caps:
            control_url = f"http://{host}/LAPI/V1.0/Smart/{selected}/Rule"
            entities.append(UniviewCapabilitySwitch(host, selected, control_url, username, password))
    else:
        for cap in caps:
            control_url = f"http://{host}/LAPI/V1.0/Smart/{cap}/Rule"
            entities.append(UniviewCapabilitySwitch(host, cap, control_url, username, password))

    if entities:
        async_add_entities(entities)


def _parse_capabilities(raw: str) -> list[str]:
    # parse Response.Data keys if present
    if not raw:
        return []
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "Response" in obj and isinstance(obj["Response"], dict):
            resp = obj["Response"]
            if "Data" in resp and isinstance(resp["Data"], dict):
                return list(resp["Data"].keys())
        for key in ("Smart", "Capabilities", "capabilities"):
            if key in obj and isinstance(obj[key], dict):
                return list(obj[key].keys())
        return list(obj.keys())
    except Exception:
        # try simple xml tag extraction
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(raw)
            return [child.tag.split('}')[-1] for child in list(root)]
        except Exception:
            return []


class UniviewCapabilitySwitch(SwitchEntity):
    def __init__(self, host: str, capability: str, control_url: str, username: str, password: str):
        self._host = host
        self._capability = capability
        self._control_url = control_url
        self._username = username
        self._password = password
        # Display name: only the capability (no IP)
        self._name = capability
        self._unique_id = f"{host}-{capability}-switch"
        self._is_on = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"control_url": self._control_url}

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": f"Uniview {self._host}",
            "manufacturer": "Uniview",
        }

    async def async_update(self) -> None:
        def _sync_get():
            try:
                resp = requests.get(self._control_url, auth=HTTPDigestAuth(self._username, self._password), timeout=10)
                if resp.status_code != 200:
                    return None
                try:
                    j = resp.json()
                    # try Response.Data.Enabled
                    if isinstance(j, dict) and "Response" in j:
                        data = j["Response"].get("Data") if isinstance(j["Response"], dict) else None
                        if isinstance(data, dict) and "Enabled" in data:
                            return bool(int(data["Enabled"]))
                except Exception:
                    # fallback to text heuristics
                    text = resp.text.lower()
                    if "enabled" in text and ("1" in text or "true" in text):
                        return True
                return False
            except Exception as exc:
                _LOGGER.debug("Error fetching capability state: %s", exc)
                return None

        state = await self.hass.async_add_executor_job(_sync_get)
        if state is None:
            self._is_on = False
        else:
            self._is_on = bool(state)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_enabled(1)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_enabled(0)

    async def _set_enabled(self, enabled: int) -> None:
        def _sync_set():
            payloads = [
                {"Enabled": enabled},
                {"Data": {"Enabled": enabled}},
                {"enabled": enabled},
            ]
            # try POST then PUT
            for payload in payloads:
                try:
                    resp = requests.post(self._control_url, json=payload, auth=HTTPDigestAuth(self._username, self._password), timeout=10)
                    if resp.status_code == 200:
                        try:
                            j = resp.json()
                            if isinstance(j, dict) and j.get("Response", {}).get("ResponseCode") == 0:
                                return True
                        except Exception:
                            return True
                    # try PUT
                    resp2 = requests.put(self._control_url, json=payload, auth=HTTPDigestAuth(self._username, self._password), timeout=10)
                    if resp2.status_code == 200:
                        try:
                            j2 = resp2.json()
                            if isinstance(j2, dict) and j2.get("Response", {}).get("ResponseCode") == 0:
                                return True
                        except Exception:
                            return True
                except Exception as exc:
                    _LOGGER.debug("Error setting capability state via payload %s: %s", payload, exc)
            return False

        ok = await self.hass.async_add_executor_job(_sync_set)
        self._is_on = bool(ok)
