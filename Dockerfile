# Use official Python slim image
FROM python:3.9-slim

# Install system dependencies for Pillow and Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    wget \
    gnupg \
    curl \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libxss1 \
    libasound2 \
    libxshmfence-dev \
    libxrandr2 \
    libxdamage1 \
    libxcomposite1 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser binaries
RUN playwright install --with-deps chromium

# Copy app source code
COPY . .

# Expose port and define runtime
ENV PORT=8080
EXPOSE 8080

# Start with Gunicorn (patched timeout)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "90"]
