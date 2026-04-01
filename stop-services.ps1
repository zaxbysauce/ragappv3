$ErrorActionPreference = "SilentlyContinue"

Write-Output "Stopping RAGv3 services..."

# Stop Frontend (node / vite)
Stop-Process -Name "node" -Force -ErrorAction SilentlyContinue

# Stop Backend (uvicorn / python)
Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "uvicorn" -Force -ErrorAction SilentlyContinue

# Stop Ollama
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

# Verify ports are freed
$ports = @{8080 = "Backend"; 3000 = "Frontend"; 11434 = "Ollama"}
$all_stopped = $true

foreach ($port in $ports.Keys) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Output "  WARNING: Port $port ($($ports[$port])) still in use"
        $all_stopped = $false
    } else {
        Write-Output "  $port ($($ports[$port])): STOPPED"
    }
}

if ($all_stopped) {
    Write-Output "ALL SERVICES STOPPED"
} else {
    Write-Output "WARNING: Some ports still in use - check for lingering processes"
}
