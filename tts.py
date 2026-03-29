"""Text-to-speech with interrupt support.

While Jarvis is speaking, the listener continues capturing audio.
If the user talks over Jarvis, playback stops immediately — just like
interrupting a real person mid-sentence.
"""

import asyncio
import os
import time
import edge_tts
from pygame import mixer
import config

mixer.init()

# Reference to the listener, set by jarvis.py at startup
_listener = None


def set_listener(listener):
    """Register the listener so TTS can coordinate interrupt detection."""
    global _listener
    _listener = listener


async def _generate_speech(text, output_path):
    """Generate speech audio using edge-tts (free Microsoft TTS)."""
    communicate = edge_tts.Communicate(text, config.TTS_VOICE)
    await communicate.save(output_path)


def speak(text):
    """Generate TTS and play it. Stops if the user interrupts.

    Returns:
        "completed" — Jarvis finished speaking normally
        "interrupted" — User talked over Jarvis, playback stopped
    """
    if not config.TTS_ENABLED or not text.strip():
        return "completed"

    speech_file = "/tmp/jarvis_speech.mp3"
    try:
        asyncio.run(_generate_speech(text, speech_file))

        # Tell listener we're about to speak
        if _listener:
            _listener.set_speaking(True)

        mixer.music.load(speech_file)
        mixer.music.play()

        # Poll for completion OR interrupt
        while mixer.music.get_busy():
            # Check if user is trying to talk over us
            if _listener and _listener.check_for_interrupt():
                mixer.music.stop()
                mixer.music.unload()
                if _listener:
                    _listener.set_speaking(False)
                print("[Interrupted by user]")
                return "interrupted"
            time.sleep(0.05)  # Check frequently for responsive interrupts

        mixer.music.unload()
        return "completed"
    finally:
        if _listener:
            _listener.set_speaking(False)
        if os.path.exists(speech_file):
            os.remove(speech_file)
