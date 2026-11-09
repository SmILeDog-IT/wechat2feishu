#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信环境探测器（只读）

扫描本机微信安装信息、数据目录、账号、数据库与附件体量，判断版本与加密状态。
不读取任何消息内容，不修改任何文件。

用法:
    python3 detect_env.py
    python3 detect_env.py --json
    python3 detect_env.py --json --out report.json
    python3 detect_env.py --root "E:\\wx\\Documents"

仅使用 Python 标准库。
"""

import argparse
import json
import os
import platform
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- 工具函数

def human_size(n):
    if n is None:
        return "-"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def safe_listdir(path):
    try:
        return os.listdir(path)
    except (OSError, PermissionError):
        return []


def dir_size(path, limit_files=200000):
    """递归统计目录大小与文件数，带文件数上限防止卡死。"""
    total = 0
    count = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                count += 1
            except OSError:
                pass
            if count >= limit_files:
                return total, count
    return total, count


def read_header(path, n=16):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError:
        return None


SQLITE_MAGIC = b"SQLite format 3\x00"


def is_encrypted(path):
    """返回 True / False / None(无法读取)"""
    head = read_header(path, 16)
    if head is None:
        return None
    if head == SQLITE_MAGIC:
        return False
    return True


# ---------------------------------------------------------------- 注册表

def _reg_read(root, subkey, value):
    try:
        import winreg
        with winreg.OpenKey(root, subkey) as k:
            v, _ = winreg.QueryValueEx(k, value)
            return v
    except Exception:
        return None


def detect_install():
    """返回 {'product': 'Weixin'|'WeChat', 'path': ..., 'version': ...}"""
    result = {"product": None, "path": None, "version": None}
    if platform.system() != "Windows":
        return result

    try:
        import winreg
        candidates = [
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tencent\Weixin", "Weixin"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tencent\Weixin", "Weixin"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Tencent\Weixin", "Weixin"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tencent\WeChat", "WeChat"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tencent\WeChat", "WeChat"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Tencent\WeChat", "WeChat"),
        ]
        for hive, sub, product in candidates:
            path = _reg_read(hive, sub, "InstallPath")
            if path and os.path.isdir(path):
                result["product"] = product
                result["path"] = path
                result["version"] = detect_exe_version(path, product)
                return result
    except Exception:
        pass

    # 回退：常见安装位置
    for product, folder in (("Weixin", "Weixin"), ("WeChat", "WeChat")):
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            p = os.path.join(base, "Tencent", folder)
            if os.path.isdir(p):
                result.update(product=product, path=p,
                              version=detect_exe_version(p, product))
                return result
    return result


def detect_exe_version(folder, product):
    """读取主程序文件版本。"""
    exe = "Weixin.exe" if product == "Weixin" else "WeChat.exe"
    full = os.path.join(folder, exe)
    if not os.path.exists(full):
        return None
    try:
        import subprocess
        ps = (
            "(Get-Item -LiteralPath '{0}').VersionInfo.FileVersion"
        ).format(full.replace("'", "''"))
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        v = (out.stdout or "").strip()
        return v or None
    except Exception:
        return None


# ---------------------------------------------------------------- 数据目录

SKIP_DIRS = {
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "node_modules",
    "appdata", "intel", "perflogs", "recovery", "msocache",
}


def candidate_roots(user_hint=None):
    """返回可能存在微信数据根目录的上级路径列表。"""
    roots = []
    if user_hint:
        roots.append(user_hint)

    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    for p in (docs, os.path.join(home, "文档"), home):
        if p and p not in roots:
            roots.append(p)

    # 其它盘符的常见位置
    for drive in "CDEFGH":
        for sub in ("Documents", "文档", "wx\\Documents", "WeChat", "微信"):
            p = f"{drive}:\\{sub}"
            if os.path.isdir(p):
                roots.append(p)
    return roots


def find_data_dirs(user_hint=None, max_depth=4):
    """查找 xwechat_files / WeChat Files 目录。"""
    found = []
    targets = {"xwechat_files": "4.x", "wechat files": "3.x"}

    def scan(base, depth):
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(base))
        except (OSError, PermissionError):
            return
        for e in entries:
            try:
                if not e.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            low = e.name.lower()
            if low in targets:
                found.append((e.path, targets[low]))
                continue
            if low in SKIP_DIRS:
                continue
            if low.startswith("$") or low.startswith("."):
                continue
            scan(e.path, depth + 1)

    for root in candidate_roots(user_hint):
        if not os.path.isdir(root):
            continue
        # 根目录本身可能就是
        low = os.path.basename(root).lower()
        if low in targets:
            found.append((root, targets[low]))
            continue
        scan(root, 0)

    # 去重
    seen = set()
    uniq = []
    for p, v in found:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append((p, v))
    return uniq


# ---------------------------------------------------------------- 账号分析

def analyze_4x(account_dir):
    """微信 4.x 账号目录分析。"""
    info = {
        "layout": "4.x",
        "path": account_dir,
        "db_files": [],
        "attachment_dirs": {},
        "has_db_storage": False,
        "has_sqlite": False,
    }
    db_storage = os.path.join(account_dir, "db_storage")
    info["has_db_storage"] = os.path.isdir(db_storage)
    info["has_sqlite"] = os.path.isdir(os.path.join(account_dir, "sqlite"))

    search_roots = [db_storage] if info["has_db_storage"] else []
    search_roots.append(os.path.join(account_dir, "sqlite"))
    search_roots.append(account_dir)

    seen = set()
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for cur, dirs, files in os.walk(root):
            # 只下钻两层，避免扫到附件
            rel_depth = cur[len(root):].count(os.sep)
            if rel_depth >= 2:
                dirs[:] = []
            for f in files:
                if not f.endswith(".db"):
                    continue
                full = os.path.join(cur, f)
                if full in seen:
                    continue
                seen.add(full)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                info["db_files"].append({
                    "name": os.path.relpath(full, account_dir),
                    "size": size,
                    "encrypted": is_encrypted(full),
                })

    for sub in ("msg\\attach", "msg\\file", "msg\\video", "msg\\image"):
        p = os.path.join(account_dir, sub)
        if os.path.isdir(p):
            size, count = dir_size(p)
            info["attachment_dirs"][sub] = {"size": size, "files": count}
    return info


def analyze_3x(account_dir):
    """微信 3.x 账号目录分析。"""
    info = {
        "layout": "3.x",
        "path": account_dir,
        "db_files": [],
        "attachment_dirs": {},
        "has_msg_dir": os.path.isdir(os.path.join(account_dir, "Msg")),
        "has_filestorage": os.path.isdir(os.path.join(account_dir, "FileStorage")),
    }
    msg_dir = os.path.join(account_dir, "Msg")
    if os.path.isdir(msg_dir):
        for cur, dirs, files in os.walk(msg_dir):
            for f in files:
                if not f.endswith(".db"):
                    continue
                full = os.path.join(cur, f)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                info["db_files"].append({
                    "name": os.path.relpath(full, account_dir),
                    "size": size,
                    "encrypted": is_encrypted(full),
                })

    fs = os.path.join(account_dir, "FileStorage")
    for sub in ("Image", "Video", "File", "CustomEmotion", "MsgAttach"):
        p = os.path.join(fs, sub)
        if os.path.isdir(p):
            size, count = dir_size(p)
            info["attachment_dirs"][sub] = {"size": size, "files": count}
    return info


def analyze_root(root_path, layout):
    """分析数据根目录下的所有账号。"""
    accounts = []
    for name in safe_listdir(root_path):
        full = os.path.join(root_path, name)
        if not os.path.isdir(full):
            continue
        if name.lower() in ("all_users", "backup"):
            continue
        if layout == "4.x":
            if not re.match(r"^wxid_.+_[0-9a-f]{4}$", name, re.I):
                # 兼容不带后缀的目录
                if not name.lower().startswith("wxid_"):
                    continue
            accounts.append(analyze_4x(full))
        else:
            if not name.lower().startswith("wxid_"):
                continue
            accounts.append(analyze_3x(full))

    total_size, total_files = dir_size(root_path)
    return {
        "path": root_path,
        "layout": layout,
        "total_size": total_size,
        "total_files": total_files,
        "accounts": accounts,
    }


# ---------------------------------------------------------------- 报告

def build_report(user_hint=None):
    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "install": detect_install(),
        "data_roots": [],
        "warnings": [],
    }

    roots = find_data_dirs(user_hint)
    if not roots:
        report["warnings"].append(
            "未找到微信数据目录。可能原因：从未在该机登录、文档目录被重定向、或无访问权限。"
        )

    for path, layout in roots:
        report["data_roots"].append(analyze_root(path, layout))

    # 汇总判断
    versions = {r["layout"] for r in report["data_roots"]}
    if versions == {"4.x"}:
        report["summary"] = {"wechat_version": "4.x", "encrypted": None}
    elif versions == {"3.x"}:
        report["summary"] = {"wechat_version": "3.x", "encrypted": None}
    elif versions:
        report["summary"] = {"wechat_version": "mixed", "encrypted": None,
                              "note": "同时存在 3.x 与 4.x 数据目录，确认用哪一个"}
    else:
        report["summary"] = {"wechat_version": "unknown", "encrypted": None}

    enc_flags = []
    msg_count = 0
    for r in report["data_roots"]:
        for acc in r["accounts"]:
            for db in acc["db_files"]:
                if "message" in db["name"].lower() or "msg" in db["name"].lower():
                    msg_count += 1
                    if db["encrypted"] is not None:
                        enc_flags.append(db["encrypted"])
    if enc_flags:
        report["summary"]["encrypted"] = all(enc_flags)
        report["summary"]["message_db_count"] = msg_count
    return report


def print_human(rep):
    print("=" * 68)
    print("微信环境探测报告")
    print("=" * 68)

    inst = rep["install"]
    print(f"\n[安装]")
    print(f"  产品     : {inst.get('product') or '未检测到'}")
    print(f"  路径     : {inst.get('path') or '-'}")
    print(f"  版本     : {inst.get('version') or '未知'}")

    print(f"\n[运行环境]")
    print(f"  系统     : {rep['os']['system']} {rep['os']['release']} ({rep['os']['machine']})")
    print(f"  Python   : {rep['python']['version']}  {rep['python']['executable']}")

    if not rep["data_roots"]:
        print(f"\n[数据目录] 未找到")
    for r in rep["data_roots"]:
        print(f"\n[数据目录] {r['path']}")
        print(f"  布局     : {r['layout']}")
        print(f"  总大小   : {human_size(r['total_size'])} / {r['total_files']} 个文件")
        for acc in r["accounts"]:
            print(f"\n  账号: {os.path.basename(acc['path'])}")
            if acc["db_files"]:
                print(f"    数据库:")
                for db in sorted(acc["db_files"], key=lambda x: -x["size"])[:10]:
                    enc = {True: "加密", False: "明文", None: "不可读"}[db["encrypted"]]
                    print(f"      {db['name']:<46} {human_size(db['size']):>10}  [{enc}]")
            if acc["attachment_dirs"]:
                print(f"    附件:")
                for k, v in acc["attachment_dirs"].items():
                    print(f"      {k:<24} {human_size(v['size']):>10} / {v['files']} 个文件")

    s = rep.get("summary", {})
    print(f"\n[结论]")
    print(f"  微信版本 : {s.get('wechat_version')}")
    if s.get("encrypted") is not None:
        print(f"  数据库   : {'加密（需工具解密）' if s['encrypted'] else '明文可直读'}")
    if s.get("message_db_count"):
        print(f"  消息相关库: {s['message_db_count']} 个（含索引、媒体、公众号库）")

    if rep["warnings"]:
        print(f"\n[警告]")
        for w in rep["warnings"]:
            print(f"  - {w}")

    print("\n下一步：")
    print("  1. 备份数据目录（整份复制到独立路径）")
    print("  2. 按 references/02-extraction-tools.md 选工具")
    print("  3. 导出后跑 validate_export.py 体检")
    print("=" * 68)


def main():
    ap = argparse.ArgumentParser(description="微信环境探测器（只读）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--out", help="把 JSON 写入文件")
    ap.add_argument("--root", help="手动指定数据根目录或其上级目录")
    args = ap.parse_args()

    rep = build_report(args.root)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(f"报告已写入: {args.out}")

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_human(rep)

    if not rep["data_roots"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
