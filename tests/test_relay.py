"""Exercise the actual command executor with a fake HA service boundary."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]


def load_relay():
    modules = {name: ModuleType(name) for name in (
        "aiohttp", "homeassistant", "homeassistant.helpers",
        "homeassistant.helpers.aiohttp_client", "homeassistant.helpers.event")}
    modules["aiohttp"].ClientError = type("ClientError", (Exception,), {})
    modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda hass: None
    modules["homeassistant.helpers.event"].async_track_time_interval = lambda *args: None
    spec = importlib.util.spec_from_file_location("relay_under_test",
        ROOT / "custom_components/mein_zuhause/__init__.py",
        submodule_search_locations=[str(ROOT / "custom_components/mein_zuhause")])
    module = importlib.util.module_from_spec(spec)
    modules["relay_under_test"] = module
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


relay_module = load_relay()


class RelayTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = AsyncMock()
        self.hass = SimpleNamespace(states={"cover.garagentor": SimpleNamespace(state="open")},
            services=SimpleNamespace(async_call=self.service))
        self.entry = SimpleNamespace(options={"entities":["cover.garagentor"], "control_entities":["cover.garagentor"]})
        self.relay = relay_module.Relay(self.hass, self.entry)
        self.relay.post = AsyncMock(return_value={})
        self.command = {"id":"one", "entity_id":"cover.garagentor", "action":"close_cover",
            "expires_at":(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat()}

    async def test_selected_action_calls_only_target_service(self):
        await self.relay.execute(self.command)
        self.service.assert_awaited_once_with("cover", "close_cover", {"entity_id":"cover.garagentor"}, blocking=True)
        self.relay.post.assert_awaited_once_with("/ack", {"id":"one", "status":"done"})

    async def test_locally_revoked_permission_blocks_already_queued_command(self):
        self.entry.options["control_entities"] = []
        await self.relay.execute(self.command)
        self.service.assert_not_awaited()
        self.relay.post.assert_awaited_once_with("/ack", {"id":"one", "status":"failed"})

    async def test_expired_command_not_executed(self):
        self.command["expires_at"] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        await self.relay.execute(self.command)
        self.service.assert_not_awaited()

    async def test_arbitrary_action_rejected(self):
        self.command["action"] = "toggle"
        await self.relay.execute(self.command)
        self.service.assert_not_awaited()

    async def test_service_failure_acknowledged_without_retry(self):
        self.service.side_effect = RuntimeError("service unavailable")
        await self.relay.execute(self.command)
        self.service.assert_awaited_once()
        self.relay.post.assert_awaited_once_with("/ack", {"id":"one", "status":"failed"})
