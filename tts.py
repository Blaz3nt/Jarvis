"""Text-to-speech with streaming and interrupt support.

Streaming: Splits response into sentences and starts speaking the first
one while generating audio for the rest. Cuts perceived latency in half.

Interrupts: While Jarvis is speaking, audio is still captured. If the
user talks over Jarvis, playback stops immediately.
"""

import asyncio
import os
import re
import time
import threading
from queue import Queue, Empty

import edge_tts
from pygame import mixer
import config

mixer.init()

# Reference to the listener for interrupt detection
_listener = None

# Audio queue for streaming playback
_audio_queue = Queue()
_stop_event = threading.Event()


def set_listener(listener):
    """Register the listener so TTS can coordinate interrupt detection."""
    global _listener
    _listener = listener


def _split_sentences(text):
    """Split text into speakable chunks (sentences or clauses).

    Keeps chunks short for faster streaming but natural for speech.
    """
    # Split on sentence endings and common pause points
    parts = re.split(r'(?<=[.!?])\s+|(?<=[,;:])\s+(?=\w{10,})', text)
    # Merge very short fragments with the next chunk
    merged = []
    buffer = ""
    for part in parts:
        buffer += (" " if buffer else "") + part
        if len(buffer) > 30:  # Minimum chunk size for natural speech
            merged.append(buffer)
            buffer = ""
    if buffer:
        if merged:
            merged[-1] += " " + buffer
        else:
            merged.append(buffer)
    return merged if merged else [text]


async def _generate_chunk(text, output_path):
    """Generate audio for a single text chunk."""
    communicate = edge_tts.Communicate(text, config.TTS_VOICE)
    await communicate.save(output_path)


def _generate_worker(sentences):
    """Background thread: generate audio for each sentence sequentially."""
    for i, sentence in enumerate(sentences):
        if _stop_event.is_set():
            break
        chunk_path = f"/tmp/jarvis_tts_chunk_{i}.mp3"
        try:
            asyncio.run(_generate_chunk(sentence, chunk_path))
            if not _stop_event.is_set():
                _audio_queue.put(chunk_path)
        except Exception as e:
            print(f"[TTS generation error: {e}]")
            break
    _audio_queue.put(None)  # Sentinel: all chunks generated


def _play_worker():
    """Background thread: play audio chunks as they become available.

    Returns "completed" or "interrupted".
    """
    result = "completed"

    while True:
        try:
            chunk_path = _audio_queue.get(timeout=0.1)
        except Empty:
            if _stop_event.is_set():
                result = "interrupted"
                break
            continue

        if chunk_path is None:
            # All chunks played
            break

        if _stop_event.is_set():
            _cleanup_file(chunk_path)
            result = "interrupted"
            break

        try:
            mixer.music.load(chunk_path)
            mixer.music.play()

            while mixer.music.get_busy():
                if _stop_event.is_set():
                    mixer.music.stop()
                    mixer.music.unload()
                    _cleanup_file(chunk_path)
                    result = "interrupted"
                    # Drain remaining queue
                    while True:
                        try:
                            remaining = _audio_queue.get_nowait()
                            if remaining:
                                _cleanup_file(remaining)
                        except Empty:
                            break
                    return result

                # Check for interrupt
                if _listener and _listener.check_for_interrupt():
                    mixer.music.stop()
                    _stop_event.set()
                    mixer.music.unload()
                    _cleanup_file(chunk_path)
                    result = "interrupted"
                    while True:
                        try:
                            remaining = _audio_queue.get_nowait()
                            if remaining:
                                _cleanup_file(remaining)
                        except Empty:
                            break
                    return result

                time.sleep(0.05)

            mixer.music.unload()
        finally:
            _cleanup_file(chunk_path)

    return result


def _cleanup_file(path):
    """Remove a temp audio file."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def speak(text):
    """Generate TTS and play it with streaming.

    Splits text into sentences, generates audio for the first sentence,
    starts playing it, then generates the rest in parallel.

    Returns:
        "completed" — Jarvis finished speaking normally
        "interrupted" — User talked over Jarvis, playback stopped
    """
    if not config.TTS_ENABLED or not text.strip():
        return "completed"

    # Reset state
    _stop_event.clear()
    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
        except Empty:
            break

    # Tell listener we're speaking
    if _listener:
        _listener.set_speaking(True)

    try:
        sentences = _split_sentences(text)

        if len(sentences) == 1:
            # Short response — no need for streaming overhead
            return _speak_simple(text)

        # Start generation in background thread
        gen_thread = threading.Thread(target=_generate_worker, args=(sentences,), daemon=True)
        gen_thread.start()

        # Play chunks as they arrive
        result = _play_worker()

        _stop_event.set()  # Signal generator to stop if still running
        gen_thread.join(timeout=5)

        if result == "interrupted":
            print("[Interrupted by user]")

        return result
    finally:
        if _listener:
            _listener.set_speaking(False)


def _speak_simple(text):
    """Non-streaming TTS for short responses."""
    speech_file = "/tmp/jarvis_speech.mp3"
    try:
        asyncio.run(_generate_chunk(text, speech_file))
        mixer.music.load(speech_file)
        mixer.music.play()

        while mixer.music.get_busy():
            if _listener and _listener.check_for_interrupt():
                mixer.music.stop()
                mixer.music.unload()
                print("[Interrupted by user]")
                return "interrupted"
            time.sleep(0.05)

        mixer.music.unload()
        return "completed"
    finally:
        _cleanup_file(speech_file)
