FROM python:3.11-slim

# System dependencies for audio, PyAudio, and pygame
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libasound2-dev \
    libsdl2-mixer-2.0-0 \
    libsdl2-2.0-0 \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for reminders DB
RUN mkdir -p /data /documents

# Default environment
ENV PYTHONUNBUFFERED=1

CMD ["python", "jarvis.py"]
