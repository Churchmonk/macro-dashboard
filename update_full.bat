@echo off
chcp 65001 >nul
cd /d "%~dp0"

set LOG=%~dp0logs\full.log
if not exist "%~dp0logs" mkdir "%~dp0logs"

echo. >> "%LOG%"
echo === FULL %date% %time% === >> "%LOG%"

python -X utf8 fetch_data.py --full >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [FULL] fetch 실패 — %date% %time% >> "%LOG%"
    exit /b 1
)

git diff --quiet data.json
if errorlevel 1 (
    git add data.json >> "%LOG%" 2>&1
    git commit -m "data(full): %date% %time:~0,5% KST" >> "%LOG%" 2>&1
    git push origin main >> "%LOG%" 2>&1
    echo [FULL] git push 완료 >> "%LOG%"
) else (
    echo [FULL] data.json 변경 없음 - skip >> "%LOG%"
)
