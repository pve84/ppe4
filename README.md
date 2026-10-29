# KOSPEL PPE4 — Home Assistant integration

Local-only Home Assistant integration for the **KOSPEL PPE4.M** instantaneous
water heater (`pl.PPE4`).  It talks to the heater's Wi-Fi module over the same
plain-HTTP register API the vendor Android app uses — no cloud, no account, no
TLS.

> **Status:** verified against a real PPE4.M (firmware API `ver 1.0`) on
> 2026-10-29: register reads, the JSON envelope, the error replies and a
> setpoint round-trip (50.0 °C → 47.0 °C → 50.0 °C) all work.  The register map
> below is the verified one; the fault register is still unknown.  Every value
> can be remapped from the options flow, and `read_registers` /
> `write_registers` actions plus the diagnostics download make further
> calibration straightforward.

## What you get

| Entity | Type | Notes |
|---|---|---|
| `water_heater.kospel_ppe4_water_heater` | water heater | current water temperature, target temperature, on/off from heater power |
| `sensor.kospel_ppe4_water_temperature` | sensor | outlet water temperature |
| `sensor.kospel_ppe4_target_temperature` | sensor | configured setpoint |
| `sensor.kospel_ppe4_inlet_temperature` | sensor | inlet temperature |
| `sensor.kospel_ppe4_outlet_temperature` | sensor | outlet temperature |
| `sensor.kospel_ppe4_flow_rate` | sensor | water flow in L/min |
| `sensor.kospel_ppe4_heater_power` | sensor | heating power in kW |
| `sensor.kospel_ppe4_fault_code` | diagnostic sensor | raw fault word (when a fault register is configured) |
| `sensor.kospel_ppe4_active_faults` | sensor | number of active faults; decoded texts in the attributes |
| `binary_sensor.kospel_ppe4_problem` | problem | on when any fault is reported |
| `button.kospel_ppe4_refresh` | button | poll the heater immediately |

Plus two actions: `ppe4.read_registers` and `ppe4.write_registers`.

## The protocol

The module serves a small REST API on TCP/80.  Registers are Modbus-style
holding registers addressed by decimal number (the app uses 1000–1695).

```text
GET  http://<host>/api/<start>/<count>
 ->  {"ver":"1.0","status":"OK","status_value":"0",
      "res":{"<register>": <value>, ...}}

POST http://<host>/api/write        body: {"<register>":<value>, ...}   (compact!)
 <-  {"ver":"1.0","status":"OK","status_value":"0"}
```

Quirks confirmed on hardware:

* every answer is wrapped in the `ver`/`status`/`status_value`/`res` envelope;
  `status` is `"OK"` or `"ERROR"` and errors carry `status_msg`;
* **write bodies must be compact JSON** — the module's parser rejects spaces
  with `status_value -10` ("A character that is not allowed was used"); the
  client serialises with `separators=(",", ":")` instead of aiohttp's `json=`;
* out-of-range reads answer `"res":` (invalid JSON) with `status OK`, and
  reading a non-register path returns `-11` ("Wrong MODBUS start address.");
* `65535` is the module's “no reading” marker (signed `-1`) and is surfaced as
  unavailable.

The integration polls three live blocks every 30 s by default:

| Block | Registers | Use |
|---|---|---|
| `/api/1014/8` | 1014–1021 | device / configuration |
| `/api/1128/25` | 1128–1152 | live measurements and parameters |
| `/api/1388/8` | 1388–1395 | live status and setpoints |

Two further pairs of 30- and 48-register blocks (`/api/1448/30`, `/api/1520/48`,
`/api/1576/30`, `/api/1648/48`) carry consumption statistics.  They are not
polled because their semantics are not established.

Writing a setpoint mirrors the app: read the five-register settings group
`1390–1394`, replace only the target register and write the group back, so
unknown fields keep their values.

## Register map and confidence

