@echo off
cd /d %~dp0
echo YiXiao Hospital Agent - multi-agent clinical decision platform
echo Set the DASHSCOPE_API_KEY environment variable first (qwen3.5-flash), or edit config.yaml
python web_server.py
pause
