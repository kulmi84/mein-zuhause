"""Read-only production smoke check. Does not send HA states or commands."""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
keys = json.loads((ROOT / ".private" / "cloudflare-secrets.json").read_text())
URL = json.loads((ROOT / ".private" / "home-assistant-setup.json").read_text())["url"]
checks = [("/health", keys["SYNC_TOKEN"], 200), ("/states", keys["READ_TOKEN"], 404),
    ("/states", keys["SYNC_TOKEN"], 401), ("/states", "incorrect", 401)]
for path, token, expected in checks:
    try:
        with urlopen(Request(URL + path, headers={"Authorization": "Bearer " + token,
                "User-Agent": "Mein-Zuhause-Healthcheck/0.1", "Accept": "application/json"}), timeout=10) as response:
            status, data = response.status, json.load(response)
    except HTTPError as error:
        status = error.code
        body = error.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except ValueError:
            print(path, status, error.headers.get("Content-Type"), body[:200])
            raise SystemExit("Endpoint did not return relay JSON")
    # Once connected to HA, the states endpoint legitimately returns 200.
    assert status == expected or (path == "/states" and expected == 404 and status == 200), (path, status)
    print(path, status, data if path == "/health" or status != 200 else "snapshot present")
