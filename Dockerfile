# Multi-stage build for Railway: builds the CRACO/React frontend, then
# bundles the static output into the FastAPI backend image. main.py serves
# everything from one process/one Railway service (see the "Serve the
# built React frontend" block in backend/app/main.py) -- the frontend's
# relative `/api/...` calls stay same-origin, no separate frontend service
# or CORS config needed in production.

# ---- Stage 1: build the React frontend (CRACO) ----
FROM node:20-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend + the built frontend ----
FROM python:3.11-slim
WORKDIR /app

# System deps for bcrypt/cryptography wheels on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/build ./frontend/build

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1

# Railway injects $PORT at runtime; default to 8000 for local `docker run`.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
