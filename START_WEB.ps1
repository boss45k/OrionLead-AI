# Start Web Frontend Only
# Run: .\START_WEB.ps1

Write-Host "Starting Web Frontend (port 3000)..." -ForegroundColor Cyan
Write-Host ""

cd web
npm start
