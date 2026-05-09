@echo off
chcp 65001 >nul
cd /d E:\first_cc
echo ========================================
echo   抖店订单处理
echo   可选: dy-1 / dy-2
echo   直接回车 = 全部两轮
echo ========================================
echo.
set /p ROUND="输入轮次 (留空=all): "
if "%ROUND%"=="" set ROUND=all
python -m order_automation.main --douyin-only --round %ROUND%
echo.
echo 执行完毕，按任意键关闭...
pause >nul
