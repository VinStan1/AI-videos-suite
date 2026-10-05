param([Parameter(Mandatory=$true)][ValidateSet('voice','whisper','ollama','images')][string]$Service)
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
Set-Location $Root
function Docker-Checked { & docker @args; if ($LASTEXITCODE -ne 0) {throw "Errore Docker: $LASTEXITCODE"} }
Docker-Checked info | Out-Null
$networks=& docker network ls --format '{{.Name}}'
if ($networks -notcontains 'cryptid-net') {Docker-Checked network create cryptid-net | Out-Null}
$Names=@{voice='cryptid-kokoro';whisper='cryptid-whisper';ollama='cryptid-ollama';images='cryptid-comfyui'}
$Name=$Names[$Service]
$existing=& docker container ls -a --format '{{.Names}}'
if ($existing -contains $Name) {Docker-Checked start $Name | Out-Null}
else {
    switch ($Service) {
        'voice' {
            Docker-Checked run -d --name $Name --network cryptid-net --init --memory=4g --cpus=2 `
                -e USE_GPU=false -e OMP_NUM_THREADS=2 ghcr.io/remsky/kokoro-fastapi-cpu:v0.7.2 | Out-Null
        }
        'whisper' {
            Docker-Checked build -f services/whisper/Dockerfile -t cryptid-whisper:1.0 .
            Docker-Checked run -d --name $Name --network cryptid-net --init --memory=3g --cpus=2 `
                -v cryptid-whisper-models:/models cryptid-whisper:1.0 | Out-Null
        }
        'ollama' {
            Docker-Checked run -d --name $Name --network cryptid-net --init --memory=5g --cpus=2 `
                -v cryptid-ollama-models:/root/.ollama -e OLLAMA_KEEP_ALIVE=0 -e OLLAMA_NUM_PARALLEL=1 ollama/ollama:latest | Out-Null
        }
        'images' {
            Write-Host 'Servizio immagini CPU: dipendenze e modello pesanti. Sul PC leggero usa i caricamenti manuali.'
            Docker-Checked build -f services/comfyui/Dockerfile -t cryptid-comfyui:1.0 .
            Docker-Checked run -d --name $Name --network cryptid-net --init --memory=8g --cpus=2 `
                -v cryptid-comfy-models:/opt/ComfyUI/models cryptid-comfyui:1.0 | Out-Null
        }
    }
}
if ($Service -eq 'ollama') {
    for ($i=0;$i -lt 30;$i++) {& docker exec cryptid-ollama ollama list 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) {break}; Start-Sleep -Seconds 1}
    Docker-Checked exec cryptid-ollama ollama pull qwen2.5:3b
}
if ($Service -eq 'images') {Docker-Checked exec cryptid-comfyui python /download_model.py}
Write-Host "Servizio avviato: $Name. Aggiorna lo stato nell'interfaccia."
Write-Host "Log: docker logs -f $Name"
Write-Host "Per liberare RAM: docker stop $Name"
