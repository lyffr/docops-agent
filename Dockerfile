FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/docops

RUN addgroup --system docops \
    && adduser --system --ingroup docops --home /home/docops docops \
    && mkdir -p /app /state \
    && chown -R docops:docops /app /state /home/docops

WORKDIR /app
COPY --chown=docops:docops pyproject.toml README.md requirements.lock ./
COPY --chown=docops:docops docops_agent ./docops_agent
COPY --chown=docops:docops data ./data
RUN pip install --requirement requirements.lock \
    && pip install --no-deps .

USER docops
EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3)"]

CMD ["uvicorn", "docops_agent.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "5", "--timeout-graceful-shutdown", "30", "--no-access-log", "--no-server-header"]
