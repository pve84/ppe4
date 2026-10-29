"""Async client for the KOSPEL PPE4 Wi-Fi module.

The module serves a small REST API over plain HTTP:

``GET  /api/<start>/<count>``
    Returns a JSON object with one entry per register in the requested range,
    keyed by the decimal register number.

``POST /api/write``
    Accepts a JSON object of register/value pairs and writes them.

No authentication is used; the API is only reachable on the local network.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Final

from .const import DEFAULT_PORT, DEFAULT_TIMEOUT

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aiohttp import ClientSession

#: Marker used by the module for a value it could not read.
INVALID_REGISTER_VALUES: Final = {-1, 65535}


class Ppe4Error(Exception):
    """Base error for the PPE4 client."""


class Ppe4ConnectionError(Ppe4Error):
    """Raised when the module cannot be reached."""


class Ppe4ProtocolError(Ppe4Error):
    """Raised when the module answers with an unexpected payload."""


def _coerce_value(value: Any) -> float | int | None:
    """Return a numeric register value or ``None`` when it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return None


class Ppe4Client:
    """Minimal client for the PPE4 register API."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        """Return the base URL of the module."""
        return f"http://{self.host}:{self.port}"

    def block_url(self, start: int, count: int) -> str:
        """Return the URL that reads ``count`` registers from ``start``."""
        return f"{self.base_url}/api/{start}/{count}"

    @property
    def write_url(self) -> str:
        """Return the write endpoint URL."""
        return f"{self.base_url}/api/write"

    async def _async_request(
        self,
        method: str,
        url: str,
        *,
        body: str | None = None,
    ) -> Any:
        """Perform one request and return the decoded JSON body."""
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if body is not None:
            # The module's parser rejects whitespace, so the JSON body must be
            # serialized compactly instead of using aiohttp's ``json=`` helper.
            kwargs["data"] = body
            kwargs["headers"] = {"Content-Type": "application/json"}
        try:
            async with self._session.request(method, url, **kwargs) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Ppe4ProtocolError(
                        f"{method} {url} returned HTTP {response.status}: "
                        f"{text[:200]}"
                    )
                try:
                    payload = await response.json(content_type=None)
                except ValueError as err:
                    raise Ppe4ProtocolError(
                        f"{method} {url} returned invalid JSON"
                    ) from err
                self._raise_for_device_error(payload)
                return payload
        except Ppe4Error:
            raise
        except TimeoutError as err:
            raise Ppe4ConnectionError(
                f"Timed out talking to {self.host}:{self.port}"
            ) from err
        except OSError as err:
            raise Ppe4ConnectionError(
                f"Cannot reach {self.host}:{self.port}: {err}"
            ) from err
        except Exception as err:  # noqa: BLE001 - transport specific
            raise Ppe4ConnectionError(
                f"Error talking to {self.host}:{self.port}: {err}"
            ) from err

    async def async_read_block(self, start: int, count: int) -> dict[int, float | int]:
        """Read ``count`` registers starting at ``start``.

        Unknown or non-numeric entries returned by the module are skipped; a
        response that is not a JSON object is a protocol error.
        """
        payload = await self._async_request("GET", self.block_url(start, count))
        return self._parse_registers(payload)

    @staticmethod
    def _raise_for_device_error(payload: Any) -> None:
        """Raise when the module reports a logical error.

        The module answers with ``{"ver": "1.0", "status": "OK"|"ERROR",
        "status_value": "...", "status_msg": "...", "res": {...}}``.
        """
        if not isinstance(payload, dict):
            return
        status = payload.get("status")
        if status is None or status == "OK":
            return
        value = payload.get("status_value")
        message = payload.get("status_msg") or "unknown module error"
        raise Ppe4ProtocolError(f"Module error {value}: {message}")

    @staticmethod
    def _parse_registers(payload: Any) -> dict[int, float | int]:
        """Convert a JSON register object into ``{register: value}``."""
        if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
            payload = payload["res"]
        if not isinstance(payload, dict):
            raise Ppe4ProtocolError(
                f"Expected a JSON object of registers, got {type(payload).__name__}"
            )
        registers: dict[int, float | int] = {}
        for key, value in payload.items():
            try:
                register = int(key)
            except (TypeError, ValueError):
                continue
            number = _coerce_value(value)
            if number is None:
                continue
            registers[register] = number
        if not registers:
            raise Ppe4ProtocolError("Response contained no usable register values")
        return registers

    async def async_read_blocks(
        self, blocks: Iterable[tuple[int, int]]
    ) -> dict[int, float | int]:
        """Read several register blocks and merge the results."""
        registers: dict[int, float | int] = {}
        for start, count in blocks:
            registers.update(await self.async_read_block(start, count))
        return registers

    async def async_write_registers(self, values: Mapping[int, float | int]) -> None:
        """Write one or more registers."""
        if not values:
            return
        payload = {str(int(register)): int(value) for register, value in values.items()}
        body = json.dumps(payload, separators=(",", ":"))
        await self._async_request("POST", self.write_url, body=body)

    async def async_close(self) -> None:
        """Placeholder for symmetry; the session is owned by Home Assistant."""
        return None
