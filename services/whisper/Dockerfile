FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 WHISPER_MODEL=base CPU_THREADS=2 HF_HOME=/models/hf OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY services/whisper/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/whisper/server.py ./
RUN useradd -u 1000 -m worker && mkdir /models && chown worker:worker /models
USER worker
EXPOSE 8000
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8000","--workers","1"]