| Logical value | Register | Scale | Verified how |
|---|---|---|---|
| Inlet temperature (Tin) | 1134 | ×0.1 | app labels `lTin`; reads 26.7 °C on cold water |
| Water temperature (Tout) | 1135 | ×0.1 | app labels `lTout`; reads 26.6 °C on cold water |
| Flow rate | 1137 | ×0.1 | `%1.1f l/min` literal at this register |
| Heater power | 1138 | ×0.1 | `%1.1f kW` literal at this register |
| Target temperature | 1391 | ×0.1 | **written and read back on hardware**: 500 → 470 → 500 |
| Live setpoint echo | 1140 | ×0.1 | followed 1391 during the write test |
| Maximum temperature | 1388 | ×0.1 | reads 60.0 °C; app labels `lTemperaturaMaksymalna` |
| Fault word | — | — | **unknown** — enable once identified |

The five-register group the vendor app writes is `1390–1394`
(`{"1390":0,"1391":<setpoint>,"1392":450,"1393":500,"1394":550}` on the test
unit); the integration preserves the other four when changing the setpoint.

Scale `0.1` means the register holds tenths (`500` → `50.0`).  If your firmware
uses whole degrees, override the scale in the options.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → *Custom repositories*.
2. Add this repository URL, category *Integration*.
3. Install "KOSPEL PPE4" and restart Home Assistant.

### Manual

Copy `custom_components/ppe4` into your Home Assistant `config/custom_components`
directory and restart.

## Configuration

1. *Settings → Devices & services → Add integration → KOSPEL PPE4*.
2. Enter the module address (e.g. `192.168.8.1` while the heater is in setup
   mode, or the DHCP address it received on your LAN) and port `80`.
   The flow reads a register block to verify the connection.

### Options

* **Polling interval** — 5–600 s (default 30).
* **Fault register / encoding** — leave *No fault handling* until you know the
  register; see *Calibrating* below.
* **Register overrides (JSON)** — remap any value, optionally with a scale:

```json
{
  "current_temperature": 1388,
  "target_temperature": [1390, 0.1],
  "inlet_temperature": 1134,
  "outlet_temperature": 1135,
  "flow_rate": 1137,
  "power": 1138
}
```

## Actions

Read a raw block (response is returned to the caller):

```yaml
action: ppe4.read_registers
data:
  start: 1388
  count: 8
response_variable: block
```

Write registers:

```yaml
action: ppe4.write_registers
data:
  registers:
    1390: 45
```

Pass `entry_id` when more than one heater is configured.

## Calibrating the register map

The app exposes everything through raw registers, which makes calibration
straightforward:

1. Open *Developer tools → Actions*, run `ppe4.read_registers` for
   `start: 1128, count: 25` with the heater idle, then again while drawing hot
   water.  The registers that move are your temperatures and flow.
2. Compare the numbers with the heater's own display (or the vendor app):
   `452` on a 45.2 °C reading means scale `0.1`, `45` means scale `1`.
3. The setpoint lives at 1391 and is mirrored at 1140; changing it via
   `ppe4.write_registers` (compact JSON is produced by the client) updates both.
3. To find the fault register, trigger a fault (e.g. close the water inlet) and
   diff the `registers` map in *Settings → Devices & services → KOSPEL PPE4 →
   Download diagnostics*.  Enable fault handling with that register and choose
   *bitmask* (bit *n* = fault *n+1*) or *single fault code*.
4. Store any correction in the options *Register overrides*.

## Fault catalogue

The app ships 29 fault texts (`IDS_62`–`IDS_90`).  They are exposed by
`sensor.kospel_ppe4_active_faults` (attributes) and
`binary_sensor.kospel_ppe4_problem` once a fault register is configured:

| Code | Meaning |
|---|---|
| 1 | Voltage on probe without heating |
| 2 | Temperature in sensor damage |
| 3 | Temperature out sensor damage |
| 4 | Temperature sensor error, negative power |
| 5 | Turbine operation error |
| 6 | Air probe error |
| 7 | Output temperature above permissible |
| 8 | Exceeding maximum flow value |
| 9 | Network frequency measurement error |
| 10 | Unknown configuration |
| 11 | Multiple detection of output temperature above permissible |
| 12 | Problem with air probe |
| 13 | Problem with turbine |
| 14 | Problem with water flow |
| 15 | Problem with water temperature |
| 16 | Problem with heating unit |
| 17 | Low battery voltage |
| 18 | Problem with battery |
| 19 | Difference in inlet-outlet sensor readings |
| 20 | Communication problem with internal clock |
| 21 | Communication problem with I2C bus |
| 22 | Problem with WIFI communication |
| 23 | CPU damage |
| 24 | Input temperature too low |
| 25 | Output temperature too low |
| 26 | CPU temperature too low |
| 27 | Input temperature too high |
| 28 | CPU temperature too high |
| 29 | Problem with EEPROM API |

