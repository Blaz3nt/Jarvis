import asyncio
import os
import edge_tts
from pygame import mixer
import time
import config

mixer.init()


async def _generate_speech(text, output_path):
    """Generate speech audio using edge-tts (free Microsoft TTS)."""
    communicate = edge_tts.Communicate(text, config.TTS_VOICE)
    await communicate.save(output_path)


def speak(text):
    """Generate TTS and play it. Blocks until playback finishes."""
    if not config.TTS_ENABLED or not text.strip():
        return

    speech_file = "/tmp/jarvis_speech.mp3"
    try:
        asyncio.run(_generate_speech(text, speech_file))
        mixer.music.load(speech_file)
        mixer.music.play()
        while mixer.music.get_busy():
            time.sleep(0.1)
        mixer.music.unload()
    finally:
        if os.path.exists(speech_file):
            os.remove(speech_file)
