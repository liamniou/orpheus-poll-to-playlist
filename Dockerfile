# Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npx vite build

# Production image
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy run script
COPY run.py .

# Create directories
RUN mkdir -p /app/data /app/downloads

# Environment
ENV APP_HOST=0.0.0.0
ENV APP_PORT=7575
ENV PYTHONUNBUFFERED=1

EXPOSE 7575

CMD ["python", "run.py"]
