"""Two-stage listening system for Jarvis.

Stage 1 (SLEEPING): Low-power wake word detection using OpenWakeWord.
  - Runs constantly, uses minimal CPU (~1-2%)
  - Listens for "jarvis" (or configured wake words)
  - When detected, transitions to CONVERSATION mode

Stage 2 (CONVERSATION): Full speech recognition using Whisper.
  - Transcribes everything the user says
  - Stays active as long as the user keeps talking
  - Times out after CONVERSATION_TIMEOUT seconds of silence
  - Returns to SLEEPING mode when conversation ends

This mimics how humans work — you don't process everything you hear,
but once someone says your name, you pay full attention until the
conversation naturally ends.
"""

import io
import time
import enum
import threading
import numpy as np
from datetime import datetime, timezone, timedelta
from queue import Queue, Empty
from tempfile import NamedTemporaryFile

import speech_recognition as sr
import torch
import whisper

try:
    from openwakeword.model import Model as WakeWordModel
    HAS_OPENWAKEWORD = True
except ImportError:
    HAS_OPENWAKEWORD = False

import config


class ListenerState(enum.Enum):
    SLEEPING = "sleeping"       # Wake word detection only
    CONVERSATION = "conversation"  # Full transcription active


class Listener:
    def __init__(self):
        self.state = ListenerState.SLEEPING
        self.last_speech_time = None
        self._audio_queue = Queue()
        self._wake_queue = Queue()

        # Speech recognizer for mic capture
        self.recorder = sr.Recognizer()
        self.recorder.energy_threshold = config.ENERGY_THRESHOLD
        self.recorder.dynamic_energy_threshold = False
        self.source = sr.Microphone(
            sample_rate=config.MIC_SAMPLE_RATE,
            device_index=config.MIC_DEVICE_INDEX,
        )

        # Whisper model (loaded lazily on first conversation)
        self._whisper_model = None
        self._temp_file = NamedTemporaryFile().name

        # Wake word model
        if HAS_OPENWAKEWORD:
            self._wake_model = WakeWordModel(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx",
            )
            print("Wake word engine loaded (OpenWakeWord).")
        else:
            self._wake_model = None
            print("OpenWakeWord not installed — falling back to keyword detection.")

        # Calibrate mic
        with self.source:
            self.recorder.adjust_for_ambient_noise(self.source)

        # Audio accumulation state for conversation mode
        self._last_sample = bytes()
        self._phrase_time = None

    def _load_whisper(self):
        """Load Whisper model on first use (saves memory when sleeping)."""
        if self._whisper_model is None:
            print(f"Loading Whisper model '{config.WHISPER_MODEL}'...")
            self._whisper_model = whisper.load_model(config.WHISPER_MODEL)
            print("Whisper model loaded.")
        return self._whisper_model

    def _audio_callback(self, _, audio: sr.AudioData):
        """Background callback — receives all audio chunks."""
        raw = audio.get_raw_data()
        if self.state == ListenerState.SLEEPING:
            self._wake_queue.put(raw)
        else:
            self._audio_queue.put(raw)

    def start(self):
        """Start the background audio listener."""
        self.recorder.listen_in_background(
            self.source,
            self._audio_callback,
            phrase_time_limit=config.RECORD_TIMEOUT,
        )
        print(f"Jarvis is sleeping. Say '{config.HOT_WORDS[0]}' to wake me up.")

    def _check_wake_word(self):
        """Check if wake word was detected in recent audio."""
        try:
            audio_chunk = self._wake_queue.get(timeout=0.1)
        except Empty:
            return False

        if self._wake_model:
            # OpenWakeWord expects int16 numpy array
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            predictions = self._wake_model.predict(audio_array)
            # Check all model scores
            for model_name, score in predictions.items():
                if score > config.WAKE_WORD_SENSITIVITY:
                    return True
            return False
        else:
            # Fallback: use Whisper to transcribe and check for hotwords
            # Only do this periodically to save CPU
            self._last_sample += audio_chunk
            now = datetime.now(timezone.utc)
            if self._phrase_time and now - self._phrase_time < timedelta(seconds=config.PHRASE_TIMEOUT):
                return False
            self._phrase_time = now

            if len(self._last_sample) < config.MIC_SAMPLE_RATE * 2:  # at least 1 sec of audio
                return False

            model = self._load_whisper()
            audio_data = sr.AudioData(self._last_sample, self.source.SAMPLE_RATE, self.source.SAMPLE_WIDTH)
            wav_data = io.BytesIO(audio_data.get_wav_data())
            with open(self._temp_file, "w+b") as f:
                f.write(wav_data.read())

            result = model.transcribe(self._temp_file, fp16=torch.cuda.is_available())
            text = result["text"].strip().lower()
            self._last_sample = bytes()

            return any(hw in text for hw in config.HOT_WORDS)

    def _transcribe_conversation(self):
        """Transcribe audio during conversation mode. Returns completed phrase or None."""
        try:
            data = self._audio_queue.get(timeout=0.1)
        except Empty:
            # Check for conversation timeout
            if self.last_speech_time:
                elapsed = (datetime.now(timezone.utc) - self.last_speech_time).total_seconds()
                if elapsed > config.CONVERSATION_TIMEOUT:
                    return "__TIMEOUT__"
            return None

        now = datetime.now(timezone.utc)
        phrase_complete = False

        if self._phrase_time and now - self._phrase_time > timedelta(seconds=config.CONVERSATION_PAUSE):
            self._last_sample = bytes()
            phrase_complete = True

        self._phrase_time = now
        self.last_speech_time = now

        # Accumulate audio
        while True:
            self._last_sample += data
            try:
                data = self._audio_queue.get_nowait()
            except Empty:
                break

        if not phrase_complete:
            return None

        # Transcribe the completed phrase
        model = self._load_whisper()
        audio_data = sr.AudioData(self._last_sample, self.source.SAMPLE_RATE, self.source.SAMPLE_WIDTH)
        wav_data = io.BytesIO(audio_data.get_wav_data())
        with open(self._temp_file, "w+b") as f:
            f.write(wav_data.read())

        result = model.transcribe(self._temp_file, fp16=torch.cuda.is_available())
        text = result["text"].strip()
        self._last_sample = bytes()

        return text if text else None

    def wake_up(self):
        """Transition from SLEEPING to CONVERSATION mode."""
        self.state = ListenerState.CONVERSATION
        self.last_speech_time = datetime.now(timezone.utc)
        self._last_sample = bytes()
        self._phrase_time = None
        # Drain any leftover audio from sleep mode
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Empty:
                break
        print("[Jarvis is now listening]")

    def go_to_sleep(self):
        """Transition from CONVERSATION back to SLEEPING."""
        self.state = ListenerState.SLEEPING
        self._last_sample = bytes()
        self._phrase_time = None
        self.last_speech_time = None
        # Drain conversation audio queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Empty:
                break
        # Reset wake word model state
        if self._wake_model:
            self._wake_model.reset()
        print(f"[Jarvis is sleeping — say '{config.HOT_WORDS[0]}' to wake]")

    def listen(self):
        """Main listen method. Call in a loop.

        Returns:
            str: Transcribed user speech (in conversation mode)
            "__WAKE__": Wake word detected (transition to conversation)
            "__TIMEOUT__": Conversation timed out (transition to sleep)
            None: Nothing happened yet
        """
        if self.state == ListenerState.SLEEPING:
            if self._check_wake_word():
                return "__WAKE__"
            return None
        else:
            return self._transcribe_conversation()
