@echo off
setlocal
cd /d "%~dp0"

if not exist "app_feishu.py" goto noapp

rem ------------------------------------------------------------------
rem 第 1 步没跑过？自动补上，别让用户自己找
rem ------------------------------------------------------------------
if not exist "venv\Scripts\pythonw.exe" (
  echo.
  echo ============================================================
  echo  还没装运行环境，先自动执行「第 1 步 / 首次安装」
  echo  装完会自动回到这里，不用手动再点一次。
  echo ============================================================
  echo.
  call "%~dp01-首次安装.bat"
)

if not exist "venv\Scripts\pythonw.exe" goto novenv

start "" "venv\Scripts\pythonw.exe" "app_feishu.py"
exit /b 0

:novenv
echo.
echo   [错误] 运行环境仍然不存在，首次安装没有成功。
echo          请先双击 1-首次安装.bat，看它报什么错。
echo.
pause
exit /b 1

:noapp
echo.
echo   [错误] 没找到 app_feishu.py。
echo          请把本脚本放在仓库根目录下运行。
echo.
pause
exit /b 1
