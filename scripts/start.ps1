param([switch]$Rebuild)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
function Docker-Checked {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker ha restituito un errore ($LASTEXITCODE)." }
}
Docker-Checked info | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'data') | Out-Null
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
$existing = & docker container ls -a --format '{{.Names}}'
if (($existing -contains 'cryptid-studio') -and -not $Rebuild) {
    Docker-Checked start cryptid-studio | Out-Null
    Write-Host 'AI Video Studio: http://localhost:7860 (dati conservati).'
    exit 0
}
$networks = & docker network ls --format '{{.Name}}'
if ($networks -notcontains 'cryptid-net') { Docker-Checked network create cryptid-net | Out-Null }
Docker-Checked build -t cryptid-studio:1.0 .
if ($existing -contains 'cryptid-studio') {
    Docker-Checked stop -t 20 cryptid-studio | Out-Null
    Docker-Checked rm cryptid-studio | Out-Null
}
$Data = Join-Path $Root 'data'
Docker-Checked run -d --name cryptid-studio --init --restart unless-stopped `
    --network cryptid-net --add-host host.docker.internal:host-gateway `
    -p '127.0.0.1:7860:8000' --env-file (Join-Path $Root '.env') `
    --mount "type=bind,source=$Data,target=/data" --memory=3g --cpus=2 `
    --cap-drop ALL --security-opt no-new-privileges cryptid-studio:1.0 | Out-Null
Write-Host 'AI Video Studio: http://localhost:7860'
Write-Host "Dati persistenti: $Data"
