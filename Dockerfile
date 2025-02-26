# Use the official Python image
FROM python:3.10

# Set environment variables
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt first (for efficient caching)
COPY requirements.txt /app/

# Install dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*  # Clean up to reduce image size

RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install
RUN playwright install-deps

# Copy the rest of the application files
COPY . /app/

# Expose port 8000 (Django default)
EXPOSE 8000

# Run the Django application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
