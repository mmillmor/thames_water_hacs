# Home Assistant Thames Water Integration

A custom Home Assistant integration to fetch smart water meter data from Thames Water and populate historical consumption statistics into Home Assistant's Energy and Water Dashboard.

## Key Features

- **Interactive Configuration Flow**: Prompts for your Thames Water username (email) and password, then presents a list of available smart meters to monitor.
- **Historical Long-Term Statistics**: Thames Water smart meter data is updated with a ~3-day delay. Rather than setting false "live" states, this integration uses Home Assistant's **Recorder Statistics API** (`async_add_external_statistics` & `async_import_statistics`) to backfill exact past hourly and daily consumption values with their true historical timestamps.
- **Energy & Water Dashboard Integration**: Integrates directly into Home Assistant's native **Energy -> Water Consumption** dashboard.
- **Sensors Included**:
  - `sensor.thames_water_<meter_id>_cumulative_consumption`: Total cumulative meter reading (in $m^3$) with attributes for data lag, last reading time, and reading type (Actual vs Estimated).
  - `sensor.thames_water_<meter_id>_latest_daily_usage`: Daily usage volume (in Liters) for the most recently published date.

---

## Why Historical Statistics?

Thames Water smart meter data is not available in real-time; readings are published to the web portal with a ~3-day lag. Standard Home Assistant sensors represent state *now*, so writing 3-day-old values directly into a standard sensor's state would distort graphs. 

This integration injects historical readings into Home Assistant's long-term statistics database mapped to their actual timestamps in the past. This allows Home Assistant's Water Dashboard to display accurate consumption for the exact days and hours water was used.

---

## Installation

### Method 1: HACS (Recommended)

1. Open **HACS** in your Home Assistant instance.
2. Click on the top-right menu and select **Custom repositories**.
3. Add `https://github.com/mmillmor/thames_water_hacs` (or your repository URL) with category **Integration**.
4. Search for **Thames Water** and click **Download**.
5. Restart Home Assistant.

### Method 2: Manual Installation

1. Download or clone this repository.
2. Copy the `custom_components/thames_water` folder into your Home Assistant directory (`/config/custom_components/thames_water`).
3. Restart Home Assistant.

---

## Setup & Configuration

1. In Home Assistant, navigate to **Settings** -> **Devices & Services**.
2. Click **Add Integration** and search for **Thames Water**.
3. Enter your Thames Water online portal username (email) and password.
4. Select the meter(s) you wish to add from the list presented.
5. (Optional) To view your water usage in the Energy Dashboard:
   - Go to **Settings** -> **Dashboards** -> **Energy**.
   - Under **Water Consumption**, click **Add Water Source**.
   - Select `Thames Water Meter <meter_id> Consumption`.

---

## Testing

Run unit tests locally with `pytest`:

```bash
pytest -v
```

---

## License

MIT License

## Credit
Built with inspiration from https://github.com/AyrtonB/Thames-Water and https://github.com/jelmer/homeassistant-thameswater
