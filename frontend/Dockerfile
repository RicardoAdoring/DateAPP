FROM python:3.11-slim AS build

WORKDIR /app

ARG NODE_VERSION=20.19.0
ARG NODE_DIST_BASE=https://nodejs.org/dist
ARG NPM_REGISTRY=https://registry.npmjs.org/

RUN apt-get update \
    -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends \
    -o Acquire::Retries=5 \
    ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "${NODE_DIST_BASE}/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz \
    && mkdir -p /usr/local/lib/nodejs \
    && tar -xJf /tmp/node.tar.xz -C /usr/local/lib/nodejs --strip-components=1 \
    && rm /tmp/node.tar.xz

ENV PATH=/usr/local/lib/nodejs/bin:$PATH

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_AMAP_JS_KEY=
ARG VITE_AMAP_SECURITY_JS_CODE=

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_AMAP_JS_KEY=$VITE_AMAP_JS_KEY \
    VITE_AMAP_SECURITY_JS_CODE=$VITE_AMAP_SECURITY_JS_CODE

COPY package*.json ./
RUN npm config set registry "$NPM_REGISTRY"
RUN npm ci

COPY . .
RUN npm run build

FROM python:3.11-slim

RUN apt-get update \
    -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends \
    -o Acquire::Retries=5 \
    nginx curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
