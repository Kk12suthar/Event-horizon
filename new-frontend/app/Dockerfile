FROM node:22-alpine AS build

WORKDIR /app
COPY new-frontend/app/package.json new-frontend/app/package-lock.json ./
RUN npm ci
COPY new-frontend/app ./
RUN npm run build

FROM caddy:2.10-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

EXPOSE 80 443 443/udp
