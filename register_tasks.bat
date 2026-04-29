@echo off
chcp 65001 >nul
echo.
echo ╔═══════════════════════════════════════════════════════╗
echo ║   DS MACRO JUNGLE — Windows Task Scheduler 등록       ║
echo ╚═══════════════════════════════════════════════════════╝
echo.

set ROOT=%~dp0
set DAILY=%ROOT%update_daily.bat
set WEEKLY=%ROOT%update_weekly.bat
set MONTHLY=%ROOT%update_monthly.bat

echo [1/4] 매일 08:10 — DS Macro Jungle Daily
echo       (시장 마감 후 — VIX/금리/크레딧/인플레)
schtasks /create /tn "DS Macro Jungle Daily" /tr "\"%DAILY%\"" /sc daily /st 08:10 /f
echo.

echo [2/4] 매주 금요일 06:30 — DS Macro Jungle Weekly
echo       (Fed H.4.1 목요일 16:30 ET 발표 = 금요일 06:30 KST 직후)
schtasks /create /tn "DS Macro Jungle Weekly" /tr "\"%WEEKLY%\"" /sc weekly /d FRI /st 06:30 /f
echo.

echo [3/4] 매달 2일 09:00 — DS Macro Jungle Monthly
echo       (ISM PMI / NFP / 실업률 — 첫 영업일 발표 다음날)
schtasks /create /tn "DS Macro Jungle Monthly" /tr "\"%MONTHLY%\"" /sc monthly /d 2 /st 09:00 /f
echo.

echo [4/4] 매달 21일 11:00 — DS Macro Jungle Monthly LPR
echo       (중국 LPR 매달 20일 09:15 CST 발표 = 21일 KST 갱신)
schtasks /create /tn "DS Macro Jungle Monthly LPR" /tr "\"%MONTHLY%\"" /sc monthly /d 21 /st 11:00 /f
echo.

echo ═══════════════════════════════════════════════════════
echo   ✅ 작업 4개 등록 완료
echo ═══════════════════════════════════════════════════════
echo.
echo  현재 등록 상태:
schtasks /query /tn "DS Macro Jungle Daily" 2>nul | findstr /i "Daily Weekly Monthly"
schtasks /query /tn "DS Macro Jungle Weekly" 2>nul | findstr /i "Weekly"
schtasks /query /tn "DS Macro Jungle Monthly" 2>nul | findstr /i "Monthly"
schtasks /query /tn "DS Macro Jungle Monthly LPR" 2>nul | findstr /i "LPR"
echo.
echo  로그 위치: %ROOT%logs\
echo  해제하려면: unregister_tasks.bat 실행
echo.
pause
