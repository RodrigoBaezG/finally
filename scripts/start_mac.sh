#!/usr/bin/env bash
# scripts/start_mac.sh — Build (if needed) and run the FinAlly container.
# Idempotent: safe to run multiple times.
#
# Usage:
#   ./scripts/start_mac.sh           # build image if missing, start container
#   ./scripts/start_mac.sh --build   # force a fresh image build before starting
#   ./scripts/start_mac.sh --no-browser  # suppress automatic browser open
#   ./scripts/start_mac.sh --help    # show this help

set -euo pipefail

IMAGE_NAME="finally:latest"
CONTAINER_NAME="finally"
PORT=8000
URL="http://localhost:${PORT}"
ENV_FILE=".env"

FORCE_BUILD=false
OPEN_BROWSER=true

# Parse arguments
for arg in "$@"; do
  case "$arg" in
    --build)        FORCE_BUILD=true ;;
    --no-browser)   OPEN_BROWSER=false ;;
    --help|-h)
      sed -n '2,9p' "$0" | sed 's/^# //'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

# Locate the project root (the directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Ensure .env exists (warn if missing)
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "WARNING: ${ENV_FILE} not found. Copying from .env.example ..."
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    echo "  Created .env from .env.example. Edit it to add your OPENROUTER_API_KEY."
  else
    echo "  No .env.example found either. Container will start without env vars."
    ENV_FILE_ARG=""
  fi
fi

ENV_FILE_ARG="--env-file ${ENV_FILE}"

# Build the image if it doesn't exist or --build was requested
if [[ "${FORCE_BUILD}" == "true" ]] || ! docker image inspect "${IMAGE_NAME}" > /dev/null 2>&1; then
  echo "Building Docker image ${IMAGE_NAME} ..."
  docker build -t "${IMAGE_NAME}" .
else
  echo "Image ${IMAGE_NAME} already exists. Skipping build (pass --build to force)."
fi

# Stop and remove any existing container with the same name (idempotency)
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping and removing existing container '${CONTAINER_NAME}' ..."
  docker stop "${CONTAINER_NAME}" > /dev/null 2>&1 || true
  docker rm   "${CONTAINER_NAME}" > /dev/null 2>&1 || true
fi

# Run the container detached
echo "Starting container '${CONTAINER_NAME}' ..."
docker run \
  --detach \
  --name "${CONTAINER_NAME}" \
  -p "${PORT}:${PORT}" \
  -v finally-data:/app/db \
  ${ENV_FILE_ARG} \
  "${IMAGE_NAME}"

echo ""
echo "FinAlly is running at: ${URL}"
echo ""
echo "To stop:  ./scripts/stop_mac.sh"
echo "To logs:  docker logs -f ${CONTAINER_NAME}"

# Open browser
if [[ "${OPEN_BROWSER}" == "true" ]]; then
  # Wait briefly for the server to start, then open
  sleep 2
  if command -v open &> /dev/null; then
    open "${URL}"
  elif command -v xdg-open &> /dev/null; then
    xdg-open "${URL}"
  fi
fi
