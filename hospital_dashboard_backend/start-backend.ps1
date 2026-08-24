$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = "E:\Linux\anaconda\envs\fastapi\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[ERROR] FastAPI Python environment not found: $python" -ForegroundColor Red
    Write-Host "Update the Python path in this script or configure the fastapi Conda environment."
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Hospital medicine transport backend" -ForegroundColor Cyan
Write-Host "Working directory: $PSScriptRoot"
Write-Host "Python:            $python"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[HTTP API]       http://127.0.0.1:8080"
Write-Host "[API docs]       http://127.0.0.1:8080/docs"
Write-Host "[Elevator TCP]   0.0.0.0:10833"
Write-Host "[Elevator UDP]   0.0.0.0:10832"
Write-Host "[Car 1]          HIS Sender + ROS Listener"
Write-Host "[Car 2]          HIS Sender + ROS Listener"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting; press Ctrl+C to stop all backend services." -ForegroundColor Yellow

$listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    Write-Host "[INFO] HTTP port 8080 is already in use by PID $($listener.OwningProcess) ($($process.ProcessName))." -ForegroundColor Yellow
    Write-Host "The backend may already be running. Open http://127.0.0.1:8080/docs"
    exit 0
}

& $python -c "import fastapi, uvicorn, requests, pymysql"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Missing backend dependencies. Run: $python -m pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

& $python ".\app.py"