@echo off
chcp 65001 >nul
cd /d %~dp0
echo 医晓 Hospital Agent · 多智能体临床决策平台
echo 需要先配置环境变量 DASHSCOPE_API_KEY（qwen3.5-flash）
python web_server.py
pause
