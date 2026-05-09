@echo off
chcp 65001 >nul
cd /d E:\first_cc
echo ========================================
echo   店管家订单处理
echo   可选: dgj-1 / dgj-2 / dgj-3
echo   直接回车 = 全部三轮
echo ========================================
echo.
set /p ROUND="输入轮次 (留空=all): "
if "%ROUND%"=="" set ROUND=all
python -m order_automation.main --dgj-only --round %ROUND%
echo.
echo 执行完毕，按任意键关闭...
pause >nul
