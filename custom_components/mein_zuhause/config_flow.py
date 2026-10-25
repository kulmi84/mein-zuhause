"""UI setup and independently selectable read/control permissions."""
import asyncio
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from .const import DOMAIN, READ_DOMAINS, CONTROL_DOMAINS, MAX_ENTITIES
from .model import validate_url, clean_alexa_names, merge_entity_selection


def names_schema(hass, selected, names):
    fields = {}
    for entity_id in selected:
        state = hass.states.get(entity_id)
        label = str(state.attributes.get("friendly_name", entity_id)) if state else entity_id
        fields[entity_id] = {"label": f"{label} ({entity_id})", "selector": {"text": {}}}
    return vol.Schema({vol.Optional("alexa_names", default=names): selector.ObjectSelector(
        selector.ObjectSelectorConfig(fields=fields))})


def selection_schema(values):
    return vol.Schema({
        vol.Required("entities", default=values.get("entities", [])):
            selector.EntitySelector(selector.EntitySelectorConfig(domain=READ_DOMAINS, multiple=True)),
        vol.Required("control_entities", default=values.get("control_entities", [])):
            selector.EntitySelector(selector.EntitySelectorConfig(domain=CONTROL_DOMAINS, multiple=True)),
    })


def selection_error(data):
    try:
        merge_entity_selection(data, MAX_ENTITIES)
    except ValueError as error:
        return str(error)
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
                self._selection = merge_entity_selection(user_input, MAX_ENTITIES)
                return await self.async_step_names()
        return self.async_show_form(step_id="entities", data_schema=selection_schema(user_input or {}), errors=errors)

    async def async_step_names(self, user_input=None):
        errors = {}
        names = (user_input or {}).get("alexa_names", {})
        if user_input is not None or not self._selection["entities"]:
            try:
                names = clean_alexa_names(self.hass.states, self._selection["entities"], names)
                return self.async_create_entry(title="Mein Zuhause", data=self._connection,
                    options={**self._selection, "alexa_names": names})
            except ValueError as error:
                errors["base"] = str(error)
        return self.async_show_form(step_id="names", data_schema=names_schema(
            self.hass, self._selection["entities"], names), errors=errors)

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
                self._selection = merge_entity_selection(user_input, MAX_ENTITIES)
                return await self.async_step_names()
        return self.async_show_form(step_id="init", data_schema=selection_schema(
            user_input if user_input is not None else self.config_entry.options), errors=errors)

    async def async_step_names(self, user_input=None):
        errors = {}
        selected = self._selection["entities"]
        names = {key: value for key, value in self.config_entry.options.get("alexa_names", {}).items()
            if key in selected}
        if user_input is not None:
            names = user_input.get("alexa_names", {})
        if user_input is not None or not selected:
            try:
                names = clean_alexa_names(self.hass.states, selected, names)
                return self.async_create_entry(title="", data={**self._selection, "alexa_names": names})
            except ValueError as error:
                errors["base"] = str(error)
        return self.async_show_form(step_id="names", data_schema=names_schema(
            self.hass, selected, names), errors=errors)
