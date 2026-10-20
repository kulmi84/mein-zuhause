"""Create local setup files after deployment; never include them in a release."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
url = sys.argv[1].rstrip("/")
keys = json.loads((ROOT / ".private" / "cloudflare-secrets.json").read_text())
path = ROOT / ".private" / "home-assistant-setup.json"
path.write_text(json.dumps({"url": url, "sync_token": keys["SYNC_TOKEN"]}, indent=2), encoding="utf-8")
alexa = ROOT / ".private" / "alexa-relay_config.json"
old = json.loads(alexa.read_text(encoding="utf-8")) if alexa.exists() else {}
alexa.write_text(json.dumps({"url": url, "read_token": keys["READ_TOKEN"],
    "control_token": keys["CONTROL_TOKEN"], "skill_id": old.get("skill_id", "REPLACE_WITH_ALEXA_SKILL_ID")}, indent=2), encoding="utf-8")
print("Private HA and Alexa configuration files prepared.")
