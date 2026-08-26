# BIT Agents API — Render / container image
FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV AGENTS_API_HOST=0.0.0.0

# Render injects PORT; default for local docker runs
EXPOSE 8765

CMD ["sh", "-c", "uvicorn agents_api:app --host 0.0.0.0 --port ${PORT:-8765}"]
