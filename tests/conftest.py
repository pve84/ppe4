"""Test fixtures for the KOSPEL PPE4 integration.

When Home Assistant is installed (the dedicated test venv), the real package is
imported normally and the ``pytest_homeassistant_custom_component`` plugin is
enabled.  With a plain system Python the Home Assistant-free modules are loaded
through a synthetic namespace package so the pure unit tests still run.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "ppe4"


def _home_assistant_available() -> bool:
    """Return True when Home Assistant can be imported."""
    try:
        import homeassistant  # noqa: F401
    except ImportError:
        return False
    return True


HA_AVAILABLE = _home_assistant_available()

if HA_AVAILABLE:
    pytest_plugins = "pytest_homeassistant_custom_component"
else:
    if "custom_components" not in sys.modules:
        namespace = types.ModuleType("custom_components")
        namespace.__path__ = [str(ROOT / "custom_components")]
        sys.modules["custom_components"] = namespace

    if "custom_components.ppe4" not in sys.modules:
        package = types.ModuleType("custom_components.ppe4")
        package.__path__ = [str(COMPONENT)]
        sys.modules["custom_components.ppe4"] = package
