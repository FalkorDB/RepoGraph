FROM python:3.12-slim

WORKDIR /app

# Install git (required for analyzing repos)
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY repograph/ repograph/

# Default command: show help
CMD ["python", "-m", "repograph.cli.main", "--help"]
