@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  第 1 步 / 首次安装    微信记录 -^> 飞书多维表格
echo ============================================================
echo.
echo  这个步骤会：
echo    - 找一个 Python 3.12（找不到会用 uv 自动下载）
echo    - 建一个独立的 Python 环境 venv\
echo    - 装好导出和界面需要的依赖
echo.
echo  只需要跑一次。装完之后，以后日常只要双击
echo  「2-启动飞书版.bat」。
echo.
echo ------------------------------------------------------------
echo.

if not exist "app.py" goto nosrc
if not exist "requirements.txt" goto nosrc

rem ------------------------------------------------------------------
rem 已经装过了？直接进自检，不重复下载
rem ------------------------------------------------------------------
if exist "venv\Scripts\pythonw.exe" (
  echo [跳过安装] 发现已有的运行环境 venv\
  echo              想彻底重装，先删掉 venv 文件夹再跑本脚本。
  echo.
  goto verify
)

rem ------------------------------------------------------------------
rem 1) 找一个 Python 3.12
rem ------------------------------------------------------------------
set "PY="

rem 1a) uv 管理的解释器（Roaming / Local / XDG 三种布局）
for %%D in ("%APPDATA%\uv\python" "%LOCALAPPDATA%\uv\python" "%USERPROFILE%\.local\share\uv\python") do (
  if not defined PY if exist "%%~D" (
    for /d %%P in ("%%~D\cpython-3.12*") do (
      if not defined PY if exist "%%~P\python.exe" set "PY=%%~P\python.exe"
    )
  )
)

rem 1b) 直接问 uv
if not defined PY (
  where uv >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%V in ('uv python find 3.12 2^>nul') do (
      if not defined PY if exist "%%~V" set "PY=%%~V"
    )
  )
)

rem 1c) 老式 py 启动器
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%V in ('py -3.12 -c "import sys;print(sys.executable)" 2^>nul') do (
      if not defined PY if exist "%%~V" set "PY=%%~V"
    )
  )
)

rem 1d) PATH 里的 python，但必须确实真的是 3.12
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%V in ('python -c "import sys;print(sys.executable if sys.version_info[:2]==(3,12) else '')" 2^>nul') do (
      if not defined PY if exist "%%~V" set "PY=%%~V"
    )
  )
)

rem 1e) 还是没找到：有 uv 就让 uv 下 3.12
if not defined PY (
  where uv >nul 2>nul
  if not errorlevel 1 (
    echo   [下载] 本机没有 Python 3.12，用 uv 自动下载（约 30 MB）...
    uv python install 3.12
    for /f "delims=" %%V in ('uv python find 3.12 2^>nul') do (
      if not defined PY if exist "%%~V" set "PY=%%~V"
    )
  )
)
if not defined PY goto nopy

echo   [1/3] 使用 Python: %PY%
"%PY%" -m venv venv
if errorlevel 1 goto fail

rem ------------------------------------------------------------------
rem 2) 装核心依赖：uv 优先，pip 兜底，最后换国内镜像
rem ------------------------------------------------------------------
echo   [2/3] 安装核心依赖 ...
set "HAS_UV="
where uv >nul 2>nul
if not errorlevel 1 set "HAS_UV=1"

if defined HAS_UV (
  uv pip install --python "venv\Scripts\python.exe" -r requirements.txt
  if not errorlevel 1 goto installed
  echo   [提示] uv 安装失败，改用 pip 重试 ...
)

venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
if not errorlevel 1 goto installed

echo   [提示] 默认源失败，改用清华镜像重试 ...
venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto fail

:installed
echo   [3/3] 依赖安装完成。

rem ------------------------------------------------------------------
rem 3) 自检
rem ------------------------------------------------------------------
:verify
echo.
echo   [自检] 检查 Python / tkinter / 核心依赖 ...
venv\Scripts\python.exe -B -c "import tkinter, zstandard, PIL, psutil, imageio_ffmpeg, wechatauto; print('         [OK] all modules importable')"
if errorlevel 1 goto verifyfail

echo.
echo ============================================================
echo  第 1 步完成，接下来：
echo ============================================================
echo.
echo    2-启动飞书版.bat      日常用这个：导出 + 飞书导入
echo    3-启动飞书配置.bat    只想配飞书凭证时用
echo.
echo  可选：
echo    可选-安装语音识别.bat  语音转文字，约 200 MB，不装也能导出
echo.
echo  注意：微信要先登录，并保持在后台运行（工具靠运行中的进程解密）。
echo.
echo  其实第 2、3 步也能自动带你走这一步，所以以后忘了也不怕：
echo  直接双击 2 或 3 就行。
echo.
pause
exit /b 0

:verifyfail
echo.
echo   [失败] 自检没通过，可能是网络或 Python 有问题。
echo          补救：删掉 venv 文件夹，再双击本脚本重来一次。
echo.
pause
exit /b 1

:nosrc
echo   [错误] 没找到 app.py / requirements.txt。
echo          请把本脚本放在仓库根目录下运行。
echo.
pause
exit /b 1

:nopy
echo.
echo   [错误] 这台机器上找不到 Python 3.12。
echo.
echo   两个办法，任选一个：
echo     1. 装 Python 3.12   https://www.python.org/downloads/
echo        安装时记得勾上 "Add python.exe to PATH"
echo     2. 装 uv             https://docs.astral.sh/uv/
echo        装好后重跑本脚本，它会自己下载 Python 3.12
echo.
pause
exit /b 1

:fail
echo.
echo   [错误] 安装失败，先检查网络。
echo          如果在防火墙 / 代理后面，手动跑：
echo            venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
pause
exit /b 1
