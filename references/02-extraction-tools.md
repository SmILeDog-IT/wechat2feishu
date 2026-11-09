# 02 · 取数工具选型

> 目标：选出能在用户机器上跑通、且**只读**的工具，并规定导出参数。
>
> ⚠️ **本文件时效性极强。** 微信客户端每月都在变，工具生态跟着剧烈波动（有项目因律师函整库删除，有项目的内置库会到期自毁）。**动手前先看「当前状态」一节，不要照抄半年前的教程。**

---

## 目录

1. [选型原则](#1-选型原则)
2. [当前状态（2026-10 实测）](#2-当前状态2026-10-实测)
3. [工具矩阵](#3-工具矩阵)
4. [首选：wechat-chat-export](#4-首选wechat-chat-export)
5. [WeFlow 的两个坑](#5-weflow-的两个坑)
6. [已下架 / 不可用](#6-已下架--不可用)
7. [通用兜底：任意工具都能接](#7-通用兜底任意工具都能接)
8. [跨平台补充](#8-跨平台补充)
9. [选型决策树](#9-选型决策树)

---

## 1. 选型原则

只认三条，其余都不重要：

1. **支持用户的实际微信版本**（4.1.15.x 这种新版本要优先考虑）
2. **能出结构化格式**（JSON / CSV / Excel），不是只有好看不好解析的 HTML
3. **只读**。凡是宣传「自动回复」「群发」「机器人」「防撤回」的，一律不用——能力越大，能碰的东西越多，风险越不成比例

附加偏好：

- 仍活跃维护（近 3 个月有提交）
- 有明确的「不需要 root / 不需要改客户端」说明
- 能把 `wxid` 翻译成群昵称

---

## 2. 当前状态（2026-10 实测）

这一节是**用血换来的**，直接决定先试哪个。

| 事实 | 影响 |
|---|---|
| 微信 4.x 全部库为 SQLCipher 加密，无一例外 | 没有「直接读明文」的捷径 |
| 微信 4.1.15.x 是较新版本，多数老工具没适配 | 只看版本号匹配的 |
| WeFlow 5.0.0 内置的 `wcdb_api.dll` **带构建过期开关，指向 2026-09-30** | 现在启动即报 `-101`，必须打社区补丁 |
| WeFlow 官方已明确不再内置解密组件 | 需自行提供 `wcdb_*` C ABI 动态库，门槛高 |
| `sjzar/chatlog` 已被律师函整库删除 | 网上教程全废，别引导用户找 fork |
| `zhuzhangxue/wechat-chat-export` 明确支持 **4.1.12+**，依赖已修到 4.1.15.x | **当前首选** |

> 结论：**先试 `wechat-chat-export`**。它版本匹配、单文件 EXE、输出结构最干净。

---

## 3. 工具矩阵

> 数据为 2026-10 调研时点的公开信息，stars 与更新时间会变，用前点开仓库看最新 release 说明。

| 项目 | 平台 | 微信版本 | 输出 | 附件 | 评价 |
|---|---|---|---|---|---|
| **zhuzhangxue/wechat-chat-export** | Windows | **4.1.12+** | TXT / MD / **JSON** | 图/文件/语音/视频 | ✅ **首选**。单文件 EXE，JSON 结构清晰，本文档已内置适配 |
| **hicccc77/WeFlow** ★15k | Win/mac/Linux | 4.x | JSON/HTML/MD/Excel/CSV | 全 | ⚠️ 功能最强但**已踩坑**，见 §5 |
| **Ray0612/WeChat-Export-Tool** | Windows | 4.x | PDF/CSV/Excel/HTML | 仅图片 | 需关微信抓密钥，JSON 不含图片，适合只要纯文本 |
| **ycccccccy/echotrace** ★3.8k | Win/mac | 4.x | 多格式 | 部分 | 与 WeFlow 同作者早期项目，新项目优先看 WeFlow |
| **BlueMatthew/WechatExporter** ★8.5k | iOS 备份 | 3.x 为主 | HTML/CSV/JSON | 部分 | 只有 iPhone 数据时用，2025-02 后未更新 |
| **WechatBakTool** | Windows | 3.x / 早期 4.x | GUI 导出 | 部分 | 3.x 首选，C# 图形界面 |

---

## 4. 首选：wechat-chat-export

仓库：`zhuzhangxue/wechat-chat-export`，Apache-2.0，单文件 EXE。

### 4.0 实测记录（2026-10-21，真实环境）

> 这一节是实机跑出来的，不是读文档抄的。可作为预期参考。

| 项目 | 实测值 |
|---|---|
| 微信版本 | 4.1.15.53（Windows 11 x64） |
| 数据目录 | 被重定向到 `E:\wx\Documents\xwechat_files\`（不在默认 C 盘） |
| 群规模 | 58 天、**5477 条**消息、8 个活跃成员 |
| 耗时 | 约 **100 秒**（含 399 张图片 + 41 条语音解密转码） |
| 输出体积 | 81 MB（其中媒体 77 MB） |
| 图片 | **399 / 399 全部成功**，零字节文件 0 个 |
| 语音 | 38 / 41（38 条成功转成 WAV） |
| 视频 | 2 / 5 |
| 身份解析 | 5329 resolved + 114 system + 34 未确认（0.6%） |
| EXE 完整性 | SHA256 与 GitHub Release 的 `digest` **逐位一致** |

**关键行为：这个 EXE 是窗口版，命令行参数不生效。** 跑 `--help` 不会打印帮助，而是直接弹出 GUI。要命令行模式必须用源码 `python cli.py`。

所以正常流程就是：**双击 EXE → 填群名 → 勾附件 → 点导出**。别指望脚本调它。

### 4.1 为什么选它

- README 明确写 **Windows 微信 4.1.12+**，依赖已包含 **4.1.15.x 兼容修复**
- 输出结构最干净：`sender`（显示名）与 `sender_username`（稳定 ID）**分开给**，不用自己 join 联系人表
- 引用回复、系统消息都做了结构化处理
- 有 `sender_status` 字段，能直接看出哪些消息的身份没确认——这是体检时最有价值的信息
- 敏感临时缓存（密钥、解密库）每次导出自建独立目录，**导出结束自动删除**

### 4.2 下载

```
https://github.com/zhuzhangxue/wechat-chat-export/releases/latest
```

选 `WeChat-Chat-Export-for-LLM.exe`（约 136 MB，单文件，不用装 Python）。

> 没有商业代码签名证书，首次运行 Windows SmartScreen 会拦一下，选「更多信息 → 仍要运行」。
> **不要为此关闭 Defender 或加全局排除项。**

### 4.3 前置条件

```text
✅ Windows 10/11 x64
✅ 微信已登录，且在后台运行（不是必须停掉，但必须登录着）
✅ 能读到微信数据目录的权限（当前用户即可，不需要管理员）
```

微信数据目录默认在：

```text
C:\Users\<用户>\Documents\xwechat_files\<wxid>_xxxx
```

**可能被迁移到别的盘**（实测过 `E:\wx\Documents\xwechat_files\`）。用 `detect_env.py` 先确认。

### 4.4 GUI 操作（推荐）

1. 双击 EXE
2. 顶部输入框填**群的准确名称**（或好友备注）
3. 勾选要导出的附件类型
   - **第一次只勾「图片」**，先验证链路
   - 文件/语音/视频等全量跑通后再补
4. 如果数据目录不对，点「微信数据目录 → 选择」
5. 点「开始导出」

### 4.5 命令行（仅源码版有效）

⚠️ **Release 里的 EXE 是窗口版，不解析命令行参数**（`--help` 会直接弹 GUI）。下面这些参数只在你用源码 `python cli.py` 时有效：

```powershell
# 需要先装依赖
pip install -r requirements.txt

python cli.py "某业务群" --out D:\wx_export --images
python cli.py "某业务群" --out D:\wx_export --db-dir "E:\wx\Documents"
python cli.py --all --limit 20 --out D:\wx_export
```

参数说明（源码模式下）：

| 参数 | 作用 |
|---|---|
| `--out` | 输出根目录，默认 `exports` |
| `--images` / `--files` / `--voices` / `--videos` | 分别开对应附件 |
| `--media` | 四类全开，**量大慎用** |
| `--transcribe-voices` | 本地 SenseVoice 语音转文字（会额外下载模型） |
| `--all` | 导出所有可识别会话，配 `--limit N` 先试跑 |
| `--db-dir` | 手动指定微信数据目录（自动探测选错时） |

> 用 EXE 的话，这些开关都在 GUI 上勾，效果一样，只是没法自动化。

### 4.6 输出结构

```text
D:\wx_export\
└─ 某业务群 [稳定摘要]\
   ├─ chat_full_for_llm.txt      ← 给人/AI 看的纯文本
   ├─ chat_full_for_llm.md       ← 带图片的 Markdown
   ├─ chat_full_parsed.json      ← ★ 唯一要喂给下游的文件
   └─ media\
      ├─ images\
      ├─ files\
      ├─ voices\               ← 可能已转成 .wav
      └─ videos\
```

### 4.7 JSON 字段结构

顶层：

```json
{
  "exporter_version": "1.4.0",
  "chat_type": "group",
  "chat_name": "某业务群",
  "message_count": 31245,
  "type_counts": { "1": 24871, "3": 4102, "49": 213 },
  "sender_resolution_counts": { "resolved": 30857, "unmapped_sender_id": 388 },
  "media_stats": { "images_requested": 4102, "images_exported": 4098 },
  "messages": [ ... ]
}
```

单条消息：

```json
{
  "local_id": 1001,
  "server_id": "7400000000000000001",
  "source_db": "message/message_0.db",
  "real_sender_id": 42,
  "type": "文本",
  "type_code": 1,
  "sender": "张三",
  "sender_username": "wxid_aaa111",
  "is_self": false,
  "sender_status": "resolved",
  "time": "2026-08-01 09:12:33",
  "content": "这个季度的预算表我下午发群里",
  "transcript": null,
  "media": null,
  "finder_feed": null
}
```

**三个必须注意的地方：**

| 坑 | 说明 |
|---|---|
| `type` 是**中文标签**（"文本"/"图片"…） | 标准类型要从中文映射，原始 `localType` 在 `type_code` |
| `sender` 是**显示名**，不是 ID | 稳定 ID 在 `sender_username`，两者别搞混 |
| **没有 `talker` 字段** | 会话标识只有顶层 `chat_name`；批量导出时靠文件夹名区分 |

引用回复不是独立字段，而是拼在 `content` 里：

```
好的
    ↳ 引用 张三：这个季度的预算表我下午发群里
```

`media` 是嵌套对象：

```json
{ "kind": "image", "path": "media/images/1003_xxx.jpg", "available": true, "previewable": true }
```

`available: false` 表示本机缓存已没了，只有 `reason`，没有 `path`。

### 4.7.1 已知的解析退化（实测）

微信 4.x 的 `localType` 有 64 位复合值，实测见过：

```
244813135921    136 条  → 引用回复（解析正常）
266287972401     34 条  → 身份解析失败的那批
8589934592049    28 条  → 解析正常
34359738417      11 条  → 【退化】输出 [文件/链接/卡片]，内容丢失
81604378673       9 条  → 拍一拍
```

两类退化要知道：

| 现象 | 数量级（本群 5477 条中） | 处理 |
|---|---|---|
| `content` 只有 `[文件/链接/卡片]` 占位 | 11 条 | 不可恢复，保留占位 |
| 拍一拍被归为 other | 44 条 | 可接受，正文里有人名和动作 |

另外 **`files_requested: 0`** 说明工具没把任何消息识别成文件消息。群里若确实有文件，会落到上面那 11 条占位里。

这些属于工具的能力边界，不是你的操作问题。**不要为了 0.2% 的消息去手写解析器**——按契约保留占位，验收时说明即可。

### 4.8 导完立刻体检

`validate_export.py` **已内置这个格式的适配**，直接跑：

```bash
python3 scripts/validate_export.py "D:\wx_export\某业务群 [xxx]\chat_full_parsed.json" --sample 5
```

它会自动识别导出器、展平字段、把中文类型映射成标准类型、把引用拆出来。

### 4.9 把飞书入口挂到这个工具上（集成方案）

`WeChat-Chat-Export-for-LLM` 是 PyInstaller 单文件 EXE，**页面改不进去**。但它开源，
源码版 GUI 是 `tkinter` 写的（`app.py`，只依赖 `psutil` 和导出核心），所以有两条路：

| 方案 | 做法 | 适合 |
|---|---|---|
| **旁挂（推荐）** | 单文件 `feishu_config_gui.py`，零依赖，双击即开 | 不想碰源码、只想配完就推 |
| **注入** | `app_feishu.py` 继承 `app.App`，底部挂按钮 + 菜单 | 想要「一个窗口导出完顺手推」 |

注入方案**不改任何第三方源码**，靠两处定位：

```python
import app as wce
class FeishuApp(wce.App):  # 继承主窗口
    ...
```

按钮插在底部按钮条 `grid row=10` 的 `column 0`（那里本来是 `weight=1` 的空白列，
所以不会挤动「清除敏感缓存 / 打开聊天预览」等原有按钮）。同时挂一个同名菜单做双保险。

源码版环境准备（Windows）——通常不用手动做，双击 `1-首次安装.bat` 即可，
它会把下面这些全做完（含 Python 3.12 探测与镜像回退）：

```bat
:: 等价于 1-首次安装.bat 里做的事
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

两条启动线：

| 双击 | 作用 |
|---|---|
| `2-启动飞书版.bat` | 主窗口 + 飞书入口（发现没 venv 会自动先装） |
| `3-启动飞书配置.bat` | 只开配置面板 |

语音转文字才需要 `sherpa-onnx==1.13.6` 和 `soundfile`（见 `requirements-asr.txt`，
或双击 `可选-安装语音识别.bat`）。它俩在 `exporter_core.py` 里是**延迟 import**
（第 1893、2021 行），不装不影响导出和 GUI 启动。

> EXE 和源码版可以共存：EXE 用来导出，源码版用来带飞书面板启动。
> 导出产物是同一份 JSON，两条路都能接着推。

---

## 5. WeFlow 的两个坑

WeFlow 功能最全（15k stars、实时增量、年度报告、HTTP API），但**现在直接装最新版会启动失败**。

### 坑一：原生库自带「构建过期开关」

WeFlow 5.0.0 随包的 `wcdb_api.dll` 里硬编码了两个过期开关，都指向 **2026-09-30 23:59:59**。时间一到：

```text
InitProtection() 返回 -101
wcdb_init()      返回 -1000
表现：弹窗「WeFlow 启动失败 / 错误码: -101」，数据库完全打不开
```

`npm run build` **修不了**——重建只会原样打包同一个过期 DLL。

已知修复路径（都需要额外操作，属于「第三方补丁」范畴）：

- 用社区补丁仓库 `AnonymousUser443/WeFlow-Community-Patch` 的 `Patch-WcdbApiExpiry.ps1` 就地修补 DLL
- 或换装该仓库提供的 Hotfix 安装包

> 重装、修复安装、升级都会覆盖 DLL，补丁要重打。

### 坑二：需要第三方解密组件

WeFlow 官方 README 明确写：

> 需要配套的第三方可插拔组件（本项目依赖自定义的原生解密组件，需自行设计）

也就是要在「设置 → 数据库 → 第三方组件路径」配一个实现 `wcdb_*` C ABI 的动态库。留空则相关功能直接返回「未配置」。

**所以选 WeFlow 之前先问一句：拿得到可用的组件吗？** 拿不到就换工具，别在这儿耗。

### 如果组件配好了，它的 HTTP API 很香

```text
GET http://127.0.0.1:5031/api/v1/messages
    ?talker=<xxx@chatroom>&start=20260801&end=20261021&limit=10000&offset=0
Authorization: Bearer <token>
```

字段与数据契约很接近，可以完全跳过导出文件。

---

## 6. 已下架 / 不可用

| 项目 | 状态 | 说明 |
|---|---|---|
| `sjzar/chatlog` | **代码与提交历史已全部删除** | 作者收到微信官方函件，以合规风险为由移除。仓库只剩一份移除通知。**不要引导用户去找 fork 或二手教程** |

> 这类项目的消失，正是本技能「契约与工具解耦」设计的理由：**下游流程不依赖任何具体工具**，工具没了换一个，`clean.csv` 不变。

---

## 7. 通用兜底：任意工具都能接

只要工具能导出「一条消息一行」的表格，就能接进来。

最低要求（缺一不可）：

| 字段 | 可接受的名字 |
|---|---|
| 会话 ID | talker / chatroom / sessionId / 会话 / chat_name |
| 发送者 | sender / from / 发送人 / wxid / 昵称 / sender_username |
| 时间 | createTime / timestamp / time / 时间 |
| 内容 | content / msg / 内容 / text |
| 类型 | type / localType / msgType / 类型 / type_code |

满足这五项，`normalize.py` 就能工作。优先 JSON（保结构），CSV 也能吃（Excel 另存为 CSV 时选 UTF-8）。

**不满足怎么办**：让用户改导出设置或换工具。不要在现场写解析器——工具换掉更省事。

---

## 8. 跨平台补充

主线是 Windows PC 微信，其他平台只在必要时提一句。

| 平台 | 难度 | 大致路线 |
|---|---|---|
| Windows PC | ★☆☆ | 本地库直接读，工具最全 |
| Android | ★★☆ | adb 备份 + 解密，或 root 后直取；生态较弱 |
| iOS | ★★★ | iTunes / 爱思整机备份 → 解析备份 → 工具导出 |

iPhone 路线额外注意：备份时**取消勾选「加密本地备份」**，否则第三方工具读不了。

---

## 9. 选型决策树

```
微信是 4.x？
├─ 是 → Windows？
│        ├─ 是 → 版本 4.1.12+？
│        │        ├─ 是 → ★ wechat-chat-export（首选，直接可用）
│        │        └─ 否 → Ray0612/WeChat-Export-Tool，或找支持该版本的旧版工具
│        └─ 否（iPhone）→ 备份后找 4.x 支持的 iOS 工具
└─ 否（3.x）→ WechatBakTool / WechatExporter
                ↓
        导出体检不通过？
                ↓
        换下一个工具，不要现场写解析器
                ↓
        所有工具都不行？
                ↓
        评估 WeFlow + 社区补丁（成本高，最后再考虑）
```

---

## 10. 一个提醒

**不要为了适配工具去降级微信客户端。** 降级过程不稳定，可能丢数据，而且下次客户端自动更新又白干。

工具适配滞后是常态，正确的应对是「换工具」或「等更新」，不是「降客户端」。
