"""Alexa-hosted Python backend for the private Mein Zuhause skill."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def load_config():
    return json.loads(Path(__file__).with_name("relay_config.json").read_text(encoding="utf-8"))


def api(config, path, token_key, data=None):
    url = config["url"].rstrip("/")
    if not url.startswith("https://"):
        raise ValueError("HTTPS required")
    request = Request(url + path,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={"Authorization": "Bearer " + config[token_key], "Content-Type": "application/json",
            "User-Agent": "Mein-Zuhause-Alexa/0.1", "Accept": "application/json"})
    with urlopen(request, timeout=3) as response:
        raw = response.read(131073)
    if len(raw) > 131072:
        raise ValueError("Response too large")
    return json.loads(raw)


def normalize(value):
    value = value.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return " ".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", value)))


def find_entity(entities, spoken):
    name = normalize(spoken)
    matches = [e for e in entities if name in (normalize(e["name"]), normalize(e["entity_id"]),
        normalize(e["entity_id"].split(".")[-1]))]
    return matches[0] if len(matches) == 1 else None


def describe(entity):
    state = entity["state"]
    if state in ("unavailable", "unknown"):
        return entity["name"] + ": Der Zustand ist gerade nicht verfügbar."
    domain = entity["entity_id"].split(".")[0]
    device_class = entity.get("device_class", "")
    if domain == "binary_sensor" and state in ("on", "off"):
        if device_class in ("door", "window", "garage_door", "opening", "gate"):
            state = "offen" if state == "on" else "geschlossen"
        elif device_class in ("motion", "occupancy", "presence"):
            state = "erkannt" if state == "on" else "nicht erkannt"
        else:
            state = "aktiv" if state == "on" else "inaktiv"
    else:
        state = {"on": "eingeschaltet", "off": "ausgeschaltet", "open": "offen",
            "closed": "geschlossen", "opening": "öffnet sich", "closing": "schließt sich",
            "locked": "verriegelt", "unlocked": "entriegelt", "jammed": "blockiert"}.get(state, state)
    unit = {"°C": "Grad Celsius", "%": "Prozent", "W": "Watt", "kW": "Kilowatt",
        "kWh": "Kilowattstunden"}.get(entity.get("unit", ""), entity.get("unit", ""))
    if re.fullmatch(r"-?\d+(\.\d+)?", state):
        state = state.replace(".", ",")
    return entity["name"] + ": " + state + (" " + unit if unit else "") + "."


def say(text, end=True):
    return {"version": "1.0", "response": {"outputSpeech": {"type": "PlainText", "text": text},
        "shouldEndSession": end}}


def lambda_handler(event, context):
    request = event.get("request", {})
    if request.get("type") == "SessionEndedRequest":
        return {"version": "1.0", "response": {}}
    try:
        config = load_config()
        skill_id = event.get("context", {}).get("System", {}).get("application", {}).get("applicationId")
        if not config.get("skill_id") or config["skill_id"] != skill_id:
            return say("Bitte prüfe die Skill-ID in der Konfiguration.")
        intent = request.get("intent", {})
        name = intent.get("name", "")
        if name in ("AMAZON.StopIntent", "AMAZON.CancelIntent"):
            return say("Bis bald.")
        if request.get("type") == "LaunchRequest" or name == "AMAZON.HelpIntent":
            return say("Willkommen bei Mein Zuhause. Frage zum Beispiel: Ist das Garagentor noch offen? "
                "Oder sage: Schalte das Außenlicht ein.", False)
        if name not in ("StatusIntent", "OpenEntitiesIntent", "TurnOnIntent", "TurnOffIntent", "OpenIntent", "CloseIntent"):
            return say("Bitte nenne den Namen einer freigegebenen Entität, zum Beispiel Garagentor.", False)
        data = api(config, "/states", "read_token")
        # Check receipt time independently of any stale flag from the relay.
        received = datetime.fromisoformat(data["received_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - received).total_seconds()
        if data.get("stale") or age > 180 or age < -60:
            return say("Die Verbindung zu Home Assistant ist gerade nicht aktuell. Bitte versuche es später erneut.")
        entities = data["entities"]
        if name == "OpenEntitiesIntent":
            openings = [e for e in entities if e["entity_id"].startswith("cover.") or
                e.get("device_class") in ("door", "window", "garage_door", "opening", "gate")]
            if not openings:
                return say("Es sind noch keine Türen, Fenster oder Tore zur Abfrage freigegeben.")
            open_entities = [e["name"] for e in openings if e["state"] in ("on", "open", "opening", "closing")]
            unknown = [e["name"] for e in openings if e["state"] not in ("on", "off", "open", "closed", "opening", "closing")]
            text = "Offen oder in Bewegung: " + ", ".join(open_entities) + "." if open_entities else "Alle abfragbaren Türen, Fenster und Tore sind geschlossen."
            if unknown:
                text += " Unbekannter Zustand: " + ", ".join(unknown) + "."
            return say(text)
        spoken = intent.get("slots", {}).get("entity", {}).get("value", "")
        entity = find_entity(entities, spoken)
        if entity is None:
            return say("Der Name ist nicht eindeutig oder nicht freigegeben. Bitte verwende den vollständigen Namen aus Home Assistant.", False)
        if name == "StatusIntent":
            return say(describe(entity))
        actions = {"TurnOnIntent": "turn_on", "TurnOffIntent": "turn_off", "OpenIntent": "open_cover", "CloseIntent": "close_cover"}
        action = actions[name]
        if action not in entity.get("actions", []):
            return say(entity["name"] + " ist für diesen Steuerbefehl nicht freigegeben.")
        if entity["state"] in ("unknown", "unavailable"):
            return say(entity["name"] + " ist gerade nicht verfügbar.")
        request_id = request.get("requestId")
        if not request_id:
            raise ValueError("Missing request ID")
        command_id = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        api(config, "/commands", "control_token", {"id": command_id, "entity_id": entity["entity_id"], "action": action})
        return say("Der Befehl für " + entity["name"] + " wurde übermittelt.")
    except HTTPError as error:
        if error.code == 404:
            return say("Es wurden noch keine Zustände übertragen. Bitte richte Mein Zuhause in Home Assistant ein.")
        return say("Die Verbindung zu Mein Zuhause ist gerade nicht verfügbar.")
    except Exception:
        return say("Die Verbindung zu Mein Zuhause ist gerade nicht verfügbar.")
