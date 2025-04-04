"""Config flow for the Foxglove Bridge integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_DEVICE_ID, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="0.0.0.0"): str,
        vol.Required(CONF_PORT, default=8765): vol.All(
            int, vol.Range(min=1, max=65535)
        ),
        CONF_API_KEY: str,
        CONF_DEVICE_ID: str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    host = data[CONF_HOST]
    port = data[CONF_PORT]

    device_id = data.get(CONF_DEVICE_ID)
    api_key = data.get(CONF_API_KEY)

    if api_key and device_id:
        websession = async_get_clientsession(hass)
        req_json = {"filename": "dummy"}
        auth_headers = {"Authorization": f"Bearer {api_key}"}
        res = await websession.post(
            "https://api.foxglove.dev/v1/data/upload",
            json=req_json,
            headers=auth_headers,
        )
        if res.status != 200:
            _LOGGER.error("Failed to authenticate: %s", res)
            raise InvalidAuth
    elif api_key or device_id:
        raise ApiKeyRequiredError

    # Return info that you want to store in the config entry.
    return {"title": f"{host}:{port}"}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Foxglove Bridge."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ApiKeyRequiredError:
                errors["base"] = "api_key_required"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class ApiKeyRequiredError(HomeAssistantError):
    """Error to indicate credentials were not provided."""
