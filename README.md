# 微信聊天记录 → 飞书多维表格

把 Windows 微信的群聊/单聊记录，导出成结构化数据，再推进飞书多维表格，做检索、统计和业务分析。

本仓库 = **上游导出工具（原样保留）+ 飞书导入扩展（本仓库新增）**。

- 上游：<https://github.com/zhuzhangxue/wechat-chat-export>（Apache-2.0）
- 新增：可视化配置中心、飞书入口注入、导入技能包

> 只读微信本地数据库，绝不写库改库。所有导出结果只落本地磁盘，不上传任何聊天内容。

**文档导航**

| 你在找什么 | 看这里 |
|---|---|
| 装上、跑起来 | 本文「快速开始」 |
| 飞书那三样凭证怎么配 | 本文「飞书侧要准备什么」+ `README-飞书版.md` |
| EXE 怎么用、怎么重新打包 | `README-EXE.md` |
| 想改代码、跑测试 | `CONTRIBUTING.md` |
| 数据安全与隐私边界 | `SECURITY.md` |
| 让 AI Agent 跑全流程 | `SKILL.md` |
| 版本改了什么 | `CHANGELOG.md` |

---

## 一、它能干什么

```
微信 PC 客户端（本地加密库）
        │  只读解密 + 导出
        ▼
chat_full_parsed.json + media/          ← 上游工具负责
        │  清洗归一（15 字段标准契约）
        ▼
clean.csv + manifest.json
        │  建表 / 分批写入 / 附件上传
        ▼
飞书多维表格                             ← 本仓库扩展负责
```

两段职责分得很清：取数靠上游，进飞书靠这里。中间隔一层**标准数据契约**，
以后换任何导出工具，下游一行都不用改。

### 当前进度

| 能力 | 状态 | 从哪进 |
|---|---|---|
| 微信本地库只读导出（文本 / 图片 / 文件 / 语音 / 视频） | ✅ 可用 | 主窗口，或 `cli.py` |
| 语音转文字（本地 SenseVoice） | ✅ 可选 | `可选-安装语音识别.bat` |
| 飞书配置面板（凭证 / Base / 策略 / 连接自检 / 断点状态） | ✅ 可用 | `3-启动飞书配置.bat` |
| 自动建表、批量写入、附件上传 | ⬜ 规划中 | 面板上两个按钮会提示缺哪个脚本 |

**先看清楚再加星**：导出这条链路是完整可用的；飞书那条链路目前只到「配好、验通」，
真正把数据推进多维表格的执行脚本（`feishu_init.py` / `feishu_push.py`）还没实现。
面板按钮点下去会明确告诉你缺什么，不会假装成功。

---

## 二、快速开始（拉下来，双击两下）

### 使用本项目 EXE

本项目支持打包为自带 Python 的 Windows 单文件程序，保留飞书配置入口。
在源码目录双击 `4-打包EXE.bat`，产物为 `dist\WeChat-To-Feishu.exe`。
使用者双击 EXE 即可运行；详细说明和当前功能范围见 [README-EXE.md](README-EXE.md)。

### 第一次

```text
双击 2-启动飞书版.bat
```

就这样。它发现没有运行环境，会自动替你跑一遍首次安装：

