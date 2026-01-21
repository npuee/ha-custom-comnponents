import logging
import json
import xml.etree.ElementTree as ET
from typing import Any

import requests
from requests.auth import HTTPDigestAuth

from homeassistant.components.binary_sensor import BinarySensorEntity
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
            entities.append(UniviewCapabilitySensor(host, selected, control_url, username, password))
    else:
        for cap in caps:
            control_url = f"http://{host}/LAPI/V1.0/Smart/{cap}/Rule"
            entities.append(UniviewCapabilitySensor(host, cap, control_url, username, password))

    if entities:
        async_add_entities(entities)


def _parse_capabilities(raw: str) -> list[str]:
    """Parse the camera capabilities JSON and return capability names under Response.Data."""
    if not raw:
        return []

    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "Response" in data and isinstance(data["Response"], dict):
            resp = data["Response"]
            if "Data" in resp and isinstance(resp["Data"], dict):
                return list(resp["Data"].keys())
        # fallback: try top-level keys
        if isinstance(data, dict):
            return list(data.keys())
    except Exception:
        pass

    # Try XML fallback
    try:
        root = ET.fromstring(raw)
        names = [child.tag for child in list(root)]
        cleaned = [n.split("}")[-1] for n in names]
        return cleaned
    except Exception:
        _LOGGER.debug("Failed to parse capabilities as JSON or XML")

    return []


class UniviewCapabilitySensor(BinarySensorEntity):
    def __init__(self, host: str, capability: str, control_url: str, username: str, password: str):
        self._host = host
        self._capability = capability
        self._control_url = control_url
        self._username = username
        self._password = password
        # Display name: only the capability (no IP)
        self._name = capability
        self._unique_id = f"{host}-{capability}"
        # _enabled reflects the camera capability Enabled state (1 == enabled)
        self._enabled = False
        # Home Assistant binary sensor state is inverted: when capability is enabled, sensor is OFF
        self._is_on = True
        # set device class for common security capabilities
        if capability.lower() in ("intrusiondetection", "crosslinedetection", "smartmotiondetection"):
            self._device_class = "safety"
        elif capability.lower() in ("facedetection",):
            self._device_class = "safety"
        else:
            self._device_class = None

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
        # status should reflect camera capability: enabled -> unsafe
        return {"control_url": self._control_url, "status": "unsafe" if self._enabled else "safe"}

    @property
    def device_class(self) -> str | None:
        return self._device_class

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": f"Uniview {self._host}",
            "manufacturer": "Uniview",
        }

    async def async_update(self) -> None:
        """Fetch the current rule/state for this capability using Digest auth."""
        def _sync_get():
            try:
                resp = requests.get(self._control_url, auth=HTTPDigestAuth(self._username, self._password), timeout=10)
                if resp.status_code != 200:
                    return None
                return resp.text
            except Exception as exc:
                _LOGGER.debug("Error fetching capability state: %s", exc)
                return None

        text = await self.hass.async_add_executor_job(_sync_get)
        if not text:
            self._is_on = False
            return

        # Try JSON parsing for known Response.Data.Enabled structure
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "Response" in obj and isinstance(obj["Response"], dict):
                data = obj["Response"].get("Data")
                if isinstance(data, dict) and "Enabled" in data:
                    try:
                        self._enabled = bool(int(data["Enabled"]))
                        # invert: when capability enabled, sensor should report OFF
                        self._is_on = not self._enabled
                        return
                    except Exception:
                        # fall through to heuristics
                        pass
        except Exception:
            pass

        # Heuristic checks for enable/active markers in text
        lowered = text.lower()
        if "<enable>1</enable>" in lowered or "<enable>true" in lowered or '"enable": true' in lowered:
            self._enabled = True
            self._is_on = False
            return

        if "enabled" in lowered or "active" in lowered:
            # Treat enabled/active as enabled -> unsafe; invert for sensor state
            self._enabled = True
            self._is_on = False
            return

        self._enabled = False
        self._is_on = True
