#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出数据质量体检

检查从微信导出的 JSON / CSV 是否满足标准数据契约的最低要求。
不合格就回阶段 A 重新导出，不要在现场写补丁脚本。

用法:
    python3 validate_export.py raw.json
    python3 validate_export.py raw.csv
    python3 validate_export.py raw.json --talker 12345678@chatroom
    python3 validate_export.py raw.json --json
    python3 validate_export.py raw.json --sample 5

仅使用 Python 标准库。退出码: 0=通过  1=有警告  2=致命
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TZ = timezone(timedelta(hours=8))

# ---------------------------------------------------------------- 字段别名

ALIASES = {
    "talker": ["talker", "chatroom", "chat_room", "sessionid", "session_id",
               "chat_id", "chatid", "conversation_id", "会话", "会话id", "群id",
               "username", "strtalker"],
    "sender_wxid": ["sender_wxid", "senderwxid", "sender", "senderusername",
                    "from", "fromuser", "wxid", "talkerid", "发送者", "发送人",
                    "发送者id", "sender_id"],
    "sender_name": ["sender_name", "sendername", "nickname", "nick_name",
                    "displayname", "display_name", "群昵称", "昵称", "发送者昵称",
                    "sendernickname", "from_nickname"],
    "ts": ["ts", "createtime", "create_time", "timestamp", "time", "msgtime",
           "msg_time", "sendtime", "send_time", "时间", "发送时间", "日期"],
    "content": ["content", "msg", "text", "message", "body", "内容", "消息",
                "消息内容", "parsedcontent", "parsed_content"],
    "type": ["type", "localtype", "local_type", "msgtype", "msg_type",
             "contenttype", "content_type", "类型", "消息类型"],
    "server_id": ["serverid", "server_id", "svrid", "msgid", "msg_id",
                  "msgsvrid", "newmsgid", "消息id"],
    "quote_content": ["quote_content", "quotecontent", "quote", "refermsg",
                      "refer_content", "引用内容", "quote_text"],
    "quote_msg_id": ["quote_msg_id", "quotemsgid", "refer_svrid", "quoteid"],
    "media_path": ["media_path", "mediapath", "media_url", "media_localpath",
                   "path", "file_path", "filepath", "attachment", "附件路径"],
    "is_self": ["is_self", "isself", "issend", "is_send", "fromme", "是否本人",
                "自己发送"],
}

VALID_TYPES = {"text", "image", "voice", "video", "file", "link",
               "quote", "emoji", "system", "other"}

# 中文类型标签 -> 契约类型（wechat-chat-export 等工具使用中文标签）
CN_TYPE_MAP = {
    "文本": "text",
    "图片": "image",
    "语音": "voice",
    "视频": "video",
    "动画表情": "emoji",
    "表情": "emoji",
    "位置": "other",
    "系统消息": "system",
    "视频号": "other",
    "名片": "other",
    "通话": "other",
}

# 文件/链接/卡片这种复合类型，靠正文前缀再拆一层
APP_TYPE_HINT = "文件/链接/卡片"


def refine_app_type(content, fallback="other"):
    c = (content or "").lstrip()
    if c.startswith("[文件]"):
        return "file"
    if c.startswith("[链接]") or c.startswith("[分享]"):
        return "link"
    if c.startswith("[动画表情]"):
        return "emoji"
    if c.startswith("[位置]"):
        return "other"
    return fallback


def is_wce_format(payload):
    """判断是否为 wechat-chat-export (zhuzhangxue) 的输出格式。"""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("messages"), list)
        and ("exporter_version" in payload or "chat_type" in payload)
    )


def adapt_wce(payload):
    """把 wechat-chat-export 的 JSON 展平成契约字段名。

    该工具字段：sender(显示名) / sender_username(稳定 ID) / type(中文标签)
    / type_code(原始 localType) / time(字符串) / media{path,available}。
    引用被拼进 content，形如 "回复正文\\n    ↳ 引用 张三：被引用内容"。
    """
    out = []
    chat_name = payload.get("chat_name") or ""
    chat_type = payload.get("chat_type") or ""
    for m in payload.get("messages") or []:
        if not isinstance(m, dict):
            continue

        content = m.get("content") or ""
        quote_content = ""
        quoted_by = ""
        mm = re.search(r"\n\s*↳\s*引用\s*([^：:\n]{1,40})[：:]\s*(.+)$", content, re.S)
        if mm:
            quoted_by = mm.group(1).strip()
            quote_content = mm.group(2).strip()
            content = content[: mm.start()].rstrip()

        cn = (m.get("type") or "").strip()
        t = CN_TYPE_MAP.get(cn)
        if t is None:
            t = refine_app_type(content, "other")
        elif cn == APP_TYPE_HINT:
            t = refine_app_type(content, "other")
        if quote_content:
            t = "quote"

        media = m.get("media") or {}
        media_path = ""
        if media.get("available") and media.get("path"):
            media_path = media["path"]

        out.append({
            "talker": chat_name or chat_type or "unknown",
            "sender_wxid": m.get("sender_username") or "",
            "sender_name": m.get("sender") or "",
            "ts": m.get("time"),
            "type": t,
            "raw_type": m.get("type_code"),
            "content": content,
            "quote_content": quote_content,
            "quote_by": quoted_by,
            "media_path": media_path,
            "is_self": m.get("is_self"),
            "server_id": m.get("server_id") or "",
            "msg_id": m.get("server_id") or "{0}:{1}".format(
                m.get("source_db") or "", m.get("local_id") or ""),
            "sender_status": m.get("sender_status") or "",
        })
    return out


