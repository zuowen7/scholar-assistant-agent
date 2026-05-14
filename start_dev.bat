@echo off
REM 清除代理环境变量，避免 httpx 导入卡住
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

REM 启动 Tauri 桌面端（使用脚本所在目录，无硬编码路径）
cd /d "%~dp0"
npx tauri dev