# 01 · 环境探测

> 目标：在动手之前，准确判断「哪一版微信、数据在哪、能不能直接读」。

---

## 目录

1. [快速判定流程](#1-快速判定流程)
2. [微信 3.x 目录结构](#2-微信-3x-目录结构)
3. [微信 4.x 目录结构](#3-微信-4x-目录结构)
4. [数据目录可能被重定向](#4-数据目录可能被重定向)
5. [加密判定](#5-加密判定)
6. [关键表与文件对照](#6-关键表与文件对照)
7. [Python 环境检查](#7-python-环境检查)

---

## 1. 快速判定流程

```
① 找数据根目录
   ├─ 有 xwechat_files\  → 微信 4.x，转 §3
   └─ 有 WeChat Files\  → 微信 3.x，转 §2
   ↓ 都找不到
② 查注册表 InstallPath
   ├─ ...\Tencent\Weixin  → 4.x
   └─ ...\Tencent\WeChat  → 3.x
   ↓ 仍找不到
③ 查安装目录的 exe 版本号
   ↓
④ 查进程
```

直接用脚本跑，别手工翻目录：

```bash
python3 scripts/detect_env.py
python3 scripts/detect_env.py --json     # 机器可读
```

---

## 2. 微信 3.x 目录结构

数据根目录默认：`C:\Users\<user>\Documents\WeChat Files\`

```
WeChat Files\
└── <wxid>\
    ├── Msg\
    │   ├── Multi\
    │   │   ├── MSG0.db ~ MSG9.db     ← 聊天记录分片
    │   │   └── MediaMSG0.db          ← 语音等媒体索引
    │   ├── MicroMsg.db               ← 联系人 + 群成员
    │   ├── FTSMSG0.db                ← 全文索引
    │   └── Media.db
    ├── FileStorage\
    │   ├── Image\YYYY-MM\            ← 图片，.dat 加密
    │   ├── Video\YYYY-MM\            ← 视频，.mp4 明文
    │   ├── File\YYYY-MM\             ← 文件，明文
    │   ├── CustomEmotion\            ← 表情
    │   └── MsgAttach\
    ├── config\
    └── temp\
```

**特征**：`MSG0.db` 这种大写下划线的分片命名，一眼就能认出来。

**加密**：SQLCipher。3.x 的密钥通常可由设备信息推出来（IMEI / 设备 ID + uin 做 MD5 取前 7 位），所以 3.x 的解密工具最多、最成熟。

---

## 3. 微信 4.x 目录结构

数据根目录默认：`C:\Users\<user>\Documents\xwechat_files\`

```
xwechat_files\
├── all_users\
│   ├── config\                       ← 全局配置
│   └── login\<wxid>\
│       └── key_info.db               ← 登录态相关（不是消息库）
└── <wxid>_<4位随机>\
    ├── db_storage\
    │   ├── message\
    │   │   ├── message_0.db          ← 聊天记录（分片，可能 1~N）
    │   │   ├── message_fts.db        ← 全文索引
    │   │   ├── media_0.db            ← 媒体元信息
    │   │   ├── message_resource.db
    │   │   └── biz_message_0.db      ← 公众号
    │   ├── contact\
    │   │   ├── contact.db            ← 联系人 + 群成员
    │   │   └── contact_fts.db
    │   ├── session\session.db        ← 会话列表
    │   ├── sns\sns.db                ← 朋友圈
    │   ├── favorite\favorite.db
    │   ├── emotion\emoticon.db
    │   └── head_image\head_image.db
    ├── msg\
    │   ├── attach\<hash>\            ← 图片/语音附件，.dat 加密
    │   ├── file\YYYY-MM\             ← 文件
    │   └── video\YYYY-MM\            ← 视频
    ├── cache\
    │   └── YYYY-MM\{Message,Emoticon,Sns,...}
    ├── config\
    └── resource\
```

**特征**：
- 账号目录名带 4 位随机后缀：`wxid_xxxxx_ced6`
- 有 `db_storage` 目录（3.x 没有）
- 消息库是 `message_0.db`（小写 + 下划线 + 数字）
- 每个 `.db` 旁边常有 `-wal` / `-shm` / `*.material` 文件，**这是微信自己的增量机制，不是损坏**

> `*.material`、`*.kvdb` 是 4.x 引入的，第三方工具未必支持。这些文件不影响读取主体 `.db`，但说明「这是个很新的版本，工具适配可能滞后」。

---

## 4. 数据目录可能被重定向

用户可以把「文档 / 下载」目录挪到别的盘。实测案例：

```
系统用户目录：C:\Users\<user>\Documents\
实际数据：    E:\wx\Documents\xwechat_files\
```

所以**不能只查默认路径**。探测顺序：

1. `%USERPROFILE%\Documents\xwechat_files`
2. `%USERPROFILE%\Documents\WeChat Files`
3. 各盘根目录往下 3 层找 `xwechat_files` / `WeChat Files`
4. 注册表 `HKCU\SOFTWARE\Tencent\Weixin` 的 `InstallPath`（只能定位安装目录）
5. 直接问用户

`detect_env.py` 已内置 1~3 的扫描。

---

## 5. 加密判定

读文件前 16 字节即可：

| 前 16 字节 | 结论 |
|---|---|
| `53 51 4C 69 74 65 20 66 6F 72 6D 61 74 20 33 00`（即 `SQLite format 3\0`） | **明文**，sqlite3 直接打开 |
| 其他任意字节 | **SQLCipher 加密**，必须解密 |

一行命令：

```bash
python3 -c "print(open(r'<db路径>','rb').read(16).hex())"
```

`detect_env.py` 会对 `message_*.db`、`contact.db`、`session.db` 逐个判定。

> ⚠️ 判定为加密后，**不要尝试自己写解密逻辑**。解密需要密钥，密钥要么由工具从进程内存读取，要么由用户提供。这是阶段 A 必须人工完成的根本原因。

---

## 6. 关键表与文件对照

### 聊天记录在哪

| 版本 | 文件 | 说明 |
|---|---|---|
| 3.x | `Msg\Multi\MSG*.db` | 按 shard 分片 |
| 4.x | `db_storage\message\message_*.db` | 分片，通常 `message_0.db` 最大 |

### 群成员昵称在哪

| 版本 | 文件 | 表 |
|---|---|---|
| 3.x | `Msg\MicroMsg.db` | `Contact` / `ChatRoom` |
| 4.x | `db_storage\contact\contact.db` | `contact` / `chatroom` |

群成员昵称**不在消息表里**，必须关联联系人表才能把 `wxid_xxx` 变成人名。这是导出工具最容易偷懒的一步——有些工具直接输出 wxid，要在体检时抓出来。

### 会话 ID 规则

| 类型 | 形态 |
|---|---|
| 群聊 | `<一串数字>@chatroom` |
| 单聊 | `wxid_xxxxxxxx` |
| 公众号 | `gh_xxxxxxxx` |

确认目标群时，认 `@chatroom` 后缀。

---

## 7. Python 环境检查

脚本零第三方依赖，但需要 Python 3.10+。

### Windows 上的经典坑

系统自带的 `python.exe` 可能是 **Microsoft Store 的 0 字节占位符**：

```
C:\Users\<user>\AppData\Local\Microsoft\WindowsApps\python.exe   ← 0 字节
```

表现：

```
> python --version
（无输出）
> echo %ERRORLEVEL%
9009
```

**判定方法**：

```powershell
Get-Item (Get-Command python).Source | Select-Object Length
```

`Length = 0` 就是占位符，等于没装。

**解决**：从 python.org 装 3.10+，安装时勾选 "Add python.exe to PATH"。装完 `python --version` 应输出 `Python 3.12.x` 之类。

### 验证清单

```bash
python3 --version                 # 有版本号
python3 -c "import json,csv,sqlite3,hashlib,urllib.request; print('ok')"
```

两条都过，才能继续。
