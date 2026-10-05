$ErrorActionPreference = 'Stop'
$existing = & docker container ls -a --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker non disponibile.' }
foreach ($name in @('cryptid-studio','cryptid-kokoro','cryptid-whisper','cryptid-ollama','cryptid-comfyui')) {
    if ($existing -contains $name) {
        & docker stop -t 20 $name
        if ($LASTEXITCODE -ne 0) { throw "Arresto non riuscito: $name" }
    }
}
Write-Host 'Container arrestati. File e modelli non sono stati eliminati.'
