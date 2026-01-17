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

    # Register a lightweight admin service to force a coordinator refresh
    async def _handle_force_refresh(call):
        entries = list(hass.data.get(DOMAIN, {}).values())
        for entry in entries:
            coordinator = entry.get("coordinator")
            if coordinator is not None:
                hass.async_create_task(coordinator.async_refresh())

    hass.services.async_register(DOMAIN, "force_refresh", _handle_force_refresh)

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

    # Schedule a background first refresh so data is fetched without blocking startup.
    try:
        hass.async_create_task(coordinator.async_config_entry_first_refresh())
    except Exception:
        _LOGGER.exception("Failed scheduling initial refresh for %s", entry.entry_id)

    # Wait briefly for the initial data to appear (so sensors can be created with data),
    # but don't block startup for too long. Poll coordinator.data up to 30 seconds.
    try:
        import asyncio

        wait_secs = 30
        for _ in range(wait_secs):
            if coordinator.data:
                break
            await asyncio.sleep(1)
    except Exception:
        _LOGGER.exception("Waiting for initial data failed for %s", entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