1. 找一个 Python 3.12（本机没有就用 uv 自动下载，约 30 MB）
2. 建独立环境 `venv\`
3. 装核心依赖（uv 优先，失败回退 pip，再失败换清华镜像）
4. 自检 `import tkinter, zstandard, PIL, psutil, imageio_ffmpeg, wechatauto`
5. 装完自动继续启动主窗口

想显式先装一次也行：双击 `1-首次安装.bat`，效果完全一样。

### 之后的日常

1. 先登录微信，**保持微信在后台运行**（工具靠读运行中的进程密钥解密）
2. 双击 `2-启动飞书版.bat`
3. 输入群名 → 勾选要导的附件类型 → 开始导出
4. 点左下角「飞书导入 →」，填配置 → 连接自检 → 开始导入

### 只想配飞书，不开导出窗口

双击 `3-启动飞书配置.bat`。

### 想要语音转文字（可选）

双击 `可选-安装语音识别.bat`，额外约 200 MB。不装也能导出，语音只会存成 WAV 不带文字稿。

### 五个入口一览

| 双击这个 | 频次 | 作用 |
|---|---|---|
| `1-首次安装.bat` | 只跑一次 | 建 venv、装依赖、自检 |
| `2-启动飞书版.bat` | 日常 | 导出窗口 + 飞书入口（会自动补第 1 步） |
| `3-启动飞书配置.bat` | 按需 | 只开飞书配置面板（会自动补第 1 步） |
| `4-打包EXE.bat` | 发布时 | 打一个自带 Python 的单文件 EXE |
| `可选-安装语音识别.bat` | 可选 | 语音转文字依赖 + 模型 |

---

## 三、飞书侧要准备什么

三样东西，缺一不可：

| 项目 | 从哪拿 |
|---|---|
| **App ID** | 飞书开发者后台 → 自建应用 → 凭证与基础信息 |
| **App Secret** | 同上 |
| **Base token** | 打开多维表格，浏览器地址 `/base/` 后面那段（`bascn` 开头） |

外加两个**必须手动做**的动作（漏了必报 `91403`）：

1. **开权限**：`bitable:app`（查看、评论、编辑和管理多维表格），然后**创建版本 → 发布**，审核通过才生效
2. **加协作者**：目标 Base 右上角 `⋯` → 添加文档协作者 → 搜**应用名称**（不是 App ID）→ 给「可编辑」

配置面板里这三项都有对应的输入框和引导文案，还会在你点「连接自检」时逐步告诉你卡在哪。

配置存 `%LOCALAPPDATA%\wechat-to-feishu\config.json`，`App Secret` 用 **Windows DPAPI** 加密，
换机器或换用户解不开。**密钥不进仓库、不进技能目录，也不在任何 git 忽略规则之外的地方落地。**

---

## 四、目录结构

```
.
├─ 1-首次安装.bat              ★ ① 建 venv、装依赖（只跑一次）
├─ 2-启动飞书版.bat            ★ ② 日常启动：导出 + 飞书按钮
├─ 3-启动飞书配置.bat          ★ ③ 只开飞书配置面板
├─ 4-打包EXE.bat               ★ ④ 打包单文件 EXE
├─ 可选-安装语音识别.bat        ★ 可选：语音转文字依赖
│
├─ app.py cli.py exporter_core.py preview.py wechat_data_dirs.py
│                             上游源码（保持原样，方便跟随上游升级）
├─ app_feishu.py               ★ 启动器：继承上游主窗口 + 挂飞书入口
├─ wechat-to-feishu.spec       PyInstaller 打包描述
│
├─ scripts/
│  ├─ feishu_config_gui.py     ★ 可视化配置中心（零第三方依赖）
│  ├─ detect_env.py            微信环境探测（只读）
│  ├─ validate_export.py       导出数据体检
│  ├─ build_exe.py             EXE 打包入口（被 4-打包EXE.bat 调用）
│  └─ quick_validate.py        校验 SKILL.md 结构是否合规
│
├─ tests/                      单元测试（52 个用例）
├─ references/                 7 份参考：环境探测、取数工具、数据契约、应用搭建、
│                              字段映射、API 限流、排错
├─ assets/                     建表模板 + 图标
│
├─ requirements.txt            核心依赖（5 个直接依赖）
├─ requirements-asr.txt        可选：语音转文字依赖
├─ requirements-build.txt      可选：打包 EXE 依赖
├─ requirements-lock.txt       完整版本锁（pip freeze，可复现）
│
├─ venv/                       Python 环境（自动生成，不进 git）
├─ exports/                    导出产物（不进 git，含真实聊天内容）
│
├─ SKILL.md                    AI Agent 技能主文件（开工三问 / 五阶段 / 六条铁律）
├─ README-飞书版.md            飞书配置面板的逐项说明
├─ README-EXE.md               EXE 版使用与重新打包
├─ CONTRIBUTING.md             开发环境、测试与提交规范
├─ CHANGELOG.md                版本变更记录
├─ SECURITY.md                 数据安全与隐私说明
├─ NOTICE                      代码组成与版权归属（Apache 2.0）
└─ THIRD_PARTY_NOTICES.md      第三方组件与许可证
```

`SKILL.md` 那一套是给 AI Agent 用的**可复用技能包**，按 Agent Skills 标准组织。
人手动操作可以完全不看它；让 AI 帮忙跑全流程时，它读的就是这些。

---

## 五、飞书配置面板长什么样

四个页签，把「导出之后要填的东西」一次收齐：

| 页签 | 内容 |
|---|---|
| ① 飞书应用 | 服务域名（飞书/Lark）、App ID、App Secret（打码 + DPAPI 加密）、权限与协作者引导 |
| ② 多维表格 | 粘贴整条 Base 链接自动拆 token/table_id、数据表下拉、新表命名模板、分表策略 |
| ③ 导入策略 | 每批条数（≤200）、批间隔、重试次数、附件策略、内嵌大小上限、去重键、时间范围、演练模式 |
| ④ 运行 | 导出目录（自动探测）、断点状态库、扫描预估、初始化表结构、开始导入 |

底部固定区：从 `.env` 导入 / 导出 `.env` / 连接自检 / 保存配置。
日志区带颜色分级，错误码直接给中文处理建议。

前三个页签 + 连接自检已经完全可用；页签④里「初始化表结构」「开始导入」两个按钮
要调用尚未实现的执行引擎，点了会明确提示缺哪个文件（见「当前进度」）。

---

## 六、两种形态

| 形态 | 怎么用 | 适合 |
|---|---|---|
| **源码版**（本仓库） | 双击 `2-启动飞书版.bat` | 想一个窗口干完全部；能挂飞书入口 |
| **官方 EXE** | 另下 `WeChat-Chat-Export-for-LLM.exe` 跑导出，本仓库的 `3-启动飞书配置.bat` 管飞书 | 不想装 Python，只要导出 |

> 官方 EXE 是 PyInstaller 单文件包，**页面改不进去**，所以它没有飞书按钮。
> 想要「导出完顺手推飞书」，用源码版；EXE 只当备用导出器。

---

## 七、环境与依赖（给要部署到别的机器的人）

### 最小要求

| 条件 | 说明 |
|---|---|
| Windows 10/11 **x64** | 只支持 Windows |
| Python **3.12**，或装了 `uv` | 都没有也能救：装 uv 后 `1-首次安装.bat` 会自己下 Python |
| 微信 **4.x** 已登录并在后台运行 | 工具靠运行中的进程拿解密密钥 |
| 能访问公网 | 装依赖 + 调飞书开放接口 |

### 四份依赖文件怎么选

| 文件 | 内容 | 用途 |
|---|---|---|
| `requirements.txt` | 5 个核心直接依赖 | 日常安装，`1-首次安装.bat` 默认用它 |
| `requirements-asr.txt` | `sherpa-onnx` + `soundfile` | 语音转文字，可选 |
| `requirements-build.txt` | `pyinstaller` 及 hooks | 只有打包 EXE 的机器需要 |
| `requirements-lock.txt` | `pip freeze` 出的完整依赖树 | 要「装出一模一样的环境」时用 |

```bat
:: 可复现安装（锁死所有传递依赖版本）
venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

