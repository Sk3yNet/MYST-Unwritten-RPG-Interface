# Build context: the repository root (see docker-compose.yml), so the adventures in campaigns/ ship with the app.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CAMPAIGNS_DIR=/srv/campaigns
WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/unwritten ./unwritten
COPY campaigns ./campaigns

RUN useradd --uid 10001 --create-home app && mkdir -p /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
# One worker: the live-update hub lives in-process.
# --timeout-graceful-shutdown: open SSE streams would otherwise hold shutdown until Docker kills the container.
CMD ["uvicorn", "unwritten.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "4"]
