@echo off
REM =====================================================================
REM  EXAMPLE ONLY - replace YOUR_ROM.rom with your own image.
REM  This wrapper assumes a VixLoader-style registry override; adapt the
REM  loader call to whatever mechanism you actually use.
REM =====================================================================
cd /d "%~dp0"

REM --- 1. self-elevate ---------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 1
)

REM --- 2. sanity check --------------------------------------------------
if not exist "%~dp0YOUR_ROM.rom" (
    echo [ERROR] YOUR_ROM.rom not found next to this script.
    pause
    exit /b 1
)

REM --- 3. load the override --------------------------------------------
call "%~dp0vix_loader.bat" load "%~dp0YOUR_ROM.rom" --gpu 0 --no-restart
if %errorLevel% neq 0 (
    echo [ERROR] loader failed with exit code %errorLevel%
    pause
    exit /b 1
)

REM --- 4. make sure the override survives a fast-startup boot -----------
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f >nul 2>&1

REM --- 5. reboot --------------------------------------------------------
echo.
echo [*] Rebooting in 8 seconds...  (keep your restore script handy)
shutdown /r /t 8 /c "Reboot to apply the VBIOS override"
exit /b 0
