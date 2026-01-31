@echo off
echo Installing requirements...
python -m pip install pyinstaller pandas playwright requests opencv-python pillow openpyxl

echo Installing Playwright browsers...
python -m playwright install chromium

REM Extract version
for /f "delims=" %%i in ('python -c "from tandaiKirim import version; print(version)"') do set APP_VERSION=%%i
echo Detected Version: %APP_VERSION%


echo Building executable...
REM --add-data format for Windows is "src;dest". 
REM We put video in root of dist in exe (.;) or keep in data folder (data;data).
REM To match our app.py logic which checks root then data, we can just put it in root ".;".
REM But cleaner is to use data folder "data\Video...;data".
REM Let's put it in root of _MEIPASS via ".;." so it's easiest to find or "data\xx;."

python -m PyInstaller --noconfirm --onefile --windowed --name "MatchaProSender_v%APP_VERSION%" --collect-all tkinter --add-data "login.py;." --add-data "tandaiKirim.py;." --add-data "data\Video_Batu_Kertas_Gunting_Kalah_Tampar.mp4;." --hidden-import "pandas" --hidden-import "playwright.sync_api" --hidden-import "cv2" --hidden-import "PIL" app.py


echo Copying accounts.json if exists...
if exist accounts.json copy accounts.json dist\

echo.
echo Build complete. executable is in the 'dist' folder.
pause
