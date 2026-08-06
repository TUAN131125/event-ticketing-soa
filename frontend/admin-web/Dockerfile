# Build with the frontend directory as context:
# docker build -f admin-web/Dockerfile .
FROM node:22-alpine AS build
WORKDIR /workspace
# Every workspace manifest is required for `npm ci` to reproduce the single root lockfile.
COPY package*.json ./
COPY shared-ui/package*.json ./shared-ui/
COPY customer-web/package*.json ./customer-web/
COPY admin-web/package*.json ./admin-web/
RUN npm ci
COPY shared-ui ./shared-ui
COPY admin-web ./admin-web

ARG VITE_ESB_API_URL
ENV VITE_ESB_API_URL=$VITE_ESB_API_URL
RUN npm run build --workspace @event-ticketing/admin-web

FROM nginx:1.27-alpine
COPY admin-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/admin-web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/health || exit 1
