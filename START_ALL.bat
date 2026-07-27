@echo off
REM Quick Start Script - Backend + Frontend (Windows CMD version)
REM Run: START_ALL.bat

setlocal enabledelayedexpansion

echo ================================
echo   OrionLead AI
echo   Starting Backend ^& Web...
echo ================================
echo.

REM Create models directory if missing
if not exist "backend\models" (
    mkdir "backend\models"
    echo [OK] Created models directory
)

REM Start Backend
echo Starting Backend API (port 5000)...
start "Backend API" cmd /k "cd backend && python run.py"
timeout /t 3 /nobreak
echo [OK] Backend started

REM Create test user
echo Creating test user...
python -c "import sys; sys.path.insert(0, 'backend'); from app import create_app; from app.models.models import db, User; from werkzeug.security import generate_password_hash; app = create_app(); app.app_context().push(); user = User.query.filter_by(email='admin@example.com').first(); user or (User.query.filter_by(email='admin@example.com').delete(), db.session.commit(), db.session.add(User(email='admin@example.com', password_hash=generate_password_hash('admin123'), full_name='Admin User', company='Test Company', role='admin', is_active=True)), db.session.commit()); print('[OK] Test user ready')" 2>nul

echo.
echo Starting Web Frontend (port 3000)...
start "Web Frontend" cmd /k "cd web && npm start"

echo.
echo ================================
echo   SYSTEM RUNNING
echo ================================
echo.
echo Web:     http://localhost:3000
echo API:     http://localhost:5000
echo.
echo Login:
echo   Email:    admin@example.com
echo   Password: admin123
echo.
echo Close these windows to stop services
echo.
pause
