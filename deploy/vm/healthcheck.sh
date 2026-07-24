#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/opt/eventhorizon
cd "$ROOT"
set -a
# shellcheck disable=SC1091
source .env
set +a

docker compose --env-file .env -f docker-compose.prod.yml ps
curl -fsS --retry 12 --retry-delay 5 --retry-all-errors \
  --resolve "$APP_DOMAIN:443:127.0.0.1" \
  "https://$APP_DOMAIN/api/health/ready" >/dev/null
curl -fsS --retry 12 --retry-delay 5 --retry-all-errors \
  --resolve "$APP_DOMAIN:443:127.0.0.1" \
  "https://$APP_DOMAIN/health" >/dev/null || true
echo "EventHorizon deployment is healthy at https://$APP_DOMAIN"
