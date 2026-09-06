# syntax=docker/dockerfile:1
# Stage 1 - build the SPA
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

# Stage 2 - serve the static bundle. Nginx (the edge container) proxies /api
# to the backend, so this image only ships files.
FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf

# The stock nginx image already drops to the "nginx" user for workers; the
# master needs root only to bind port 80 inside the container network.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

EXPOSE 80
