"""Constants and register model for the KOSPEL PPE4 integration.

The heater exposes a plain-HTTP, JSON-over-registers API served by its Wi-Fi
module (see README.md for the protocol evidence):

* ``GET  http://<host>/api/<start>/<count>`` reads ``count`` consecutive
  registers starting at ``start`` and returns a JSON object keyed by the
  decimal register number, e.g. ``{"1388": 452, "1389": 0, ...}``.
* ``POST http://<host>/api/write`` writes a JSON object of register/value
  pairs, e.g. ``{"1390": 45, "1391": 0, ...}``.

Register numbering and the concrete meaning of most registers were recovered
from the vendor Android application.  Units are proven for the live block
(``°C``, ``l/min``, ``kW`` are the exact format strings shipped next to those
register lookups); the mapping of a register to a *specific* physical quantity
(inlet vs. outlet vs. setpoint) is inferred and can be overridden from the
integration options.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DOMAIN: Final = "ppe4"
MANUFACTURER: Final = "KOSPEL"
MODEL: Final = "PPE4.M"
DEFAULT_NAME: Final = "KOSPEL PPE4"

DEFAULT_PORT: Final = 80
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 600
DEFAULT_TIMEOUT: Final = 10

#: Register blocks the vendor app polls for live data (start, count).
LIVE_BLOCKS: Final[tuple[tuple[int, int], ...]] = (
    (1014, 8),
    (1128, 25),
    (1388, 8),
)

#: Register group written by the vendor app when settings are saved.
WRITE_GROUP_START: Final = 1390
WRITE_GROUP_COUNT: Final = 5

#: Value the module uses for "no reading" (signed -1).
INVALID_VALUE: Final = 65535

#: Number of fault bits described by the shipped fault catalogue.
FAULT_COUNT: Final = 29

#: Fault catalogue shipped in the Android app as resource strings
#: ``IDS_62`` .. ``IDS_90`` (English text, in shipped order).
FAULTS: Final[dict[int, str]] = {
    1: "Voltage on probe without heating",
    2: "Temperature in sensor damage",
    3: "Temperature out sensor damage",
    4: "Temperature sensor error, negative power",
    5: "Turbine operation error",
    6: "Air probe error",
    7: "Output temperature above permissible",
    8: "Exceeding maximum flow value",
    9: "Network frequency measurement error",
    10: "Unknown configuration",
    11: "Multiple detection of output temperature above permissible",
    12: "Problem with air probe",
    13: "Problem with turbine",
    14: "Problem with water flow",
    15: "Problem with water temperature",
    16: "Problem with heating unit",
    17: "Low battery voltage",
    18: "Problem with battery",
    19: "Difference in inlet-outlet sensor readings",
    20: "Communication problem with internal clock",
    21: "Communication problem with I2C bus",
    22: "Problem with WIFI communication",
    23: "CPU damage",
    24: "Input temperature too low",
    25: "Output temperature too low",
    26: "CPU temperature too low",
    27: "Input temperature too high",
    28: "CPU temperature too high",
    29: "Problem with EEPROM API",
}

#: Polish fault text, used for the ``fault_*`` diagnostic attributes.
FAULTS_PL: Final[dict[int, str]] = {
    1: "Napięcie na sondzie bez zał. grzania",
    2: "Uszkodzenie czujnika temperatury wejściowego",
    3: "Uszkodzenie czujnika temperatury wyjściowego",
    4: "Błąd czujników temp.",
    5: "Błąd pracy turbinki",
    6: "Błąd sondy powietrznej",
    7: "Temp. na wyj. powyżej dopuszczalnej",
    8: "Przekroczenie wartości maks. przepływu",
    9: "Błąd pomiaru częstotliwości sieci",
    10: "Nieznana konfiguracja",
    11: "Detekcja temp. na wyj. powyżej",
    12: "Problem z sondą powietrza",
    13: "Problem z turbinką",
    14: "Problem z przepływem wody",
    15: "Problem z temperaturą wody",
    16: "Problem z zespołem grzejnym",
    17: "Niski poziom napięcia baterii",
    18: "Problem z baterią",
    19: "Różnica w odczycie czujników",
    20: "Problem kom. z zegarem wew.",
    21: "Problem kom. z magistralą i2c",
    22: "Problem z kom. WIFI",
    23: "Uszkodzenie CPU",
    24: "Temp. wejściowa za niska",
    25: "Temp. wyjściowa za niska",
    26: "Temp. CPU za niska",
    27: "Temp. wejściowa za wysoka",
    28: "Temperatura CPU za wysoka",
    29: "Problem z zapisem EEPROM",
}


@dataclass(frozen=True, kw_only=True)
class RegisterSpec:
    """Description of one logical value backed by a heater register."""

    key: str
    register: int
    translation_key: str
    scale: float = 0.1
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    precision: int | None = None
    icon: str | None = None
    entity_category: str | None = None


#: Registers with a proven unit (``%1.1f °C``, ``%1.1f l/min``, ``%1.1f kW``
#: literals sit next to these register numbers in the vendor app) and an
#: inferred physical assignment.  Everything here can be overridden in the
#: integration options.
REGISTER_SPECS: Final[tuple[RegisterSpec, ...]] = (
    RegisterSpec(
        key="inlet_temperature",
        register=1134,
        translation_key="inlet_temperature",
        unit="°C",
        device_class="temperature",
        precision=1,
    ),
    RegisterSpec(
        key="current_temperature",
        register=1135,
        translation_key="current_temperature",
        unit="°C",
        device_class="temperature",
        precision=1,
    ),
    RegisterSpec(
        key="flow_rate",
        register=1137,
        translation_key="flow_rate",
        unit="L/min",
        device_class=None,
        state_class="measurement",
        precision=1,
    ),
    RegisterSpec(
        key="power",
        register=1138,
        translation_key="power",
        unit="kW",
        device_class="power",
        state_class="measurement",
        precision=1,
    ),
    RegisterSpec(
        key="target_temperature",
        register=1391,
        translation_key="target_temperature",
        unit="°C",
        device_class="temperature",
        state_class=None,
        precision=1,
        icon="mdi:thermometer-check",
    ),
    RegisterSpec(
        key="max_temperature",
        register=1388,
        translation_key="max_temperature",
        unit="°C",
        device_class="temperature",
        state_class=None,
        precision=1,
        icon="mdi:thermometer-high",
        entity_category="diagnostic",
    ),
)

#: Specification used for the optional fault register (raw status word).
FAULT_SPEC: Final = RegisterSpec(
    key="fault_code",
    register=0,
    translation_key="fault_code",
    scale=1.0,
    unit=None,
    device_class=None,
    state_class=None,
    icon="mdi:alert-circle-outline",
)

#: Values accepted by the ``fault_encoding`` option.
FAULT_ENCODING_BITMASK: Final = "bitmask"
FAULT_ENCODING_CODE: Final = "code"
FAULT_ENCODING_NONE: Final = "none"
FAULT_ENCODINGS: Final = (
    FAULT_ENCODING_NONE,
    FAULT_ENCODING_BITMASK,
    FAULT_ENCODING_CODE,
)

#: Temperature limits used by the water heater entity.
MIN_TEMPERATURE: Final = 20.0
MAX_TEMPERATURE: Final = 60.0
TARGET_TEMPERATURE_STEP: Final = 1.0
