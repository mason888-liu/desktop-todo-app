@echo off
chcp 65001 >nul
cd /d E:\first_cc
echo ========================================
echo   店管家 + 抖店 订单处理自动化（全流程）
echo ========================================
echo.
python -m order_automation.main --round all
echo.
echo 执行完毕，按任意键关闭...
pause >nul
