FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source code
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir -e .

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

ENTRYPOINT ["odh"]
CMD ["--config", "/etc/opnsense-dyndns-hetzner/config.yaml"]
