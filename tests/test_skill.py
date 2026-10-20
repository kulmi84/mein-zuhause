import importlib.util
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


skill = load("skill", "alexa/lambda_function.py")
model = load("model", "custom_components/mein_zuhause/model.py")


class SkillTest(unittest.TestCase):
    def setUp(self):
        self.entity = {"entity_id": "cover.garagentor", "name": "Garagentor", "state": "open", "device_class": "garage", "unit": "", "actions": []}
        self.data = {"received_at": datetime.now(timezone.utc).isoformat(), "stale": False, "entities": [self.entity]}
        self.config = {"skill_id": "test"}

    def ask(self, name, data=None, spoken="Garagentor"):
        event = {"context": {"System": {"application": {"applicationId": "test"}}}, "request": {
            "type": "IntentRequest", "requestId": "test-request", "intent": {"name": name,
            "slots": {"entity": {"value": spoken}}}}}
        with patch.object(skill, "load_config", return_value=self.config), patch.object(skill, "api", return_value=data or self.data) as api:
            result = skill.lambda_handler(event, None)
        return result["response"]["outputSpeech"]["text"], api

    def test_garage_open_and_closed(self):
        self.assertIn("offen", self.ask("StatusIntent")[0])
        self.entity["state"] = "closed"
        self.assertIn("geschlossen", self.ask("StatusIntent")[0])

    def test_contact_and_unknown(self):
        self.entity.update(entity_id="binary_sensor.garagentor", device_class="garage_door", state="on")
        self.assertIn("offen", self.ask("StatusIntent")[0])
        self.entity["state"] = "unavailable"
        self.assertIn("nicht verfügbar", self.ask("StatusIntent")[0])

    def test_alexa_split_german_compound(self):
        self.assertIn("offen", self.ask("StatusIntent", spoken="Garagen Tor")[0])

    def test_spacing_collision_does_not_choose_a_device(self):
        self.data["entities"].append(dict(self.entity, entity_id="cover.other", name="Garagen Tor"))
        self.assertIn("nicht eindeutig", self.ask("StatusIntent")[0])

    def test_stale_never_reports_current(self):
        self.data["received_at"] = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
        self.assertIn("nicht aktuell", self.ask("StatusIntent")[0])

    def test_read_permission_does_not_control(self):
        text, api = self.ask("OpenIntent")
        self.assertIn("nicht freigegeben", text)
        self.assertEqual(api.call_count, 1)

    def test_control_accepted_not_claimed_success(self):
        self.entity["actions"] = ["close_cover"]
        text, api = self.ask("CloseIntent")
        self.assertIn("übermittelt", text)
        self.assertNotIn("geschlossen", text)
        self.assertEqual(api.call_count, 2)

    def test_ambiguous_names_do_not_choose_a_device(self):
        self.data["entities"].append(dict(self.entity, entity_id="cover.andere_garage"))
        self.assertIn("nicht eindeutig", self.ask("StatusIntent")[0])

    def test_no_openings_not_all_closed(self):
        self.data["entities"] = []
        self.assertIn("noch keine", self.ask("OpenEntitiesIntent")[0])

    def test_wrong_skill_id(self):
        self.config["skill_id"] = "other"
        text, api = self.ask("StatusIntent")
        self.assertIn("Skill-ID", text)
        api.assert_not_called()

    def test_snapshot_excludes_unselected_and_private_attributes(self):
        states = {"cover.garagentor": SimpleNamespace(state="open", attributes={"friendly_name":"Garagentor", "access_token":"secret"}),
            "sensor.private": SimpleNamespace(state="secret", attributes={})}
        snapshot = model.make_snapshot(states, ["cover.garagentor"], [])
        self.assertEqual(len(snapshot), 1)
        self.assertNotIn("secret", str(snapshot))
        self.assertEqual(snapshot[0]["actions"], [])

    def test_lock_never_controllable(self):
        self.assertEqual(model.allowed_actions("lock.front_door", True), [])

    def test_alexa_override_changes_speech_and_target_keeps_identity(self):
        states = {"cover.garagentor": SimpleNamespace(state="open", attributes={"friendly_name": "HA Garage"})}
        names = model.clean_alexa_names(states, ["cover.garagentor"], {"cover.garagentor": "  Einfahrt  "})
        self.data["entities"] = model.make_snapshot(states, ["cover.garagentor"], ["cover.garagentor"], names)
        text, api = self.ask("CloseIntent", spoken="Einfahrt")
        self.assertIn("Einfahrt", text)
        self.assertEqual(api.call_args.args[3]["entity_id"], "cover.garagentor")
        self.assertEqual(states["cover.garagentor"].attributes["friendly_name"], "HA Garage")

    def test_blank_alias_falls_back_and_removed_entity_alias_is_discarded(self):
        states = {"sensor.a": SimpleNamespace(state="1", attributes={"friendly_name": "Temperatur"})}
        names = model.clean_alexa_names(states, ["sensor.a"], {"sensor.a": " ", "sensor.removed": "Alt"})
        self.assertEqual(names, {})
        self.assertEqual(model.make_snapshot(states, ["sensor.a"], [], names)[0]["name"], "Temperatur")

    def test_spoken_alias_collisions_and_invalid_values_rejected(self):
        states = {"cover.a": SimpleNamespace(attributes={"friendly_name": "Garagentor"})}
        for names in ({"cover.b": "Garagen Tor"}, {"cover.b": "!"}, {"cover.b": "x" * 121}, {"cover.b": 3}):
            with self.assertRaises(ValueError):
                model.clean_alexa_names(states, ["cover.a", "cover.b"], names)

    def test_url_validation(self):
        for url in ("http://host", "https://user:password@host", "https://host/path", "https://host?token=secret"):
            with self.assertRaises(ValueError):
                model.validate_url(url)


if __name__ == "__main__":
    unittest.main()
