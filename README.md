# Net Metering for Home Assistant

A custom Home Assistant integration that estimates and accumulates **grid energy import and export** from your existing solar-production and household-consumption sensors. It does not require a physical grid meter.

> **Important:** These are calculated estimates, not direct measurements from a utility meter. Accuracy depends on the two source sensors and their reset behaviour.

## What it creates

After setup, the integration creates a **Net Metering** device with these entities:

- **Grid Import** (`kWh`) — cumulative estimated energy imported from the grid.
- **Grid Export** (`kWh`) — cumulative estimated energy exported to the grid.
- **Energy Consumption Fault** — diagnostic binary sensor that turns on when the configured consumption sensor is unavailable or invalid.

Cumulative totals are stored in Home Assistant storage so they survive Home Assistant restarts. Changing either source sensor establishes new reference readings without resetting the existing cumulative totals.

## How the calculation works

At each scheduled calculation, the integration compares the change in solar production with the change in household energy consumption:

```text
net energy = solar-production delta - consumption delta

net energy > 0  -> add the surplus to Grid Export
net energy < 0  -> add the absolute value to Grid Import
net energy = 0  -> no change to either total
```

Deltas and cumulative totals are rounded to six decimal places. The integration detects counter rollbacks and uses reference-only cycles after initial setup, sensor changes, and relevant reset boundaries to avoid adding a false delta.

Calculations are scheduled at minutes `:00`, `:05`, `:10`, `:15`, `:20`, `:25`, `:29`, `:30`, `:35`, `:40`, `:45`, `:50`, and `:55`. Date-boundary handling uses the `Asia/Kolkata` timezone.

### Source sensor requirements

1. **Solar Production Sensor** — a numeric energy entity in `kWh`, normally the inverter/SolarMan daily production total.
2. **Energy Consumption Sensor** — a numeric energy entity in `kWh` representing cumulative household energy consumption.

Both readings should increase as energy accumulates during a measurement period. In the setup flow, select whether each source sensor resets to zero at midnight. Defaults are **Yes** for solar production and **No** for consumption.

### Known limitations

- If the solar sensor is unavailable, its delta is treated as zero for that calculation and the last valid solar reference is preserved. Interval estimates can therefore be inaccurate while the sensor is unavailable and when it recovers.
- If the energy-consumption sensor is unavailable or invalid, calculations are suspended and the diagnostic fault entity turns on. The first valid reading after recovery establishes a new reference; energy accrued during the outage may not be counted.
- The integration estimates import/export from two sensors; it cannot replace a calibrated bidirectional utility meter for billing or settlement.
- Date-boundary logic is designed around `Asia/Kolkata`.

## Installation with HACS

This repository is prepared as a HACS custom integration. Once it is public on GitHub:

1. Open **HACS** in Home Assistant.
2. Open the top-right menu and choose **Custom repositories**.
3. Add `https://github.com/sheminasalam/net-metering` and choose **Integration** as the category.
4. Add the repository, open **Net Metering**, and download/install it.
5. Restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration**, search for **Net Metering**, and select the two source sensors and their reset behaviour.

[Open the repository on GitHub](https://github.com/sheminasalam/net-metering)

## Manual installation

1. Copy the `custom_components/net_metering` directory into the `custom_components` directory in your Home Assistant configuration directory. Create `custom_components` if it does not exist.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Net Metering**.

The resulting directory should look like this:

```text
<config>/
└── custom_components/
    └── net_metering/
        ├── __init__.py
        ├── manifest.json
        ├── config_flow.py
        ├── coordinator.py
        ├── calculation_engine.py
        ├── store.py
        ├── sensor.py
        ├── binary_sensor.py
        ├── diagnostics.py
        └── translations/
            └── en.json
```

## Troubleshooting

- Confirm both configured entities expose numeric `kWh` states.
- Check the **Energy Consumption Fault** entity if import/export stops updating.
- Download the integration diagnostics from its Home Assistant config-entry page when reporting a problem. Review the diagnostics before sharing them publicly, since they include sensor entity IDs and recent readings.
- Please report issues in the [GitHub issue tracker](https://github.com/sheminasalam/net-metering/issues) and include your Home Assistant version, relevant log messages, and a redacted diagnostics file.

## Development and tests

The calculation engine has unit tests that run independently of a Home Assistant installation. From the repository root, run:

```bash
python -m pip install pytest
python -m pytest -q
```

GitHub Actions is configured to run the unit tests, Home Assistant `hassfest`, and HACS validation on pushes and pull requests.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
