@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo Python environment missing. Run the first-install script first.
  pause
  exit /b 1
)

"venv\Scripts\python.exe" -m pip install --disable-pip-version-check --cache-dir "build\pip-cache" -r requirements-build.txt
if errorlevel 1 goto failed

"venv\Scripts\python.exe" scripts\build_exe.py
if errorlevel 1 goto failed

echo.
echo Ready: dist\WeChat-To-Feishu.exe
pause
exit /b 0

:failed
echo.
echo Build failed. See the error above.
pause
exit /b 1
