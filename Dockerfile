FROM python:3.9-slim

# Install system dependencies for Pillow + Chromium for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    wget gnupg curl unzip \
    fonts-liberation libnss3 libatk-bridge2.0-0 \
    libxss1 libasound2 libx11-xcb1 libgtk-3-0 \
    libgbm-dev libxshmfence1 libxcomposite1 \
    libxrandr2 libxcb1 libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium (headless browser)
RUN playwright install --with-deps

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
