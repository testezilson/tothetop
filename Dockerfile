# Monorepo (testezilson/tothetop): use quando o Root Directory no Railway for a raiz do repositório.
# Se o serviço apontar só para a pasta allthewaytothetop, use o Dockerfile em allthewaytothetop/ em vez deste.
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

COPY allthewaytothetop/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY allthewaytothetop/ .

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMIUM_BIN=/usr/bin/chromium
ENV CYBERSCORE_DB_PATH=/app/data/cyberscore.db
ENV SELENIUM_HEADLESS=1
ENV PYTHONUNBUFFERED=1
# Garante import de main.py em /app (evita "Could not import module main")
ENV PYTHONPATH=/app

# $PORT só expande dentro de sh -c (não use forma JSON/exec com "$PORT" literal)
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
