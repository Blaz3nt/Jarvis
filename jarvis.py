#!/usr/bin/env python3
"""Jarvis — Voice-activated AI assistant powered by Claude.

Listening behavior (like a human):
  1. SLEEPING: Always on, but only listening for the wake word ("Jarvis").
     Uses near-zero CPU via OpenWakeWord.
  2. CONVERSATION: Once woken, Jarvis pays full attention. It transcribes
     and responds to everything you say — no need to repeat the wake word.
  3. SLEEP AGAIN: After a configurable silence timeout (default 30s),
     Jarvis goes back to sleep until you call again.

This means you can have natural back-and-forth conversations:
  You: "Hey Jarvis"
  Jarvis: "Yes sir?"
  You: "Check my email"           ← no wake word needed
  Jarvis: "You have 3 new emails..."
  You: "Read the first one"       ← still in conversation
  Jarvis: "It's from..."
  [30 seconds of silence]
  Jarvis: [goes back to sleep]
"""

import time

import assist
import config
import tts
from listener import Listener
from tools.reminders import init_scheduler


def main():
    # Initialize reminders (announces via TTS when triggered)
    init_scheduler(callback=lambda msg: tts.speak(f"Reminder: {msg}"))

    # Initialize the two-stage listener
    listener = Listener()
    listener.start()

    while True:
        result = listener.listen()

        if result is None:
            # Nothing happened — keep listening
            continue

        if result == "__WAKE__":
            # Wake word detected — enter conversation mode
            listener.wake_up()
            tts.speak("Yes sir?")
            continue

        if result == "__TIMEOUT__":
            # Conversation timed out — go back to sleep
            listener.go_to_sleep()
            continue

        # We have transcribed speech in conversation mode
        text = result.strip()
        if not text:
            continue

        # Check if user is saying the wake word again mid-conversation
        # (just treat it as continued conversation)
        for hw in config.HOT_WORDS:
            text = text.lower().replace(f"hey {hw}", "").replace(hw, "").strip()
        if not text:
            continue

        print(f"You: {text}")

        # Ask Claude
        response = assist.ask(text)
        print(f"Jarvis: {response}")

        # Speak the response
        tts.speak(response)

        # Reset the conversation timer (user just interacted)
        listener.last_speech_time = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )


if __name__ == "__main__":
    main()
