@echo off
chcp 65001 >nul
cd /d "%~dp0"

set LOG=%~dp0logs\monthly.log
if not exist "%~dp0logs" mkdir "%~dp0logs"

echo. >> "%LOG%"
echo === MONTHLY %date% %time% === >> "%LOG%"

python -X utf8 fetch_data.py --monthly >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [MONTHLY] fetch 실패 — %date% %time% >> "%LOG%"
    exit /b 1
)

git diff --quiet data.json
if errorlevel 1 (
    git add data.json >> "%LOG%" 2>&1
    git commit -m "data(monthly): %date% %time:~0,5% KST" >> "%LOG%" 2>&1
    git push origin main >> "%LOG%" 2>&1
    echo [MONTHLY] git push 완료 >> "%LOG%"
) else (
    echo [MONTHLY] data.json 변경 없음 - skip >> "%LOG%"
)
