"""Create independent random relay keys once. Never print credentials."""
import json
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]
private = ROOT / ".private"
private.mkdir(exist_ok=True)
path = private / "cloudflare-secrets.json"
if not path.exists():
    path.write_text(json.dumps({name: secrets.token_urlsafe(48) for name in
        ("SYNC_TOKEN", "READ_TOKEN", "CONTROL_TOKEN")}, indent=2), encoding="utf-8")
print("Private keys prepared; no credentials printed.")