def wce_meta(payload):
    return {
        "format": "wechat-chat-export",
        "exporter_version": payload.get("exporter_version"),
        "chat_name": payload.get("chat_name"),
        "chat_type": payload.get("chat_type"),
        "declared_count": payload.get("message_count"),
        "media_stats": payload.get("media_stats"),
        "sender_resolution_counts": payload.get("sender_resolution_counts"),
    }


def norm_key(k):
    return re.sub(r"[\s_\-]", "", str(k)).lower()


def build_index(keys):
    """把实际出现的列名映射到契约字段。"""
    idx = {}
    normalized = {norm_key(k): k for k in keys}
    for field, cands in ALIASES.items():
        for c in cands:
            ck = norm_key(c)
            if ck in normalized:
                idx[field] = normalized[ck]
                break
    return idx


# ---------------------------------------------------------------- 读取

def load_records(path):
    """返回 (records, meta)。meta 携带导出工具信息，非该格式时为空 dict。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            data = json.load(f)
        if is_wce_format(data):
            return adapt_wce(data), wce_meta(data)
        return extract_list(data), {}
    if ext in (".csv", ".txt"):
        return load_csv(path), {}
    raise SystemExit(f"不支持的文件类型: {ext}（只接受 .json / .csv）")


def extract_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("messages", "records", "data", "list", "items", "rows", "msg_list"):
            v = data.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = extract_list(v)
                if inner:
                    return inner
        # 单条记录
        if any(isinstance(v, (str, int, float)) for v in data.values()):
            return [data]
    raise SystemExit("JSON 结构无法识别：顶层既不是数组，也找不到 messages/records/data 列表")


def load_csv(path):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                return list(csv.DictReader(f, dialect=dialect))
        except UnicodeDecodeError:
            continue
        except Exception as e:
            raise SystemExit(f"CSV 读取失败: {e}")
    raise SystemExit("CSV 编码无法识别，请另存为 UTF-8")


# ---------------------------------------------------------------- 解析

def parse_ts(v):
    """返回 (秒级时间戳, 错误原因)"""
    if v is None or v == "":
        return None, "空值"
    if isinstance(v, bool):
        return None, "布尔值"
    if isinstance(v, (int, float)):
        n = int(v)
        if n <= 0:
            return None, "非正数"
        if n > 10**12:          # 毫秒
            n //= 1000
        if n < 10**8:           # 太小，不像真实时间
            return None, f"数值过小({n})"
        return n, None
    s = str(v).strip()
    if re.fullmatch(r"\d{10}", s):
        return int(s), None
    if re.fullmatch(r"\d{13}", s):
        return int(s) // 1000, None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d",
                "%Y-%m-%dT%H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=TZ)
            return int(dt.timestamp()), None
        except ValueError:
            continue
    return None, f"无法解析: {s[:32]}"


# ---------------------------------------------------------------- 检查

def validate(path, expect_talker=None, sample=0):
    fatal = []
    warns = []
    stats = {}

    if not os.path.exists(path):
        return {"fatal": [f"文件不存在: {path}"], "warns": [], "stats": {}}

    size = os.path.getsize(path)
    if size == 0:
        return {"fatal": ["文件为空"], "warns": [], "stats": {}}

    meta = {}
    try:
        records, meta = load_records(path)
    except SystemExit as e:
        return {"fatal": [str(e)], "warns": [], "stats": {}}
    except Exception as e:
        return {"fatal": [f"解析失败: {e}"], "warns": [], "stats": {}}

    if not records:
        return {"fatal": ["记录数为 0，导出失败"], "warns": [], "stats": {}}

    stats["records"] = len(records)
    stats["file_size"] = size
    if meta:
        stats["meta"] = meta

    # 导出工具自报条数对账（wechat-chat-export 会写 message_count）
    declared = meta.get("declared_count")
    if isinstance(declared, int) and declared != len(records):
        fatal.append(
            f"条数对不上：工具自报 {declared} 条，实际解析出 {len(records)} 条。"
            "JSON 可能被截断或手工改过。"
        )

    # 字段映射
    keys = set()
    for r in records[:200]:
        if isinstance(r, dict):
            keys.update(r.keys())
    idx = build_index(keys)
    stats["mapped_fields"] = sorted(idx.keys())
    stats["missing_fields"] = sorted(set(ALIASES) - set(idx))

    required = ["talker", "sender_wxid", "ts", "content", "type"]
    for f in required:
        if f not in idx:
            fatal.append(
                f"缺少必要字段「{f}」——在源数据里找不到任何可识别的列名。"
                f"实际列名: {', '.join(sorted(keys)[:12])}"
            )

    if fatal:
        return {"fatal": fatal, "warns": warns, "stats": stats}

    # 逐条抽样检查
    talkers = Counter()
    types = Counter()
    empty_sender = 0
    wxid_like_sender = 0
    bad_ts = 0
    bad_type = 0
    ts_list = []
    scanned = 0
    sender_status = Counter()

    has_name_col = "sender_name" in idx
    has_wxid_col = "sender_wxid" in idx

    for r in records:
        if not isinstance(r, dict):
            continue
        scanned += 1

        st = r.get("sender_status")
        if st:
            sender_status[st] += 1

        t = r.get(idx["talker"])
        if t:
            talkers[str(t)] += 1

        if has_name_col:
            s_name = r.get(idx["sender_name"])
            if not s_name:
                empty_sender += 1
            elif str(s_name).startswith("wxid_"):
                wxid_like_sender += 1
        else:
            # 没有昵称列，只能用原始 ID 兜底判断
            s_id = r.get(idx.get("sender_wxid")) if has_wxid_col else None
            if not s_id:
                empty_sender += 1
            elif str(s_id).startswith("wxid_"):
                wxid_like_sender += 1

        ts, err = parse_ts(r.get(idx["ts"]))
        if ts is None:
            bad_ts += 1
        else:
            ts_list.append(ts)

        ty = str(r.get(idx["type"]) or "").strip().lower()
        if ty in VALID_TYPES:
            types[ty] += 1
        elif ty.isdigit():
            types["__raw__"] += 1
            bad_type += 1
        else:
            types["other"] += 1
            bad_type += 1

    stats["scanned"] = scanned
    stats["type_distribution"] = dict(types.most_common())
    stats["talkers"] = dict(talkers.most_common(5))
    if sender_status:
        stats["sender_status"] = dict(sender_status.most_common())

    # 致命：会话不一致
    if len(talkers) > 1:
        fatal.append(
            f"会话 ID 不唯一：发现 {len(talkers)} 个会话 "
            f"({', '.join(list(talkers)[:3])})。导出时可能选了多个会话或没过滤。"
        )
    if expect_talker and talkers and expect_talker not in talkers:
        fatal.append(
            f"目标会话不符：期望 {expect_talker}，实际 {list(talkers)[:3]}"
        )

    # 致命：时间全无效
    if bad_ts == scanned and scanned > 0:
        fatal.append("所有时间戳都无法解析，字段映射可能错了")
    elif scanned and bad_ts / scanned > 0.5:
        fatal.append(f"超过一半的时间戳无效（{bad_ts}/{scanned}）")

    # 警告项
    if not has_name_col:
        warns.append(
            "未找到昵称字段（sender_name / 昵称 / 群昵称），飞书表里只能显示 wxid。"
            "重新导出时请开启「昵称解析」，或额外导出群成员表做 join。"
        )
    elif scanned and empty_sender / scanned > 0.05:
        warns.append(f"发送者为空占比 {empty_sender/scanned:.1%}（{empty_sender}/{scanned}）")

    if has_name_col and scanned and wxid_like_sender / scanned > 0.5:
        warns.append(
            f"昵称未解析：{wxid_like_sender/scanned:.0%} 的发送者仍是 wxid，"
            f"重新导出时请开启「昵称解析」"
        )
    if scanned and bad_type / scanned > 0.2:
        warns.append(
            f"类型未归一：{bad_type/scanned:.0%} 的记录类型是原始数字或未知值，"
            f"需要 normalize.py 做映射"
        )
    bad_identity = {k: v for k, v in sender_status.items()
                    if k not in ("resolved", "system")}
    if bad_identity:
        total_bad = sum(bad_identity.values())
        detail = ", ".join(
            f"{k}={v}" for k, v in
            sorted(bad_identity.items(), key=lambda x: -x[1])[:3]
        )
        warns.append(
            f"发送者身份未确认：{total_bad} 条（{detail}）。这些记录会显示为"
            f"「未知发送者」，需要时回阶段 A 重导或从联系人表补齐。"
        )

    if "quote_content" not in idx:
        warns.append("没有引用字段，引用关系无法还原（可接受，但会丢信息）")
    if "media_path" not in idx:
        warns.append("没有附件路径字段，附件阶段无法执行")

    # 时间范围与断档
    if ts_list:
        ts_list.sort()
        first = datetime.fromtimestamp(ts_list[0], TZ)
        last = datetime.fromtimestamp(ts_list[-1], TZ)
        stats["time_range"] = {
            "first": first.strftime("%Y-%m-%d %H:%M:%S"),
            "last": last.strftime("%Y-%m-%d %H:%M:%S"),
            "span_days": (last - first).days,
        }
        # 断档检测
        gaps = []
        for a, b in zip(ts_list, ts_list[1:]):
            if b - a > 30 * 86400:
                gaps.append((datetime.fromtimestamp(a, TZ).strftime("%Y-%m-%d"),
                             datetime.fromtimestamp(b, TZ).strftime("%Y-%m-%d"),
                             (b - a) // 86400))
        if gaps:
            stats["gaps"] = [f"{g[0]} → {g[1]} 空 {g[2]} 天" for g in gaps[:5]]
            warns.append(f"检测到 {len(gaps)} 处超过 30 天的消息断档")

    if sample:
        stats["sample"] = []
        n = len(records)
        if n <= sample:
            picks = list(range(n))
        else:
            picks = [int(i * n / sample) for i in range(sample)]
        for i in picks:
            r = records[i]
            if not isinstance(r, dict):
                continue
            stats["sample"].append({
                "talker": r.get(idx.get("talker")),
                "sender": r.get(idx.get("sender_name")) or r.get(idx.get("sender_wxid")),
                "ts": r.get(idx.get("ts")),
                "type": r.get(idx.get("type")),
                "content": str(r.get(idx.get("content")) or "")[:60],
            })

    return {"fatal": fatal, "warns": warns, "stats": stats}


# ---------------------------------------------------------------- 输出

def print_report(res, path):
    st = res["stats"]
    print("=" * 68)
    print("导出数据体检")
    print("=" * 68)
    print(f"文件: {path}")

    meta = st.get("meta") or {}
    if meta:
        print(f"导出器: {meta.get('format')} v{meta.get('exporter_version')}")
        print(f"会话  : {meta.get('chat_name')} ({meta.get('chat_type')})")

    if st:
        print(f"记录数: {st.get('records')}   大小: {st.get('file_size', 0)/1024:.1f} KB")
        if st.get("sender_status"):
            sstats = ", ".join(f"{k}={v}" for k, v in st["sender_status"].items())
            print(f"身份解析: {sstats}")
        if st.get("mapped_fields"):
            print(f"已识别字段: {', '.join(st['mapped_fields'])}")
        if st.get("missing_fields"):
            print(f"未识别字段: {', '.join(st['missing_fields'])}")
        if st.get("type_distribution"):
            dist = ", ".join(f"{k}={v}" for k, v in st["type_distribution"].items())
            print(f"类型分布: {dist}")
        if st.get("time_range"):
            tr = st["time_range"]
            print(f"时间范围: {tr['first']} ~ {tr['last']}  (跨度 {tr['span_days']} 天)")
        if st.get("gaps"):
            print("断档:")
            for g in st["gaps"]:
                print(f"  - {g}")

    if st.get("sample"):
        print("\n抽样:")
        for i, s in enumerate(st["sample"], 1):
            print(f"  {i}. [{s.get('type')}] {s.get('sender')} @ {s.get('ts')}")
            print(f"     {s.get('content')}")

    print()
    if res["fatal"]:
        print("【致命问题】")
        for x in res["fatal"]:
            print(f"  [致命] {x}")
    if res["warns"]:
        print("【警告】")
        for x in res["warns"]:
            print(f"  [警告] {x}")
    if not res["fatal"] and not res["warns"]:
        print("通过：没有发现问题，可以进入清洗阶段。")
    elif not res["fatal"]:
        if any("昵称" in w for w in res["warns"]):
            print("\n结论：可以继续，但建议先处理上述警告（尤其是昵称未解析）。")
        else:
            print("\n结论：可以继续，上述警告可在清洗阶段处理。")
    else:
        print("\n结论：不建议继续。请回阶段 A 调整导出设置后重新导出。")

    print("=" * 68)


def main():
    ap = argparse.ArgumentParser(description="微信导出数据体检")
    ap.add_argument("path", help="导出的 JSON 或 CSV 文件")
    ap.add_argument("--talker", help="期望的会话 ID，例如 12345678@chatroom")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--sample", type=int, default=0, help="输出 N 条抽样")
    args = ap.parse_args()

    res = validate(args.path, args.talker, args.sample)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print_report(res, args.path)

    if res["fatal"]:
        return 2
    if res["warns"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
