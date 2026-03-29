import os


# Claude API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# Token budget — max conversation history messages to keep (saves tokens)
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "20"))

# Whisper
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny.en")

# Audio
MIC_DEVICE_INDEX = int(os.environ.get("MIC_DEVICE_INDEX", "0"))
MIC_SAMPLE_RATE = int(os.environ.get("MIC_SAMPLE_RATE", "16000"))
ENERGY_THRESHOLD = int(os.environ.get("ENERGY_THRESHOLD", "1000"))
RECORD_TIMEOUT = int(os.environ.get("RECORD_TIMEOUT", "2"))
PHRASE_TIMEOUT = int(os.environ.get("PHRASE_TIMEOUT", "3"))

# TTS
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")
TTS_ENABLED = os.environ.get("TTS_ENABLED", "true").lower() == "true"

# Hotwords
HOT_WORDS = os.environ.get("HOT_WORDS", "jarvis").lower().split(",")

# Email (IMAP)
EMAIL_IMAP_SERVER = os.environ.get("EMAIL_IMAP_SERVER", "")
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# Documents directory (mounted volume in Docker)
DOCUMENTS_PATH = os.environ.get("DOCUMENTS_PATH", "/documents")

# Reminders database
REMINDERS_DB = os.environ.get("REMINDERS_DB", "/data/reminders.db")

# Smart Home (Home Assistant)
HASS_URL = os.environ.get("HASS_URL", "")
HASS_TOKEN = os.environ.get("HASS_TOKEN", "")

# System prompt for Jarvis personality
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", """You are Jarvis, an AI assistant like from Iron Man. Witty, concise, slightly sarcastic.
Keep responses under 60 words unless detail is requested. Use tools when relevant.
Do NOT repeat tool output verbatim — summarize it briefly.""")
