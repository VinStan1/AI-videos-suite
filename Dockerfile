FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data HOME=/tmp FFMPEG_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg espeak-ng fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/cryptid
COPY requirements.txt requirements-test.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY workflows ./workflows
COPY examples ./examples
COPY tests ./tests
COPY scripts/smoke_test.py ./scripts/smoke_test.py
RUN useradd -m -u 1000 studio && mkdir -p /data && chown studio:studio /data
USER studio
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
