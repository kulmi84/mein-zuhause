"""Publish selected states; collect short-lived commands over outbound HTTPS."""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import time
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN
from .model import allowed_actions, make_snapshot

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    relay = Relay(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = relay
    await relay.tick()
    entry.async_on_unload(async_track_time_interval(hass, relay.tick, timedelta(seconds=5)))
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    relay = hass.data[DOMAIN].pop(entry.entry_id)
    relay.stopped = True
    async with relay.lock:
        pass
    return True


class Relay:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.lock = asyncio.Lock()
        self.last_snapshot = None
        self.last_sent = 0
        self.stopped = False
        self.failed = False

    async def post(self, path, data):
        async with async_get_clientsession(self.hass).post(
            self.entry.data["url"] + path, json=data,
            headers={"Authorization": "Bearer " + self.entry.data["sync_token"]},
            timeout=aiohttp.ClientTimeout(total=8), allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise ValueError("relay response")
            return await response.json()

    async def tick(self, _now=None):
        if self.stopped or self.lock.locked():
            return
        async with self.lock:
            if self.stopped:
                return
            try:
                selected = self.entry.options.get("entities", [])
                controlled = self.entry.options.get("control_entities", [])
                snapshot = make_snapshot(self.hass.states, selected, controlled,
                    self.entry.options.get("alexa_names", {}))
                data = {}
                if snapshot != self.last_snapshot or time.monotonic() - self.last_sent >= 60:
                    data["entities"] = snapshot
                response = await self.post("/sync", data)
                if "entities" in data:
                    self.last_snapshot = snapshot
                    self.last_sent = time.monotonic()
                for command in response.get("commands", []):
                    if not self.stopped:
                        await self.execute(command)
                if self.failed:
                    _LOGGER.info("Mein Zuhause: Relay wieder erreichbar")
                self.failed = False
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
                if not self.failed:
                    _LOGGER.warning("Mein Zuhause: Relay nicht erreichbar oder Konfiguration ungültig")
                self.failed = True

    async def execute(self, command):
        status = "failed"
        try:
            entity_id = command["entity_id"]
            action = command["action"]
            selected = self.entry.options.get("entities", [])
            controlled = self.entry.options.get("control_entities", [])
            expires = datetime.fromisoformat(command["expires_at"].replace("Z", "+00:00"))
            if (entity_id not in selected or entity_id not in controlled
                    or action not in allowed_actions(entity_id, True)
                    or expires <= datetime.now(timezone.utc)):
                raise ValueError("Command not allowed or expired")
            state = self.hass.states.get(entity_id)
            if not state or state.state in ("unknown", "unavailable"):
                raise ValueError("Unavailable entity")
            await self.hass.services.async_call(
                entity_id.split(".")[0], action, {"entity_id": entity_id}, blocking=True)
            status = "done"
        except Exception:  # An action failure must be acknowledged, never retried.
            _LOGGER.warning("Mein Zuhause: Ein Steuerbefehl konnte nicht ausgeführt werden")
        await self.post("/ack", {"id": command["id"], "status": status})
