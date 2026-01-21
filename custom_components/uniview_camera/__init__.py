import asyncio
import json
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS


async def async_setup(hass: HomeAssistant, config: dict):
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Register device in device registry using DeviceInfo from the device API
    device_info_raw = entry.data.get("device_info")
    device_name = None
    device_model = None
    firmware = None
    serial = None
    try:
        if device_info_raw:
            obj = json.loads(device_info_raw)
            if isinstance(obj, dict) and "Response" in obj and isinstance(obj["Response"], dict):
                data = obj["Response"].get("Data")
                if isinstance(data, dict):
                    device_model = data.get("DeviceModel")
                    device_name = data.get("DeviceName")
                    firmware = data.get("FirmwareVersion")
                    serial = data.get("SerialNumber")
    except Exception:
        # ignore parse errors
        pass

    device_registry = dr.async_get(hass)
    identifiers = {(DOMAIN, entry.data.get("host"))}
    # Add serial as an additional identifier if present
    if serial:
        identifiers.add((DOMAIN, f"serial:{serial}"))

    # Prefer display name as "Uniview - <SerialNumber>" when serial is available
    display_name = f"Uniview - {serial}" if serial else (device_name or entry.data.get("host"))

    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
        manufacturer="Uniview",
        model=device_model,
        name=display_name,
        sw_version=firmware,
    )

    # Ensure existing device entry is updated to use the preferred display name
    try:
        if device and (device.name != display_name or device.sw_version != firmware or device.model != device_model):
            device_registry.async_update_device(
                device.id,
                name=display_name,
                sw_version=firmware,
                model=device_model,
                manufacturer="Uniview",
            )
    except Exception:
        # ignore device update errors
        pass

    # Forward setup to platforms (use plural API to support newer HA versions)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = all(
        await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(entry, p) for p in PLATFORMS]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
