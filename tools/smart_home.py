import requests
import config


def _hass_request(method, endpoint, data=None):
    """Make a request to the Home Assistant API."""
    if not config.HASS_URL or not config.HASS_TOKEN:
        raise ValueError("Home Assistant not configured. Set HASS_URL and HASS_TOKEN.")

    url = f"{config.HASS_URL.rstrip('/')}/api/{endpoint}"
    headers = {
        "Authorization": f"Bearer {config.HASS_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.request(method, url, headers=headers, json=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


def control_device(entity_id, action, value=None):
    """Control a smart home device."""
    domain = entity_id.split(".")[0]

    service_map = {
        "turn_on": "turn_on",
        "turn_off": "turn_off",
        "toggle": "toggle",
    }

    data = {"entity_id": entity_id}

    if action == "set_brightness" and domain == "light":
        service = "turn_on"
        data["brightness"] = int(value) if value else 255
    elif action == "set_temperature" and domain == "climate":
        service = "set_temperature"
        data["temperature"] = float(value) if value else 72
    elif action in service_map:
        service = service_map[action]
    else:
        return f"Unsupported action '{action}' for {domain}."

    try:
        _hass_request("POST", f"services/{domain}/{service}", data)
        return f"Done: {action} on {entity_id}" + (f" (value: {value})" if value else "")
    except requests.exceptions.ConnectionError:
        return f"Could not connect to Home Assistant at {config.HASS_URL}."
    except Exception as e:
        return f"Error controlling {entity_id}: {e}"


def list_devices(domain=""):
    """List available smart home devices."""
    try:
        states = _hass_request("GET", "states")
    except requests.exceptions.ConnectionError:
        return f"Could not connect to Home Assistant at {config.HASS_URL}."
    except Exception as e:
        return f"Error listing devices: {e}"

    if domain:
        states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]

    if not states:
        return f"No devices found" + (f" for domain '{domain}'" if domain else "") + "."

    results = []
    for s in sorted(states, key=lambda x: x["entity_id"]):
        eid = s["entity_id"]
        state = s["state"]
        name = s.get("attributes", {}).get("friendly_name", eid)
        results.append(f"{name} ({eid}): {state}")

    return "\n".join(results)
