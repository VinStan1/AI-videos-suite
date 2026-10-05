FROM python:3.12-slim-bookworm
ARG COMFY_REF=v0.3.76
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt
RUN git clone --depth 1 --branch "$COMFY_REF" https://github.com/Comfy-Org/ComfyUI.git ComfyUI
WORKDIR /opt/ComfyUI
RUN pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cpu
RUN printf 'torch==2.7.1\ntorchvision==0.22.1\ntorchaudio==2.7.1\n' > /tmp/torch-constraints.txt \
    && pip install --no-cache-dir -r requirements.txt -c /tmp/torch-constraints.txt
COPY services/comfyui/download_model.py /download_model.py
RUN useradd -u 1000 -m worker && chown -R worker:worker /opt/ComfyUI
USER worker
EXPOSE 8188
CMD ["python","main.py","--listen","0.0.0.0","--port","8188","--cpu","--disable-auto-launch"]
