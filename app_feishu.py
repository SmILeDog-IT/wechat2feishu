#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
微信聊天导出工具 · 飞书增强版启动器

做法：不改 wechat-chat-export 的任何源码文件，继承它的主窗口，在底部空白处
挂一个「飞书导入 →」按钮和一个同名菜单。点开就是完整的飞书配置面板。

为什么不用官方 EXE：那是 PyInstaller 单文件包，页面改不进去。源码版 GUI 是
tkinter 写的，所以这里用继承注入，官方升级时只要重新拉源码即可，本文件不动。

启动:
    venv\Scripts\pythonw.exe app_feishu.py
"""

from __future__ import annotations

import ctypes
import multiprocessing
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
IS_FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else HERE
ERROR_LOG = APP_DIR / "_launcher_error.log"


# 上游源码与启动器同级；EXE 模式下模块由 PyInstaller 打包，不再从磁盘查找
SRC_DIR = HERE

# 飞书配置面板（零依赖单文件）可能的落点，按顺序找第一个存在的
GUI_CANDIDATES = [
    HERE / "scripts" / "feishu_config_gui.py",
    HERE / "feishu_config_gui.py",
]
_env_dir = os.environ.get("WECHAT_TO_FEISHU_SCRIPTS", "").strip()
if _env_dir:
    GUI_CANDIDATES.insert(0, Path(_env_dir) / "feishu_config_gui.py")


def _fatal(title: str, text: str) -> None:
    """最底层的弹窗，不依赖 tkinter，import 阶段出错也能报出来。"""
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except Exception:
        pass


def _die(msg: str) -> None:
    _fatal("启动失败", msg)
    raise SystemExit(1)


def _locate_gui() -> Path:
    for cand in GUI_CANDIDATES:
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    _die(
        "找不到飞书配置面板 feishu_config_gui.py。\n\n"
        "找过这些位置：\n"
        + "\n".join(str(p) for p in GUI_CANDIDATES)
        + "\n\n可以设环境变量 WECHAT_TO_FEISHU_SCRIPTS 指向它所在的目录。"
    )
    raise SystemExit(1)


def _boot() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    if not IS_FROZEN and not (HERE / "app.py").is_file():
        _die(
            f"找不到上游导出工具源码：\n{HERE / 'app.py'}\n\n"
            "请把本启动器放在 wechat-chat-export 源码目录下（与 app.py 同级）。"
        )

    # EXE 中模块由 PyInstaller 加载，无需在解包目录寻找 .py 源文件。
    if not IS_FROZEN:
        gui_file = _locate_gui()
        sys.path.insert(0, str(SRC_DIR))
        sys.path.insert(0, str(gui_file.parent))

    import tkinter as tk

    import app as wce
    import feishu_config_gui as feishu

    class FeishuApp(wce.App):
        """官方主窗口 + 一个飞书入口，其余行为完全继承。"""

        def __init__(self):
            super().__init__()
            self._feishu_win = None
            self._feishu_ui = None
            try:
                self.title(wce.APP_TITLE + " · 飞书版")
            except Exception:
                pass
            self._install_menu()
            self._install_button()
            self.log("飞书增强已加载：点左下角「飞书导入」配置并推送。")

        def _install_menu(self):
            try:
                bar = tk.Menu(self)
                bar.add_command(label="飞书导入", command=self.open_feishu)
                self.configure(menu=bar)
            except Exception:
                pass

        def _install_button(self):
            bottom = self._find_bottom_frame()
            if bottom is None:
                return
            try:
                self.feishu_btn = tk.Button(
                    bottom,
                    text="飞书导入 →",
                    command=self.open_feishu,
                    bg="#3370ff", fg="white", relief="flat", cursor="hand2",
                    activebackground="#245bdb", activeforeground="white",
                    font=("Microsoft YaHei UI", 9, "bold"),
                    padx=14, pady=4, bd=0,
                )
                self.feishu_btn.grid(row=0, column=0, sticky="w")
            except Exception:
                pass

        def _find_bottom_frame(self):
            """底部按钮条是 pad 里 grid row=10 的那个 Frame，按位置找，不靠变量名。"""
            try:
                for pad in self.winfo_children():
                    for child in pad.winfo_children():
                        info = child.grid_info()
                        if info and str(info.get("row")) == "10":
                            return child
            except Exception:
                pass
            return None

        def open_feishu(self):
            if self._feishu_win is not None:
                try:
                    if self._feishu_win.winfo_exists():
                        self._feishu_win.deiconify()
                        self._feishu_win.lift()
                        self._feishu_win.focus_force()
                        return
                except Exception:
                    pass

            win = tk.Toplevel(self)
            win.transient(self)
            self._feishu_win = win
            self._feishu_ui = feishu.FeishuConfigUI(win, on_close=win.destroy)

            # 直接沿用主窗口当前的导出目录，少点一次「浏览」
            try:
                out = self.out_var.get().strip()
                if out and not self._feishu_ui.vars["export_dir"].get():
                    self._feishu_ui.vars["export_dir"].set(out)
            except Exception:
                pass

    FeishuApp().mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        _boot()
    except SystemExit:
        raise
    except BaseException:
        tb = traceback.format_exc()
        try:
            ERROR_LOG.write_text(tb, encoding="utf-8")
        except Exception:
            pass
        _fatal(
            "启动失败",
            "启动器崩了，详细信息已写入：\n"
            f"{ERROR_LOG}\n\n"
            "------ 摘要 ------\n"
            + tb.strip()[-1400:],
        )
        raise
