$ErrorActionPreference = "SilentlyContinue"

# Stop existing services
Stop-Process -Name "node" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "uvicorn" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Start Ollama (hidden)
Start-Process "C:\Users\TMIPSA\AppData\Local\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden

# Start FlagEmbed container (embedding + reranking on GPU)
$flagEmbedExists = docker ps --format "{{.Names}}" 2>&1 | Select-String -SimpleMatch "flag-embed"
if (-not $flagEmbedExists) {
    Write-Output "Starting FlagEmbed container (embedding + reranking)..."
    docker run -d --name flag-embed --gpus all -p 18080:18080 `
        -v C:\Users\TMIPSA\.cache\huggingface\hub:/root/.cache/huggingface/hub `
        flag-embed:latest 2>&1 | Out-Null
} else {
    Write-Output "FlagEmbed container already running"
}

# Start Backend (hidden)
Start-Process "C:\RAGv3\ragappv3\backend\venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","9090" -WorkingDirectory "C:\RAGv3\ragappv3\backend" -WindowStyle Hidden

# Start Frontend (hidden)
# Use cmd /c to avoid npm .cmd being opened in Notepad by Start-Process
Start-Process cmd -ArgumentList "/c","npm run dev" -WorkingDirectory "C:\RAGv3\ragappv3\frontend" -WindowStyle Hidden

# Wait for services to start
Write-Output "Waiting for services to start..."
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 5
    $backend = Get-NetTCPConnection -LocalPort 9090 -ErrorAction SilentlyContinue
    $frontend = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
    if ($backend -and $frontend) { break }
    Write-Output "  Waiting... ($(($i+1)*5)s)"
}

# Verify
$ollama = if (Get-NetTCPConnection -LocalPort 11434 -ErrorAction SilentlyContinue) { "OK" } else { "DOWN" }
$backend = if (Get-NetTCPConnection -LocalPort 9090 -ErrorAction SilentlyContinue) { "OK" } else { "DOWN" }
$frontend = if (Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue) { "OK" } else { "DOWN" }
$flagembed = if (Get-NetTCPConnection -LocalPort 18080 -ErrorAction SilentlyContinue) { "OK" } else { "DOWN" }

Write-Output "=== Service Status ==="
Write-Output "  11434 (Ollama):      $ollama"
Write-Output "  18080 (FlagEmbed):   $flagembed"
Write-Output "  9090  (Backend):     $backend"
Write-Output "  3000  (Frontend):    $frontend"

if ($ollama -eq "OK" -and $backend -eq "OK" -and $frontend -eq "OK") {
    Write-Output "ALL SERVICES RUNNING"
    if ($flagembed -ne "OK") {
        Write-Output "NOTE: FlagEmbed still loading models - give it another 60-90s"
    }
} else {
    Write-Output "WARNING: Some services failed to start"
}