These are the controller's diagnostic fault texts.  The seven-segment display
on the heater itself uses a different set (`E01`–`E11`, `W01`–`W06`) documented
in the installation manual.

## Troubleshooting

| Symptom | Check |
|---|---|
| *Could not read registers* | Ping the module, confirm port 80, confirm Home Assistant is on the same Wi-Fi/LAN |
| Values are 10× too high | Set scale `1` for that register in the overrides |
| Values are 10× too low | Set scale `0.1` for that register |
| Target temperature has no effect | Confirm 1391 changes in the diagnostics; older firmware may use 1390 |
| Write returns `-10` | Body contained whitespace/non-compact JSON — use the integration, not hand-written curl |
| Faults never appear | Configure the fault register and encoding in the options |

Diagnostics (*Download diagnostics*) include the resolved register map, the raw
register dump and the decoded fault state.

## Hardware verification (2026-10-29)

Tested against a live PPE4.M at `192.168.2.165` (API `ver 1.0`):

| Check | Result |
|---|---|
| `GET /api/1014/8`, `1128/25`, `1388/8` | 41 registers read, envelope parsed |
| `GET http://<host>/` | module's "KOSPEL PPE4 Wi-Fi configuration" page |
| Setpoint write 50.0 → 47.0 °C | `OK`; 1391 = 470, live echo 1140 = 470 |
| Restore 47.0 → 50.0 °C | `OK`; 1391 = 500, 1140 = 500 |
| Spaced JSON body | rejected with `-10 A character that is not allowed was used` |
| Out-of-range read | `Ppe4ProtocolError` (invalid empty `res`) |
| Error path `/api/write` via GET | `-11 Wrong MODBUS start address.` |

Measured values at test time: Tin 26.7 °C, Tout 26.6 °C, flow 0 L/min,
power 0 kW, setpoint 50.0 °C, max temperature 60.0 °C (heater idle).

## Evidence and provenance

The protocol, register numbers and fault catalogue were recovered from
`KOSPEL-PPE4_1.0.0_apkcube.apks` (`base.apk`
SHA-256 `23b5953e1082edd749c69d40387cd333cfe16ec562c6d9d0435ba72ecbf16c90`,
v1+v2+v3 signed, one signer).  The app is a Delphi/FireMonkey build with all
logic in `lib/arm64-v8a/libPPE4.so`; the Android DEX only contains Play
Services/AdMob.

Concrete evidence for this integration:

* URL templates `http://%s/api/{1014/8,1128/25,1388/8,1448/30,1520/48,1576/30,1648/48,write}`
  in `libPPE4.so` (`0x187e68c`…`0x18804cc`).
* Writers send `{"1390":%d,"1391":%d,"1392":%d,"1393":%d,"1394":%d}` (`0x187f37c`),
  next to an `application/json` literal.
* Register-count match: each path count equals the contiguous register-key
  block the app parses (1014→8, 1128→25, 1388→8, 1448→30, 1520→48, 1576→30,
  1648→48, 1000→44).
* Unit literals `%1.1f °C`, `%1.1f l/min`, `%1.1f kW` adjacent to registers
  1134/1135/1138 and 1137.
* Fault texts as resource strings `IDS_62`…`IDS_90` with 22 translations.

## Development

```bash
python3 -m pytest            # 33 pure-python unit tests, no Home Assistant needed
```

For Home Assistant-level tests add
`pytest-homeassistant-custom-component` (they require a full HA test harness).

```
custom_components/ppe4/
├── __init__.py          # setup, actions
├── api.py               # HTTP client (no HA imports, unit-tested)
├── registers.py         # register-map + fault decoding (no HA imports)
├── const.py             # catalogue and defaults
├── coordinator.py       # polling + setpoint write
├── config_flow.py       # add / reconfigure / options
├── entity.py            # device info
├── sensor.py            # register sensors, fault sensors
├── binary_sensor.py     # problem
├── water_heater.py      # target temperature
├── button.py            # refresh
├── diagnostics.py
├── services.yaml
├── strings.json
└── translations/en.json
```
