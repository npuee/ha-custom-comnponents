from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_API, PLATFORMS, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration as legacy stub (no-op)."""
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
    """Set up a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.warning("async_setup_entry called for %s", entry.entry_id)

    api_url = entry.data.get("api_url", DEFAULT_API)
    update_interval = entry.options.get("update_interval", UPDATE_INTERVAL)

    async def async_fetch_data():
        _LOGGER.warning("async_fetch_data starting for entry %s", entry.entry_id)
        import async_timeout
        from aiohttp import ClientError
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        import asyncio

        session = async_get_clientsession(hass)
        attempts = 3
        backoff = 1
        for attempt in range(1, attempts + 1):
            _LOGGER.warning("fetch attempt %s for %s", attempt, api_url)
            try:
                async with async_timeout.timeout(10):
                    resp = await session.get(api_url)
                    resp.raise_for_status()
                    data = await resp.json()
                    _LOGGER.warning("fetch success for %s, received %s items", entry.entry_id, (len(data) if hasattr(data, '__len__') else 'unknown'))
                    return data
            except ClientError as err:
                _LOGGER.warning("Attempt %s: HTTP error fetching fuel data: %s", attempt, err)
            except asyncio.TimeoutError:
                _LOGGER.warning("Attempt %s: Timeout fetching fuel data", attempt)
            except Exception:
                _LOGGER.exception("Attempt %s: Unexpected error fetching fuel data", attempt)

            if attempt < attempts:
                await asyncio.sleep(backoff)
                backoff *= 2

        # All attempts failed
        _LOGGER.error("All attempts to fetch fuel data failed for %s", entry.entry_id)
        return None

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=async_fetch_data,
        update_interval=timedelta(seconds=update_interval),
    )

    # store coordinator
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
    _LOGGER.warning("stored coordinator for entry %s", entry.entry_id)

    # Create devices for unique fuel types when data becomes available.
    from homeassistant.helpers import device_registry as dr

    async def _create_devices_from_data() -> None:
        data = coordinator.data
        if not data:
            return

        # extract companies list, support multiple API shapes
        def _extract_companies(d):
            if isinstance(d, dict):
                for k in ("Companies", "companies", "companiesList", "priceInfo", "PriceInfo"):
                    v = d.get(k)
                    if isinstance(v, list):
                        return v
                # nested under 'data'
                if isinstance(d.get("data"), dict):
                    for k in ("priceInfo", "Companies", "companies", "companiesList"):
                        v = d["data"].get(k)
                        if isinstance(v, list):
                            return v
            if isinstance(d, list):
                return d
            return None

        companies = _extract_companies(data)
        if not companies:
            return

        registry = dr.async_get(hass)
        seen = set()
        _LOGGER.warning("_create_devices_from_data: found %s companies", (len(companies) if hasattr(companies, '__len__') else 'unknown'))
        for comp in companies:
            stations = comp.get("Stations") or comp.get("stations") or comp.get("stationInfos") or comp.get("stationinfos")
            if stations is None and isinstance(comp, dict) and any(k in comp for k in ("Id", "id", "stationId", "DisplayName", "displayName")):
                stations = [comp]
            if not stations:
                continue
            for station in stations:
                fuels = station.get("Fuels") or station.get("fuels") or station.get("Prices") or station.get("fuelInfos") or station.get("fuelinfos")
                if not fuels:
                    continue
                for fuel in fuels:
                    fid = fuel.get("FuelTypeId") or fuel.get("fuelTypeId") or fuel.get("FuelType") or fuel.get("fuelType") or fuel.get("Id") or fuel.get("id")
                    fname = fuel.get("FuelTypeName") or fuel.get("FuelName") or fuel.get("name") or fuel.get("Name") or str(fid)
                    if fid is None:
                        continue
                    device_identifier = f"fuel_type_{fid}"
                    if device_identifier in seen:
                        continue
                    seen.add(device_identifier)
                    _LOGGER.warning("Creating device identifier=%s name=%s", device_identifier, fname)
                    dev = registry.async_get_or_create(
                        config_entry_id=entry.entry_id,
                        identifiers={(DOMAIN, device_identifier)},
                        name=str(fname),
                        manufacturer="FuelEstonia",
                    )
                    _LOGGER.warning("Created device id=%s", getattr(dev, 'id', dev))

    # Try creating devices now and also on future coordinator updates
    hass.async_create_task(_create_devices_from_data())
    coordinator.async_add_listener(lambda: hass.async_create_task(_create_devices_from_data()))

    # Schedule the coordinator's initial refresh in the background so data
    # becomes available and device creation runs without blocking startup.
    try:
        hass.async_create_task(coordinator.async_config_entry_first_refresh())
    except Exception:
        _LOGGER.exception("Failed scheduling initial refresh for %s", entry.entry_id)

    # forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
