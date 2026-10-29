"""Home Assistant level tests: does the integration create entities?

These run with ``pytest-homeassistant-custom-component`` in the dedicated venv.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import CONF_HOST, CONF_PORT  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.ppe4.const import DOMAIN  # noqa: E402

HOST = "192.168.2.165"

BLOCKS = {
    (1014, 8): {
        "1014": 300,
        "1015": 600,
        "1016": 300,
        "1017": 600,
        "1018": 300,
        "1019": 600,
        "1020": 300,
        "1021": 600,
    },
    (1128, 25): {
        "1128": 1665,
        "1129": 21,
        "1130": 0,
        "1131": 0,
        "1132": 0,
        "1133": 0,
        "1134": 267,
        "1135": 266,
        "1136": 520,
        "1137": 0,
        "1138": 0,
        "1139": 0,
        "1140": 500,
        "1141": 0,
        "1142": 90,
        "1143": 15000,
        "1144": 15000,
        "1145": 0,
        "1146": 26,
        "1147": 10,
        "1148": 30,
        "1149": 5,
        "1150": 2,
        "1151": 2,
        "1152": 34,
    },
    (1388, 8): {
        "1388": 600,
        "1389": 0,
        "1390": 0,
        "1391": 500,
        "1392": 450,
        "1393": 500,
        "1394": 550,
        "1395": 700,
    },
}


def envelope(registers: dict[str, int]) -> dict:
    """Return the module's response envelope."""
    return {
        "ver": "1.0",
        "status": "OK",
        "status_value": "0",
        "res": registers,
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from the repository."""
    yield


def _mock_device(aioclient_mock, overrides: dict[str, int] | None = None):
    """Serve the three live blocks, optionally with register overrides."""
    blocks = {key: dict(values) for key, values in BLOCKS.items()}
    for register, value in (overrides or {}).items():
        for values in blocks.values():
            if register in values:
                values[register] = value
    for (start, count), registers in blocks.items():
        aioclient_mock.get(
            f"http://{HOST}:80/api/{start}/{count}", json=envelope(registers)
        )
    return aioclient_mock


@pytest.fixture
def mock_device(aioclient_mock):
    """Serve the three live blocks."""
    return _mock_device(aioclient_mock)


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_PORT: 80},
        options={},
        title="KOSPEL PPE4 (test)",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities(hass: HomeAssistant, mock_device) -> None:
    """The integration sets up and creates its entities."""
    entry = await _setup_entry(hass)
    assert entry.state.name == "LOADED"

    states = {state.entity_id: state for state in hass.states.async_all()}
    print("\nENTITIES:", sorted(states))

    sensor_ids = sorted(eid for eid in states if eid.startswith("sensor."))
    assert "sensor.kospel_ppe4_inlet_temperature" in sensor_ids
    assert "sensor.kospel_ppe4_water_temperature" in sensor_ids
    assert "sensor.kospel_ppe4_flow_rate" in sensor_ids
    assert "sensor.kospel_ppe4_heater_power" in sensor_ids
    assert "sensor.kospel_ppe4_target_temperature" in sensor_ids
    assert "sensor.kospel_ppe4_maximum_temperature" in sensor_ids

    assert states["sensor.kospel_ppe4_inlet_temperature"].state == "26.7"
    assert states["sensor.kospel_ppe4_water_temperature"].state == "26.6"
    assert states["sensor.kospel_ppe4_target_temperature"].state == "50.0"
    assert states["sensor.kospel_ppe4_maximum_temperature"].state == "60.0"
    assert states["sensor.kospel_ppe4_error"].state == "OK"
    assert "water_heater." in " ".join(states)


async def test_error_code_is_exposed(hass: HomeAssistant, aioclient_mock) -> None:
    """An error code in a slot shows up on the error and problem sensors."""
    _mock_device(aioclient_mock, {"1131": 4})
    await _setup_entry(hass)

    error = hass.states.get("sensor.kospel_ppe4_error")
    assert error is not None
    assert error.state == "4: Temperature sensor error, negative power"
    assert error.attributes["errors"][0]["code"] == 4
    assert error.attributes["registers"] == {"1130": 0, "1131": 4, "1132": 0, "1133": 0}

    problem = hass.states.get("binary_sensor.kospel_ppe4_problem")
    assert problem is not None
    assert problem.state == "on"


async def test_unknown_error_value_is_visible(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A code outside the catalogue still raises the problem sensor."""
    _mock_device(aioclient_mock, {"1132": 99})
    await _setup_entry(hass)

    error = hass.states.get("sensor.kospel_ppe4_error")
    assert error is not None
    assert "99" in error.state
    assert error.attributes["unknown_values"] == [99]
    assert hass.states.get("binary_sensor.kospel_ppe4_problem").state == "on"


async def test_set_temperature_writes_whole_group(
    hass: HomeAssistant, mock_device
) -> None:
    """Setting the target writes the five-register settings group."""
    await _setup_entry(hass)
    mock_device.get(
        f"http://{HOST}:80/api/1390/5",
        json=envelope(
            {"1390": 0, "1391": 500, "1392": 450, "1393": 500, "1394": 550}
        ),
    )
    mock_device.post(
        f"http://{HOST}:80/api/write",
        json={"ver": "1.0", "status": "OK", "status_value": "0"},
    )

    await hass.services.async_call(
        "water_heater",
        "set_temperature",
        {
            "entity_id": "water_heater.kospel_ppe4_water_heater",
            "temperature": 47,
        },
        blocking=True,
    )

    posts = [call for call in mock_device.mock_calls if call[0] == "POST"]
    assert posts, "no write request was made"
    assert posts[-1][2] == '{"1390":0,"1391":470,"1392":450,"1393":500,"1394":550}'
