@echo off
chcp 65001 >nul
echo.
echo ╔═══════════════════════════════════════════╗
echo ║   DS MACRO JUNGLE — 데이터 업데이트       ║
echo ╚═══════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo [1/3] 실시간 데이터 수집 중...
python -X utf8 fetch_data.py
if errorlevel 1 (
    echo [오류] 데이터 수집 실패. 종료합니다.
    pause
    exit /b 1
)

echo.
echo [2/3] GitHub에 업데이트 푸시 중...
git add data.json
git commit -m "data: %date% %time:~0,5% KST 업데이트"
git push origin main

echo.
echo [3/3] 완료!
echo  대시보드 URL: 아래 GitHub Pages 주소 확인
git remote -v
echo.
pause
