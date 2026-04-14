@echo off
chcp 65001 >nul
echo.
echo ╔═══════════════════════════════════════════╗
echo ║   DS MACRO JUNGLE — 로컬 서버 시작        ║
echo ╚═══════════════════════════════════════════╝
echo.
cd /d "%~dp0"

echo [1/2] HTTP 서버 시작 (포트 8010)...
start "DS Macro HTTP Server" cmd /k "cd /d %~dp0 && python -m http.server 8010"

timeout /t 2 /nobreak >nul

echo [2/2] ngrok 터널 시작...
echo  (ngrok 창이 열리면 Forwarding 주소를 팀원들과 공유하세요)
echo.
start "DS Macro ngrok" cmd /k "ngrok http 8010"

timeout /t 5 /nobreak >nul

echo  ngrok 대시보드: http://localhost:4040
echo.
start http://localhost:4040
