#!/usr/bin/env python3
"""Jarvis — Voice-activated AI assistant powered by Claude."""

import io
import time
from datetime import datetime, timedelta, timezone
from queue import Queue
from tempfile import NamedTemporaryFile

import speech_recognition as sr
import torch
import whisper

import assist
import config
import tts
from tools.reminders import init_scheduler


def main():
    # Initialize reminder scheduler (announces reminders via TTS)
    init_scheduler(callback=lambda msg: tts.speak(f"Reminder: {msg}"))

    # Audio state
    phrase_time = None
    last_sample = bytes()
    data_queue = Queue()

    # Speech recognizer
    recorder = sr.Recognizer()
    recorder.energy_threshold = config.ENERGY_THRESHOLD
    recorder.dynamic_energy_threshold = False

    source = sr.Microphone(sample_rate=config.MIC_SAMPLE_RATE, device_index=config.MIC_DEVICE_INDEX)

    # Load Whisper model (local, no API cost)
    print(f"Loading Whisper model '{config.WHISPER_MODEL}'...")
    audio_model = whisper.load_model(config.WHISPER_MODEL)
    print("Model loaded.")

    with source:
        recorder.adjust_for_ambient_noise(source)

    def record_callback(_, audio: sr.AudioData) -> None:
        data_queue.put(audio.get_raw_data())

    recorder.listen_in_background(source, record_callback, phrase_time_limit=config.RECORD_TIMEOUT)
    temp_file = NamedTemporaryFile().name
    transcription = [""]

    print(f"Jarvis is listening. Say {config.HOT_WORDS} to activate.")

    while True:
        now = datetime.now(timezone.utc)

        if not data_queue.empty():
            phrase_complete = False

            if phrase_time and now - phrase_time > timedelta(seconds=config.PHRASE_TIMEOUT):
                last_sample = bytes()
                phrase_complete = True

            phrase_time = now

            while not data_queue.empty():
                last_sample += data_queue.get()

            audio_data = sr.AudioData(last_sample, source.SAMPLE_RATE, source.SAMPLE_WIDTH)
            wav_data = io.BytesIO(audio_data.get_wav_data())

            with open(temp_file, "w+b") as f:
                f.write(wav_data.read())

            result = audio_model.transcribe(temp_file, fp16=torch.cuda.is_available())
            text = result["text"].strip()

            if phrase_complete:
                transcription.append(text)

                if any(hw in text.lower() for hw in config.HOT_WORDS):
                    if text:
                        print(f"You: {text}")
                        response = assist.ask(text)
                        print(f"Jarvis: {response}")
                        tts.speak(response)
                else:
                    print("Listening...")
            else:
                transcription[-1] = text

            time.sleep(0.25)


if __name__ == "__main__":
    main()
