# 06 · 飞书 API 调用规范

> 目标：批量写入不翻车。限流、重试、幂等、断点续传，四件事做好就够了。

---

## 目录

1. [认证](#1-认证)
2. [批量写入](#2-批量写入)
3. [限流与重试](#3-限流与重试)
4. [幂等设计](#4-幂等设计)
5. [断点续传](#5-断点续传)
6. [错误码对照](#6-错误码对照)
7. [最小可用调用示例](#7-最小可用调用示例)

---

## 1. 认证

### 1.1 获取 tenant_access_token

```
POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
Content-Type: application/json

{ "app_id": "...", "app_secret": "..." }
```

```json
{ "code": 0, "tenant_access_token": "t-xxx", "expire": 7200 }
```

### 1.2 缓存策略（必须做）

`expire` 是秒数（通常 7200 = 2 小时）。17,000 个附件上传肯定跨期，不做缓存会出现「跑到一半突然全 401」。

规则：

```
缓存 token 到本地文件或内存
刷新时机：剩余有效期 < 300 秒
刷新时加文件锁，防止多进程同时刷新
```

用标准库实现：

```python
import json, os, time, urllib.request, threading

_lock = threading.Lock()
_cache = {"token": None, "expire_at": 0}

def get_token(app_id, app_secret):
    with _lock:
        if _cache["token"] and time.time() < _cache["expire_at"] - 300:
            return _cache["token"]
        req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        if data.get("code") != 0:
            raise RuntimeError(f"取 token 失败: {data}")
        _cache["token"] = data["tenant_access_token"]
        _cache["expire_at"] = time.time() + data.get("expire", 7200)
        return _cache["token"]
```

### 1.3 携带方式

```
Authorization: Bearer <tenant_access_token>
```

只带一次前缀，别写成 `Bearer Bearer t-xxx`。

---

## 2. 批量写入

### 2.1 单批上限

```
POST /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create
{
  "records": [ { "fields": {...} }, ... ]
}
```

| 限制 | 值 |
|---|---|
| 单次最多记录数（平台上限） | 500 |
| **本技能建议值** | **200** |

为什么建议 200：

- 单条 payload 里有多行文本，500 条容易撞请求体大小限制
- 失败时重试成本低
- 与常见 SDK/CLI 的保守值一致，兼容性最好

### 2.2 必须串行

**不要并发写同一张表。** 并发写会触发 `1254291`（并发冲突），重试也能成，但会白烧时间和配额。

```
正确：批1 完成 → 批2 完成 → 批3 ...
错误：批1~批N 同时发出
```

### 2.3 分批伪代码

```python
for i in range(0, len(rows), 200):
    batch = rows[i:i+200]
    payload = {"records": [{"fields": to_fields(r)} for r in batch]}
    resp = api_post(url, payload)
    if resp["code"] != 0:
        handle_error(resp)      # 见 §6
    save_watermark(i + len(batch))
    time.sleep(0.3)             # 温柔一点
```

---

## 3. 限流与重试

### 3.1 限流常识

飞书对单应用的调用频率有限制，不同接口阈值不同。保守做法：

| 操作 | 建议节奏 |
|---|---|
| 批量写记录 | 每批间隔 200~500 ms |
| 单个附件上传 | 串行，间隔 100~300 ms |
| 读接口 | 可以适度并发，但别超过 10 路 |

**不要靠"我这边很快"来判断**，租户档位不同，容量差别很大。

### 3.2 退避重试

只对**可恢复错误**重试：

```python
RETRYABLE = {1254291, 1254290, 1255001, 99991400}   # 冲突 / 超时 / 限流

def api_call(fn, max_retries=5):
    delay = 1.0
    for attempt in range(max_retries):
        resp = fn()
        if resp.get("code") == 0:
            return resp
        if resp.get("code") not in RETRYABLE:
            raise ApiError(resp)          # 不可恢复，立刻抛
        time.sleep(delay)
        delay = min(delay * 2, 30)        # 1,2,4,8,16 封顶 30
    raise ApiError("重试耗尽")
```

对 `429` HTTP 状态码同理处理。

### 3.3 不要重试的错误

| 错误 | 为什么不能重试 |
|---|---|
| `91403` | 权限问题，重试一万次也一样 |
| `1254045` | 字段名不存在，是配置错 |
| `1254015` | 值类型不对，是数据错 |
| `10014` | App ID 错 |

重试这些只会把日志刷满，还会让限流雪上加霜。

---

## 4. 幂等设计

### 4.1 消息幂等

用 `msg_id` 作为业务唯一键。

写入前查一次目标表：

```
POST /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search
{ "filter": { "conjunction": "and", "conditions": [
    { "field_name": "消息ID", "operator": "is", "value": ["<msg_id>"] }
] } }
```

但逐条查 3 万次太慢。更实用的做法：

**先用 `msg_id` 的哈希前缀建一个本地索引**，或者一次性把目标表已有 `msg_id` 拉下来放进集合（3 万条内存无压力），写入前本地判重。

```python
existing = set(fetch_all_msg_ids(table_id))   # 一次拉全量
for row in rows:
    if row["msg_id"] in existing:
        continue
    ...
```

### 4.2 附件幂等

按 `md5` 去重，**同一文件只上传一次**，`file_token` 复用：

```python
if md5 in token_cache:          # 本地 sqlite：md5 → file_token
    token = token_cache[md5]
else:
    token = upload(file); token_cache[md5] = token
```

17,389 个文件里，表情包和重复转发的图片能占相当比例，这一步能省大量时间。

### 4.3 幂等验收

同一批数据跑两遍，记录总数必须不变。变了就是幂等有漏。

---

## 5. 断点续传

### 5.1 状态库

用一个本地 sqlite 存进度（不要用内存，也不要用一个 json 文件反复覆盖）：

```sql
CREATE TABLE IF NOT EXISTS progress (
  task_id     TEXT PRIMARY KEY,
  table_id    TEXT,
  offset      INTEGER DEFAULT 0,
  done        INTEGER DEFAULT 0,
  updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS file_tokens (
  md5         TEXT PRIMARY KEY,
  file_token  TEXT,
  uploaded_at TEXT
);
```

### 5.2 续跑逻辑

```
启动 → 读 task_id 的 offset
     → 从 offset 继续
     → 每批成功立刻 UPDATE progress
     → 全部完成置 done=1
```

关键点：**先写数据，再更新水位**。反过来的话，崩在中间会丢数据。

### 5.3 中断恢复演练

跑之前必须验证一次：

1. 跑到 30% 强制 `Ctrl+C`
2. 重新启动，看是否从 30% 继续
3. 跑完对账，总数应与一次跑完完全一致

不做这个演练，断点续传就是纸面上的功能。

---

## 6. 错误码对照

| code | 含义 | 处理 |
|---|---|---|
| `0` | 成功 | — |
| `91403` | Forbidden / 无权限 | **不要重试**。加文档协作者（`04-feishu-app-setup.md` §4） |
| `99991663` | tenant_access_token 无效 | 重新获取 token，检查是否过期或前缀重复 |
| `99991672` | 无权限访问该资源 | scope 没开或没发布 |
| `1254045` | FieldNameNotFound | 字段名拼错，先 `field-list` 拿真实字段名 |
| `1254015` | 字段值类型不匹配 | 日期要毫秒、数字要 int、复选框要 bool |
| `1254104` | 批量数量超限 | 拆小批次（≤200） |
| `1254291` | 并发写冲突 / 数据未就绪 | 等待后重试，并改为串行 |
| `1254290` | 请求过于频繁 | 退避重试 |
| `1255001` | 内部错误 | 退避重试 |
| `10014` | app not found | App ID 错 |
| `10003` | invalid param | 请求体格式错 |

### 排查顺序

```
1. 是不是 91403？→ 协作者
2. 是不是 1254045/1254015？→ 字段名和类型
3. 是不是 1254xxx？→ 拆批 / 退避
4. 都不是 → 看 response body 的 msg，别猜
```

---

## 7. 最小可用调用示例

纯标准库，可直接跑：

```python
import json, time, urllib.error, urllib.request

BASE = "https://open.feishu.cn/open-apis"

def request(method, path, token=None, payload=None, timeout=60):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {"code": e.code, "msg": body}

def batch_create(token, app_token, table_id, records):
    return request(
        "POST",
        f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
        token,
        {"records": [{"fields": r} for r in records]},
    )
```

用法：

```python
token = get_token(app_id, app_secret)
for i in range(0, len(rows), 200):
    resp = batch_create(token, app_token, table_id, rows[i:i+200])
    if resp["code"] != 0:
        raise RuntimeError(resp)
    time.sleep(0.3)
```

---

## 8. 一个真实教训

有人在 5 万条数据上开了 8 路并发写，前 2 万条飞快，然后开始疯狂 `1254291`，最后跑了 6 小时还没跑完，日志里全是重试。

**正确姿势**：单线程、每批 200、间隔 300ms。听着慢，但 5 万条也就 250 批 × 0.5 秒 ≈ 2 分钟。稳定比聪明重要。
