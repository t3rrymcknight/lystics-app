# Use the official Python slim image
FROM python:3.9-slim

# Install OS dependencies required by Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

# Create a working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy your source code
COPY . .

# Let Cloud Run know which port to expose
ENV PORT=8080
EXPOSE 8080

# Start the app
CMD ["python", "app.py"]
