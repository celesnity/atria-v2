# The template is a UI-only federation remote. It deliberately has no Python
# connector runtime, module registration, heartbeat, worker, or legacy APIs.
FROM node:20-slim AS frontend-build

WORKDIR /minderSDK
COPY minderSDK/ ./
RUN npm ci --ignore-scripts

WORKDIR /frontend
COPY modules/module_template/frontend/package.json modules/module_template/frontend/package-lock.json* ./
RUN npm ci
COPY modules/module_template/frontend/ ./
ARG MT_PUBLIC_BASE=http://localhost:9300
ENV MT_PUBLIC_BASE=$MT_PUBLIC_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY modules/module_template/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html/dashboard
EXPOSE 9300
