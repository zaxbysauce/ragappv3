$ErrorActionPreference = "SilentlyContinue"

Write-Output "Stopping RAGv3 services..."

# Stop Frontend (node / vite)
Stop-Process -Name "node" -Force -ErrorAction SilentlyContinue

# Stop Backend (uvicorn / python)
Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "uvicorn" -Force -ErrorAction SilentlyContinue

# Stop Ollama
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
taskkill /F /IM ollama.exe >$null 2>&1

Start-Sleep -Seconds 3

# Verify ports are freed
$ports = @{9090 = "Backend"; 3000 = "Frontend"; 11434 = "Ollama"; 18080 = "FlagEmbed"}
$all_stopped = $true

foreach ($port in $ports.Keys) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) {
        # Find the owning process
        $owningPid = $conn.OwningProcess
        $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { "unknown" }
        $label = $ports[$port]
        Write-Output "  WARNING: Port $port ($label) held by $procName (PID $owningPid)"
        $all_stopped = $false
    } else {
        Write-Output "  $port ($($ports[$port])): STOPPED"
    }
}

if ($all_stopped) {
    Write-Output "ALL SERVICES STOPPED"
} else {
    Write-Output ""
    Write-Output "NOTE: Port 8080 may be held by Docker (Onyx) - run Docker Desktop to manage it"
    Write-Output "      Port 11434 is Ollama - it will auto-restart if set to run at login"
}
