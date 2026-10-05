#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SERVICE="${1:-}"
case "$SERVICE" in voice|whisper|ollama|images) ;; *) echo 'Uso: bash scripts/start-ai.sh voice|whisper|ollama|images'; exit 1;; esac
docker info >/dev/null
docker network inspect cryptid-net >/dev/null 2>&1 || docker network create cryptid-net >/dev/null
case "$SERVICE" in
 voice) NAME=cryptid-kokoro;; whisper) NAME=cryptid-whisper;; ollama) NAME=cryptid-ollama;; images) NAME=cryptid-comfyui;;
esac
if docker container inspect "$NAME" >/dev/null 2>&1; then
  docker start "$NAME" >/dev/null
else
  case "$SERVICE" in
    voice)
      docker run -d --name "$NAME" --network cryptid-net --init --memory=4g --cpus=2 \
        -e USE_GPU=false -e OMP_NUM_THREADS=2 ghcr.io/remsky/kokoro-fastapi-cpu:v0.7.2 >/dev/null ;;
    whisper)
      docker build -f services/whisper/Dockerfile -t cryptid-whisper:1.0 .
      docker run -d --name "$NAME" --network cryptid-net --init --memory=3g --cpus=2 \
        -v cryptid-whisper-models:/models cryptid-whisper:1.0 >/dev/null ;;
    ollama)
      docker run -d --name "$NAME" --network cryptid-net --init --memory=5g --cpus=2 \
        -v cryptid-ollama-models:/root/.ollama -e OLLAMA_KEEP_ALIVE=0 -e OLLAMA_NUM_PARALLEL=1 ollama/ollama:latest >/dev/null ;;
    images)
      echo 'Servizio immagini CPU: installazione e modelli pesanti. Per il PC leggero usa immagini caricate.'
      docker build -f services/comfyui/Dockerfile -t cryptid-comfyui:1.0 .
      docker run -d --name "$NAME" --network cryptid-net --init --memory=8g --cpus=2 \
        -v cryptid-comfy-models:/opt/ComfyUI/models cryptid-comfyui:1.0 >/dev/null ;;
  esac
fi
if [ "$SERVICE" = 'ollama' ]; then
  for i in $(seq 1 30); do
    if docker exec cryptid-ollama ollama list >/dev/null 2>&1; then break; fi
    sleep 1
  done
  docker exec cryptid-ollama ollama pull qwen2.5:3b
fi
if [ "$SERVICE" = 'images' ]; then docker exec cryptid-comfyui python /download_model.py; fi
echo "Servizio avviato: $NAME. Aggiorna lo stato nell'interfaccia."
echo "Log: docker logs -f $NAME"
echo "Per liberare RAM: docker stop $NAME"
