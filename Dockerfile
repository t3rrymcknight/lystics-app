# Use the official Python base image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install any system dependencies you might need (here none are strictly required besides Pillow’s own deps)
# RUN apt-get update && apt-get install -y <packages> && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt into the container
COPY requirements.txt requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source code
COPY . .

# Set the entry point to run the Flask app
# The PORT environment variable is provided by Cloud Run
ENV PORT 8080
EXPOSE 8080

# Command to run our Flask app
CMD ["python", "app.py"]
