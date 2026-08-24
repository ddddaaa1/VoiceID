# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc AS uv

FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --gid 10001 voiceid \
    && useradd --uid 10001 --gid voiceid --create-home --shell /usr/sbin/nologin voiceid

WORKDIR /app
COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock README.md ./
COPY LICENSES ./LICENSES
COPY src ./src

RUN uv sync --frozen --no-dev --extra ml --extra api --extra persistence \
    && mkdir -p /app/data /app/artifacts \
    && chown -R voiceid:voiceid /app/data /app/artifacts /home/voiceid

USER 10001:10001

EXPOSE 8000
VOLUME ["/app/data", "/app/artifacts"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).read()"]

CMD ["uvicorn", "voiceid.adapters.api.durable_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
