FROM python:3.9-slim

# Install system dependencies for Pillow only (image processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source code
COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "90"]
