@echo off
rem ============================================
rem  CDS GUI - one-click build script
rem  Run by double-clicking, or:  .\build.bat
rem  Output: dist\gui\  (gui.exe + deps + templates)
rem ============================================

echo [1/3] Checking PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo     PyInstaller not found, installing...
    pip install pyinstaller
)

echo [2/3] Cleaning old build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist gui.spec.manifest del /q gui.spec.manifest 2>nul

echo [3/3] Building with PyInstaller (onedir mode)...
python -m PyInstaller --noconfirm gui.spec

if errorlevel 1 (
    echo.
    echo Build FAILED. See errors above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  BUILD OK!
echo  Output folder: dist\gui\
echo    - dist\gui\gui.exe    main program
echo    - dist\gui\templates\ Visio template files
echo  Copy the whole dist\gui folder to another
echo  machine and run gui.exe (no Python needed).
echo ============================================
pause
