# Use quando o Root Directory do Railway for allthewaytothetop (repositório ou subpasta do monorepo).
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    libgbm1 \
    libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMIUM_BIN=/usr/bin/chromium
ENV CYBERSCORE_DB_PATH=/app/data/cyberscore.db
ENV SELENIUM_HEADLESS=1
ENV PYTHONUNBUFFERED=1

# $PORT em formato shell (exec JSON não expande variáveis)
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
