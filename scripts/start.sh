#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v docker >/dev/null || { echo 'Installa e avvia Docker prima di continuare.' >&2; exit 1; }
docker info >/dev/null
mkdir -p "$ROOT/data"
[ -f .env ] || cp .env.example .env
if docker container inspect cryptid-studio >/dev/null 2>&1 && [ "${1:-}" != '--rebuild' ]; then
  docker start cryptid-studio >/dev/null
  echo 'AI Video Studio: http://localhost:7860 (dati conservati).'
  exit 0
fi
docker network inspect cryptid-net >/dev/null 2>&1 || docker network create cryptid-net >/dev/null
docker build -t cryptid-studio:1.0 .
if docker container inspect cryptid-studio >/dev/null 2>&1; then
  docker stop -t 20 cryptid-studio >/dev/null
  docker rm cryptid-studio >/dev/null
fi
docker run -d --name cryptid-studio --init --restart unless-stopped \
  --network cryptid-net --add-host host.docker.internal:host-gateway \
  -p 127.0.0.1:7860:8000 --env-file "$ROOT/.env" \
  --mount "type=bind,source=$ROOT/data,target=/data" \
  --user "$(id -u):$(id -g)" --memory=3g --cpus=2 \
  --cap-drop ALL --security-opt no-new-privileges \
  cryptid-studio:1.0 >/dev/null
echo 'AI Video Studio: http://localhost:7860'
echo "Dati persistenti: $ROOT/data"
