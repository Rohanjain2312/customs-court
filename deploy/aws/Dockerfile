# syntax=docker/dockerfile:1.7
# TariffAgent MCP server image for Amazon Bedrock AgentCore Runtime (MCP protocol).
# Deploy-ready, not deployed.
#
# AgentCore MCP contract (docs checked 2026-09-28, runtime-mcp-protocol-contract.html):
# host 0.0.0.0, port 8000, POST /mcp, streamable HTTP, stateless recommended, ARM64 image.
# Build from the repo root:
#   uv run python scripts/export_deploy_data.py --fixture      # or without --fixture for real data
#   docker build --platform linux/arm64 -f deploy/aws/Dockerfile -t tariffagent-mcp:aws-local .
# Build args:
#   VECTORS=0 (default) gives a BM25-only image. The fixture data has no vector index.
#   VECTORS=1 installs sentence-transformers with CPU-only torch and bakes
#             BAAI/bge-small-en-v1.5 into the image. Use it with the real data export,
#             which includes the vector index.
#   DATA_SRC  staged data dir inside the build context (default deploy/.build/data).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.9

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /uvx /bin/
ARG VECTORS=0
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
# Install the locked dependency set. The lock resolves torch with CUDA wheels on
# Linux; they add gigabytes and do nothing here, so they are filtered out and the
# same torch version is installed from the CPU-only index instead.
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
# Editable install so tariffagent.config.ROOT resolves to /app.
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
# Data is read-only at runtime. The staged SQLite file uses a rollback journal, so
# read-only opens need no -wal or -shm files.
COPY ${DATA_SRC} /data
# REDACT_EVAL=true hides every evaluation-set ruling from every tool, so a public
# endpoint cannot leak golden answers. Set it to false only for a private server.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
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
EXPOSE 8000
CMD ["tariffagent-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
