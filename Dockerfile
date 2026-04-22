# Stage 1: Build the Next.js frontend static export
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Install dependencies first for better layer caching
COPY frontend/package*.json ./
RUN npm ci

# Copy source and build the static export
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime with FastAPI
FROM python:3.12-slim AS runtime

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for better layer caching
COPY backend/pyproject.toml backend/uv.lock ./backend/

# Install third-party dependencies only — skip installing the project itself
# (the `app/` package doesn't exist in this layer yet). This keeps the heavy
# deps layer cacheable across code changes.
RUN cd backend && uv sync --frozen --no-dev --no-install-project

# Copy backend source
COPY backend/ ./backend/

# Install the project itself now that the source is present. Deps are already
# in the venv so this step is fast.
RUN cd backend && uv sync --frozen --no-dev

# Copy the frontend static export from the build stage
COPY --from=frontend-builder /build/out ./backend/static/

# Ensure the db directory exists for the volume mount target
RUN mkdir -p /app/db

EXPOSE 8000

# Run uvicorn via uv — reads env vars from runtime (not baked in)
CMD ["uv", "run", "--project", "backend", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
