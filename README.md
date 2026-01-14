
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

- The integration requires a `contract_number` when adding the integration.
- On setup it fetches the API endpoint: `https://cms.keskkonnateenused.ee/wp-json/general-purpose-api/upcoming-discharges?contractNumber=<contract>`.
- The setup will attempt to extract the address from the API and ask you to confirm it; the confirmed `address` is saved to the config entry and used as the device name/identifier for created sensors.
- One sensor per garbage type is created. Sensor names use the format: `{garbage} pickup` (for example: `Glass pickup`).
- Each sensor's state is the number of days until the next pickup for that garbage type.
- Default update interval: once per hour. Change via the integration options.

Troubleshooting

- If you see errors when adding the integration, check Home Assistant logs. With Docker Compose:

```bash
docker compose logs --no-color --tail=400 ha-dev
```

- If the config flow does not detect an address you can enter it manually on the confirmation form.
- If sensors show unknown/unavailable, call the integration refresh service or restart Home Assistant to force the coordinator to fetch data.
