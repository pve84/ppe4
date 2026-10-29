"""Sanity checks for the integration package layout."""

from __future__ import annotations

import json
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ppe4"

REQUIRED_MANIFEST_KEYS = {
    "domain",
    "name",
    "codeowners",
    "config_flow",
    "documentation",
    "integration_type",
    "iot_class",
    "version",
}

ENTITY_TRANSLATION_KEYS = {
    "water_heater": ("water_heater",),
    "sensor": (
        "inlet_temperature",
        "flow_rate",
        "power",
        "current_temperature",
        "target_temperature",
        "max_temperature",
        "error",
    ),
    "binary_sensor": ("problem",),
    "button": ("refresh",),
}


def test_manifest() -> None:
    """The manifest has the keys Home Assistant requires."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert REQUIRED_MANIFEST_KEYS <= manifest.keys()
    assert manifest["domain"] == COMPONENT.name
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_polling"
    version = manifest["version"].split(".")
    assert len(version) == 3 and all(part.isdigit() for part in version)


def test_translations_cover_entities() -> None:
    """Every entity translation key used by the platforms exists."""
    strings = json.loads((COMPONENT / "strings.json").read_text())
    entity = strings["entity"]
    for platform, keys in ENTITY_TRANSLATION_KEYS.items():
        assert platform in entity
        for key in keys:
            assert key in entity[platform], f"missing translation for {platform}.{key}"


def test_translation_files_match_strings() -> None:
    """The English translation mirrors strings.json."""
    strings = json.loads((COMPONENT / "strings.json").read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())
    assert strings == english


def test_config_flow_errors_translated() -> None:
    """Config and options flow errors referenced in code exist in strings."""
    strings = json.loads((COMPONENT / "strings.json").read_text())
    assert "cannot_connect" in strings["config"]["error"]
    assert "invalid_registers" in strings["options"]["error"]
    assert "error_registers_required" in strings["options"]["error"]


def test_services_file_parses() -> None:
    """services.yaml is valid YAML and documents the two actions."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - optional dependency
        return
    services = yaml.safe_load((COMPONENT / "services.yaml").read_text())
    assert set(services) == {"read_registers", "write_registers"}
    assert "start" in services["read_registers"]["fields"]
    assert "registers" in services["write_registers"]["fields"]


def test_python_files_compile() -> None:
    """Every module compiles."""
    import py_compile
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        for path in COMPONENT.glob("*.py"):
            py_compile.compile(
                str(path), cfile=str(Path(tmp) / f"{path.stem}.pyc"), doraise=True
            )
