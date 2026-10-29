"""Tests for the PPE4 HTTP client.

The tests use ``asyncio.run`` instead of pytest-asyncio so the suite runs with
a plain pytest installation.
"""

from __future__ import annotations

import asyncio

import pytest

from custom_components.ppe4.api import (
    Ppe4Client,
    Ppe4ConnectionError,
    Ppe4ProtocolError,
)


class FakeResponse:
    """Minimal aiohttp response double."""

    def __init__(self, status: int = 200, payload=None, text: str = "") -> None:
        self.status = status
        self._payload = payload
        self._text = text

    async def text(self) -> str:
        return self._text

    async def json(self, content_type=None):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None


class FakeSession:
    """Records requests and returns queued responses."""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(*responses) -> tuple[Ppe4Client, FakeSession]:
    """Return a client wired to a fake session."""
    session = FakeSession(*responses)
    return Ppe4Client(session, "192.168.8.1"), session


def test_urls() -> None:
    """URLs follow the module's routing scheme."""
    client, _ = make_client()
    assert client.base_url == "http://192.168.8.1:80"
    assert client.block_url(1388, 8) == "http://192.168.8.1:80/api/1388/8"
    assert client.write_url == "http://192.168.8.1:80/api/write"


def test_read_block_parses_numbers() -> None:
    """Numeric values are kept, junk entries are skipped."""

    async def run() -> None:
        client, session = make_client(
            FakeResponse(payload={"1388": 452, "1389": "0", "1390": 45.5, "junk": "x"})
        )
        registers = await client.async_read_block(1388, 8)
        assert registers == {1388: 452, 1389: 0, 1390: 45.5}
        method, url, kwargs = session.calls[0]
        assert method == "GET"
        assert url.endswith("/api/1388/8")
        assert kwargs["timeout"] == client.timeout

    asyncio.run(run())


def test_read_block_rejects_non_object() -> None:
    """A JSON array is not a register response."""

    async def run() -> None:
        client, _ = make_client(FakeResponse(payload=[1, 2, 3]))
        with pytest.raises(Ppe4ProtocolError):
            await client.async_read_block(1388, 8)

    asyncio.run(run())


def test_read_block_rejects_empty_payload() -> None:
    """A response without registers is an error."""

    async def run() -> None:
        client, _ = make_client(FakeResponse(payload={"nope": "nope"}))
        with pytest.raises(Ppe4ProtocolError):
            await client.async_read_block(1388, 8)

    asyncio.run(run())


def test_read_block_rejects_http_error() -> None:
    """Non-200 answers carry the status code."""

    async def run() -> None:
        client, _ = make_client(FakeResponse(status=500, text="boom"))
        with pytest.raises(Ppe4ProtocolError, match="HTTP 500"):
            await client.async_read_block(1000, 2)

    asyncio.run(run())


def test_read_block_rejects_bad_json() -> None:
    """Invalid JSON is a protocol error."""

    async def run() -> None:
        client, _ = make_client(FakeResponse(payload=ValueError("bad json")))
        with pytest.raises(Ppe4ProtocolError):
            await client.async_read_block(1000, 2)

    asyncio.run(run())


def test_read_blocks_merges() -> None:
    """Several blocks are merged into one register map."""

    async def run() -> None:
        client, session = make_client(
            FakeResponse(payload={"1014": 1}), FakeResponse(payload={"1388": 2})
        )
        registers = await client.async_read_blocks([(1014, 8), (1388, 8)])
        assert registers == {1014: 1, 1388: 2}
        assert len(session.calls) == 2

    asyncio.run(run())


def test_write_registers_sends_string_keys() -> None:
    """Writes use the JSON object the vendor app sends."""

    async def run() -> None:
        client, session = make_client(FakeResponse(payload={"ok": True}))
        await client.async_write_registers({1390: 450, 1391: 0})
        method, url, kwargs = session.calls[0]
        assert method == "POST"
        assert url.endswith("/api/write")
        assert kwargs["json"] == {"1390": 450, "1391": 0}

    asyncio.run(run())


def test_write_registers_noop_when_empty() -> None:
    """An empty write does not hit the network."""

    async def run() -> None:
        client, session = make_client()
        await client.async_write_registers({})
        assert session.calls == []

    asyncio.run(run())


def test_connection_error_is_wrapped() -> None:
    """OS errors become connection errors."""

    async def run() -> None:
        client, _ = make_client(OSError("no route to host"))
        with pytest.raises(Ppe4ConnectionError):
            await client.async_read_block(1000, 2)

    asyncio.run(run())


def test_timeout_is_wrapped() -> None:
    """Timeouts become connection errors."""

    async def run() -> None:
        client, _ = make_client(TimeoutError())
        with pytest.raises(Ppe4ConnectionError):
            await client.async_read_block(1000, 2)

    asyncio.run(run())
