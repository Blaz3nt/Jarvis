"""Three-stage listening system for Jarvis.

Stage 1 (SLEEPING): Low-power wake word detection using OpenWakeWord.
  - Runs constantly, uses minimal CPU (~1-2%)
  - Listens for "jarvis" (or configured wake words)
  - When detected, transitions to CONVERSATION mode

Stage 2 (CONVERSATION): Full speech recognition using Whisper.
  - Transcribes everything the user says
  - Stays active as long as the user keeps talking
  - Times out after CONVERSATION_TIMEOUT seconds of silence
  - Transitions to LINGERING (not straight to sleep)

Stage 3 (LINGERING): Grace period after conversation ends.
  - Still transcribes audio for GRACE_PERIOD seconds
  - If user speaks, jumps back to CONVERSATION (no wake word needed)
  - Like a human who stopped talking but is still half-listening
  - After grace period expires with no speech, transitions to SLEEPING

Interrupt support:
  - While Jarvis is speaking (TTS playing), audio is still captured
  - The main loop can call check_for_interrupt() to detect if the user
    started talking over Jarvis
  - If interrupted, TTS stops and the user's speech is processed
"""

import io
import enum
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
    SLEEPING = "sleeping"           # Wake word detection only
    CONVERSATION = "conversation"   # Full transcription active
    LINGERING = "lingering"         # Grace period — still half-listening


