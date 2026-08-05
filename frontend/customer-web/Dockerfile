# Build with the frontend directory as context:
# docker build -f customer-web/Dockerfile .
FROM node:22-alpine AS build
WORKDIR /workspace
COPY package*.json ./
COPY shared-ui/package*.json ./shared-ui/
COPY customer-web/package*.json ./customer-web/
COPY admin-web/package*.json ./admin-web/
RUN npm ci
COPY shared-ui ./shared-ui
COPY customer-web ./customer-web

ARG VITE_IDENTITY_API_URL
ARG VITE_ESB_API_URL
ARG VITE_REALTIME_WS_URL
ARG VITE_AUTH_TRANSPORT
ENV VITE_IDENTITY_API_URL=$VITE_IDENTITY_API_URL \
    VITE_ESB_API_URL=$VITE_ESB_API_URL \
    VITE_REALTIME_WS_URL=$VITE_REALTIME_WS_URL \
    VITE_AUTH_TRANSPORT=$VITE_AUTH_TRANSPORT
RUN npm run build --workspace @event-ticketing/customer-web

FROM nginx:1.27-alpine
COPY customer-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/customer-web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost/health || exit 1