### 为什么 `venv\` 不进 git

Windows 的 venv **是路径绑定的**，不能当“绿色包”拷给别人：

- `venv\pyvenv.cfg` 里的 `home` 是你机器上的绝对路径
- `venv\Scripts\pip.exe` 之类还内嵌了打包时的绝对路径
- `site-packages` 里几十个 `.pyd` 是 `cp312/x64` 专用机器码

换台机器、换个用户名，直接崩。所以仓库只提交源码和依赖清单，环境用
`1-首次安装.bat` 在本机**重建**——这才是可复现。

同理 `exports/`（真实聊天内容）和 `config.json`（飞书密钥）也都不进仓库。

---

## 八、开发与测试

### 跑测试

```bat
venv\Scripts\python.exe -m unittest discover -s tests -v
```

52 个用例，覆盖批量导出分析、图片/视频通道、发送者映射、敏感缓存清理和数据目录探测。
用例只使用临时目录与打桩数据，**不会读取你本机的微信库**，随便跑。

### 改代码前先看这三处

| 想改什么 | 先看哪里 |
|---|---|
| 导出行为、消息类型、附件处理 | `exporter_core.py`（上游，尽量别动） |
| 界面按钮与日志 | `app.py`（上游）+ `app_feishu.py`（本项目注入层） |
| 飞书侧配置与连接自检 | `scripts/feishu_config_gui.py` |

