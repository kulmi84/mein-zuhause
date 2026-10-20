"""Pure policy shared by snapshot publishing and command execution."""
from urllib.parse import urlsplit


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


def make_snapshot(states, selected, controlled):
    result = []
    for entity_id in selected:
        state = states.get(entity_id)
        attrs = state.attributes if state else {}
        result.append({
            "entity_id": entity_id,
            "name": str(attrs.get("friendly_name", entity_id))[:120],
            "state": str(state.state if state else "unavailable")[:255],
            "device_class": str(attrs.get("device_class", ""))[:60],
            "unit": str(attrs.get("unit_of_measurement", ""))[:30],
            "actions": allowed_actions(entity_id, entity_id in controlled),
        })
    return result
