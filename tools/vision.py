"""Vision tools — Jarvis can see via camera and screenshots.

Supports:
- Webcam/USB camera capture ("what do you see?", "who's at the door?")
- Screenshot analysis ("what's on my screen?", "read this error")
- Image file analysis (from documents directory)

Uses Claude's native vision — images are sent as base64 in the message.
No extra API cost beyond normal token pricing for the image.
"""

import base64
import os
import subprocess
from datetime import datetime

import config

# Where to save temporary captures
CAPTURE_DIR = "/tmp/jarvis_vision"
os.makedirs(CAPTURE_DIR, exist_ok=True)


def capture_camera(camera_index=0, description=""):
    """Capture a frame from a camera.

    Returns a dict with base64 image data for Claude vision,
    plus a text description of what was captured.
    """
    output_path = os.path.join(CAPTURE_DIR, f"camera_{datetime.now().strftime('%H%M%S')}.jpg")

    try:
        # Use ffmpeg to grab a single frame (works in Docker with device passthrough)
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "v4l2",
                "-i", f"/dev/video{camera_index}",
                "-frames:v", "1",
                "-q:v", "2",
                output_path,
            ],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"Camera capture failed: {result.stderr.decode()[:200]}"

        with open(output_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        return {
            "__vision__": True,
            "image_base64": image_data,
            "media_type": "image/jpeg",
            "description": description or "Camera capture",
        }
    except FileNotFoundError:
        return "ffmpeg not installed. Cannot capture camera."
    except subprocess.TimeoutExpired:
        return "Camera capture timed out."
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def capture_screenshot(description=""):
    """Capture a screenshot of the current display.

    Returns a dict with base64 image data for Claude vision.
    """
    output_path = os.path.join(CAPTURE_DIR, f"screen_{datetime.now().strftime('%H%M%S')}.png")

    try:
        # Try multiple screenshot methods
        for cmd in [
            ["scrot", "-o", output_path],                    # Linux with scrot
            ["import", "-window", "root", output_path],      # ImageMagick
            ["grim", output_path],                           # Wayland
        ]:
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=5)
                if result.returncode == 0 and os.path.exists(output_path):
                    break
            except FileNotFoundError:
                continue
        else:
            return "No screenshot tool available. Install scrot, imagemagick, or grim."

        with open(output_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        return {
            "__vision__": True,
            "image_base64": image_data,
            "media_type": "image/png",
            "description": description or "Screenshot",
        }
    except subprocess.TimeoutExpired:
        return "Screenshot capture timed out."
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def analyze_image(file_path, description=""):
    """Analyze an image file from the documents directory.

    Returns a dict with base64 image data for Claude vision.
    """
    # Ensure path is within documents directory
    base = os.path.realpath(config.DOCUMENTS_PATH)
    target = os.path.realpath(os.path.join(base, file_path))
    if not target.startswith(base):
        return "Access denied: path is outside the documents directory."

    if not os.path.isfile(target):
        return f"Image not found: {file_path}"

    # Detect media type
    ext = os.path.splitext(target)[1].lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext)
    if not media_type:
        return f"Unsupported image format: {ext}. Supported: jpg, png, gif, webp."

    with open(target, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    return {
        "__vision__": True,
        "image_base64": image_data,
        "media_type": media_type,
        "description": description or f"Image: {file_path}",
    }
