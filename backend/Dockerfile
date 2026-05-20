FROM python:3.11-slim

ARG NODE_VERSION=20.19.0
ARG NODE_DIST_BASE=https://nodejs.org/dist

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/usr/local/lib/nodejs/bin:$PATH

WORKDIR /app

RUN apt-get update \
    -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends \
    -o Acquire::Retries=5 \
    build-essential ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "${NODE_DIST_BASE}/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz \
    && mkdir -p /usr/local/lib/nodejs \
    && tar -xJf /tmp/node.tar.xz -C /usr/local/lib/nodejs --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && npm install -g @amap/amap-maps-mcp-server@0.0.8

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY data ./data
COPY eval ./eval
COPY scripts ./scripts

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
