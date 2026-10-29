"""Test fixtures for the KOSPEL PPE4 integration.

The integration package imports Home Assistant when it is imported, so the
tests register a namespace package for ``custom_components.ppe4`` and import
the Home Assistant-free modules (``api``, ``registers``, ``const``) directly.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "ppe4"

if "custom_components" not in sys.modules:
    namespace = types.ModuleType("custom_components")
    namespace.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = namespace

if "custom_components.ppe4" not in sys.modules:
    package = types.ModuleType("custom_components.ppe4")
    package.__path__ = [str(COMPONENT)]
    sys.modules["custom_components.ppe4"] = package
