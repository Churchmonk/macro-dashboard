@echo off
chcp 65001 >nul
echo.
echo ╔═══════════════════════════════════════════════════════╗
echo ║   DS MACRO JUNGLE — 작업 스케줄러 해제                ║
echo ╚═══════════════════════════════════════════════════════╝
echo.

schtasks /delete /tn "DS Macro Jungle Daily" /f
schtasks /delete /tn "DS Macro Jungle Weekly" /f
schtasks /delete /tn "DS Macro Jungle Monthly" /f
schtasks /delete /tn "DS Macro Jungle Monthly LPR" /f

echo.
echo ✅ 등록된 모든 매크로 대시보드 작업 해제 완료
echo.
pause
