#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信聊天记录 -> 飞书多维表格：可视化配置中心

一个窗口把「导出之后」要填的参数全管了：飞书应用凭证、多维表格位置、
字段/分表策略、附件策略、写入节奏、时间范围。配完点一下就能自检连通性，
不用再手改 .env 和 JSON。

设计约束：
  * 零第三方依赖，只用标准库（tkinter / urllib / ctypes）
  * 密钥用 Windows DPAPI 加密后落盘，不写明文
  * 配置落在 %LOCALAPPDATA%\\wechat-to-feishu\\config.json
  * 可作为独立窗口运行，也可被 wechat-chat-export 启动器挂载

用法:
    python feishu_config_gui.py
    python feishu_config_gui.py --export-dir "D:\\wx_export\\某业务群"
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

# ---------------------------------------------------------------- 常量

APP_TITLE = "微信 → 飞书 导入配置"
FONT = "Microsoft YaHei UI"
MONO = "Consolas"

CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "wechat-to-feishu"
CONFIG_PATH = CONFIG_DIR / "config.json"

if getattr(sys, "frozen", False):
    # 单文件 EXE 的 __file__ 位于临时解包目录，用户文件应相对 EXE 定位。
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    SKILL_SCRIPTS = PROJECT_ROOT / "scripts"
else:
    SKILL_SCRIPTS = Path(__file__).resolve().parent
    PROJECT_ROOT = SKILL_SCRIPTS.parent

DOMAINS = {
    "feishu": ("飞书（国内版 feishu.cn）", "https://open.feishu.cn"),
    "lark": ("Lark（国际版 larksuite.com）", "https://open.larksuite.com"),
}

DEFAULTS = {
    # 飞书应用
    "domain": "feishu",
    "app_id": "",
    "app_secret": "",
    # 多维表格
    "base_token": "",
    "table_id": "",
    "table_name_template": "微信记录_{YYYY-MM}",
    "sharding": "auto",
    "create_missing_fields": True,
    # 导入策略
    "batch_size": 200,
    "sleep_ms": 300,
    "max_retries": 5,
    "attachment_mode": "hybrid",
    "inline_max_mb": 20,
    "dedup_key": "msg_id",
    "time_start": "",
    "time_end": "",
    # 运行
    "export_dir": "",
    "state_db": "",
    "log_level": "INFO",
    "dry_run": False,
}

COLLECT_ORDER = [
    "domain", "app_id", "app_secret",
    "base_token", "table_id", "table_name_template", "sharding",
    "create_missing_fields",
    "batch_size", "sleep_ms", "max_retries",
    "attachment_mode", "inline_max_mb", "dedup_key", "time_start", "time_end",
    "export_dir", "state_db", "log_level", "dry_run",
]

CN_FIELD_TYPE = {
    1: "多行文本", 2: "数字", 3: "单选", 4: "多选", 5: "日期",
    7: "复选框", 11: "人员", 13: "电话", 15: "超链接", 17: "附件",
    18: "单向关联", 19: "查找引用", 20: "公式", 21: "双向关联",
    1001: "创建时间", 1002: "最后更新时间", 1003: "创建人",
    1004: "修改人", 1005: "自动编号",
}

ERR_HINT = {
    10014: "App ID 不对，或者登录的不是同一个租户，重新复制一次。",
    10003: "请求格式错，检查 App Secret 前后有没有多余空格。",
    10013: "App Secret 不对，回开发者后台重新生成一次。",
    91403: "应用没被加为这个文档的协作者。回飞书：Base 右上角 ⋯ → 添加文档协作者 → 搜应用名称（不是 App ID）→ 可编辑。",
    99991672: "应用权限（scope）没开，或者改了没发版。回开发者后台勾权限，然后创建版本并发布。",
    99991663: "token 无效或过期，通常是应用版本没发布成功。",
    1254045: "字段名不存在，表结构和模板对不上。",
    1254005: "Base 或数据表 ID 不对，检查地址栏那一段。",
}


# ---------------------------------------------------------------- DPAPI

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _from_blob(blob: _BLOB) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def dpapi_encrypt(text: str) -> str:
    """用当前 Windows 用户的 DPAPI 加密。换机器/换用户解不开，这正是我们要的。"""
    if not text:
        return ""
    try:
        blob_in, _keep = _to_blob(text.encode("utf-8"))
        blob_out = _BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 1,
            ctypes.byref(blob_out),
        )
        if not ok:
            raise OSError("CryptProtectData failed")
        return "dpapi:" + base64.b64encode(_from_blob(blob_out)).decode("ascii")
    except Exception:
        return "plain:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


def dpapi_decrypt(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith("dpapi:"):
        try:
            raw = base64.b64decode(stored[6:])
            blob_in, _keep = _to_blob(raw)
            blob_out = _BLOB()
            ok = ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(blob_in), None, None, None, None, 1,
                ctypes.byref(blob_out),
            )
            if not ok:
                return ""
            return _from_blob(blob_out).decode("utf-8")
        except Exception:
            return ""
    if stored.startswith("plain:"):
        try:
            return base64.b64decode(stored[6:]).decode("utf-8")
        except Exception:
            return ""
    return stored


# ---------------------------------------------------------------- 配置读写

