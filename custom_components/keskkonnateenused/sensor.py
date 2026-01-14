from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.dt import parse_datetime, utcnow

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _safe_get(d: dict | list | None, *keys, default=None):
    if d is None:
        return default
    if isinstance(d, list):
        return d
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default


async def async_setup_entry(hass, entry, async_add_entities):
    _LOGGER.debug("sensor.async_setup_entry called for %s", entry.entry_id)
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not entry_data:
        _LOGGER.error("No coordinator for entry %s", entry.entry_id)
        return

    coordinator = entry_data["coordinator"]
    created = False

    def _extract_list(d):
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k in ("data", "items", "upcomingDischarges", "discharges"): 
                v = d.get(k)
                if isinstance(v, list):
                    return v
        return None

    async def _create_entities():
        nonlocal created
        if created:
            return
        data = coordinator.data
        if not data:
            _LOGGER.debug("No data available in coordinator for entry %s", entry.entry_id)
            return

        items = _extract_list(data) or []
        if not items and isinstance(data, list):
            items = data

        garbage_map: dict[str, list[dict]] = {}

        # find garbage type and date fields heuristically
        date_keys = ("date", "pickupDate", "plannedDate", "dischargeDate", "serviceDate", "next_date", "start")
        garbage_keys = ("garbage", "waste", "type", "name")

        for it in items:
            if not isinstance(it, dict):
                continue
            g = None
            for k in garbage_keys:
                if k in it and isinstance(it[k], str):
                    g = it[k]
                    break
            if g is None:
                # try nested/alternative
                g = str(it.get("garbage", "unknown")).strip()

            # find date value
            dval = None
            for dk in date_keys:
                if dk in it and it[dk]:
                    dval = it[dk]
                    break

            entry_record = {"raw": it, "date": dval}
            garbage_map.setdefault(g, []).append(entry_record)

        entities: list[GarbagePickupSensor] = []

        # helper to create safe identifier from address
        def _slugify(s: str) -> str:
            import re
            if s is None:
                return "unknown"
            s2 = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_")
            return s2[:64] if s2 else "unknown"

        address_keys = ("address", "addressText", "street", "streetAddress", "location", "addr", "address_line")

        # prefer stored address from config entry data if available
        stored_address = entry.data.get("address") if hasattr(entry, "data") else None
        for gtype, records in garbage_map.items():
            if stored_address:
                address_str = str(stored_address)
            else:
                # try to extract an address from one of the records
                address_str = None
                for rec in records:
                    raw = rec.get("raw") or {}
                    for ak in address_keys:
                        if ak in raw and raw[ak]:
                            address_str = str(raw[ak]).strip()
                            break
                    if address_str:
                        break
                if not address_str:
                    address_str = str(entry.data.get("contract_number", f"keskkonnateenused_{entry.entry_id}"))

            slug = _slugify(address_str)
            unique_id = f"{entry.entry_id}_{slug}_{gtype}"
            name = f"{gtype} pickup"
            device_info = {
                "identifiers": {(DOMAIN, f"address_{slug}")},
                "name": address_str,
                "manufacturer": "Keskkonnateenused",
            }

            entities.append(GarbagePickupSensor(coordinator, unique_id, name, gtype, records, device_info))

        if entities:
            async_add_entities(entities, True)
            created = True

    coordinator.async_add_listener(lambda: hass.async_create_task(_create_entities()))
    await _create_entities()


class GarbagePickupSensor(CoordinatorEntity, SensorEntity):
    entity_registry_enabled_default = True

    def __init__(self, coordinator, unique_id: str, name: str, garbage_type: str, records: list[dict], device_info: dict | None = None):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:trash-can"
        self._attr_native_unit_of_measurement = "days"
        self._garbage_type = garbage_type
        self._records = records
        self._state: Any = None
        self._device_info = device_info

    @property
    def native_value(self):
        return self._state

    @property
    def available(self) -> bool:
        return self._state is not None

    def _parse_date(self, val) -> datetime | None:
        if val is None:
            return None
        try:
            dt = parse_datetime(val)
            if dt is None and isinstance(val, (int, float)):
                # maybe unix timestamp
                return datetime.fromtimestamp(float(val), tz=timezone.utc)
            if dt is not None and dt.tzinfo is None:
                # assume UTC
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            try:
                # fallback: try ISO parsing
                return datetime.fromisoformat(str(val))
            except Exception:
                return None

    def _compute_days_to(self, target: datetime) -> int:
        if target is None:
            return -1
        now = utcnow()
        try:
            # compare dates to yield full days
            delta = target.date() - now.date()
            return delta.days
        except Exception:
            return -1

    def _update_state_from_data(self) -> None:
        data = self.coordinator.data
        items = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)

        # use our cached records if items not available
        records = self._records

        soonest: datetime | None = None
        for rec in records:
            dval = rec.get("date")
            if dval is None:
                # try locate in raw dict
                raw = rec.get("raw", {})
                for k in ("date", "pickupDate", "plannedDate", "dischargeDate", "serviceDate", "next_date", "start"):
                    if k in raw:
                        dval = raw[k]
                        break
            dt = self._parse_date(dval)
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if soonest is None or dt < soonest:
                soonest = dt

        if soonest is None:
            self._state = None
        else:
            days = self._compute_days_to(soonest)
            self._state = int(days)

    def _handle_coordinator_update(self) -> None:
        try:
            self._update_state_from_data()
        except Exception:
            _LOGGER.exception("Error updating sensor %s", self._attr_unique_id)
            self._state = None
        self.async_write_ha_state()

    @property
    def device_info(self):
        return self._device_info
