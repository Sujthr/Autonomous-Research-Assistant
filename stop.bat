@echo off
echo.
echo ============================================
echo   Autonomous Research Agent -- Stopping
echo ============================================

REM --- Kill the gateway window by its title --------------------------------
echo Stopping LLM Gateway V3...
taskkill /FI "WINDOWTITLE eq LLM-Gateway-V3*" /T /F >nul 2>&1
if errorlevel 1 (
    echo   [!!] Gateway window not found -- may already be stopped.
) else (
    echo   [OK] Gateway stopped.
)

REM --- Kill any orphaned python processes running main.py or mcp_server.py
for /f "tokens=2" %%P in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH 2^>nul') do (
    wmic process where "ProcessId=%%~P" get CommandLine /value 2>nul | find "main.py" >nul && (
        taskkill /PID %%~P /F >nul 2>&1
    )
    wmic process where "ProcessId=%%~P" get CommandLine /value 2>nul | find "mcp_server.py" >nul && (
        taskkill /PID %%~P /F >nul 2>&1
    )
)

echo   [OK] All agent processes cleared.
echo ============================================
echo.