`app.py` / `cli.py` / `exporter_core.py` / `preview.py` / `wechat_data_dirs.py`
来自上游，保持原样是为了上游更新时能直接覆盖。本项目新增的能力全部落在
`app_feishu.py`、`scripts/` 和文档里，改动请也落在这几处。

### 最低限度的静态检查

项目没有强绑 linter，提交前至少确认能编译：

```bat
venv\Scripts\python.exe -m py_compile app_feishu.py scripts\*.py
```

### 提交信息

第一行用「【类型】 一句话总结」，类型取 新增 / 修复 / 优化 / BUG / 文档 / 重构。
完整约定见 `CONTRIBUTING.md`。

---

## 九、硬约束（不参与讨论）

1. **只读微信库**，绝不写库改库
2. **先备份再动手**，实验都在副本上跑
3. **POC 先行**，先跑「单群 + 1000 条 + 50 张图」小闭环
4. **幂等**，消息以 `msg_id` 唯一、附件以 `md5` 唯一，跑三遍结果一致
5. **密钥不进仓库**，`app_secret` 只从 DPAPI 配置或环境变量读
6. **不改数据**，原始内容、发送者、时间一个字都不动

---

## 十、常见问题

**第一次双击没反应 / 一闪就没？**
开一个 CMD 在仓库根目录跑下面这条，能看到完整报错：

```bat
venv\Scripts\python.exe app_feishu.py
```

如果报 `venv` 不存在，说明首次安装没跑完 —— 双击 `1-首次安装.bat` 重来一次。
装依赖失败的日志也会打在它自己的窗口里。

**装依赖卡在下载 / 报网络错误？**
`1-首次安装.bat` 已经内置了「uv → pip → 清华镜像」三级回退。仍然失败就手动指定源：

```bat
venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**自检报 `91403`？**
应用没被加为 Base 协作者。Base 右上角 `⋯` → 添加文档协作者 → 搜应用名称 → 可编辑。改完直接重试，不用等。

**自检报 `99991672`？**
权限没开或改了没发版。开发者后台勾 `bitable:app` → 创建版本 → 发布。

**Python 装了但 `python` 没反应？**
Windows 上 `python` 常指向 Microsoft Store 的 0 字节占位符（exit 9009）。
`1-首次安装.bat` 会自动找 uv 管理的 3.12、`py` 启动器或 PATH 里的真 3.12，不用你操心。

**微信更新后读不出数据？**
上游依赖 `wechatauto-replica` 是精确锁版本的，微信大版本更新可能要吃上游适配。
见 `references/02-extraction-tools.md`。

**导出目录越大越慢？**
先只导文本（不勾附件）跑通链路，附件单独一趟补。

---

## 十一、许可与致谢

本项目基于 [zhuzhangxue/wechat-chat-export](https://github.com/zhuzhangxue/wechat-chat-export)（Apache-2.0）扩展，遵循同一许可，见 `LICENSE`。
哪些文件来自上游、哪些是本项目新增，写在 `NOTICE` 里。

底层微信数据库读取能力来自 [fanyuantaier/wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica)。
第三方组件与许可证见 `THIRD_PARTY_NOTICES.md`。

安全问题与密钥泄漏的处理流程见 `SECURITY.md`，贡献方式见 `CONTRIBUTING.md`。

---

## 十二、免责声明

本项目是独立开源工具，与腾讯、微信及其关联公司**没有**任何隶属、授权、认可或合作关系。
微信、WeChat、Weixin 及相关商标归其各自权利人所有。

**请只处理你本人有权访问和处理的数据**，并自行遵守所在地法律法规、软件服务条款
以及聊天参与者的隐私权。导出的聊天记录和密钥属于敏感数据，不要提交仓库、不要公开分享。

软件按「现状」提供，微信版本、系统环境或上游依赖变化都可能导致功能失效或导出结果不完整。
