# syntax=docker/dockerfile:1.7
# Python 3.10 is hardcoded throughout this Dockerfile because the CARLA wheel in
# carla_wheels/ is CPython-3.10 ABI-tagged; bumping requires a rebuilt CARLA wheel
# and updating the apt package and the venv path below. The lanelet2 binding no
# longer constrains this: simple-lanelet2 ships abi3 wheels for CPython 3.9+.
FROM ubuntu:22.04 AS base
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.10 python3.10-venv python3-pip \
      libgl1 \
      git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/
WORKDIR /workspace

# Single deps stage: copy full workspace sources and run a single uv sync.
# Every dependency now resolves to a prebuilt wheel, so this is one download
# step with nothing compiled; splitting it into separate runtime and dev syncs
# would only trade a smaller layer for a second resolution of the same lock.
FROM base AS deps
COPY pyproject.toml uv.lock .python-version ./
COPY autoware_lanelet2_to_opendrive/ autoware_lanelet2_to_opendrive/
COPY autoware_carla_scenario/ autoware_carla_scenario/
COPY carla_wheels/ carla_wheels/
RUN uv sync --frozen --dev --extra carla

FROM deps AS dev
ENV PATH="/workspace/.venv/bin:${PATH}"
CMD ["bash"]

FROM base AS convert
COPY --from=deps /workspace /workspace
ENV PATH="/workspace/.venv/bin:${PATH}"
WORKDIR /io
ENTRYPOINT ["convert"]
CMD ["--help"]
