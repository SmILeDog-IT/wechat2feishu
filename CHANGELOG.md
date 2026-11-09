# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循语义化版本。日期为发布日。

## [0.1.0] - 2026-11-04

首个公开版本。**导出链路完整可用，飞书写入链路只到「配置 + 自检」。**

### 新增

- 微信 PC 端本地数据库只读导出：文本、图片、文件、语音、视频，支持全量扫描与单会话导出。
- 语音转文字（可选）：本地 SenseVoice 模型推理，不联网；依赖与模型单独安装。
- `app_feishu.py` 启动器：继承上游主窗口，在底部注入「飞书导入 →」按钮与同名菜单，不改动上游源码。
- 飞书可视化配置中心 `scripts/feishu_config_gui.py`：应用凭证、Base 链接解析、分表策略、
  导入策略、导出目录扫描、连接自检，零第三方依赖。
- `App Secret` 使用 Windows DPAPI 加密存储，不支持跨机器/跨用户解密。
- 敏感临时缓存：一次性工作目录 + 退出清理 + 启动时残留回收，另提供 `--clear-sensitive-cache`。
- EXE 打包：`4-打包EXE.bat` + `scripts/build_exe.py` + PyInstaller spec，产出单文件 `WeChat-To-Feishu.exe`。
- Agent 技能包：`SKILL.md` 与 `references/` 七份参考文档（环境探测、取数工具、数据契约、
  应用搭建、字段映射、API 限流、排错）。
- 单元测试 52 个，覆盖批量导出、图片/视频通道、发送者映射、敏感缓存与数据目录探测。

### 已知限制

- 自动建表（`feishu_init.py`）、批量写入（`feishu_push.py`）、附件上传（`upload_media.py`）
  **尚未实现**，面板上对应按钮会提示缺失的脚本。
- 仅支持 Windows 10/11 x64，依赖微信 4.x 已登录并保持后台运行。
- 上游源码 `app.py` / `cli.py` / `exporter_core.py` / `preview.py` / `wechat_data_dirs.py`
  保持原样，本项目只在其外围扩展。

### 变更

- 移除 `scripts/init_skill.py`（与本项目功能无关的通用技能脚手架）。
- 移除 `assets/config.example.yaml`（无任何代码读取，且与实际的 `config.json` 结构不一致）。
- 删除 `scripts/validate_export.py` 中未被调用的 `truthy()`。
- 简化 `app_feishu.py` 中永不生效的 `src/` 分离布局分支与冗余路径候选。
- README 补充「当前进度」能力矩阵、开发与测试说明，目录结构按仓库实际内容重写。
