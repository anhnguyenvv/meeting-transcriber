@echo off
chcp 65001 > nul 2>&1
title Meeting Transcriber -- Cai dat tu dong
color 0A

:: ════════════════════════════════════════════════════════════
::  install.bat -- Cai dat tu dong cho Windows 11
::  Double-click de chay. Khong can biet lap trinh!
:: ════════════════════════════════════════════════════════════

cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo.
echo  +=======================================================+
echo  ^|        Meeting Transcriber -- Cai dat Windows        ^|
echo  ^|   Nhat  ^|  Anh  ^|  Viet  --  100%% chay local        ^|
echo  +=======================================================+
echo.
echo  Script nay se tu dong:
echo    [1] Kiem tra Python 3.11
echo    [2] Kiem tra Ollama (LLM runner)
echo    [3] Tao moi truong Python ao
echo    [4] Cai dat thu vien
echo    [5] Chay wizard chon model va cau hinh
echo.
pause

:: ── BUOC 1: Kiem tra Python ──────────────────────────────────────────────────
echo.
echo [1/4] Kiem tra Python...
echo -------------------------------------------------------

python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [!] Python chua duoc cai dat hoac chua co trong PATH.
    echo.
    echo  Lam theo cac buoc sau:
    echo    1. Mo trinh duyet, vao: https://www.python.org/downloads/
    echo    2. Tai file ".exe" moi nhat
    echo    3. Chay file vua tai -- QUAN TRONG: tich o "Add Python to PATH"
    echo    4. Sau khi cai xong, dong cua so nay va chay lai install.bat
    echo.
    echo  Muon tu dong cai qua winget khong?
    choice /C YN /M "Nhan Y de cai tu dong, N de tu cai thu cong"
    if !errorlevel! == 1 (
        echo.
        echo  Dang cai Python 3.11 qua winget...
        winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
        if !errorlevel! neq 0 (
            echo  [!] Cai tu dong that bai. Vui long cai tay tu python.org
            pause
            exit /b 1
        )
        :: Refresh PATH
        call refreshenv > nul 2>&1
        python --version > nul 2>&1
        if !errorlevel! neq 0 (
            echo  [!] Cai xong nhung van khong nhan dien duoc Python.
            echo      Khoi dong lai may tinh roi chay lai install.bat.
            pause
            exit /b 1
        )
    ) else (
        echo  Vui long cai Python roi chay lai script nay.
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  [OK] %PY_VER% da san sang

:: ── BUOC 2: Kiem tra Ollama ───────────────────────────────────────────────────
echo.
echo [2/4] Kiem tra Ollama...
echo -------------------------------------------------------

ollama --version > nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [!] Ollama chua duoc cai dat.
    echo.
    echo  Ollama la phan mem chay mo hinh AI (LLM) tren may ban.
    echo  Hoan toan mien phi!
    echo.
    echo  Lam theo cac buoc sau:
    echo    1. Mo trinh duyet, vao: https://ollama.com/download
    echo    2. Click "Download for Windows"
    echo    3. Chay file .exe vua tai, cai nhu phan mem binh thuong
    echo    4. Sau khi cai xong, dong cua so nay va chay lai install.bat
    echo.
    echo  Nhan phim bat ky de mo trang tai Ollama trong trinh duyet...
    pause > nul
    start https://ollama.com/download
    echo.
    echo  Sau khi cai Ollama xong, nhan phim bat ky de tiep tuc...
    pause > nul
    ollama --version > nul 2>&1
    if !errorlevel! neq 0 (
        echo  [!] Van khong tim thay Ollama. Vui long cai dat va thu lai.
        pause
        exit /b 1
    )
)

echo  [OK] Ollama da duoc cai dat

:: Kiem tra Ollama dang chay
curl -s http://localhost:11434 > nul 2>&1
if %errorlevel% neq 0 (
    echo  [i] Dang khoi dong Ollama...
    start /b ollama serve > nul 2>&1
    timeout /t 3 /nobreak > nul
)

:: ── BUOC 3: Tao moi truong Python ao ─────────────────────────────────────────
echo.
echo [3/4] Tao moi truong Python ao...
echo -------------------------------------------------------

if exist ".venv\Scripts\activate.bat" (
    echo  [OK] Moi truong ao da ton tai -- bo qua tao moi
) else (
    echo  Dang tao .venv ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [!] Khong tao duoc moi truong ao. Thu cai lai Python.
        pause
        exit /b 1
    )
    echo  [OK] Tao xong moi truong ao
)

:: Kich hoat
call .venv\Scripts\activate.bat
echo  [OK] Da kich hoat moi truong ao

:: ── BUOC 4: Cai thu vien Python ──────────────────────────────────────────────
echo.
echo [4/4] Cai dat thu vien Python (co the mat 5-10 phut)...
echo -------------------------------------------------------
echo  Dang tai va cai:
echo    - faster-whisper  (nhan dang giong noi)
echo    - pyannote.audio  (phan tach nguoi noi)
echo    - gradio          (giao dien web)
echo    - torch, sounddevice, ffmpeg, va nhieu thu vien khac
echo.

pip install --upgrade pip --quiet
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo  [!] Cai dat that bai.
    echo.
    echo  Thu giai phap:
    echo    - Dam bao may co ket noi internet
    echo    - Tat antivirus tam thoi va thu lai
    echo    - Hoac cai tay: pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo  [OK] Cai dat thu vien hoan tat!

:: ── BUOC 5: Chay wizard cau hinh ─────────────────────────────────────────────
echo.
echo +=======================================================+
echo ^|  Sap xong! Chay wizard chon model va cau hinh...     ^|
echo +=======================================================+
echo.
timeout /t 2 /nobreak > nul

python setup_wizard.py

if %errorlevel% neq 0 (
    echo.
    echo  [!] Wizard gap loi. Thu chay thu cong: python setup_wizard.py
)

echo.
echo  Cam on da su dung Meeting Transcriber!
echo  De chay app sau nay: double-click run.bat hoac file tren Desktop.
echo.
pause
