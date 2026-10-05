#!/usr/bin/env bash
set -euo pipefail
for name in cryptid-studio cryptid-kokoro cryptid-whisper cryptid-ollama cryptid-comfyui; do
  if docker container inspect "$name" >/dev/null 2>&1; then docker stop -t 20 "$name"; fi
done
echo 'Container arrestati. File e modelli non sono stati eliminati.'
