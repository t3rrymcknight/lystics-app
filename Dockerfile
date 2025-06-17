# Use the official Python 3.9 slim image
FROM python:3.9-slim

# Install system dependencies required by Pillow for JPEG, PNG
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Set a working directory
WORKDIR /app

# Copy in requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY . .

# Expose port for Cloud Run
ENV PORT=8080
EXPOSE 8080

# Launch the app via Gunicorn (Cloud Run entrypoint)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
