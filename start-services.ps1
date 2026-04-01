$ErrorActionPreference = "SilentlyContinue"

# Stop existing services
Stop-Process -Name "node" -Force
Stop-Process -Name "python" -Force
Stop-Process -Name "uvicorn" -Force
Stop-Process -Name "ollama" -Force
Start-Sleep -Seconds 3

# Start Ollama (hidden)
Start-Process "C:\Users\TMIPSA\AppData\Local\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden

# Start Backend (hidden)
Start-Process "C:\RAGv3\ragappv3\backend\venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8080" -WorkingDirectory "C:\RAGv3\ragappv3\backend" -WindowStyle Hidden

# Start Frontend (hidden)
Start-Process "npm" -ArgumentList "run","dev" -WorkingDirectory "C:\RAGv3\ragappv3\frontend" -WindowStyle Hidden

# Wait for services to start
Write-Output "Waiting for services to start..."
for ($i = 0; $i -lt 24; $i++) {
    Start-Sleep -Seconds 5
    $backend = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
    $frontend = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue
    if ($backend -and $frontend) { break }
    Write-Output "  Waiting... ($(($i+1)*5)s)"
}

# Verify
$ollama = if (Get-NetTCPConnection -LocalPort 11434 -ErrorAction SilentlyContinue) { "OK" } else { "DOWN" }
$backend = if (Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue) { "OK" } else { "DOWN" }
$frontend = if (Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue) { "OK" } else { "DOWN" }

Write-Output "=== Service Status ==="
Write-Output "  11434 (Ollama):    $ollama"
Write-Output "  8080  (Backend):   $backend"
Write-Output "  3001  (Frontend):  $frontend"

if ($ollama -eq "OK" -and $backend -eq "OK" -and $frontend -eq "OK") {
    Write-Output "ALL SERVICES RUNNING"
} else {
    Write-Output "WARNING: Some services failed to start"
}
