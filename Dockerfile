FROM python:3.12-slim

WORKDIR /app

# Install runtime deps. openssh-client is present so SSH tools can work when
# explicitly enabled and an SSH config is mounted read-only.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    git \
    libgomp1 \
    openssl \
    openssh-client \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies. STT_MODE=gpu adds CUDA runtime wheels used by
# faster-whisper/CTranslate2; STT_MODE=cpu keeps the image lighter.
ARG STT_MODE=cpu
COPY requirements.txt requirements.docker.txt requirements-gpu.txt ./
RUN pip install --no-cache-dir -r requirements.docker.txt \
    && if [ "$STT_MODE" = "gpu" ]; then pip install --no-cache-dir -r requirements-gpu.txt; fi

ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid ${APP_GID} ollama-hooks 2>/dev/null || groupmod -n ollama-hooks $(getent group ${APP_GID} | cut -d: -f1) \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --home-dir /data --shell /bin/sh ollama-hooks \
    && mkdir -p /config /data /workspace /data/.ssh \
    && chmod 700 /data/.ssh \
    && chown -R ${APP_UID}:${APP_GID} /config /data /workspace

# Copy project
COPY . .
RUN chown -R ollama-hooks:ollama-hooks /app

EXPOSE 8765

USER ollama-hooks
ENV OLLAMA_HOOKS_CONFIG=/config/config.toml \
    OLLAMA_HOOKS_DATA_DIR=/data \
    OLLAMA_WEB_NO_VENV=1 \
    HOME=/data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, ssl, urllib.request; scheme='https' if os.environ.get('WEB_CERT_FILE') and os.environ.get('WEB_KEY_FILE') else 'http'; ctx=ssl._create_unverified_context() if scheme == 'https' else None; urllib.request.urlopen(f'{scheme}://127.0.0.1:8765/healthz', timeout=3, context=ctx).read()"

ENTRYPOINT ["tini", "--"]
CMD ["python", "scripts/ollama_web.py"]
