@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================
echo   Autonomous Research Agent -- Starting
echo ============================================

REM --- Sync .env to gateway's expected location ---------------------------
copy /Y ".env" "5e4a8833-292d-4ce5-be97-749c7656bdbf\.env" >nul

REM --- Start LLM Gateway V3 in a separate window --------------------------
echo [1/2] Starting LLM Gateway V3 on http://localhost:8101 ...
start "LLM-Gateway-V3" cmd /k "cd /d "%~dp05e4a8833-292d-4ce5-be97-749c7656bdbf\llm_gatewayV3" && python main.py"

REM --- Wait for gateway to be ready (poll port 8101) ----------------------
echo [2/2] Waiting for gateway to be ready...
:WAIT
timeout /t 2 /nobreak >nul
curl -s http://localhost:8101/v1/providers >nul 2>&1
if errorlevel 1 goto WAIT

echo.
echo  Gateway is UP at http://localhost:8101
echo  Dashboard  : http://localhost:8101
echo.
echo ============================================
echo   Ready. Example commands:
echo     python agent6.py "Find top causes of EV battery degradation"
echo     python agent6.py --remember "Tesla uses 4680 cells"
echo     python agent6.py "What did we learn about Tesla batteries?"
echo     python agent6.py --session
echo ============================================
echo.
endlocal
