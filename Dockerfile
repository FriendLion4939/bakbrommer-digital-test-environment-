# Bakbrommer Twin — container image for the home server.
FROM python:3.12-slim

# gcc is needed for the software-in-the-loop example (C controller compiled for the PC).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY bakbrommer_twin ./bakbrommer_twin
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .

# User files live in volumes so they survive image updates.
ENV BAKBROMMER_DATA_DIR=/data \
    BAKBROMMER_RUNS_DIR=/runs
VOLUME ["/data", "/runs"]
EXPOSE 8501

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["ui"]
