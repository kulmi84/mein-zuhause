"""Export our independent logo in Alexa/HA sizes; generate localization/model."""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
source = ASSETS / "mein-zuhause-master.png"
if source.exists():
    # Size exports only. The independent generated master stays unchanged.
    image = Image.open(source).convert("RGBA")
    canvas = Image.new("RGBA", image.size, "black")
    canvas.alpha_composite(image)
    for size in (108, 512):
        canvas.convert("RGB").resize((size, size), Image.Resampling.LANCZOS).save(ASSETS / ("mein-zuhause-%s.png" % size))
    brand = ROOT / "custom_components" / "mein_zuhause" / "brand"
    brand.mkdir(exist_ok=True)
    canvas.convert("RGB").resize((256, 256), Image.Resampling.LANCZOS).save(brand / "icon.png")
    canvas.convert("RGB").resize((512, 512), Image.Resampling.LANCZOS).save(brand / "icon@2x.png")

fields = {"entities": "Entitäten für Abfragen", "control_entities": "Zusätzlich zur Steuerung freigeben"}
description = ("Nur ausgewählte Entitäten werden übertragen (maximal 100). Für Steuerung muss eine Entität in beiden Listen stehen. "
    "Die Steuerfreigabe erlaubt bei Toren auch das Öffnen. Für reine Statusfragen die zweite Liste leer lassen. "
    "Alexa verwendet die vollständigen Anzeigenamen aus Home Assistant.")
errors = {"cannot_connect": "Der Cloudflare-Worker ist nicht erreichbar.",
    "invalid_connection": "HTTPS-Adresse oder Sync-Schlüssel ungültig.",
    "too_many": "Bitte höchstens 100 Entitäten auswählen.",
    "control_not_selected": "Steuerbare Entitäten müssen auch für Abfragen ausgewählt sein."}
strings = {"title": "Mein Zuhause – Alexa", "config": {"step": {
    "user": {"title": "Mein Zuhause verbinden", "description": "Adresse des eigenen Cloudflare-Workers und dessen Sync-Schlüssel eingeben. Es wird kein Home-Assistant-Zugriffstoken benötigt.",
        "data": {"url": "Cloudflare-Worker-Adresse (https://…)", "sync_token": "Sync-Schlüssel"}},
    "entities": {"title": "Entitäten freigeben", "description": description, "data": fields}},
    "error": errors, "abort": {"single_instance_allowed": "Mein Zuhause ist bereits eingerichtet."}},
    "options": {"step": {"init": {"title": "Entitätsauswahl", "description": description, "data": fields}}, "error": errors}}
component = ROOT / "custom_components" / "mein_zuhause"
(component / "translations").mkdir(exist_ok=True)
for path in (component / "strings.json", component / "translations" / "de.json"):
    path.write_text(json.dumps(strings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

samples = {
    "StatusIntent": ["wie ist der Status von {entity}", "nach dem Status von {entity}", "ob {entity} noch offen ist",
        "ob das {entity} noch offen ist", "ob die {entity} offen ist", "ist {entity} offen", "ist das {entity} noch offen",
        "ist die {entity} eingeschaltet", "wie warm ist {entity}", "nach {entity}"],
    "OpenEntitiesIntent": ["was ist noch offen", "welche Fenster sind offen", "welche Türen sind offen"],
    "TurnOnIntent": ["schalte {entity} ein", "schalte das {entity} ein", "schalte die {entity} ein"],
    "TurnOffIntent": ["schalte {entity} aus", "schalte das {entity} aus", "schalte die {entity} aus"],
    "OpenIntent": ["öffne {entity}", "öffne das {entity}", "öffne die {entity}"],
    "CloseIntent": ["schließe {entity}", "schließe das {entity}", "schließe die {entity}"],
}
intents = [{"name": name, "samples": phrases, "slots": [{"name": "entity", "type": "HOME_ENTITY"}] if any("{entity}" in p for p in phrases) else []} for name, phrases in samples.items()]
intents += [{"name": "AMAZON." + name + "Intent", "samples": []} for name in ("Help", "Stop", "Cancel", "Fallback")]
model = {"interactionModel": {"languageModel": {"invocationName": "mein zuhause", "intents": intents,
    "types": [{"name": "HOME_ENTITY", "values": [{"name": {"value": name}} for name in
        ("Garagentor", "Außenlicht", "Terrassentür", "Wohnzimmerfenster", "Wohnzimmer Temperatur")]}]}}}
model["interactionModel"]["languageModel"]["types"][0]["values"][0]["name"]["synonyms"] = ["garagen tor"]
(ROOT / "alexa" / "interaction-model.de-DE.json").write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Icons, German setup UI and Alexa model prepared.")
