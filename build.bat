@echo off
echo Installing requirements...
python -m pip install pyinstaller pandas playwright requests

echo Installing Playwright browsers...
python -m playwright install chromium

REM Extract version
for /f "delims=" %%i in ('python -c "from tandaiKirim import version; print(version)"') do set APP_VERSION=%%i
echo Detected Version: %APP_VERSION%

echo Building executable...
python -m PyInstaller --noconfirm --onefile --windowed --name "MatchaProSender_v%APP_VERSION%" --collect-all tkinter --add-data "login.py;." --add-data "tandaiKirim.py;." --hidden-import "pandas" --hidden-import "playwright.sync_api" app.py

echo.
echo Build complete. executable is in the 'dist' folder.
pause
