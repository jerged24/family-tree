FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend

ENV MEDIA_DIR=/data/media \
    DATABASE_URL=sqlite:////data/app.db \
    ENV=production

# Railway sets $PORT; default 8000 for local runs.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
