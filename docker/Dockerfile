# Build Stage
FROM python:3.12-slim AS builder

# Set build-time environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install git and system packages required during installation
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv python package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /build

# Copy dependencies manifest files and project metadata
COPY pyproject.toml uv.lock README.md ./

# Create virtual environment and install only dependencies (cached layer)
RUN uv venv /app/.venv && uv pip install --python /app/.venv/bin/python --no-cache -r pyproject.toml

# Copy project source code
COPY src ./src

# Install the code-assistant package into the virtual environment
RUN uv pip install --python /app/.venv/bin/python --no-cache -e .


# Runtime Stage
FROM python:3.12-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

# Install runtime utilities (git, bash, and curl for API readiness check if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment and source code from the builder stage
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /build/src /app/src
COPY --from=builder /build/pyproject.toml /app/pyproject.toml

# Create a non-root app user for security
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /workspace && \
    chown -R appuser:appuser /app /workspace

USER appuser
ENV HOME=/home/appuser

# Configure Git safe directory permissions for the container-bound workspace
RUN git config --global --add safe.directory /workspace

WORKDIR /workspace

# Default command launches the interactive shell. Override via docker run arguments.
ENTRYPOINT ["code-assistant"]
CMD []
