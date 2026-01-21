
Fuel Estonia - Home Assistant custom integration skeleton

This repository contains a minimal skeleton custom integration `fuel_estonia`.

Install:

1. Copy the `custom_components/fuel_estonia` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

Notes:
- Entities are created disabled by default. Enable the ones you want in the entity registry.
- The integration fetches data from `https://fuelest.ee/Home/GetLatestPriceDataByStations?countryId=1` by default.
- Fill `company_map.json` with mappings from company id to name.

**Important**
-

- After you enable any sensors in Home Assistant, trigger an immediate data refresh so the entities populate their states right away by calling the service `fuel_estonia.force_refresh`.
	- Use Settings → Developer Tools → Services and call `fuel_estonia.force_refresh`, or call the REST API:

```bash
TOKEN=$(cat token.txt)
curl -X POST -H "Authorization: Bearer $TOKEN" \
	-H "Content-Type: application/json" \
	http://<home-assistant-host>:8123/api/services/fuel_estonia/force_refresh
```

This is necessary because entities are created disabled by default and will not have state history until the coordinator fetches data.

## Keskkonnateenused integration

The repository contains a custom integration `keskkonnateenused` that fetches upcoming garbage pickups from the Keskkonnateenused public API and creates sensors per garbage type.

Installation

1. Ensure the folder `custom_components/keskkonnateenused` is present under your Home Assistant `custom_components` directory (this repo includes it).
2. Restart Home Assistant (or the container).
3. In Home Assistant, go to Settings → Devices & Services → Add Integration → search `Keskkonnateenused`.
4. Enter your `contract_number` when prompted. The config flow will attempt to fetch the API and prefill the address for confirmation.

Behavior

- The integration requires a `contract_number` when adding the integration input but without leading L.
- On setup it fetches the API endpoint: `https://cms.keskkonnateenused.ee/wp-json/general-purpose-api/upcoming-discharges?contractNumber=<contract>`.
- The setup will attempt to extract the address from the API and ask you to confirm it; the confirmed `address` is saved to the config entry and used as the device name/identifier for created sensors.
- One sensor per garbage type is created. Sensor names use the format: `{garbage} pickup` (for example: `Glass pickup`).
- Each sensor's state is the number of days until the next pickup for that garbage type.
- Default update interval: once per hour. Change via the integration options.


## Uniview camera integration

This repository also includes a minimal Uniview camera custom integration under `custom_components/uniview_camera`.

Installation

1. Copy `custom_components/uniview_camera` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration via Settings → Devices & Services → Add Integration → search `Uniview`.

What it does

- Prompts for `host` (IP), `username` and `password` during setup.
- The integration queries `http://<host>/LAPI/V1.0/Smart/Capabilities` to discover smart features.
- If multiple capabilities are present, the flow asks you to select exactly one to expose.
- Creates one or more entities for that capability:
	- Binary sensor (device class `safety` for common security features). The entity name is the capability (e.g. `IntrusionDetection`).
	- Optional switch to enable/disable the capability via `http://<host>/LAPI/V1.0/Smart/<Capability>/Rule`.
- Device registry: registered as manufacturer `Uniview`, `model` from `DeviceModel`, `sw_version` from `FirmwareVersion`, and preferred display name `Uniview - <SerialNumber>` when available.

Authentication and networking

- The device uses HTTP Digest authentication. The integration performs Digest calls using `requests` inside an executor to avoid blocking the Home Assistant event loop.
- If the integration cannot parse JSON it will attempt XML fallbacks for capability discovery.

Notes

- Video/streaming was intentionally removed from this integration (no camera/stream platform).
- Binary sensor `status` attribute reflects the camera capability ("unsafe" when the capability is enabled). The binary sensor state is inverted by design (enabled capability -> sensor OFF) to fit the user's preference.
 - Binary sensor `status` attribute reflects the camera capability: `Enabled == 1` maps to "unsafe" and `Enabled == 0` maps to "safe". This follows the Home Assistant binary sensor convention for safety-type sensors.
