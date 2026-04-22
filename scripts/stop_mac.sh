#!/usr/bin/env bash
# scripts/stop_mac.sh — Stop and remove the FinAlly container.
# The 'finally-data' volume is NOT removed so the SQLite DB persists.
# Idempotent: safe to run when container is already stopped/absent.

set -euo pipefail

CONTAINER_NAME="finally"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping container '${CONTAINER_NAME}' ..."
  docker stop "${CONTAINER_NAME}" > /dev/null 2>&1 || true

  echo "Removing container '${CONTAINER_NAME}' ..."
  docker rm "${CONTAINER_NAME}" > /dev/null 2>&1 || true

  echo "Container stopped and removed."
  echo "(Volume 'finally-data' was kept — your data is safe.)"
else
  echo "No container named '${CONTAINER_NAME}' found. Nothing to do."
fi
