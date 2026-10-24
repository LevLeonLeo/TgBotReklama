@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python не найден. Установите Python 3.12+ с python.org
    echo и при установке включите "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo.
    echo Создан файл .env. Заполните BOT_TOKEN и ADMIN_IDS и запустите снова.
    echo.
    pause
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo Не удалось создать .venv.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
python -m pip install -q -r requirements.txt
python run.py
pause
