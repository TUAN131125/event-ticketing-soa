# Build with the frontend directory as context:
# docker build -f admin-web/Dockerfile .
FROM node:22-alpine AS build
WORKDIR /workspace
COPY package*.json ./
COPY shared-ui/package*.json ./shared-ui/
COPY admin-web/package*.json ./admin-web/
RUN npm install
COPY shared-ui ./shared-ui
COPY admin-web ./admin-web
RUN npm run build --workspace @event-ticketing/admin-web

FROM nginx:1.27-alpine
COPY admin-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/admin-web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/health || exit 1
