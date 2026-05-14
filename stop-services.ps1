param(
    [string]$BackendPort = $(if ($env:PORT) { $env:PORT } else { "9090" }),
    [string]$FrontendPort = $(if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3000" }),
    [string]$OllamaPort = "11434",
    [string]$EmbeddingPort = $(if ($env:EMBEDDING_PORT) { $env:EMBEDDING_PORT } else { "8080" }),
    [string]$EmbeddingContainerName = $(if ($env:EMBEDDING_CONTAINER) { $env:EMBEDDING_CONTAINER } else { "harrier-embed" }),
    [switch]$StopOllama,
    [switch]$StopEmbedding
)

$ErrorActionPreference = "SilentlyContinue"

Write-Output "Stopping RAGv3 development services..."
Write-Output "  Stops backend/frontend ports by default."
Write-Output "  Pass -StopEmbedding to stop/remove the Harrier TEI container."
Write-Output "  Pass -StopOllama to stop Ollama."

function Stop-ProcessOnPort {
    param(
        [string]$Port,
        [string]$Label
    )

    $connections = Get-NetTCPConnection -LocalPort ([int]$Port) -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Output "  $Port ($Label): already stopped"
        return
    }

    foreach ($connection in $connections) {
        $proc = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { "unknown" }
        if ($proc) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Output "  $Port ($Label): stopped $procName (PID $($proc.Id))"
        }
    }
}

Stop-ProcessOnPort $BackendPort "Backend"
Stop-ProcessOnPort $FrontendPort "Frontend"

if ($StopEmbedding) {
    docker stop $EmbeddingContainerName 2>&1 | Out-Null
    docker rm $EmbeddingContainerName 2>&1 | Out-Null
} elseif (Get-NetTCPConnection -LocalPort ([int]$EmbeddingPort) -ErrorAction SilentlyContinue) {
    Write-Output "  $EmbeddingPort (Harrier TEI): still running; pass -StopEmbedding to stop container $EmbeddingContainerName"
}

if ($StopOllama) {
    Stop-ProcessOnPort $OllamaPort "Ollama"
} elseif (Get-NetTCPConnection -LocalPort ([int]$OllamaPort) -ErrorAction SilentlyContinue) {
    Write-Output "  $OllamaPort (Ollama): still running; pass -StopOllama to stop it"
}

Start-Sleep -Seconds 1

$remaining = @{
    $BackendPort = "Backend"
    $FrontendPort = "Frontend"
}

foreach ($port in $remaining.Keys) {
    if (Get-NetTCPConnection -LocalPort ([int]$port) -ErrorAction SilentlyContinue) {
        Write-Output "  WARNING: Port $port ($($remaining[$port])) is still in use"
    }
}
