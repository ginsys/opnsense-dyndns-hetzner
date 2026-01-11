FROM python:3.12-slim

WORKDIR /app

# Copy source and install in single step
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

ENTRYPOINT ["odh"]
CMD ["--config", "/etc/opnsense-dyndns-hetzner/config.yaml"]
