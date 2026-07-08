@echo off
setlocal ENABLEDELAYEDEXPANSION
cd /d C:\ContentWizard

echo.
echo ============================================================
echo  ENORMOUS DOOR CONTENT WIZARD -- Build v2.0.0-viral-ux
echo ============================================================
echo.

if not exist "EnormousDoorContentWizard.py" (
  echo ERROR: EnormousDoorContentWizard.py not found in C:\ContentWizard
  echo Make sure the file is placed directly in C:\ContentWizard before running.
  pause & exit /b 1
)
findstr /C:"2.0.0-viral-ux" "EnormousDoorContentWizard.py" >nul
if errorlevel 1 (
  echo ERROR: Source file is not v2.0.0-viral-ux.
  echo Place the correct EnormousDoorContentWizard.py in C:\ContentWizard.
  pause & exit /b 1
)
where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python launcher not found. Install Python 3.11 from python.org.
  pause & exit /b 1
)

echo [OK] Source file verified: v2.0.0-viral-ux
echo.
echo Installing dependencies...
py -3.11 -m pip install --upgrade pip --quiet
py -3.11 -m pip install pillow numpy moviepy imageio imageio-ffmpeg proglog decorator tkinterdnd2 pytesseract pyinstaller --quiet
if errorlevel 1 (
  echo ERROR: pip install failed. Check your internet connection.
  pause & exit /b 1
)
echo [OK] Dependencies ready.

echo Cleaning previous build...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo [OK] Clean.

echo.
echo Building EXE with PyInstaller...
py -3.11 -m PyInstaller ^
  --noconfirm --onedir --windowed ^
  --name EnormousDoorContentWizard ^
  --hidden-import tkinterdnd2 ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageTk ^
  --collect-submodules moviepy ^
  --collect-submodules imageio ^
  --collect-submodules imageio_ffmpeg ^
  --collect-submodules proglog ^
  --collect-submodules decorator ^
  --copy-metadata moviepy ^
  --copy-metadata imageio ^
  --copy-metadata imageio_ffmpeg ^
  --copy-metadata proglog ^
  --copy-metadata decorator ^
  EnormousDoorContentWizard.py

if errorlevel 1 (
  echo.
  echo Build failed. Review the output above for details.
  pause & exit /b 1
)

if exist release_notes.txt              copy /Y release_notes.txt              "dist\EnormousDoorContentWizard\release_notes.txt"              >nul
if exist requirements_windows_build.txt copy /Y requirements_windows_build.txt "dist\EnormousDoorContentWizard\requirements_windows_build.txt" >nul

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  EXE: C:\ContentWizard\dist\EnormousDoorContentWizard\
echo            EnormousDoorContentWizard.exe
echo ============================================================
pause
