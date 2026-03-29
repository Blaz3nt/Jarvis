#!/usr/bin/env python3
"""Jarvis — Voice-activated AI assistant powered by Claude.

Listening behavior (like a human):
  1. SLEEPING: Always on, only listening for "Jarvis" (low power).
  2. CONVERSATION: Full attention — responds to everything, no wake word needed.
  3. LINGERING: After silence timeout, still half-listening for a grace period.
     If you speak during this window, Jarvis re-engages without the wake word.
  4. Back to SLEEPING only after the grace period expires with no speech.

Interrupts:
  You can cut Jarvis off mid-sentence by just talking. It will stop
  speaking and process what you said instead.

Example flow:
  You: "Hey Jarvis"
  Jarvis: "Yes sir?"
  You: "Check my email"                  ← no wake word needed
  Jarvis: "You have 3 new emails from—"
  You: "Just the first one"              ← interrupted mid-sentence
  Jarvis: "Right. The first is from..."
  [30s silence → lingering]
  You: "Actually, reply to that"         ← re-engaged without wake word!
  Jarvis: "What would you like to say?"
  [60s more silence → fully asleep]
"""

from datetime import datetime, timezone

import assist
import config
import tts
from listener import Listener
from tools.reminders import init_scheduler


def main():
    # Initialize reminders
    init_scheduler(callback=lambda msg: tts.speak(f"Reminder: {msg}"))

    # Initialize listener and connect it to TTS for interrupt detection
    listener = Listener()
    tts.set_listener(listener)
    listener.start()

    while True:
        result = listener.listen()

        if result is None:
            continue

        # --- Wake word detected ---
        if result == "__WAKE__":
            listener.wake_up()
            tts.speak("Yes sir?")
            continue

        # --- Conversation timed out → enter grace period (not full sleep) ---
        if result == "__TIMEOUT__":
            listener.start_lingering()
            continue

        # --- Grace period expired with no speech → now fully sleep ---
        if result == "__GRACE_EXPIRED__":
            listener.go_to_sleep()
            continue

        # --- User spoke during grace period → re-engage! ---
        if isinstance(result, str) and result.startswith("__RE_ENGAGE__:"):
            text = result.split(":", 1)[1].strip()
            listener.wake_up()
            print(f"[Re-engaged]")
            if text:
                _handle_speech(listener, text)
            continue

        # --- Normal conversation speech ---
        text = result.strip()
        if not text:
            continue

        # Strip wake word from mid-conversation speech
        cleaned = text.lower()
        for hw in config.HOT_WORDS:
            cleaned = cleaned.replace(f"hey {hw}", "").replace(hw, "").strip()
        if not cleaned:
            continue

        _handle_speech(listener, cleaned)


def _handle_speech(listener, text):
    """Process user speech: send to Claude, speak response, handle interrupts."""
    print(f"You: {text}")

    response = assist.ask(text)
    print(f"Jarvis: {response}")

    result = tts.speak(response)

    if result == "interrupted":
        # User talked over Jarvis — get what they said
        interrupted_text = listener.get_interrupt_audio()
        if interrupted_text:
            # Strip wake words
            cleaned = interrupted_text.lower()
            for hw in config.HOT_WORDS:
                cleaned = cleaned.replace(f"hey {hw}", "").replace(hw, "").strip()
            if cleaned:
                print(f"[Interrupted with: {cleaned}]")
                _handle_speech(listener, cleaned)

    # Reset conversation timer
    listener.last_speech_time = datetime.now(timezone.utc)


if __name__ == "__main__":
    main()