class Listener:
    def __init__(self):
        self.state = ListenerState.SLEEPING
        self.last_speech_time = None
        self.last_jarvis_spoke = None  # When Jarvis last finished speaking
        self._lingering_since = None   # When we entered LINGERING state
        self._audio_queue = Queue()
        self._wake_queue = Queue()
        self._interrupt_queue = Queue()  # Audio captured during TTS playback
        self._is_speaking = False        # True while TTS is playing

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

        # Audio accumulation state
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
        """Background callback — routes audio to the right queue based on state."""
        raw = audio.get_raw_data()
        if self._is_speaking:
            # Jarvis is talking — capture audio for interrupt detection
            self._interrupt_queue.put(raw)
        elif self.state == ListenerState.SLEEPING:
            self._wake_queue.put(raw)
        else:
            # CONVERSATION or LINGERING
            self._audio_queue.put(raw)

    def start(self):
        """Start the background audio listener."""
        self.recorder.listen_in_background(
            self.source,
            self._audio_callback,
            phrase_time_limit=config.RECORD_TIMEOUT,
        )
        print(f"Jarvis is sleeping. Say '{config.HOT_WORDS[0]}' to wake me up.")

    # --- Speaking state (for interrupt detection) ---

    def set_speaking(self, speaking):
        """Call this when TTS starts/stops so we can detect interrupts."""
        self._is_speaking = speaking
        if speaking:
            # Drain interrupt queue from old data
            while not self._interrupt_queue.empty():
                try:
                    self._interrupt_queue.get_nowait()
                except Empty:
                    break

    def check_for_interrupt(self):
        """Check if user is speaking while Jarvis is talking.

        Returns True if significant audio was detected (likely an interrupt).
        """
        if not self._is_speaking:
            return False

        chunks = []
        while not self._interrupt_queue.empty():
            try:
                chunks.append(self._interrupt_queue.get_nowait())
            except Empty:
                break

        if not chunks:
            return False

        # Check audio energy — is someone actually talking?
        combined = b"".join(chunks)
        audio_array = np.frombuffer(combined, dtype=np.int16).astype(np.float32)
        rms_energy = np.sqrt(np.mean(audio_array ** 2))

        # If energy is significantly above threshold, it's likely speech
        return rms_energy > config.ENERGY_THRESHOLD * 1.5

    def get_interrupt_audio(self):
        """After an interrupt is detected, collect and transcribe what was said.

        Call this after stopping TTS to get the interrupted speech.
        """
        # Collect any remaining interrupt audio + new audio
        all_audio = bytes()
        for q in (self._interrupt_queue, self._audio_queue):
            while not q.empty():
                try:
                    all_audio += q.get_nowait()
                except Empty:
                    break

        if len(all_audio) < config.MIC_SAMPLE_RATE:  # less than 0.5s
            return None

        model = self._load_whisper()
        audio_data = sr.AudioData(all_audio, self.source.SAMPLE_RATE, self.source.SAMPLE_WIDTH)
        wav_data = io.BytesIO(audio_data.get_wav_data())
        with open(self._temp_file, "w+b") as f:
            f.write(wav_data.read())

        result = model.transcribe(self._temp_file, fp16=torch.cuda.is_available())
        text = result["text"].strip()
        return text if text else None

    # --- Wake word detection ---

    def _check_wake_word(self):
        """Check if wake word was detected in recent audio."""
        try:
            audio_chunk = self._wake_queue.get(timeout=0.1)
        except Empty:
            return False

        if self._wake_model:
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            predictions = self._wake_model.predict(audio_array)
            for model_name, score in predictions.items():
                if score > config.WAKE_WORD_SENSITIVITY:
                    return True
            return False
        else:
            # Fallback: use Whisper to transcribe and check for hotwords
            self._last_sample += audio_chunk
            now = datetime.now(timezone.utc)
            if self._phrase_time and now - self._phrase_time < timedelta(seconds=config.PHRASE_TIMEOUT):
                return False
            self._phrase_time = now

            if len(self._last_sample) < config.MIC_SAMPLE_RATE * 2:
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

    # --- Conversation transcription ---

    def _transcribe_conversation(self):
        """Transcribe audio during conversation/lingering mode."""
        try:
            data = self._audio_queue.get(timeout=0.1)
        except Empty:
            # No audio — check timeouts
            if self.state == ListenerState.CONVERSATION and self.last_speech_time:
                elapsed = (datetime.now(timezone.utc) - self.last_speech_time).total_seconds()
                if elapsed > config.CONVERSATION_TIMEOUT:
                    return "__TIMEOUT__"
            elif self.state == ListenerState.LINGERING and self._lingering_since:
                elapsed = (datetime.now(timezone.utc) - self._lingering_since).total_seconds()
                if elapsed > config.GRACE_PERIOD:
                    return "__GRACE_EXPIRED__"
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

        if text and self.state == ListenerState.LINGERING:
            # User spoke during grace period — re-engage!
            return "__RE_ENGAGE__:" + text

        return text if text else None

    # --- State transitions ---

    def wake_up(self):
        """Transition to CONVERSATION mode."""
        self.state = ListenerState.CONVERSATION
        self.last_speech_time = datetime.now(timezone.utc)
        self._last_sample = bytes()
        self._phrase_time = None
        self._lingering_since = None
        # Drain leftover audio
        for q in (self._audio_queue, self._wake_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except Empty:
                    break
        print("[Jarvis is now listening]")

    def start_lingering(self):
        """Transition from CONVERSATION to LINGERING (grace period)."""
        self.state = ListenerState.LINGERING
        self._lingering_since = datetime.now(timezone.utc)
        self._last_sample = bytes()
        self._phrase_time = None
        print(f"[Jarvis is still half-listening for {config.GRACE_PERIOD}s...]")

    def go_to_sleep(self):
        """Transition to SLEEPING."""
        self.state = ListenerState.SLEEPING
        self._last_sample = bytes()
        self._phrase_time = None
        self.last_speech_time = None
        self._lingering_since = None
        # Drain all queues
        for q in (self._audio_queue, self._wake_queue, self._interrupt_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except Empty:
                    break
        if self._wake_model:
            self._wake_model.reset()
        print(f"[Jarvis is sleeping — say '{config.HOT_WORDS[0]}' to wake]")

    # --- Main listen method ---

    def listen(self):
        """Main listen method. Call in a loop.

        Returns:
            str: Transcribed user speech (in conversation mode)
            "__WAKE__": Wake word detected
            "__TIMEOUT__": Conversation timed out → enters lingering
            "__GRACE_EXPIRED__": Grace period over → go to sleep
            "__RE_ENGAGE__:<text>": User spoke during grace → back to conversation
            None: Nothing happened yet
        """
        if self.state == ListenerState.SLEEPING:
            if self._check_wake_word():
                return "__WAKE__"
            return None
        else:
            # Both CONVERSATION and LINGERING use the same transcription
            return self._transcribe_conversation()
