# 参与贡献

欢迎 Issue 和 PR。这个项目处理的是聊天记录这类敏感数据，所以规矩比一般项目多一点，
但都是为了让别人敢用、也让你自己改得放心。

---

## 一、先认清哪儿能动

仓库里有两种血统的代码，**改动边界不一样**：

| 文件 | 血统 | 能不能改 |
|---|---|---|
| `app.py` `cli.py` `exporter_core.py` `preview.py` `wechat_data_dirs.py` | 上游 `zhuzhangxue/wechat-chat-export` | **尽量不改**，保持原样才能在上游更新时直接覆盖 |
| `app_feishu.py` | 本项目 | 随便改，飞书入口注入都在这里 |
| `scripts/feishu_config_gui.py` | 本项目 | 随便改 |
| `scripts/detect_env.py` `validate_export.py` `quick_validate.py` | 本项目 | 随便改 |
| `scripts/build_exe.py` `wechat-to-feishu.spec` | 本项目 | 打包逻辑，改完要真的打一次 |
| 文档 / `references/` | 本项目 | 欢迎纠错，尤其是和代码对不上的地方 |

确实需要改上游文件时，请在 PR 描述里写清楚**为什么非改不可**，以及上游升级时怎么处理。

---

## 二、搭环境

```bat
:: 方式一：双击 1-首次安装.bat，等它提示 [OK] all modules importable
:: 方式二：手动
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m py_compile app_feishu.py scripts\*.py
```

开发飞书面板不需要微信在跑：

```bat
venv\Scripts\python.exe scripts\feishu_config_gui.py
```

面板会以独立窗口启动，配置读写、连接自检都能验。**只有真导数据才需要微信登录并后台运行。**

---

## 三、跑测试

```bat
venv\Scripts\python.exe -m unittest discover -s tests -v
```

- 当前 52 个用例，全部通过是提交前的底线；
- 用例只用临时目录和打桩数据，**不会碰你本机的微信库**；
- 修 bug 请尽量补一个能复现该 bug 的用例，否则下一个人会替你重新踩一遍。

涉及飞书接口的改动没法用单测兜住，请在 PR 里贴自检结果（脱敏后的日志）。

---

## 四、代码约定

1. **标准库优先**。新增第三方依赖要在 PR 里说明理由，并同步更新 `requirements*.txt` 与 `THIRD_PARTY_NOTICES.md`。
2. **不写死密钥、路径、账号**。任何 `cli_` / `bascn` / `wxid_` 开头的真实值都不许进代码和文档。
3. **不美化数据**。原始消息内容、发送者、时间不许改；要过滤就在飞书侧用视图。
4. **只读微信库**。任何写库、改库、删库的 PR 直接拒。
5. **注释写「为什么」**，不写「是什么」。中文注释，和现有风格保持一致。
6. 面向用户的报错要给**下一步动作**，别只甩错误码 —— 面板里 `91403` 的话术就是范例。

---

## 五、提交信息

第一行固定格式：

```
【类型】 一句话总结
```

类型取：`新增` / `修复` / `优化` / `BUG` / `文档` / `重构` / `构建`。

例子：

```
【修复】 修复语音缓存残留导致重复转写

问题现象：同一段语音在两次导出中重复调用识别模型，第二次命中缓存但日志仍报失败。
修复逻辑：缓存文件名加入音频 md5 前缀，命中后不再重新解码。
影响范围：仅影响语音转写路径，文本与图片导出不受影响。
```

正文用完整句子说明**原因、做法、影响面**。别写「update」「fix bug」这种，
半年后连你自己都看不懂。

---

## 六、PR 清单

- [ ] 测试全绿（或说明哪些没跑、为什么）
- [ ] 新行为补了文档或 `references/` 里的说明
- [ ] 没有引入真实密钥、聊天内容、本机绝对路径
- [ ] 如果改了打包相关文件，本地至少打过一次 EXE
- [ ] 如果新增了用户可见功能，README 的「当前进度」表同步更新

---

## 七、绝对不能提交的东西

`exports/`、`*.db`、`config.json`、`.env`、任何含聊天记录或密钥的截图。
这些已经在 `.gitignore` 里，但**别指望它兜底** —— 提交前自己 `git status` 看一眼。

如果你不小心把真实数据推上去了，处理方式见 [SECURITY.md](SECURITY.md)：
先改密钥，再清历史，别只删文件了事。