def guess_export_dir() -> str:
    """找本机最像「刚导出的聊天文件夹」的目录，省一次浏览。"""
    roots = [
        PROJECT_ROOT / "exports",
        Path.cwd() / "exports",
        Path.home() / "exports",
    ]
    best, best_mtime = "", -1.0
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                if (child / "chat_full_parsed.json").is_file():
                    m = child.stat().st_mtime
                    if m > best_mtime:
                        best, best_mtime = str(child), m
        except OSError:
            continue
    return best


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if not CONFIG_PATH.is_file():
        cfg["export_dir"] = guess_export_dir()
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg["export_dir"] = guess_export_dir()
        return cfg
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k == "app_secret":
                cfg[k] = dpapi_decrypt(str(v))
            elif k in DEFAULTS:
                cfg[k] = v
    if not cfg.get("export_dir"):
        cfg["export_dir"] = guess_export_dir()
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    out = dict(cfg)
    out["app_secret"] = dpapi_encrypt(str(cfg.get("app_secret") or ""))
    out["_saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CONFIG_PATH.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except Exception:
        pass


def env_path_candidates() -> list[Path]:
    here = SKILL_SCRIPTS
    return [
        here / ".env",
        here.parent / ".env",
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ]


def read_env_file(path: Path) -> dict:
    data = {}
    if not path.is_file():
        return data
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def write_env_file(path: Path, cfg: dict) -> None:
    api = DOMAINS.get(cfg.get("domain"), DOMAINS["feishu"])[1]
    lines = [
        "# 由 feishu_config_gui.py 生成，改配置请回 GUI 改",
        "# ⚠️ 含密钥，不要发人、不要提交仓库",
        "",
        f"FEISHU_APP_ID={cfg.get('app_id', '')}",
        f"FEISHU_APP_SECRET={cfg.get('app_secret', '')}",
        f"FEISHU_BASE_TOKEN={cfg.get('base_token', '')}",
        f"FEISHU_TABLE_ID={cfg.get('table_id', '')}",
        f"FEISHU_BASE_URL={'' if api.endswith('open.feishu.cn') else api}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- HTTP

def api_base(domain: str) -> str:
    return DOMAINS.get(domain, DOMAINS["feishu"])[1] + "/open-apis"


def http_json(method, url, token=None, payload=None, timeout=30):
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except Exception:
            return {"code": e.code, "msg": body[:300]}
    except Exception as e:
        return {"code": -1, "msg": f"{type(e).__name__}: {e}"}


def parse_base_url(text: str):
    """从整条 Base 链接里抠出 (base_token, table_id)。也接受裸 token。"""
    text = (text or "").strip()
    if not text:
        return "", ""
    token = ""
    table_id = ""
    m = re.search(r"/base/([A-Za-z0-9_-]{6,})", text)
    if m:
        token = m.group(1)
    m2 = re.search(r"[?&]table=([A-Za-z0-9]+)", text)
    if m2:
        table_id = m2.group(1)
    if not token and re.fullmatch(r"[A-Za-z0-9_-]{6,}", text):
        token = text
    return token, table_id


# ---------------------------------------------------------------- 导出目录体检

def scan_export(folder: str) -> dict:
    """轻量统计：条数、时间范围、媒体数量、体积。不加载整份 JSON 到内存以外的地方。"""
    info = {"ok": False, "error": "", "count": 0, "first": "", "last": "",
            "media": 0, "media_bytes": 0, "path": folder}
    p = Path(folder or "")
    if not p.is_dir():
        info["error"] = "目录不存在"
        return info
    json_file = p / "chat_full_parsed.json"
    if not json_file.is_file():
        info["error"] = "目录里没有 chat_full_parsed.json"
        return info
    try:
        raw = json.loads(json_file.read_text(encoding="utf-8"))
    except Exception as e:
        info["error"] = f"JSON 解析失败：{e}"
        return info
    msgs = raw.get("messages") if isinstance(raw, dict) else raw
    if not isinstance(msgs, list):
        info["error"] = "JSON 里找不到 messages 数组"
        return info
    info["count"] = len(msgs)
    times = []
    for m in msgs:
        ts = m.get("create_time") or m.get("timestamp") or m.get("time")
        if isinstance(ts, str) and ts.isdigit():
            ts = int(ts)
        if isinstance(ts, (int, float)) and ts > 0:
            times.append(int(ts))
    if times:
        fmt = "%Y-%m-%d %H:%M"
        info["first"] = datetime.fromtimestamp(min(times)).strftime(fmt)
        info["last"] = datetime.fromtimestamp(max(times)).strftime(fmt)
    media_dir = p / "media"
    if media_dir.is_dir():
        for f in media_dir.rglob("*"):
            if f.is_file():
                info["media"] += 1
                try:
                    info["media_bytes"] += f.stat().st_size
                except OSError:
                    pass
    info["ok"] = True
    return info


def human_size(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB"):
        if n < step:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= step
    return f"{n:.1f} TB"


# ---------------------------------------------------------------- 界面

class FeishuConfigUI:
    """把整个配置面板挂到任意 Tk/Toplevel 上。"""

    def __init__(self, root, on_close=None):
        self.root = root
        self.on_close = on_close
        self.q = queue.Queue()
        self.proc = None
        self.tables = []
        self.cfg = load_config()
        self.vars = {}

        self.root.title(APP_TITLE)
        self.root.geometry("980x840")
        self.root.minsize(880, 720)
        try:
            self.root.configure(bg="#f5f6f8")
        except Exception:
            pass

        style = ttk.Style(self.root)
        for theme in ("vista", "winnative", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure(".", font=(FONT, 10))
        style.configure("TNotebook.Tab", padding=(18, 8))
        style.configure("Hint.TLabel", foreground="#8a9099", font=(FONT, 9))
        style.configure("Head.TLabel", font=(FONT, 11, "bold"), foreground="#1f2329")

        self.root.grid_rowconfigure(1, weight=3)
        self.root.grid_rowconfigure(2, weight=2)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_notebook()
        self._build_log()
        self._build_footer()

        self.apply_cfg(self.cfg)
        self.root.after(120, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self.log("配置中心已就绪。", "info")
        if CONFIG_PATH.is_file():
            self.log(f"已载入配置：{CONFIG_PATH}", "info")
        else:
            self.log("还没有配置文件，填完点「保存配置」即可生成。", "warn")

    # ---------- 布局骨架

    def _build_header(self):
        head = tk.Frame(self.root, bg="#3370ff", height=64)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_propagate(False)
        tk.Label(
            head, text="微信 → 飞书 导入配置", bg="#3370ff", fg="white",
            font=(FONT, 16, "bold"),
        ).pack(side="left", padx=22, pady=(12, 0))
        tk.Label(
            head,
            text="填完这一页，导出、清洗、建表、推送都不用再碰命令行",
            bg="#3370ff", fg="#d6e4ff", font=(FONT, 9),
        ).pack(side="left", padx=(0, 0), pady=(18, 0))
        tk.Button(
            head, text="打开开发者后台", command=lambda: webbrowser.open(
                "https://open.feishu.cn/app"
            ),
            bg="#2b62e0", fg="white", relief="flat", cursor="hand2",
            activebackground="#245bdb", activeforeground="white",
            font=(FONT, 9), padx=12, pady=4, bd=0,
        ).pack(side="right", padx=18, pady=14)

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.grid(row=1, column=0, sticky="nsew", padx=14, pady=(12, 6))
        for title, builder in (
            ("① 飞书应用", self._page_app),
            ("② 多维表格", self._page_base),
            ("③ 导入策略", self._page_policy),
            ("④ 运行", self._page_run),
        ):
            frame = ttk.Frame(self.nb, padding=18)
            self.nb.add(frame, text=title)
            builder(frame)

    def _build_log(self):
        box = ttk.LabelFrame(self.root, text=" 运行日志 ", padding=(10, 6, 10, 8))
        box.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 6))
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            box, height=9, wrap="word", font=(MONO, 9),
            bg="#1f2329", fg="#d7dbe0", insertbackground="#d7dbe0",
            relief="flat", padx=10, pady=8,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_configure("ok", foreground="#4ac26b")
        self.log_text.tag_configure("err", foreground="#ff6b6b")
        self.log_text.tag_configure("warn", foreground="#ffc53d")
        self.log_text.tag_configure("info", foreground="#a9b4c2")
        self.log_text.tag_configure("step", foreground="#5ec8f0")
        self.log_text.configure(state="disabled")

        bar = ttk.Frame(box)
        bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(bar, text="清空日志", command=self.clear_log).pack(side="right")
        ttk.Button(
            bar, text="复制全部",
            command=lambda: self._copy_log(),
        ).pack(side="right", padx=(0, 8))
        self.status_var = tk.StringVar(value="未连接")
        ttk.Label(
            bar, textvariable=self.status_var, style="Hint.TLabel",
        ).pack(side="left")

    def _build_footer(self):
        foot = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        foot.grid(row=3, column=0, sticky="ew")
        foot.grid_columnconfigure(0, weight=1)

        ttk.Button(foot, text="从 .env 导入", command=self.on_import_env).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(foot, text="导出 .env", command=self.on_export_env).grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(foot, text="连接自检", command=self.on_test).grid(
            row=0, column=3, padx=(0, 8)
        )
        self.btn_save = tk.Button(
            foot, text="保存配置", command=self.on_save,
            bg="#3370ff", fg="white", relief="flat", cursor="hand2",
            activebackground="#245bdb", activeforeground="white",
            font=(FONT, 10, "bold"), padx=22, pady=6, bd=0,
        )
        self.btn_save.grid(row=0, column=4)

    # ---------- 各页面

    def _page_app(self, p):
        p.grid_columnconfigure(1, weight=1)

        ttk.Label(p, text="飞书自建应用", style="Head.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            p,
            text="开发者后台 → 凭证与基础信息，复制 App ID 和 App Secret。"
                 "Secret 会被 Windows 加密后本地保存，不回显明文、不上传。",
            style="Hint.TLabel", wraplength=760,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

        ttk.Label(p, text="服务域名").grid(row=2, column=0, sticky="w", pady=6)
        self.vars["domain"] = tk.StringVar()
        self.cb_domain = ttk.Combobox(
            p, textvariable=self.vars["domain"], state="readonly", width=34,
            values=[v[0] for v in DOMAINS.values()],
        )
        self.cb_domain.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=6)
        ttk.Label(
            p, text="国内版选「飞书」；用的是 larksuite.com 才选 Lark。",
            style="Hint.TLabel",
        ).grid(row=2, column=2, sticky="w", padx=(12, 0))

        ttk.Label(p, text="App ID").grid(row=3, column=0, sticky="w", pady=6)
        self.vars["app_id"] = tk.StringVar()
        ttk.Entry(p, textvariable=self.vars["app_id"], width=46).grid(
            row=3, column=1, sticky="ew", padx=(12, 0), pady=6
        )
        ttk.Label(p, text="cli_ 开头", style="Hint.TLabel").grid(
            row=3, column=2, sticky="w", padx=(12, 0)
        )

        ttk.Label(p, text="App Secret").grid(row=4, column=0, sticky="w", pady=6)
        secret_row = ttk.Frame(p)
        secret_row.grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=6)
        secret_row.grid_columnconfigure(0, weight=1)
        self.vars["app_secret"] = tk.StringVar()
        self.ent_secret = ttk.Entry(
            secret_row, textvariable=self.vars["app_secret"], width=46, show="•"
        )
        self.ent_secret.grid(row=0, column=0, sticky="ew")
        self.vars["show_secret"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            secret_row, text="显示", variable=self.vars["show_secret"],
            command=self._toggle_secret,
        ).grid(row=0, column=1, padx=(10, 0))
        ttk.Label(p, text="应用凭证里的 Secret", style="Hint.TLabel").grid(
            row=4, column=2, sticky="w", padx=(12, 0)
        )

        ttk.Separator(p).grid(row=5, column=0, columnspan=3, sticky="ew", pady=18)

        ttk.Label(p, text="必开的两组权限", style="Head.TLabel").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        ttk.Label(
            p,
            text="权限管理 → 开通以下两项，然后「创建版本 → 发布」，审核通过才生效：\n"
                 "    · 查看、评论、编辑和管理多维表格  (bitable:app)\n"
                 "    · 获取应用信息                    (application:application:readonly)\n"
                 "改完权限必须重新发版，不重新发版等于没改。",
            justify="left", foreground="#4e5969",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(0, 14))

        ttk.Label(
            p,
            text="⚠ 还有一步最容易漏：应用建好后，到目标 Base 右上角 ⋯ → "
                 "添加文档协作者 → 搜索应用名称 → 给「可编辑」。\n"
                 "   不做这步，后面所有读写都会报 91403。",
            foreground="#d4380d", wraplength=760, justify="left",
        ).grid(row=8, column=0, columnspan=3, sticky="w")

    def _page_base(self, p):
        p.grid_columnconfigure(1, weight=1)

        ttk.Label(p, text="落在哪个多维表格", style="Head.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            p,
            text="直接把浏览器地址栏那一整条粘进来，token 和 table_id 会自动拆出来。",
            style="Hint.TLabel", wraplength=760,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

        ttk.Label(p, text="Base 链接 / Token").grid(row=2, column=0, sticky="w", pady=6)
        self.vars["base_input"] = tk.StringVar()
        ent = ttk.Entry(p, textvariable=self.vars["base_input"], width=60)
        ent.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=6)
        ent.bind("<FocusOut>", lambda e: self.on_parse_base())
        ent.bind("<Return>", lambda e: self.on_parse_base())
        ttk.Button(p, text="解析", command=self.on_parse_base).grid(
            row=2, column=2, padx=(10, 0)
        )

        ttk.Label(p, text="base_token").grid(row=3, column=0, sticky="w", pady=6)
        self.vars["base_token"] = tk.StringVar()
        ttk.Entry(p, textvariable=self.vars["base_token"], width=60).grid(
            row=3, column=1, sticky="ew", padx=(12, 0), pady=6
        )
        ttk.Label(p, text="bascn 开头", style="Hint.TLabel").grid(
            row=3, column=2, sticky="w", padx=(10, 0)
        )

        ttk.Label(p, text="数据表").grid(row=4, column=0, sticky="w", pady=6)
        self.vars["table_id"] = tk.StringVar()
        self.cb_table = ttk.Combobox(
            p, textvariable=self.vars["table_id"], width=58, values=[],
        )
        self.cb_table.grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=6)
        ttk.Label(
            p, text="先连接自检再选；留空则按模板新建",
            style="Hint.TLabel",
        ).grid(row=4, column=2, sticky="w", padx=(10, 0))

        ttk.Label(p, text="新表命名").grid(row=5, column=0, sticky="w", pady=6)
        self.vars["table_name_template"] = tk.StringVar()
        ttk.Entry(p, textvariable=self.vars["table_name_template"], width=60).grid(
            row=5, column=1, sticky="ew", padx=(12, 0), pady=6
        )
        ttk.Label(p, text="{YYYY-MM} 会被替换成月份", style="Hint.TLabel").grid(
            row=5, column=2, sticky="w", padx=(10, 0)
        )

        ttk.Label(p, text="分表策略").grid(row=6, column=0, sticky="w", pady=6)
        self.vars["sharding"] = tk.StringVar()
        ttk.Combobox(
            p, textvariable=self.vars["sharding"], state="readonly", width=58,
            values=["auto（按条数自动决定）", "单表（全塞一张）",
                    "按月分表", "按月 + 按会话"],
        ).grid(row=6, column=1, sticky="ew", padx=(12, 0), pady=6)

        self.vars["create_missing_fields"] = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            p, text="目标表缺字段时自动按模板补建（不会删改已有字段）",
            variable=self.vars["create_missing_fields"],
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(14, 0))

        ttk.Separator(p).grid(row=8, column=0, columnspan=3, sticky="ew", pady=16)
        ttk.Label(p, text="字段模板", style="Head.TLabel").grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        ttk.Label(
            p,
            text="发送时间 / 日期 / 发送者 / 消息类型 / 内容 / 引用内容 / 附件 / "
                 "附件链接 / 是否本人 / 消息ID / 原始类型   —— 共 11 列\n"
                 "模板文件：assets/bitable-template.json，列顺序和类型都在里面写死。",
            style="Hint.TLabel", justify="left", wraplength=760,
        ).grid(row=10, column=0, columnspan=3, sticky="w")

    def _page_policy(self, p):
        p.grid_columnconfigure(1, weight=1)

        ttk.Label(p, text="写入节奏", style="Head.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )

        ttk.Label(p, text="每批条数").grid(row=1, column=0, sticky="w", pady=5)
        self.vars["batch_size"] = tk.IntVar(value=200)
        ttk.Spinbox(
            p, from_=1, to=200, textvariable=self.vars["batch_size"], width=10,
        ).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=5)
        ttk.Label(p, text="飞书单次上限 200，别改大", style="Hint.TLabel").grid(
            row=1, column=2, sticky="w", padx=(10, 0)
        )

        ttk.Label(p, text="批间隔 (ms)").grid(row=2, column=0, sticky="w", pady=5)
        self.vars["sleep_ms"] = tk.IntVar(value=300)
        ttk.Spinbox(
            p, from_=0, to=5000, increment=50,
            textvariable=self.vars["sleep_ms"], width=10,
        ).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=5)
        ttk.Label(p, text="撞限流就调到 500~800", style="Hint.TLabel").grid(
            row=2, column=2, sticky="w", padx=(10, 0)
        )

        ttk.Label(p, text="最大重试").grid(row=3, column=0, sticky="w", pady=5)
        self.vars["max_retries"] = tk.IntVar(value=5)
        ttk.Spinbox(
            p, from_=0, to=10, textvariable=self.vars["max_retries"], width=10,
        ).grid(row=3, column=1, sticky="w", padx=(12, 0), pady=5)
        ttk.Label(p, text="91403 不重试，直接停", style="Hint.TLabel").grid(
            row=3, column=2, sticky="w", padx=(10, 0)
        )

        ttk.Separator(p).grid(row=4, column=0, columnspan=3, sticky="ew", pady=14)

        ttk.Label(p, text="附件策略", style="Head.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )
        ttk.Label(p, text="处理方式").grid(row=6, column=0, sticky="w", pady=5)
        self.vars["attachment_mode"] = tk.StringVar()
        ttk.Combobox(
            p, textvariable=self.vars["attachment_mode"], state="readonly", width=46,
            values=[
                "混合：图片内嵌 + 大文件云盘链接",
                "全部内嵌附件字段",
                "只写文字，附件跳过",
            ],
        ).grid(row=6, column=1, sticky="w", padx=(12, 0), pady=5)

        ttk.Label(p, text="内嵌大小上限").grid(row=7, column=0, sticky="w", pady=5)
        size_row = ttk.Frame(p)
        size_row.grid(row=7, column=1, sticky="w", padx=(12, 0), pady=5)
        self.vars["inline_max_mb"] = tk.IntVar(value=20)
        ttk.Spinbox(
            size_row, from_=1, to=200, textvariable=self.vars["inline_max_mb"], width=8,
        ).pack(side="left")
        ttk.Label(size_row, text="MB   超过就走云盘，不占 Base 附件配额").pack(
            side="left", padx=(8, 0)
        )

        ttk.Separator(p).grid(row=8, column=0, columnspan=3, sticky="ew", pady=14)

        ttk.Label(p, text="去重与范围", style="Head.TLabel").grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )
        ttk.Label(p, text="去重键").grid(row=10, column=0, sticky="w", pady=5)
        self.vars["dedup_key"] = tk.StringVar(value="msg_id")
        ttk.Combobox(
            p, textvariable=self.vars["dedup_key"], state="readonly", width=46,
            values=["msg_id", "server_id", "md5(内容+时间+发送者)"],
        ).grid(row=10, column=1, sticky="w", padx=(12, 0), pady=5)
        ttk.Label(p, text="同一批跑三遍，结果必须一致", style="Hint.TLabel").grid(
            row=10, column=2, sticky="w", padx=(10, 0)
        )

        ttk.Label(p, text="时间范围").grid(row=11, column=0, sticky="w", pady=5)
        range_row = ttk.Frame(p)
        range_row.grid(row=11, column=1, sticky="w", padx=(12, 0), pady=5)
        self.vars["time_start"] = tk.StringVar()
        self.vars["time_end"] = tk.StringVar()
        ttk.Entry(range_row, textvariable=self.vars["time_start"], width=14).pack(side="left")
        ttk.Label(range_row, text="  至  ").pack(side="left")
        ttk.Entry(range_row, textvariable=self.vars["time_end"], width=14).pack(side="left")
        ttk.Label(range_row, text="   YYYY-MM-DD，留空=全部").pack(side="left")

        self.vars["dry_run"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            p, text="演练模式：只统计不写入（第一次建议先勾上）",
            variable=self.vars["dry_run"],
        ).grid(row=12, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def _page_run(self, p):
        p.grid_columnconfigure(1, weight=1)

        ttk.Label(p, text="数据来源与执行", style="Head.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )

        ttk.Label(p, text="导出目录").grid(row=1, column=0, sticky="w", pady=5)
        self.vars["export_dir"] = tk.StringVar()
        ttk.Entry(p, textvariable=self.vars["export_dir"], width=58).grid(
            row=1, column=1, sticky="ew", padx=(12, 0), pady=5
        )
        ttk.Button(p, text="浏览", command=self.on_pick_export).grid(
            row=1, column=2, padx=(10, 0)
        )

        ttk.Label(p, text="断点状态库").grid(row=2, column=0, sticky="w", pady=5)
        self.vars["state_db"] = tk.StringVar()
        ttk.Entry(p, textvariable=self.vars["state_db"], width=58).grid(
            row=2, column=1, sticky="ew", padx=(12, 0), pady=5
        )
        ttk.Label(p, text="留空=导出目录下 .push_state.db", style="Hint.TLabel").grid(
            row=2, column=2, sticky="w", padx=(10, 0)
        )

        ttk.Label(p, text="日志级别").grid(row=3, column=0, sticky="w", pady=5)
        self.vars["log_level"] = tk.StringVar(value="INFO")
        ttk.Combobox(
            p, textvariable=self.vars["log_level"], state="readonly", width=12,
            values=["DEBUG", "INFO", "WARN", "ERROR"],
        ).grid(row=3, column=1, sticky="w", padx=(12, 0), pady=5)

        ttk.Separator(p).grid(row=4, column=0, columnspan=3, sticky="ew", pady=14)

        ttk.Label(p, text="开跑之前先体检", style="Head.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        scan_row = ttk.Frame(p)
        scan_row.grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Button(scan_row, text="扫描导出目录", command=self.on_scan).pack(side="left")
        self.scan_var = tk.StringVar(value="还没扫描")
        ttk.Label(
            scan_row, textvariable=self.scan_var, style="Hint.TLabel",
        ).pack(side="left", padx=(14, 0))

        ttk.Separator(p).grid(row=7, column=0, columnspan=3, sticky="ew", pady=16)

        ttk.Label(p, text="执行", style="Head.TLabel").grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )
        run_row = ttk.Frame(p)
        run_row.grid(row=9, column=0, columnspan=3, sticky="w")

        ttk.Button(
            run_row, text="① 初始化表结构", command=self.on_init_table,
        ).pack(side="left")
        ttk.Button(
            run_row, text="② 开始导入", command=self.on_start_import,
        ).pack(side="left", padx=(10, 0))
        self.btn_stop = ttk.Button(
            run_row, text="中止", command=self.on_stop, state="disabled",
        )
        self.btn_stop.pack(side="left", padx=(10, 0))

        ttk.Label(
            p,
            text="建议顺序：连接自检 → 扫描目录 → 演练模式跑 100 条 → 关掉演练跑全量。\n"
                 "执行引擎（normalize / feishu_init / feishu_push）属阶段二，脚本不在时会明确告诉你缺哪个。",
            style="Hint.TLabel", justify="left", wraplength=760,
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(16, 0))

    # ---------- 配置收集 / 回填

    def _domain_map(self):
        return {v[0]: k for k, v in DOMAINS.items()}

    ATTR_DISPLAY = {
        "hybrid": "混合：图片内嵌 + 大文件云盘链接",
        "inline": "全部内嵌附件字段",
        "text_only": "只写文字，附件跳过",
    }

    SHARD_DISPLAY = {
        "auto": "auto（按条数自动决定）",
        "single": "单表（全塞一张）",
        "month": "按月分表",
        "month_chat": "按月 + 按会话",
    }

    def collect(self) -> dict:
        cfg = {}
        for key in COLLECT_ORDER:
            var = self.vars.get(key)
            if var is None:
                cfg[key] = DEFAULTS.get(key)
                continue
            try:
                cfg[key] = var.get()
            except tk.TclError:
                cfg[key] = DEFAULTS.get(key)

        cfg["domain"] = self._domain_map().get(cfg.get("domain"), "feishu")

        rev = {v: k for k, v in self.ATTR_DISPLAY.items()}
        cfg["attachment_mode"] = rev.get(cfg.get("attachment_mode"), "hybrid")

        rev2 = {v: k for k, v in self.SHARD_DISPLAY.items()}
        cfg["sharding"] = rev2.get(cfg.get("sharding"), "auto")

        for k in ("batch_size", "sleep_ms", "max_retries", "inline_max_mb"):
            try:
                cfg[k] = int(cfg.get(k) or 0)
            except (TypeError, ValueError):
                cfg[k] = DEFAULTS[k]

        for k in ("time_start", "time_end", "app_id", "app_secret",
                  "base_token", "table_id", "export_dir", "state_db"):
            cfg[k] = str(cfg.get(k) or "").strip()
        return cfg

    def apply_cfg(self, cfg: dict):
        cfg = {**DEFAULTS, **cfg}
        self.vars["domain"].set(
            DOMAINS.get(cfg.get("domain"), DOMAINS["feishu"])[0]
        )
        for key in ("app_id", "app_secret", "base_token", "table_id",
                    "table_name_template", "export_dir", "state_db",
                    "time_start", "time_end"):
            if key in self.vars:
                self.vars[key].set(cfg.get(key) or "")
        self.vars["sharding"].set(
            self.SHARD_DISPLAY.get(cfg.get("sharding"), self.SHARD_DISPLAY["auto"])
        )
        self.vars["attachment_mode"].set(
            self.ATTR_DISPLAY.get(
                cfg.get("attachment_mode"), self.ATTR_DISPLAY["hybrid"]
            )
        )
        self.vars["batch_size"].set(cfg.get("batch_size") or 200)
        self.vars["sleep_ms"].set(cfg.get("sleep_ms") or 0)
        self.vars["max_retries"].set(cfg.get("max_retries") or 0)
        self.vars["inline_max_mb"].set(cfg.get("inline_max_mb") or 20)
        self.vars["create_missing_fields"].set(
            bool(cfg.get("create_missing_fields", True))
        )
        self.vars["dry_run"].set(bool(cfg.get("dry_run", False)))
        self.vars["log_level"].set(cfg.get("log_level") or "INFO")
        if cfg.get("base_token"):
            self.vars["base_input"].set(cfg["base_token"])
        self.vars["dedup_key"].set(cfg.get("dedup_key") or "msg_id")

    # ---------- 日志

    def log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _copy_log(self):
        text = self.log_text.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log("日志已复制到剪贴板。", "ok")

    def _toggle_secret(self):
        self.ent_secret.configure(show="" if self.vars["show_secret"].get() else "•")

    # ---------- 线程与队列

    def _spawn(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log(item[1], item[2] if len(item) > 2 else "info")
                elif kind == "status":
                    self.status_var.set(item[1])
                elif kind == "tables":
                    self.tables = item[1]
                    labels = [
                        f"{t.get('name')}  ·  {t.get('table_id')}"
                        for t in self.tables
                    ]
                    self.cb_table.configure(values=labels)
                    if labels and not self.vars["table_id"].get():
                        self.cb_table.current(0)
                elif kind == "done":
                    self.root.after(0, item[1])
        except queue.Empty:
            pass
        except Exception as e:
            self.log(f"界面回调异常：{e}", "err")
        try:
            self.root.after(120, self._poll)
        except Exception:
            pass

    def _on_window_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno(APP_TITLE, "导入还在跑，确定关掉窗口？"):
                return
        if self.on_close:
            self.on_close()
        else:
            self.root.destroy()

    # ---------- 解析 Base 链接

    def on_parse_base(self):
        raw = self.vars["base_input"].get().strip()
        if not raw:
            return
        token, table_id = parse_base_url(raw)
        if not token:
            self.log("没从这段文字里认出 base_token，检查是不是把整条 /base/ 链接粘全了。", "warn")
            return
        self.vars["base_token"].set(token)
        if table_id:
            self.vars["table_id"].set(table_id)
        self.log(f"已解析 base_token={token}", "ok")
        if table_id:
            self.log(f"已解析 table_id={table_id}", "ok")

    # ---------- 选目录

    def on_pick_export(self):
        init = self.vars["export_dir"].get().strip()
        if not init or not Path(init).is_dir():
            # 优先用自动探测到的目录；都没有就落回项目根的 exports
            init = guess_export_dir()
        if not init or not Path(init).is_dir():
            fallback = PROJECT_ROOT / "exports"
            try:
                fallback.mkdir(parents=True, exist_ok=True)
            except OSError:
                fallback = PROJECT_ROOT
            init = str(fallback)
        path = filedialog.askdirectory(
            parent=self.root, title="选择导出的聊天文件夹", initialdir=init,
        )
        if path:
            self.vars["export_dir"].set(path)
            self.log(f"导出目录：{path}", "info")

    # ---------- 扫描

    def on_scan(self):
        folder = self.vars["export_dir"].get().strip()
        if not folder:
            messagebox.showinfo(APP_TITLE, "先选导出目录。")
            return
        self.status_var.set("扫描中…")
        self._spawn(self._scan_worker, folder)

    def _scan_worker(self, folder):
        self.q.put(("log", f"扫描 {folder} …"))
        info = scan_export(folder)
        if not info["ok"]:
            self.q.put(("log", f"扫描失败：{info['error']}", "err"))
            self.q.put(("status", "扫描失败"))
            return
        batch = max(1, int(self.collect().get("batch_size") or 200))
        batches = (info["count"] + batch - 1) // batch
        self.q.put(("log", f"消息 {info['count']} 条，媒体 {info['media']} 个 "
                           f"（{human_size(info['media_bytes'])}）", "ok"))
        if info["first"]:
            self.q.put(("log", f"时间范围 {info['first']} ~ {info['last']}", "ok"))
        self.q.put(("log", f"按每批 {batch} 条算，共 {batches} 批。", "info"))
        text = (f"{info['count']} 条消息 · {info['media']} 个附件 · "
                f"{human_size(info['media_bytes'])}")
        self.q.put(("done", lambda: self.scan_var.set(text)))
        self.q.put(("status", "扫描完成"))

    # ---------- 连接自检

    def on_test(self):
        cfg = self.collect()
        if not cfg["app_id"] or not cfg["app_secret"]:
            messagebox.showwarning(APP_TITLE, "先填 App ID 和 App Secret。")
            return
        if not cfg["base_token"]:
            messagebox.showwarning(APP_TITLE, "先填 Base token（或粘整条链接点解析）。")
            return
        self.status_var.set("自检中…")
        self.log("─" * 40, "info")
        self._spawn(self._test_worker, cfg)

    def _test_worker(self, cfg):
        api = api_base(cfg["domain"])
        put = self.q.put

        put(("log", "[1/4] 获取 tenant_access_token …", "step"))
        res = http_json(
            "POST", api + "/auth/v3/tenant_access_token/internal",
            payload={"app_id": cfg["app_id"], "app_secret": cfg["app_secret"]},
        )
        if res.get("code") != 0:
            self._explain(res, "获取 token")
            put(("status", "自检失败"))
            return
        token = res["tenant_access_token"]
        put(("log", f"  拿到 token，有效期 {res.get('expire', 0) // 60} 分钟", "ok"))

        put(("log", "[2/4] 读取多维表格元信息 …", "step"))
        res = http_json("GET", f"{api}/bitable/v1/apps/{cfg['base_token']}", token)
        if res.get("code") != 0:
            self._explain(res, "读取 Base")
            put(("log", "  排查顺序：① token 从 /base/ 后复制的吗？"
                        "② 应用加为文档协作者了吗？③ 版本发布了吗？", "warn"))
            put(("status", "自检失败"))
            return
        app = (res.get("data") or {}).get("app") or {}
        put(("log", f"  Base 名称：{app.get('name')}", "ok"))

        put(("log", "[3/4] 读取数据表列表 …", "step"))
        res = http_json(
            "GET", f"{api}/bitable/v1/apps/{cfg['base_token']}/tables?page_size=100",
            token,
        )
        if res.get("code") != 0:
            self._explain(res, "读取数据表")
            put(("status", "自检失败"))
            return
        items = (res.get("data") or {}).get("items") or []
        if not items:
            put(("log", "  Base 里还没有数据表，稍后可用「初始化表结构」新建。", "warn"))
        else:
            put(("log", f"  共 {len(items)} 张表", "ok"))
            for t in items:
                put(("log", f"    - {t.get('name')}  ({t.get('table_id')})", "info"))
        put(("tables", items))

        tid = cfg.get("table_id") or (items[0]["table_id"] if items else "")
        if tid:
            put(("log", f"[4/4] 读取字段（{tid}）…", "step"))
            res = http_json(
                "GET",
                f"{api}/bitable/v1/apps/{cfg['base_token']}/tables/{tid}/fields?page_size=100",
                token,
            )
            if res.get("code") != 0:
                self._explain(res, "读取字段")
            else:
                fields = (res.get("data") or {}).get("items") or []
                put(("log", f"  共 {len(fields)} 个字段", "ok"))
                for f in fields:
                    t = f.get("type")
                    put(("log", f"    - {f.get('field_name'):<14} "
                               f"type={t:<5} {CN_FIELD_TYPE.get(t, '')}", "info"))
                names = {f.get("field_name") for f in fields}
                need = {"发送时间", "发送者", "消息类型", "内容", "消息ID"}
                missing = sorted(need - names)
                if missing:
                    put(("log", f"  缺少模板字段：{', '.join(missing)}"
                               f"（可勾选自动补建）", "warn"))

        put(("log", "自检通过：凭证有效、Base 可读。", "ok"))
        put(("status", "自检通过"))

    def _explain(self, res, stage):
        code = res.get("code")
        msg = res.get("msg") or res.get("message") or ""
        self.q.put(("log", f"  ✗ {stage}失败  code={code}  msg={msg}", "err"))
        hint = ERR_HINT.get(code)
        if hint:
            self.q.put(("log", f"    → {hint}", "warn"))

    # ---------- 保存 / env

    def on_save(self):
        cfg = self.collect()
        problems = []
        if not cfg["app_id"]:
            problems.append("App ID 为空")
        elif not cfg["app_id"].startswith("cli_"):
            problems.append("App ID 一般以 cli_ 开头，确认没粘错")
        if not cfg["app_secret"]:
            problems.append("App Secret 为空")
        if not cfg["base_token"]:
            problems.append("base_token 为空")
        if cfg["batch_size"] > 200:
            problems.append("每批条数不能超过 200")

        if problems:
            messagebox.showwarning(
                APP_TITLE, "还有几项要处理：\n\n· " + "\n· ".join(problems)
            )
            self.log("保存未完成：" + "；".join(problems), "warn")
            return

        try:
            save_config(cfg)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"写入配置失败：{e}")
            return
        self.cfg = cfg
        self.log(f"配置已保存 → {CONFIG_PATH}", "ok")
        self.log("密钥用 Windows DPAPI 加密存储，换机器需重填。", "info")
        self.status_var.set("配置已保存")
        messagebox.showinfo(
            APP_TITLE,
            f"配置已保存到：\n{CONFIG_PATH}\n\n"
            "接下来点「连接自检」验证凭证，通过后就能跑导入了。",
        )

    def on_import_env(self):
        for path in env_path_candidates():
            if path.is_file():
                env = read_env_file(path)
                if not env:
                    continue
                if env.get("FEISHU_APP_ID"):
                    self.vars["app_id"].set(env["FEISHU_APP_ID"])
                if env.get("FEISHU_APP_SECRET"):
                    self.vars["app_secret"].set(env["FEISHU_APP_SECRET"])
                if env.get("FEISHU_BASE_TOKEN"):
                    tok = env["FEISHU_BASE_TOKEN"]
                    self.vars["base_token"].set(tok)
                    self.vars["base_input"].set(tok)
                if env.get("FEISHU_TABLE_ID"):
                    self.vars["table_id"].set(env["FEISHU_TABLE_ID"])
                url = (env.get("FEISHU_BASE_URL") or "").strip()
                if "larksuite" in url:
                    self.vars["domain"].set(DOMAINS["lark"][0])
                self.log(f"已从 {path} 导入凭证。", "ok")
                return
        messagebox.showinfo(
            APP_TITLE,
            "没找到可用的 .env。\n\n找过这些位置：\n"
            + "\n".join(str(p) for p in env_path_candidates()),
        )

    def on_export_env(self):
        cfg = self.collect()
        if not cfg["app_id"] or not cfg["app_secret"]:
            messagebox.showwarning(APP_TITLE, "先填 App ID 和 App Secret。")
            return
        target = filedialog.asksaveasfilename(
            parent=self.root, title="导出 .env",
            initialdir=str(SKILL_SCRIPTS if SKILL_SCRIPTS.is_dir() else PROJECT_ROOT),
            initialfile=".env",
            defaultextension="",
        )
        if not target:
            return
        try:
            write_env_file(Path(target), cfg)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"写入失败：{e}")
            return
        self.log(f".env 已导出 → {target}", "ok")
        self.log("注意：这是明文密钥文件，别发给别人、别提交仓库。", "warn")

    # ---------- 执行引擎

    def _engine_path(self, name) -> Path:
        return SKILL_SCRIPTS / name

    def _run_engine(self, script, extra_args=None):
        cfg = self.collect()
        path = self._engine_path(script)
        if not path.is_file():
            self.log(f"缺少执行脚本：{path}", "err")
            messagebox.showinfo(
                APP_TITLE,
                f"执行引擎还没到位：\n\n{path}\n\n"
                "配置部分（凭证、Base、策略）已经能保存和自检，"
                "建表和推送脚本属于下一阶段，接上后这里直接调用。",
            )
            return

        if not CONFIG_PATH.is_file():
            save_config(cfg)
        self.log(f"启动 {script} …", "step")
        cmd = [sys.executable, str(path), "--config", str(CONFIG_PATH)]
        if extra_args:
            cmd += list(extra_args)
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(SKILL_SCRIPTS), creationflags=0x08000000,
            )
        except Exception as e:
            self.log(f"启动失败：{e}", "err")
            return
        self.btn_stop.configure(state="normal")
        self.status_var.set(f"{script} 运行中")
        self._spawn(self._pump_proc, self.proc)

    def _pump_proc(self, proc):
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line:
                self.q.put(("log", line, "info"))
        code = proc.wait()
        level = "ok" if code == 0 else "err"
        self.q.put(("log", f"{proc.args[1] if len(proc.args) > 1 else ''} 退出码 {code}", level))
        self.q.put(("status", "完成" if code == 0 else "失败"))
        self.q.put(("done", lambda: self.btn_stop.configure(state="disabled")))

    def on_init_table(self):
        self._run_engine("feishu_init.py")

    def on_start_import(self):
        cfg = self.collect()
        if cfg.get("dry_run"):
            self.log("演练模式已开启：只统计不写入。", "warn")
        self._run_engine("feishu_push.py")

    def on_stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.log("已请求中止。", "warn")
        self.btn_stop.configure(state="disabled")


def run_standalone(export_dir=None):
    root = tk.Tk()
    ui = FeishuConfigUI(root)
    if export_dir:
        ui.vars["export_dir"].set(export_dir)
    root.mainloop()
    return ui


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    export_dir = None
    args = sys.argv[1:]
    if "--export-dir" in args:
        i = args.index("--export-dir")
        if i + 1 < len(args):
            export_dir = args[i + 1]
    run_standalone(export_dir)


def _fatal(title, text):
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback

        tb = traceback.format_exc()
        log = CONFIG_DIR / "_gui_error.log"
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            log.write_text(tb, encoding="utf-8")
        except Exception:
            log = None
        _fatal(
            "配置面板启动失败",
            "详细信息" + (f"已写入：\n{log}\n\n------ 摘要 ------\n" if log else "：\n")
            + tb.strip()[-1400:],
        )
        raise
