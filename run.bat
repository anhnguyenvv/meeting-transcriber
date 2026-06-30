@echo off
chcp 65001 > nul 2>&1
title Meeting Transcriber
cd /d "%~dp0"

:: Kiem tra da cai dat chua
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo  [!] Chua cai dat! Vui long chay install.bat truoc.
    echo.
    echo  Double-click vao file install.bat de cai dat tu dong.
    echo.
    pause
    exit /b 1
)

:: Kiem tra .env
if not exist ".env" (
    echo.
    echo  [!] Chua co file .env - Dang chay wizard cau hinh...
    echo.
    call .venv\Scripts\activate.bat
    python setup_wizard.py
    goto :run
)

:run
call .venv\Scripts\activate.bat

:: Kiem tra Ollama
curl -s http://localhost:11434 > nul 2>&1
if %errorlevel% neq 0 (
    echo  [i] Dang khoi dong Ollama...
    start /b ollama serve > nul 2>&1
    timeout /t 3 /nobreak > nul
)

echo  [OK] Dang khoi dong Meeting Transcriber...
echo  [OK] Mo trinh duyet tai: http://localhost:7860
echo.
start "" http://localhost:7860

python app.py

:: Neu app dong
echo.
echo  App da dong. Nhan phim bat ky de thoat.
pause > nul
