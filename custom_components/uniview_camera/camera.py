import logging
import aiohttp
import requests
from requests.auth import HTTPDigestAuth

try:
    # Newer HA versions expose CameraEntity
    from homeassistant.components.camera import CameraEntity as CameraBase
except Exception:
    # Fallback to older Camera class name
    from homeassistant.components.camera import Camera as CameraBase
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    data = entry.data
    host = data.get("host")
    username = data.get("username")
    password = data.get("password")
    capabilities = data.get("capabilities")

    cam = UniviewCamera(host, username, password, capabilities)
    async_add_entities([cam])


async def async_unload_entry(hass: HomeAssistant, entry):
    return True


class UniviewCamera(CameraBase):
    def __init__(self, host: str, username: str, password: str, capabilities: str):
        self._host = host
        self._username = username
        self._password = password
        self._capabilities = capabilities
        self._name = f"Uniview {host}"
        self._unique_id = host
        # Provide attributes expected by Home Assistant camera base
        self._webrtc_provider = None
        self._attr_should_poll = False
        self._available = True
        # Indicate WebRTC/async streaming support (default to False)
        self._supports_native_async_webrtc = False
        self._supports_streaming = False
        # tokens used by HA camera for streaming access; ensure at least one entry
        self.access_tokens = [None]

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def available(self):
        return self._available

    @property
    def content_type(self) -> str | None:
        """Return the content type of the camera image."""
        return "image/jpeg"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": self._name,
            "manufacturer": "Uniview",
        }

    def stream_source(self) -> str:
        """Return RTSP stream URL for this camera (sync API)."""
        return f"rtsp://{self._username}:{self._password}@{self._host}:554/media/video1"

    async def async_stream_source(self) -> str:
        """Return RTSP stream URL for this camera (async API)."""
        return self.stream_source()

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        session = async_get_clientsession(self.hass)
        url = f"http://{self._host}/LAPI/V1.0/Streaming/channels/101/picture"

        def _sync_digest_fetch():
            try:
                resp = requests.get(url, auth=HTTPDigestAuth(self._username, self._password), timeout=10)
                if resp.status_code == 200:
                    return resp.content
                return None
            except requests.exceptions.RequestException as exc:
                _LOGGER.debug("Sync digest snapshot error: %s", exc)
                return None

        # Try digest via requests in executor (async-safe)
        try:
            content = await self.hass.async_add_executor_job(_sync_digest_fetch)
            if content:
                return content

            # Fallback to Basic auth via aiohttp
            async with session.get(url, auth=aiohttp.BasicAuth(self._username, self._password), timeout=10) as resp2:
                if resp2.status == 200:
                    _LOGGER.warning("Using Basic auth fallback for snapshot")
                    return await resp2.read()
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Error fetching image from %s: %s", self._host, exc)
        return None
