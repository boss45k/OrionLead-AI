# Quick Start Script - Backend + Frontend
# Run: .\START_ALL.bat

Write-Host "================================" -ForegroundColor Cyan
Write-Host "  OrionLead AI" -ForegroundColor Cyan
Write-Host "  Starting Backend & Web..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Create models directory if missing
$modelsDir = ".\backend\models"
if (-not (Test-Path $modelsDir)) {
    New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
    Write-Host "✓ Created models directory" -ForegroundColor Green
}

# Start Backend in background
Write-Host "Starting Backend API (port 5000)..." -ForegroundColor Yellow
$backendProcess = Start-Process powershell -ArgumentList "-NoExit -Command `"cd $pwd\backend; python run.py`"" -PassThru
$backendPID = $backendProcess.Id
Write-Host "✓ Backend started (PID: $backendPID)" -ForegroundColor Green

# Wait for backend to initialize
Write-Host "Waiting for backend to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Create test user
Write-Host "Creating test user..." -ForegroundColor Yellow
$testUserScript = @"
import sys
sys.path.insert(0, '$pwd\backend')
from app import create_app
from app.models.models import db, User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    user = User.query.filter_by(email='admin@example.com').first()
    if not user:
        user = User(
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            full_name='Admin User',
            company='Test Company',
            role='admin',
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
        print('✓ Test user created')
    else:
        print('✓ Test user already exists')
"@

$testUserScript | python 2>&1 | ForEach-Object { Write-Host $_ -ForegroundColor Green }

# Start Web Frontend
Write-Host ""
Write-Host "Starting Web Frontend (port 3000)..." -ForegroundColor Yellow
$webProcess = Start-Process powershell -ArgumentList "-NoExit -Command `"cd $pwd\web; npm start`"" -PassThru
$webPID = $webProcess.Id
Write-Host "✓ Web started (PID: $webPID)" -ForegroundColor Green

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  SYSTEM RUNNING" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "📱 Web:     http://localhost:3000" -ForegroundColor Cyan
Write-Host "🔌 API:     http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Login Credentials:" -ForegroundColor Yellow
Write-Host "  Email:    admin@example.com" -ForegroundColor Yellow
Write-Host "  Password: admin123" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Gray
Write-Host ""

# Wait for processes
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
catch {
    Write-Host "Stopping services..." -ForegroundColor Yellow
    Stop-Process -Id $backendPID -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $webPID -Force -ErrorAction SilentlyContinue
    Write-Host "All services stopped" -ForegroundColor Green
}
