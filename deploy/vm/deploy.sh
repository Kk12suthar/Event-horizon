#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_TAG=${1:?image tag is required}
ROOT=/opt/eventhorizon
METADATA=http://metadata.google.internal/computeMetadata/v1

metadata() {
  curl -fsS -H 'Metadata-Flavor: Google' "$METADATA/$1"
}

PROJECT_ID=$(metadata project/project-id)
ACCESS_TOKEN=$(metadata instance/service-accounts/default/token | jq -r .access_token)

access_secret() {
  local name=$1
  curl -fsS \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT_ID/secrets/$name/versions/latest:access" \
    | jq -r .payload.data | base64 -d
}

cd "$ROOT"
umask 077
access_secret eventhorizon-runtime-env >.env.tmp
mv .env.tmp .env
access_secret eventhorizon-firebase-credentials >secrets/firebase-credentials.json.tmp
mv secrets/firebase-credentials.json.tmp secrets/firebase-credentials.json

set -a
# shellcheck disable=SC1091
source .env
set +a
export IMAGE_TAG

REGISTRY_HOST="${GCP_REGION}-docker.pkg.dev"
ACCESS_TOKEN=$(metadata instance/service-accounts/default/token | jq -r .access_token)
printf '%s' "$ACCESS_TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$REGISTRY_HOST"

docker compose --env-file .env -f docker-compose.prod.yml pull
docker compose --env-file .env -f docker-compose.prod.yml up -d --remove-orphans --wait --wait-timeout 240
docker image prune -af --filter 'until=168h'

"$ROOT/deploy/vm/healthcheck.sh"
