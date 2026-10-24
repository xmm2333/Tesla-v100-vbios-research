@echo off
REM =====================================================================
REM  EXAMPLE ONLY - clears any VBIOS registry override and restores
REM  the GPU to its onboard physical stock VBIOS firmware.
REM  This wrapper assumes a VixLoader-style registry override.
REM =====================================================================
cd /d "%~dp0"

REM --- 1. self-elevate ---------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 1
)

REM --- 2. unload override via loader -----------------------------------
echo [*] Unloading registry VBIOS override...
call "%~dp0vix_loader.bat" unload --gpu 0 --no-restart
if %errorLevel% neq 0 (
    echo [NOTE] Loader returned exit code %errorLevel%, cleaning registry manually...
)

REM --- 3. clean residual override keys -----------------------------------
set "GPU_KEY=HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000"
reg delete "%GPU_KEY%" /v EnableGpuFirmware /f >nul 2>&1
reg delete "%GPU_KEY%" /v vbios /f >nul 2>&1
reg delete "%GPU_KEY%" /v VixLoaderPreviousEnableGpuFirmware /f >nul 2>&1
reg delete "%GPU_KEY%" /v RomOverride /f >nul 2>&1

REM --- 4. reset clocks to hardware defaults -----------------------------
nvidia-smi -rac >nul 2>&1
nvidia-smi -rgc >nul 2>&1

REM --- 5. reboot --------------------------------------------------------
echo.
echo [*] Override cleared successfully.
echo [*] Rebooting in 8 seconds to reload physical onboard firmware...
shutdown /r /t 8 /c "Reboot to reload physical stock VBIOS"
exit /b 0
