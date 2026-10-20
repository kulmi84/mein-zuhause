"""Pure policy shared by snapshot publishing and command execution."""
from urllib.parse import urlsplit
import re
import unicodedata


def speech_key(value):
    value = value.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return "".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", value)))


def clean_alexa_names(states, selected, names):
    """Store only explicit overrides, rejecting ambiguous spoken names."""
    if not isinstance(names, dict):
        raise ValueError("invalid_names")
    result, seen = {}, set()
    for entity_id in selected:
        value = names.get(entity_id, "")
        if not isinstance(value, str) or len(value.strip()) > 120:
            raise ValueError("invalid_names")
        value = value.strip()
        state = states.get(entity_id)
        fallback = str(state.attributes.get("friendly_name", entity_id)) if state else entity_id
        key = speech_key(value or fallback)
        if not key:
            raise ValueError("invalid_names")
        if key in seen:
            raise ValueError("duplicate_names")
        seen.add(key)
        if value:
            result[entity_id] = value
    return result


def validate_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("Use an HTTPS origin, without a path or credentials")
    return value.rstrip("/")


def allowed_actions(entity_id, enabled):
    if not enabled:
        return []
    domain = entity_id.split(".")[0]
    if domain in ("light", "switch", "fan", "input_boolean"):
        return ["turn_on", "turn_off"]
    if domain == "cover":
        return ["open_cover", "close_cover"]
    return []


def make_snapshot(states, selected, controlled, alexa_names=None):
    result = []
    for entity_id in selected:
        state = states.get(entity_id)
        attrs = state.attributes if state else {}
        result.append({
            "entity_id": entity_id,
            "name": str((alexa_names or {}).get(entity_id) or attrs.get("friendly_name", entity_id))[:120],
            "state": str(state.state if state else "unavailable")[:255],
            "device_class": str(attrs.get("device_class", ""))[:60],
            "unit": str(attrs.get("unit_of_measurement", ""))[:30],
            "actions": allowed_actions(entity_id, entity_id in controlled),
        })
    return result
