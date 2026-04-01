@echo off
color 0A
title Safe 6ix - Toronto

echo.
echo ========================================================================
echo                          SAFE 6IX - TORONTO
echo                   Pedestrian Safety Route Planner
echo ========================================================================
echo.

REM -----------------------------------------------------------------------
REM STEP 1: Check required software
REM -----------------------------------------------------------------------

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.9+ from https://www.python.org/
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 16+ from https://nodejs.org/
    pause
    exit /b 1
)

npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Reinstall Node.js from https://nodejs.org/
    pause
    exit /b 1
)

echo  Python, Node.js, and npm found!
echo.

REM -----------------------------------------------------------------------
REM STEP 2: Backend setup (first time only)
REM -----------------------------------------------------------------------

cd "%~dp0backend"

if not exist "venv\" (
    echo  First-time setup: Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  Virtual environment created!
    echo.
)

echo  Activating virtual environment and installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies. Check your internet connection.
    pause
    exit /b 1
)
echo  Backend dependencies ready!
echo.

REM -----------------------------------------------------------------------
REM STEP 3: Frontend setup (first time only)
REM -----------------------------------------------------------------------

cd "%~dp0frontend"

if not exist "node_modules\" (
    echo  First-time setup: Installing frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Failed to install Node.js dependencies. Check your internet connection.
        pause
        exit /b 1
    )
    echo  Frontend dependencies installed!
    echo.
)

cd "%~dp0"

REM -----------------------------------------------------------------------
REM STEP 4: Check .env file
REM -----------------------------------------------------------------------

if not exist ".env" (
    echo  No .env file found. Let's set up your API keys.
    echo.
    echo  You need a GraphHopper API key (free):
    echo    1. Go to https://www.graphhopper.com/
    echo    2. Sign up for a free account
    echo    3. Copy your API key from the dashboard
    echo.
    set /p "GRAPHHOPPER_KEY=Enter your GraphHopper API Key: "
    echo.
    (
        echo GRAPHHOPPER_API_KEY=%GRAPHHOPPER_KEY%
        echo BACKEND_PORT=8000
        echo FRONTEND_URL=http://localhost:3000
        echo DATA_REFRESH_INTERVAL=60
    ) > .env
    echo  .env file created!
    echo.
)

REM -----------------------------------------------------------------------
REM STEP 5: Launch backend and frontend
REM -----------------------------------------------------------------------

echo  Starting Safe 6ix...
echo.
echo  This will open TWO windows:
echo    1. Backend Server  (http://localhost:8000)
echo    2. Frontend App    (http://localhost:3000)
echo.
echo  Keep both windows open while using the app.
echo  To stop: press Ctrl+C in each window, or just close them.
echo.
pause

echo.
echo  [1/2] Starting backend...
start "Safe 6ix Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate && set PYTHONIOENCODING=utf-8 && set PYTHONUTF8=1 && cd app && python -X utf8 -m uvicorn main:app --port 8000"

echo  Waiting for backend to initialize...
timeout /t 8 /nobreak >nul

echo  [2/2] Starting frontend...
start "Safe 6ix Frontend" cmd /k "cd /d "%~dp0frontend" && npm start"

echo.
echo ========================================================================
echo.
echo   Backend:   http://localhost:8000
echo   Frontend:  http://localhost:3000
echo.
echo ========================================================================
echo.

timeout /t 5 /nobreak >nul
start http://localhost:3000

echo  This window can be closed. Keep the server windows open!
echo.
pause
