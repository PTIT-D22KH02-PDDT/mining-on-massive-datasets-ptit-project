FROM python:3.12-slim

# Install Java (required for PySpark)
RUN apt-get update && \
    apt-get install -y default-jre && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Force uv to use copy instead of hardlink to avoid Docker filesystem errors
ENV UV_LINK_MODE=copy

WORKDIR /opt/app

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project

# Copy project files
COPY . /opt/app
RUN uv sync

ENV PYSPARK_PYTHON=python3
ENV PATH="/opt/app/.venv/bin:$PATH"

CMD ["python3", "src/api/main.py"]