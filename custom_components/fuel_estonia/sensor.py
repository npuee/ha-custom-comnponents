import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    """Set up sensors from config entry coordinator data."""
    _LOGGER.warning("sensor.async_setup_entry called for %s", entry.entry_id)
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not entry_data:
        _LOGGER.error("No coordinator for entry %s", entry.entry_id)
        return

    coordinator = entry_data["coordinator"]
    created = False

    async def _create_entities():
        nonlocal created
        if created:
            return
        data = coordinator.data
        if not data:
            _LOGGER.warning("No data available in coordinator for entry %s during entity creation", entry.entry_id)
            return
            return

        # Determine companies list (support multiple API shapes)
        def _extract_companies(d):
            if isinstance(d, dict):
                for k in ("Companies", "companies", "companiesList", "priceInfo", "PriceInfo"):
                    v = _safe_get(d, k, default=None)
                    if isinstance(v, list):
                        return v
                if isinstance(d.get("data"), dict):
                    for k in ("priceInfo", "Companies", "companies", "companiesList"):
                        v = _safe_get(d.get("data"), k, default=None)
                        if isinstance(v, list):
                            return v
            if isinstance(d, list):
                return d
            return None

        companies = _extract_companies(data)

        if not companies:
            _LOGGER.warning("Unable to find companies/stations structure in data for entry %s", entry.entry_id)
            return

        entities: list[FuelStationSensor] = []

        _LOGGER.warning("Found %s companies in data for entry %s", (len(companies) if hasattr(companies, '__len__') else 'unknown'), entry.entry_id)
        for comp in companies:
            stations = _safe_get(comp, "Stations", "stations", "stationInfos", "stationinfos", default=None)
            if stations is None and isinstance(comp, dict) and any(k in comp for k in ("Id", "id", "stationId", "DisplayName", "displayName")):
                stations = [comp]
            if not stations:
                continue
            for station in stations:
                station_id = _safe_get(station, "Id", "id", "stationId", default=None)
                station_name = _safe_get(station, "DisplayName", "displayName", "displayname", "Name", default=str(station_id))
                fuels = _safe_get(station, "Fuels", "fuels", "Prices", "fuelInfos", "fuelinfos", default=None)
                if not fuels:
                    continue
                for fuel in fuels:
                    fuel_type_id = _safe_get(fuel, "FuelTypeId", "fuelTypeId", "FuelType", "fuelType", "Id", "id", default=None)
                    fuel_type_name = _safe_get(fuel, "FuelTypeName", "FuelName", "name", "Name", default=str(fuel_type_id))
                    price = _safe_get(fuel, "Price", "price", default=None)
                    # normalize price to float when possible
                    try:
                        price = float(price) if price is not None else None
                    except Exception:
                        price = None

                    if fuel_type_id is None or station_id is None:
                        _LOGGER.warning("Skipping fuel/station with missing id (fuel=%s, station=%s)", fuel, station)
                        continue

                    device_identifier = f"fuel_type_{fuel_type_id}"
                    device_info = {
                        "identifiers": {(DOMAIN, device_identifier)},
                        "name": f"{fuel_type_name}",
                        "manufacturer": "FuelEstonia",
                    }

                    unique_id = f"{entry.entry_id}_{fuel_type_id}_{station_id}"
                    name = f"{station_name} - {fuel_type_name}"

                    entities.append(FuelStationSensor(coordinator, unique_id, name, price, device_info))

        if entities:
            _LOGGER.warning("Creating %s sensor entities for entry %s", len(entities), entry.entry_id)
            async_add_entities(entities, True)
            created = True

    # Register listener so we create entities once data arrives (non-blocking)
    coordinator.async_add_listener(lambda: hass.async_create_task(_create_entities()))

    # Attempt immediate creation in case data already present
    await _create_entities()


class FuelStationSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing price of a fuel at a station."""

    entity_registry_enabled_default = False

    def __init__(self, coordinator, unique_id: str, name: str, price: Any, device_info: dict):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:fuel"
        self._attr_native_unit_of_measurement = "EUR"
        self._state = price
        self._device_info = device_info

    @property
    def native_value(self):
        if self._state is None:
            return None
        try:
            return f"{float(self._state):.3f}"
        except Exception:
            return None

    @property
    def available(self) -> bool:
        return self._state is not None

    @property
    def device_info(self):
        return self._device_info

    def _handle_coordinator_update(self) -> None:
        """Update the entity state when coordinator data changes."""
        # On each update, attempt to refresh our value from coordinator data
        data = self.coordinator.data
        # Attempt to find our price by scanning data (support multiple API shapes)
        found = None

        def _extract_companies(d):
            if isinstance(d, dict):
                # top-level shapes: Companies, priceInfo or nested under data
                for k in ("Companies", "companies", "companiesList", "priceInfo", "PriceInfo"):
                    v = _safe_get(d, k, default=None)
                    if isinstance(v, list):
                        return v
                if isinstance(d.get("data"), dict):
                    for k in ("priceInfo", "Companies", "companies", "companiesList"):
                        v = _safe_get(d.get("data"), k, default=None)
                        if isinstance(v, list):
                            return v
            if isinstance(d, list):
                return d
            return None

        companies = _extract_companies(data)

        if companies:
            # unique_id format: entryid_fuelid_stationid
            parts = self.unique_id.split("_")
            if len(parts) >= 3:
                fuel_id = parts[-2]
                station_id = parts[-1]
                for comp in companies:
                    stations = _safe_get(comp, "Stations", "stations", "stationInfos", "stationinfos", default=None)
                    if stations is None and isinstance(comp, dict) and any(k in comp for k in ("Id", "id", "stationId", "DisplayName", "displayName")):
                        stations = [comp]
                    if not stations:
                        continue
                    for station in stations:
                        sid = _safe_get(station, "Id", "id", "stationId", default=None)
                        if str(sid) != str(station_id):
                            continue
                        fuels = _safe_get(station, "Fuels", "fuels", "Prices", "fuelInfos", "fuelinfos", default=None)
                        if not fuels:
                            continue
                        for fuel in fuels:
                            fid = _safe_get(fuel, "FuelTypeId", "fuelTypeId", "FuelType", "fuelType", "Id", "id", default=None)
                            price = _safe_get(fuel, "Price", "price", default=None)
                            if str(fid) == str(fuel_id):
                                found = price
                                break
                        if found is not None:
                            break
                    if found is not None:
                        break

        # normalize found to float when possible
        try:
            self._state = float(found) if found is not None else None
        except Exception:
            self._state = None
        self.async_write_ha_state()
