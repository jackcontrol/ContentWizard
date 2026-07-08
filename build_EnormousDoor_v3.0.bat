@echo off
setlocal ENABLEDELAYEDEXPANSION
cd /d C:\ContentWizard

echo.
echo ============================================================
echo  ENORMOUS DOOR CONTENT WIZARD -- Build v3.0.0-optimized
echo ============================================================
echo.

REM ── Step 1: Find the Python file (handle renamed/numbered copies) ──
set PYFILE=
for %%f in (*.py) do (
    findstr /C:"3.0.0-optimized" "%%f" >nul 2>nul
    if not errorlevel 1 set PYFILE=%%f
)

if "%PYFILE%"=="" (
    echo ERROR: Could not find EnormousDoorContentWizard.py ^(v3.0.0-optimized^)
    echo        in C:\ContentWizard
    echo.
    echo Files found in this folder:
    dir /b *.py 2>nul
    echo.
    echo Copy EnormousDoorContentWizard.py here and try again.
    pause & exit /b 1
)

echo [OK] Found source file: %PYFILE%

REM ── Rename to standard name if needed ─────────────────────────────
if /i not "%PYFILE%"=="EnormousDoorContentWizard.py" (
    echo     Renaming "%PYFILE%" to EnormousDoorContentWizard.py ...
    ren "%PYFILE%" EnormousDoorContentWizard.py
    echo [OK] Renamed.
)

REM ── Step 2: Python ────────────────────────────────────────────────
where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python launcher ^(py^) not found. Install Python 3.11 from python.org.
    pause & exit /b 1
)
echo [OK] Python launcher found.

REM ── Step 3: Dependencies ─────────────────────────────────────────
echo.
echo Installing / updating dependencies...
py -3.11 -m pip install --upgrade pip --quiet
py -3.11 -m pip install pillow numpy moviepy imageio imageio-ffmpeg proglog decorator tkinterdnd2 pytesseract pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause & exit /b 1
)
echo [OK] Dependencies ready.

REM ── Step 4: Clean ────────────────────────────────────────────────
echo Cleaning previous build...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo [OK] Clean.

REM ── Step 5: PyInstaller ──────────────────────────────────────────
echo.
echo Building EXE...
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
    echo ERROR: Build failed. See output above for details.
    pause & exit /b 1
)

REM ── Step 6: Copy support files ───────────────────────────────────
if exist release_notes.txt         copy /Y release_notes.txt         "dist\EnormousDoorContentWizard\release_notes.txt" >nul
if exist requirements_windows_build.txt copy /Y requirements_windows_build.txt "dist\EnormousDoorContentWizard\requirements_windows_build.txt" >nul

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  EXE location:
echo  C:\ContentWizard\dist\EnormousDoorContentWizard\
echo      EnormousDoorContentWizard.exe
echo ============================================================
pause
