FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (for audio processing, building, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libasound-dev \
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --system

# Copy application source
COPY . .

# Expose port
EXPOSE 8080

# Switch to non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Command to run the application
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
