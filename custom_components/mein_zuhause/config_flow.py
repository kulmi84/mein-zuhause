"""UI setup and independently selectable read/control permissions."""
import asyncio
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from .const import DOMAIN, READ_DOMAINS, CONTROL_DOMAINS, MAX_ENTITIES
from .model import validate_url


def selection_schema(values):
    return vol.Schema({
        vol.Required("entities", default=values.get("entities", [])):
            selector.EntitySelector(selector.EntitySelectorConfig(domain=READ_DOMAINS, multiple=True)),
        vol.Required("control_entities", default=values.get("control_entities", [])):
            selector.EntitySelector(selector.EntitySelectorConfig(domain=CONTROL_DOMAINS, multiple=True)),
    })


def selection_error(data):
    if len(data["entities"]) > MAX_ENTITIES:
        return "too_many"
    if not set(data["control_entities"]).issubset(data["entities"]):
        return "control_not_selected"
    return None


class MeinZuhauseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            try:
                user_input["url"] = validate_url(user_input["url"])
                if len(user_input["sync_token"]) < 32:
                    raise ValueError("short token")
                async with async_get_clientsession(self.hass).get(
                    user_input["url"] + "/health",
                    headers={"Authorization": "Bearer " + user_input["sync_token"]},
                    timeout=aiohttp.ClientTimeout(total=10), allow_redirects=False,
                ) as response:
                    if response.status != 200 or (await response.json()).get("service") != DOMAIN:
                        raise ValueError("wrong endpoint or credentials")
                self._connection = user_input
                return await self.async_step_entities()
            except ValueError:
                errors["base"] = "invalid_connection"
            except (aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("url"): str,
            vol.Required("sync_token"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        }), errors=errors)

    async def async_step_entities(self, user_input=None):
        errors = {}
        if user_input is not None:
            error = selection_error(user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title="Mein Zuhause", data=self._connection, options=user_input)
        return self.async_show_form(step_id="entities", data_schema=selection_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MeinZuhauseOptionsFlow()


class MeinZuhauseOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            error = selection_error(user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=selection_schema(
            user_input if user_input is not None else self.config_entry.options), errors=errors)
