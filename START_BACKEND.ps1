# Start Backend Only
# Run: .\START_BACKEND.ps1

Write-Host "Starting Backend API (port 5000)..." -ForegroundColor Cyan
Write-Host ""

cd backend
python run.py
