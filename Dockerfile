# FreshChain AI backend — runs anywhere that runs containers (Cloud Run, Render, Fly, a VM).
FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY samples samples

# Cloud Run sets $PORT. SQLite lives inside the container (resets on redeploy) unless DATABASE_URL points at Cloud SQL.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
