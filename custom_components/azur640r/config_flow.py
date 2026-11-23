"""Config flow for the Azur 640R integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import AzurAuthError, AzurClient, AzurConnectionError, DEFAULT_PORT_NAME
from .const import CONF_KEY, CONF_PORT_NAME, DOMAIN, LOGGER

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Optional(CONF_PORT_NAME, default=DEFAULT_PORT_NAME): TextSelector(),
        vol.Optional(CONF_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def _async_attempt_connect(host: str, port_name: str, key: str | None) -> str | None:
    """Try connecting and immediately disconnecting again. Returns an error
    translation key, or None on success. Never logs/returns the raw
    exception text -- it could embed the encryption key."""
    client = AzurClient(host, port_name=port_name, key=key)
    try:
        await client.connect()
    except AzurAuthError:
        return "invalid_auth"
    except (ValueError, ConnectionError, OSError, TimeoutError, AzurConnectionError):
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected error probing Azur 640R at %s", host)
        return "unknown"
    else:
        await client.disconnect()
        return None


class Azur640RConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Azur 640R integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

            error = await _async_attempt_connect(
                user_input[CONF_HOST],
                user_input[CONF_PORT_NAME],
                user_input.get(CONF_KEY),
            )
            if not error:
                return self.async_create_entry(
                    title="Cambridge Audio Azur 640R",
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT_NAME: user_input[CONF_PORT_NAME],
                        CONF_KEY: user_input.get(CONF_KEY),
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input or {}),
            errors=errors,
        )
