# Use the official Python 3.9 slim image
FROM python:3.9-slim

# Install system dependencies required by Pillow for JPEG, PNG, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    # (Optional) If you need to handle other file formats (e.g., TIFF), add more libs
  && rm -rf /var/lib/apt/lists/*

# Set a working directory (folder) inside the container
WORKDIR /

# Copy in the requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code (including app.py) into the container
COPY . .

# Cloud Run expects the container to listen on port 8080
ENV PORT=8080
EXPOSE 8080

# This is the command to start your Flask app
CMD ["python", "app.py"]
