@echo off
chcp 936 >nul
title 传统古色 · 3D 博物馆 —— 本地服务器
cd /d "%~dp0"

echo ============================================
echo   传统古色 · 3D 博物馆   本地服务器
echo ============================================
echo.

rem ---- 8899 端口已在监听就只开浏览器，不重复启动 ----
netstat -ano | findstr ":8899" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 goto already

rem ---- 找 Python：PATH 里的 python 优先，其次 py 启动器 ----
set "PY=python"
where python >nul 2>&1 || set "PY=py"
where %PY% >nul 2>&1
if errorlevel 1 goto nopython

echo   正在启动本地服务器，稍后浏览器会自动打开...
echo.

start /b "" %PY% "%~dp0tools\serve.py" 8899

rem ---- 等服务器就绪（约 2 秒）----
ping -n 3 127.0.0.1 >nul

start "" "http://127.0.0.1:8899/?v=%RANDOM%"

echo.
echo   入口已开:  http://127.0.0.1:8899
echo   若浏览器没有自动打开，请手动访问上面的地址。
echo   关闭本窗口即停止服务器。
echo.
pause
exit /b

:already
echo   8899 端口已在运行，直接打开浏览器...
start "" "http://127.0.0.1:8899/?v=%RANDOM%"
echo.
echo   入口已开:  http://127.0.0.1:8899
echo   关闭本窗口不会停止已在运行的服务器。
echo.
echo   若页面仍是旧版，请在那个标签页按 Ctrl+F5 强制刷新。
pause
exit /b

:nopython
echo   [x] 没有找到 Python（python / py 都不在 PATH 里）。
echo       本项目只需要一个静态服务器，装好 Python 后重新双击本文件即可；
echo       或在本目录手动执行:  python -m http.server 8899 --bind 127.0.0.1
echo.
pause
exit /b
