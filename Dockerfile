# Use official Playwright base image with Python pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set working directory inside the container
WORKDIR /app

# Copy dependency requirements
COPY requirements.txt .

# Install python libraries
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files to the container
COPY . .

# Expose port 8080 (standard Flask port)
EXPOSE 8080

# Start Flask app by default
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
