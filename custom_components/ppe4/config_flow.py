"""Config flow for the KOSPEL PPE4 integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Ppe4Client, Ppe4Error
from .const import (
    DEFAULT_ERROR_REGISTERS,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ERROR_ENCODING_CODE,
    ERROR_ENCODINGS,
    LIVE_BLOCKS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGISTER_SPECS,
)
from .registers import (
    OPTION_ERROR_ENCODING,
    OPTION_ERROR_REGISTERS,
    OPTION_REGISTERS,
    OPTION_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)

_REGISTER_KEYS = {spec.key for spec in REGISTER_SPECS}


def _parse_error_registers(raw: str) -> list[int]:
    """Parse a comma separated list of error registers."""
    registers: list[int] = []
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            register = int(item)
        except ValueError:
            return []
        if register <= 0:
            return []
        registers.append(register)
    return registers


class Ppe4ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for KOSPEL PPE4."""

    VERSION = 1

    async def _async_validate(self, host: str, port: int) -> None:
        """Validate that the module answers with a register block."""
        client = Ppe4Client(
            async_get_clientsession(self.hass), host=host, port=port
        )
        for start, count in LIVE_BLOCKS:
            try:
                registers = await client.async_read_block(start, count)
            except Ppe4Error:
                continue
            if any(start <= register < start + count for register in registers):
                return
        raise Ppe4Error("No register data returned by the module")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the module address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            try:
                await self._async_validate(host, port)
            except Ppe4Error as err:
                _LOGGER.debug("Connection test failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, {CONF_HOST: "192.168.8.1", CONF_PORT: DEFAULT_PORT}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the module address."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            try:
                await self._async_validate(host, port)
            except Ppe4Error as err:
                _LOGGER.debug("Connection test failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data={CONF_HOST: host, CONF_PORT: port}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA,
                {
                    CONF_HOST: entry.data.get(CONF_HOST, ""),
                    CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
                },
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Return the options flow."""
        return Ppe4OptionsFlow()


def _parse_overrides(raw: str) -> dict[str, Any]:
    """Parse and validate the register override JSON."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ValueError("invalid_json") from err
    if not isinstance(parsed, dict):
        raise ValueError("invalid_json")
    result: dict[str, Any] = {}
    for key, value in parsed.items():
        if key not in _REGISTER_KEYS:
            raise ValueError("unknown_register_key")
        if isinstance(value, bool):
            raise ValueError("invalid_json")
        if isinstance(value, int):
            result[key] = value
            continue
        if (
            isinstance(value, (list, tuple))
            and 1 <= len(value) <= 2
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        ):
            result[key] = list(value)
            continue
        raise ValueError("invalid_json")
    return result


class Ppe4OptionsFlow(OptionsFlow):
    """Options for polling, error decoding and register overrides."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        options = dict(self.config_entry.options)
        existing_overrides = json.dumps(
            options.get(OPTION_REGISTERS, {}), indent=2
        )
        default_error_registers = options.get(
            OPTION_ERROR_REGISTERS,
            ",".join(str(register) for register in DEFAULT_ERROR_REGISTERS),
        )

        if user_input is not None:
            try:
                overrides = _parse_overrides(user_input.get(OPTION_REGISTERS, ""))
            except ValueError:
                errors["base"] = "invalid_registers"
            else:
                error_registers = str(user_input.get(OPTION_ERROR_REGISTERS, ""))
                if not _parse_error_registers(error_registers):
                    errors["base"] = "error_registers_required"
                else:
                    return self.async_create_entry(
                        title="",
                        data={
                            OPTION_SCAN_INTERVAL: int(
                                user_input[OPTION_SCAN_INTERVAL]
                            ),
                            OPTION_ERROR_ENCODING: user_input[OPTION_ERROR_ENCODING],
                            OPTION_ERROR_REGISTERS: error_registers,
                            OPTION_REGISTERS: overrides,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(
                    OPTION_SCAN_INTERVAL,
                    default=options.get(OPTION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Required(
                    OPTION_ERROR_ENCODING,
                    default=options.get(OPTION_ERROR_ENCODING, ERROR_ENCODING_CODE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(ERROR_ENCODINGS),
                        translation_key="error_encoding",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    OPTION_ERROR_REGISTERS, default=default_error_registers
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT
                    )
                ),
                vol.Optional(
                    OPTION_REGISTERS, default=existing_overrides
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        multiline=True, type=selector.TextSelectorType.TEXT
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
