from tools.email_tool import read_emails, search_emails
from tools.documents import search_documents, read_document, list_documents
from tools.reminders import create_reminder, list_reminders, delete_reminder
from tools.smart_home import control_device, list_devices
from tools.system_info import get_system_info
from tools.vision import capture_camera, capture_screenshot, analyze_image

# All tool definitions for Claude's tool_use API
TOOL_DEFINITIONS = [
    {
        "name": "read_emails",
        "description": "Read recent emails from the user's inbox. Returns subject, sender, date, and a preview of each email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Email folder to read from (default: INBOX)",
                    "default": "INBOX"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of recent emails to fetch (default: 5, max: 20)",
                    "default": 5
                }
            },
            "required": []
        }
    },
    {
        "name": "search_emails",
        "description": "Search emails by subject, sender, or keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (searches subject and sender)"
                },
                "folder": {
                    "type": "string",
                    "description": "Email folder to search (default: INBOX)",
                    "default": "INBOX"
                },
                "count": {
                    "type": "integer",
                    "description": "Max results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_documents",
        "description": "List available documents in the user's documents directory. Shows filenames, sizes, and modification dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Subdirectory to list (relative to documents root). Empty for root.",
                    "default": ""
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.pdf', '*.txt')",
                    "default": "*"
                }
            },
            "required": []
        }
    },
    {
        "name": "read_document",
        "description": "Read the contents of a document. Supports .txt, .md, .py, .json, .csv, .log and other text files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Path to the document relative to the documents directory"
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines to read (default: 100)",
                    "default": 100
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "search_documents",
        "description": "Search for a keyword or phrase across all documents in the documents directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter which files to search (default: '*')",
                    "default": "*"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_reminder",
        "description": "Create a reminder that will alert the user at a specified time. Supports one-time and recurring reminders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The reminder message"
                },
                "time": {
                    "type": "string",
                    "description": "When to trigger the reminder. ISO 8601 format (e.g. '2024-03-15T14:30:00') or relative (e.g. 'in 30 minutes', 'in 2 hours')"
                },
                "recurring": {
                    "type": "string",
                    "description": "Recurrence pattern: 'daily', 'weekly', 'monthly', or null for one-time",
                    "default": ""
                }
            },
            "required": ["message", "time"]
        }
    },
    {
        "name": "list_reminders",
        "description": "List all active reminders.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "delete_reminder",
        "description": "Delete a reminder by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_id": {
                    "type": "integer",
                    "description": "The ID of the reminder to delete"
                }
            },
            "required": ["reminder_id"]
        }
    },
    {
        "name": "control_device",
        "description": "Control a smart home device (lights, switches, thermostats, etc.) via Home Assistant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Home Assistant entity ID (e.g. 'light.living_room', 'switch.fan')"
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform: 'turn_on', 'turn_off', 'toggle', 'set_brightness', 'set_temperature'",
                    "enum": ["turn_on", "turn_off", "toggle", "set_brightness", "set_temperature"]
                },
                "value": {
                    "type": "number",
                    "description": "Value for the action (e.g. brightness 0-255, temperature in F/C)"
                }
            },
            "required": ["entity_id", "action"]
        }
    },
    {
        "name": "list_devices",
        "description": "List available smart home devices from Home Assistant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Filter by domain: 'light', 'switch', 'climate', 'sensor', etc. Empty for all.",
                    "default": ""
                }
            },
            "required": []
        }
    },
    {
        "name": "get_system_info",
        "description": "Get system information: CPU usage, memory, disk space, network status, uptime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "detail": {
                    "type": "string",
                    "description": "Level of detail: 'summary' or 'full'",
                    "default": "summary",
                    "enum": ["summary", "full"]
                }
            },
            "required": []
        }
    },
    # --- Vision tools ---
    {
        "name": "capture_camera",
        "description": "Capture a photo from a camera (webcam, USB camera, security camera). Use this when the user asks you to look at something, see who's at the door, or check on something visually.",
        "input_schema": {
            "type": "object",
            "properties": {
                "camera_index": {
                    "type": "integer",
                    "description": "Camera device index (default: 0 for primary webcam)",
                    "default": 0
                },
                "description": {
                    "type": "string",
                    "description": "What you're looking for (helps focus the analysis)",
                    "default": ""
                }
            },
            "required": []
        }
    },
    {
        "name": "capture_screenshot",
        "description": "Take a screenshot of the user's screen. Use this when the user asks you to look at their screen, read an error, or help with something visible on the display.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What to focus on in the screenshot",
                    "default": ""
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_image",
        "description": "Analyze an image file from the documents directory. Supports jpg, png, gif, webp.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the image file relative to the documents directory"
                },
                "description": {
                    "type": "string",
                    "description": "What to look for in the image",
                    "default": ""
                }
            },
            "required": ["file_path"]
        }
    },
    # --- Monitor tools ---
    {
        "name": "create_monitor",
        "description": "Create a background monitor that alerts the user when a system metric crosses a threshold. Monitors run continuously and announce alerts via TTS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for this monitor"
                },
                "metric": {
                    "type": "string",
                    "description": "What to monitor",
                    "enum": ["cpu", "memory", "disk", "network_sent", "network_recv"]
                },
                "threshold": {
                    "type": "number",
                    "description": "Alert threshold value (percentage for cpu/memory/disk, MB for network)"
                },
                "operator": {
                    "type": "string",
                    "description": "Alert when metric is 'above' or 'below' threshold",
                    "enum": ["above", "below"],
                    "default": "above"
                },
                "interval_minutes": {
                    "type": "integer",
                    "description": "How often to check (default: 5 minutes)",
                    "default": 5
                }
            },
            "required": ["name", "metric", "threshold"]
        }
    },
    {
        "name": "list_monitors",
        "description": "List all active background monitors.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "remove_monitor",
        "description": "Remove a background monitor by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the monitor to remove"
                }
            },
            "required": ["name"]
        }
    }
]

# Map tool names to their handler functions
TOOL_HANDLERS = {
    "read_emails": read_emails,
    "search_emails": search_emails,
    "list_documents": list_documents,
    "read_document": read_document,
    "search_documents": search_documents,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
    "delete_reminder": delete_reminder,
    "control_device": control_device,
    "list_devices": list_devices,
    "get_system_info": get_system_info,
    "capture_camera": capture_camera,
    "capture_screenshot": capture_screenshot,
    "analyze_image": analyze_image,
}


def _lazy_import_monitors():
    """Import monitors lazily to avoid circular imports."""
    from monitors import create_custom_monitor, list_monitors as _list_monitors, remove_monitor as _remove_monitor
    return create_custom_monitor, _list_monitors, _remove_monitor


def execute_tool(name, arguments):
    """Execute a tool by name with the given arguments. Returns a string result."""
    # Handle monitor tools (lazy import)
    if name == "create_monitor":
        create_custom_monitor, _, _ = _lazy_import_monitors()
        return create_custom_monitor(**arguments)
    elif name == "list_monitors":
        _, _list_monitors, _ = _lazy_import_monitors()
        return _list_monitors()
    elif name == "remove_monitor":
        _, _, _remove_monitor = _lazy_import_monitors()
        return _remove_monitor(**arguments)

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    try:
        result = handler(**arguments)
        # Vision tools return dicts with image data — mark for special handling
        if isinstance(result, dict) and result.get("__vision__"):
            return result
        return result
    except Exception as e:
        return f"Tool error ({name}): {e}"
