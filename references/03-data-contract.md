# 03 · 标准数据契约

> 这份文件是全流程的**唯一真相**。上游工具随便换，`clean.csv` 的列定义不能变。

---

## 目录

1. [为什么需要契约](#1-为什么需要契约)
2. [字段定义（15 列）](#2-字段定义15-列)
3. [类型归一映射](#3-类型归一映射)
4. [特殊类型处理](#4-特殊类型处理)
5. [manifest.json](#5-manifestjson)
6. [体检清单](#6-体检清单)

---

## 1. 为什么需要契约

微信导出的数据有几个固定毛病：

- 同一条消息，不同工具字段名完全不同
- 消息类型是数字，且数字含义不直观
- 引用、链接、文件、小程序全都塞在同一个类型号里，内容是一段 XML
- 群昵称和 `wxid` 分离在两个库
- 时间戳有秒级有毫秒级，还有本地时间字符串

如果下游直接吃某个工具的原始输出，等于把整个流程焊死在这个工具上。工具一旦下架（已有先例），全部重做。

契约层就是那道防火墙。

---

## 2. 字段定义（15 列）

`clean.csv` 固定 15 列，顺序不变，UTF-8 编码，带表头。

| # | 列名 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| 1 | `msg_id` | string | ✅ | 全局唯一。优先用工具给的 `serverId`/`MsgSvrID`；没有就用 `md5(talker + ts + sender + content)` |
| 2 | `server_id` | string | | 微信服务端消息 ID。引用关系靠它关联，有就要 |
| 3 | `talker` | string | ✅ | 会话 ID。群为 `xxx@chatroom` |
| 4 | `sender_wxid` | string | ✅ | 发送者原始 ID |
| 5 | `sender_name` | string | ✅ | 群内昵称 / 备注名。解析不出来就填 `sender_wxid`，**不许留空** |
| 6 | `ts` | int | ✅ | 秒级 Unix 时间戳（10 位） |
| 7 | `datetime` | string | ✅ | `YYYY-MM-DD HH:mm:ss`，本地时区 |
| 8 | `type` | string | ✅ | 归一类型，见 §3，取值必须在枚举内 |
| 9 | `raw_type` | int | ✅ | 微信原始 `localType`，保命用，排错全靠它 |
| 10 | `content` | string | ✅ | 展示文本。非文本类型给可读占位（如 `[图片]`） |
| 11 | `quote_msg_id` | string | | 被引用消息的 `server_id` |
| 12 | `quote_content` | string | | 被引用消息的内容快照 |
| 13 | `media_path` | string | | 附件相对路径（相对工作目录） |
| 14 | `media_md5` | string | | 附件指纹，去重和断点续传都靠它 |
| 15 | `is_self` | bool | ✅ | `1` = 用户自己发的，`0` = 别人发的 |

### 几条硬规定

- **`msg_id` 必须稳定**。同一份源数据跑两遍，`msg_id` 必须完全一致，否则幂等失效
- **`ts` 用秒级**，不要毫秒。导出工具给毫秒就除 1000
- **`datetime` 由 `ts` 推导**，不要各自独立生成，否则会对不上
- **`content` 允许为空字符串**（如纯图片消息），但字段本身不能缺
- **`sender_name` 不许留空**，解析失败退化成 wxid
- **CSV 里的换行**：`content` 含换行时用标准 CSV 引号转义，不要手工替换成 `\n` 字面量

### 已知导出工具的字段差异

契约是理想形态，现实工具各有各的脾气。目前实测过的差异：

**`wechat-chat-export`（zhuzhangxue，首选工具）**

| 契约字段 | 工具字段 | 处理 |
|---|---|---|
| `talker` | *（无）* | 用顶层 `chat_name` 兜底。它是群名不是 `@chatroom` ID，做会话校验时要放宽 |
| `sender_name` | `sender` | 直接用。注意这里是**显示名** |
| `sender_wxid` | `sender_username` | 直接用。**别把 `sender` 当 ID** |
| `type` | `type`（中文标签） | 走中文映射表，见下 |
| `raw_type` | `type_code` | 直接用（这是真正的 `localType`） |
| `ts` | `time` | 字符串 `YYYY-MM-DD HH:mm:ss`，直接解析 |
| `content` | `content` | 引用被拼在正文里，需拆 |
| `quote_content` | *（无独立字段）* | 从 `content` 里 `↳ 引用 X：Y` 拆出来 |
| `media_path` | `media.path` | 仅当 `media.available == true` 时有效 |
| `msg_id` | `server_id` | 缺失时用 `source_db:local_id` 兜底 |
| — | `sender_status` | 额外字段，**很有用**：`resolved` 之外的都算身份未确认 |

中文类型 → 契约类型：

```
文本→text    图片→image   语音→voice   视频→video
动画表情→emoji   位置→other   系统消息→system   视频号→other
文件/链接/卡片→ 看正文前缀：[文件]→file  [链接]/[分享]→link  否则 other
有引用 → quote（优先级最高）
```

> `validate_export.py` **已内置这套适配**，检测到该格式会自动展平。别的工具就按上表手工对应，或在 `normalize.py` 里加一段转换。

---

## 3. 类型归一映射

`type` 只能取这 10 个值：

```
text | image | voice | video | file | link | quote | emoji | system | other
```

### 微信 localType → 标准 type

| localType | 含义 | 标准 type | 内容处理 |
|---|---|---|---|
| `1` | 文本 | `text` | 原文 |
| `3` | 图片 | `image` | `[图片]` + `media_path` |
| `34` | 语音 | `voice` | `[语音]`（时长可从 XML 取，可选） |
| `42` | 名片 | `other` | `[名片]` + 昵称 |
| `43` | 视频 | `video` | `[视频]` + `media_path` |
| `47` | 表情 | `emoji` | `[表情]`，一般跳过附件 |
| `48` | 位置 | `other` | `[位置]` + 地名 |
| `49` | **App 消息（大类）** | 见下 | 必须拆子类型 |
| `50` | 语音/视频通话 | `other` | `[通话]` |
| `62` | 小视频 | `video` | `[小视频]` |
| `10000` | 系统提示 | `system` | 原文（入群、改群名等） |
| `10002` | 系统提示（撤回等） | `system` | 原文 |
| 其他 | 未知 | `other` | `[未知类型:<raw_type>]` |

### `49` 的子类型（最容易漏）

`49` 的内容是一段 XML，里面还有一个 `appmsg type`，必须再拆一层：

| appmsg type | 含义 | 标准 type | 抽取字段 |
|---|---|---|---|
| `5` | 链接/图文 | `link` | `<title>` + `<url>` |
| `6` | 文件 | `file` | `<title>`（文件名）+ `<totallen>`（大小） |
| `57` | **引用回复** | `quote` | `<title>` = 被引用内容，`<refermsg>` 里含被引用的 `svrid` |
| `19` | 合并转发 | `other` | `[聊天记录]` + `<title>` |
| `33` / `36` | 小程序 | `other` | `[小程序]` + 标题 |
| `51` / `52` / `53` | 视频号 / 公众号视频 | `other` | `[视频号]` |
| `2000` / `2001` | 转账 / 红包 | `other` | `[转账]` / `[红包]` |
| `2003` | 视频号直播 | `other` | `[直播]` |
| `87` | 群公告 | `system` | 原文 |
| `2001` | 红包 | `other` | `[红包]` |
| 其他 | — | `other` | `[App消息:<subtype>]` |

> 判断不出来时，**保底策略**：`type=other`，`content` 里塞原始 XML 的前 200 字符。宁可难看，不能丢数据。

---

## 4. 特殊类型处理

### 4.1 引用回复

- `type = quote`
- `quote_content` = XML 里 `<title>` 的文本
- `quote_msg_id` = XML 里 `<refermsg><svrid>` 的值
- `content` = 引用者的回复正文

拿不到 `quote_msg_id` 时，`quote_msg_id` 留空但 `quote_content` 必须有——内容比链接重要。

### 4.2 合并转发

无法还原成多条独立消息（内部是嵌套 XML）。统一：

- `type = other`
- `content = [聊天记录] <title>`

不要尝试展开，收益低、出错率高。

### 4.3 语音

- `type = voice`
- `content = [语音]`
- 原始是 SILK 格式，**在飞书里无法播放**。需要转码（见 `07-troubleshooting.md`）。不做转码时，只保留时长信息

### 4.4 系统消息

入群、退群、改群名、撤回等。保留原文，`sender_wxid` 填 `system`，`sender_name` 填 `系统`。

分析时要能过滤掉它们，所以 `type = system` 必须打准。

### 4.5 撤回消息

部分工具会输出「xxx 撤回了一条消息」并附原内容。保留工具给的内容，不要自作主张删掉。

---

## 5. manifest.json

清洗产物旁边的账本，用于对账和排错。

```json
{
  "generated_at": "2026-10-21T10:00:00+08:00",
  "source": "inbox/raw.json",
  "talker": "12345678@chatroom",
  "group_name": "某业务群",
  "total": 31245,
  "time_range": {
    "first": "2026-08-01 09:12:33",
    "last": "2026-10-20 23:41:07"
  },
  "type_distribution": {
    "text": 24871,
    "image": 4102,
    "file": 213,
    "quote": 1204,
    "voice": 402,
    "system": 388,
    "other": 65
  },
  "media": {
    "referenced": 4715,
    "found": 4698,
    "missing": 17,
    "missing_list": ["msg/attach/xxx/yyy.dat"]
  },
  "warnings": [
    "17 个附件在本地找不到对应文件"
  ]
}
```

**用途**：验收时的三个数（导出条数 / clean 行数 / Base 记录数）就靠 `total` 对账。

---

## 6. 体检清单

`validate_export.py` 逐项检查。失败分级：

### 🔴 致命（不通过就停）

| 检查 | 判据 |
|---|---|
| 文件可读 | JSON 能解析 / CSV 有表头 |
| 记录数 | > 0 |
| 必填字段存在 | 契约 15 列里标记必填的，源数据至少能映射出 8 个 |
| 时间字段有效 | 能解析出时间，且不全为 0 或同一秒 |
| 会话 ID 一致 | 所有记录的 `talker` 相同，且匹配用户给的目标群 |

### 🟡 警告（可继续，但要报告）

| 检查 | 判据 |
|---|---|
| 发送者为空 | 空值比例 > 5% |
| 类型未知 | `other` 占比 > 20% |
| 昵称未解析 | 超过一半 `sender_name` 等于 `wxid` |
| 时间断档 | 中间有 > 30 天没有任何消息 |
| 附件缺失 | `media_path` 指向的文件不存在 |

### 输出示例

```
[致命] 会话 ID 不一致：期望 1234@chatroom，实际发现 3 个不同会话
[警告] 发送者为空占比 8.2%（2560/31245）
[警告] 昵称未解析：78% 的 sender_name 仍是 wxid_xxx
结论：不建议继续，请重新导出（只选目标群，开启昵称解析）
```

**体检不通过时，先回阶段 A 改导出设置，不要在现场写补丁脚本。**
