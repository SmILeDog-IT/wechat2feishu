# Windows EXE 使用说明

双击 `WeChat-To-Feishu.exe` 打开「微信聊天导出给大模型 · 飞书版」。
程序内置 Python 和核心依赖，使用者无需安装 Python。

## 使用

1. 将 EXE 放到有写入权限的文件夹，例如 `D:\WeChat-To-Feishu`。
2. 登录 Windows 微信 4.x，并保持微信运行。
3. 双击 EXE，输入好友或群聊名称，选择附件类型，开始导出。
4. 默认结果保存在 EXE 同目录的 `exports` 文件夹；也可以在窗口中另选目录。
5. 点「飞书导入」打开配置面板。飞书配置与源码版共用当前 Windows 用户的
   `%LOCALAPPDATA%\wechat-to-feishu\config.json`。

单文件程序启动时会先解包运行库，第一次打开可能需要等几秒。
支持 Windows 10/11 x64。

## 当前功能范围

- 包含聊天导出、附件处理、聊天预览和飞书配置面板。
- 语音解码器可以在程序提示时下载；语音转文字依赖及模型属于可选组件。
  默认核心环境构建的 EXE 不含语音识别运行库。如需此功能，先安装
  `requirements-asr.txt` 再重新打包；模型可在运行时按提示下载。
- 当前仓库尚未提供 `feishu_init.py` 和 `feishu_push.py`，因此自动建表、
  推送到飞书的执行步骤暂不可用。EXE 与源码版的功能进度一致。

## 重新打包

在源码目录双击 `4-打包EXE.bat`。也可以手动执行：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\venv\Scripts\python.exe scripts\build_exe.py
```

生成文件为 `dist\WeChat-To-Feishu.exe`，同目录附带本说明、`LICENSE`、`NOTICE`
和 `THIRD_PARTY_NOTICES.md`。发布给其他人时请一并保留这四个文件。
