# Dockerfile
FROM python:3.9-slim

# Install OS-level deps needed by Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files in the root directory into /app
COPY . .

# Flask must listen on 0.0.0.0:8080 for Cloud Run
ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
