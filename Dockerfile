FROM python:3.12-slim

# FFmpeg is required for audio playback
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment variables (override in Unraid Docker template)
ENV DISCORD_TOKEN=""
ENV MUSIC_DIR="/music"
ENV DATA_DIR="/data"
ENV WEB_HOST="0.0.0.0"
ENV WEB_PORT="8080"

EXPOSE 8080

CMD ["python", "main.py"]
