from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, BASE_API, PLATFORMS, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    contract = entry.data.get("contract_number")
    if not contract:
        _LOGGER.error("No contract_number in config entry %s", entry.entry_id)
        return False

    api_url = f"{BASE_API}{contract}"
    update_interval = entry.options.get("update_interval", UPDATE_INTERVAL)

    async def async_fetch_data():
        _LOGGER.debug("Fetching keskkonnateenused data for %s", entry.entry_id)
        import async_timeout
        from aiohttp import ClientError
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        import asyncio

        session = async_get_clientsession(hass)
        attempts = 3
        backoff = 1
        for attempt in range(1, attempts + 1):
            try:
                async with async_timeout.timeout(10):
                    resp = await session.get(api_url)
                    resp.raise_for_status()
                    data = await resp.json()
                    _LOGGER.debug("Fetched %s items for %s", (len(data) if hasattr(data, '__len__') else 'unknown'), entry.entry_id)
                    return data
            except ClientError as err:
                _LOGGER.warning("HTTP error fetching data attempt %s: %s", attempt, err)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout fetching data attempt %s", attempt)
            except Exception:
                _LOGGER.exception("Unexpected error fetching data attempt %s", attempt)

            if attempt < attempts:
                await asyncio.sleep(backoff)
                backoff *= 2

        _LOGGER.error("All attempts to fetch keskkonnateenused data failed for %s", entry.entry_id)
        return None

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=async_fetch_data,
        update_interval=timedelta(seconds=update_interval),
    )

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    try:
        hass.async_create_task(coordinator.async_config_entry_first_refresh())
    except Exception:
        _LOGGER.exception("Failed scheduling initial refresh for %s", entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
