@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  可选功能 / 语音转文字（ASR）
echo ============================================================
echo.
echo  不装也能正常导出：语音照样会导出成 WAV，
echo  只是不带文字稿。装了才会把语音转成文字。
echo.
echo  这一步会额外装 sherpa-onnx + soundfile（约 200 MB），
echo  并下载本地 SenseVoice 模型。走公网，慢的话耐心等。
echo.
echo ------------------------------------------------------------
echo.

if not exist "venv\Scripts\python.exe" (
  echo   [提示] 还没装运行环境，先自动执行「第 1 步 / 首次安装」。
  echo.
  call "%~dp01-首次安装.bat"
)
if not exist "venv\Scripts\python.exe" goto novenv

echo   [1/2] 安装语音依赖 ...
venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-asr.txt
if errorlevel 1 (
  echo   [提示] 默认源失败，改用清华镜像重试 ...
  venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-asr.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 goto fail
)

echo.
echo   [2/2] 下载 SenseVoice 模型 ...
venv\Scripts\python.exe cli.py --install-asr
if errorlevel 1 goto fail

echo.
echo ============================================================
echo  装好了。以后导出时勾上「语音转文字」即可。
echo ============================================================
echo.
pause
exit /b 0

:novenv
echo.
echo   [错误] 运行环境仍然不存在，首次安装没有成功。
echo          请先双击 1-首次安装.bat。
echo.
pause
exit /b 1

:fail
echo.
echo   [错误] 安装失败，先检查网络。
echo.
pause
exit /b 1
