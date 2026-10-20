"""Build the installable HA zip and Alexa upload files without private keys."""
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist"
OUT.mkdir(exist_ok=True)
component = ROOT / "custom_components" / "mein_zuhause"
with ZipFile(OUT / "mein-zuhause-ha.zip", "w", ZIP_DEFLATED) as archive:
    for path in sorted(component.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            archive.write(path, path.relative_to(ROOT))
for path in (ROOT / "alexa").glob("*"):
    if path.is_file():
        shutil.copy2(path, OUT / path.name)
with ZipFile(OUT / "mein-zuhause-alexa.zip", "w", ZIP_DEFLATED) as archive:
    archive.write(ROOT / "alexa" / "lambda_function.py", "lambda/lambda_function.py")
    archive.write(ROOT / "alexa" / "relay_config.example.json", "lambda/relay_config.json")
    archive.writestr("lambda/requirements.txt", "")
print("Built dist/mein-zuhause-ha.zip and Alexa files (without credentials).")
