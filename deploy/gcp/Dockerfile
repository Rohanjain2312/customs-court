# syntax=docker/dockerfile:1.7
# TariffAgent MCP server image for Google Cloud Run. Deploy-ready, not deployed.
#
# Cloud Run container contract (docs checked 2026-09-28, run/docs/container-contract):
# Linux x86_64 image, listen on 0.0.0.0 on $PORT (Cloud Run injects it; default 8080),
# in-memory writable filesystem. Stateless streamable HTTP at /mcp.
# Build from the repo root:
#   uv run python scripts/export_deploy_data.py --fixture      # or without --fixture for real data
#   docker build --platform linux/amd64 -f deploy/gcp/Dockerfile -t tariffagent-mcp:gcp-local .
# On an ARM Mac the amd64 build runs under emulation and is slower.
# Build args: same as deploy/aws/Dockerfile (VECTORS, DATA_SRC).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.9

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /uvx /bin/
ARG VECTORS=0
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
# Locked dependency set; CUDA torch wheels swapped for the CPU-only build (see the AWS Dockerfile).
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eu; \
    extra=""; [ "$VECTORS" = "1" ] && extra="--extra embed"; \
    uv export --frozen --no-dev --no-emit-project --no-hashes $extra -o /tmp/req.txt; \
    grep -v -E '^(torch|triton|nvidia-|cuda-)' /tmp/req.txt > /tmp/req-cpu.txt; \
    uv venv /app/.venv; \
    uv pip install --python /app/.venv/bin/python --no-deps -r /tmp/req-cpu.txt; \
    if [ "$VECTORS" = "1" ]; then \
      tv=$(grep -E '^torch==' /tmp/req.txt | sed -E 's/^torch==([^ ;]+).*/\1/'); \
      uv pip install --python /app/.venv/bin/python --index-url https://download.pytorch.org/whl/cpu "torch==${tv}"; \
    fi
COPY src ./src
RUN uv pip install --python /app/.venv/bin/python --no-deps -e .
ENV HF_HOME=/app/hf
RUN if [ "$VECTORS" = "1" ]; then \
      /app/.venv/bin/python -c "from sentence_transformers import SentenceTransformer as S; m=S('BAAI/bge-small-en-v1.5', device='cpu'); print('model dim', m.get_sentence_embedding_dimension())"; \
    else mkdir -p /app/hf; fi

FROM ${PYTHON_IMAGE} AS runtime
ARG VECTORS=0
ARG DATA_SRC=deploy/.build/data
RUN useradd --system --uid 10001 --home-dir /home/app --create-home app
COPY --from=build /app /app
COPY ${DATA_SRC} /data
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DATA_DIR=/data \
    USE_VECTORS=${VECTORS} \
    REDACT_EVAL=true \
    OFFLINE=true \
    HF_HOME=/app/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false
USER app
WORKDIR /home/app
EXPOSE 8080
# Shell form so $PORT from Cloud Run is used. exec keeps the server as PID 1 for SIGTERM.
CMD exec tariffagent-mcp --transport http --host 0.0.0.0 --port "${PORT}"
