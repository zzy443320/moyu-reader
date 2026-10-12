# -*- coding: utf-8 -*-
"""
摸鱼阅读器 —— 桌面悬浮小说浮窗
================================

一个始终置顶、半透明、可随手拖拽的阅读小窗。
专门为「上班摸鱼看小说」设计。

快捷键
------
    鼠标左键拖拽      移动浮窗（标题栏 / 状态栏 / 正文区都可以拖）
    拖窗口边缘或角落  缩放窗口大小（鼠标移到边上会变成缩放箭头）
    双击标题栏        最大化 / 还原（也可按 F11）
    鼠标滚轮          上下滚动
    空格              暂停 / 继续 自动滚动
    Ctrl + ↑ / ↓      字号 变大 / 变小
    Ctrl + ← / →      滚动速度 变慢 / 变快
    Ctrl + 滚轮       文字透明度
    Ctrl + D          切换「伪装模式」（隐藏标题栏与工具栏，只留正文）
    Ctrl + H          一键隐藏 / 恢复（老板键）
    Ctrl + O          打开本地 txt 小说
    Ctrl + B          打开书库
    Ctrl + Q / Esc    关闭浮窗（也可点右上角红色的 ✕）

依赖：仅 Python 标准库 tkinter（Windows 自带 Python 即含）
"""

from __future__ import annotations

import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont

APP_DIR = Path(__file__).resolve().parent
BOOKS_DIR = APP_DIR / "books"
CONFIG_PATH = APP_DIR / "config.json"

# ---------------------------------------------------------------- 主题配色
# 默认走「低对比灰」——不刺眼、不像弹窗，混在 VS Code / 终端旁边不显眼
BG = "#F2F1EE"          # 极浅灰（伪装成普通侧栏/面板）
FG = "#3A3A3C"          # 正文深灰
SUBTLE = "#9C9A96"      # 次要文字 / 边框
ACCENT = "#6E6E73"      # 强调色（中性灰，取消原来的暖棕）
BAR_BG = "#EAE9E5"      # 工具条底色

# 备选配色，可在 config.json 里把 "theme" 改成对应键名
THEMES = {
    "灰": {"BG": "#F2F1EE", "FG": "#3A3A3C", "SUBTLE": "#9C9A96",
           "ACCENT": "#6E6E73", "BAR_BG": "#EAE9E5"},
    "纸": {"BG": "#FBF8F1", "FG": "#2B2B2B", "SUBTLE": "#8A8578",
           "ACCENT": "#B5651D", "BAR_BG": "#F3EEE3"},
    "暗": {"BG": "#1E1F22", "FG": "#C8C8C8", "SUBTLE": "#5C5D61",
           "ACCENT": "#7A7C81", "BAR_BG": "#26272B"},
    "豆沙": {"BG": "#F0EBE6", "FG": "#403A36", "SUBTLE": "#9B918A",
             "ACCENT": "#7D6E63", "BAR_BG": "#E7E1DB"},
}

DEFAULT_CONFIG = {
    "alpha": 0.85,          # 整窗不透明度（低调一些）
    "font_size": 15,
    "line_spacing": 8,      # 行距（像素）
    "auto_speed": 0.6,      # 自动滚动速度（像素/帧）
    "width": 430,
    "height": 560,
    "geometry": "",         # 记住上次窗口位置
    "book": "",             # 上次读的书
    "progress": {},         # {书名: 滚动位置比例}
    "theme": "灰",          # 配色方案
    "edge_dock": True,      # 是否开启「侧边收条 / 鼠标移入才展开」
    "edge_side": "left",    # 收条贴哪一边：left / right
    "edge_width": 6,        # 收条宽度（像素）
    "edge_alpha": 0.18,     # 收条状态下的不透明度（约等于藏起来）
    "peek_delay": 150,      # 鼠标在收条上连续停留多久才展开（防误触）
    "hide_delay": 280,      # 鼠标连续离开窗口多久才收起（小一点更跟手）
}


class MoyuReader:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = self._load_config()

        # 配色：从主题表里取（允许 config.json 覆盖单项）
        theme = THEMES.get(self.cfg.get("theme"), THEMES["灰"])
        self.C_BG = self.cfg.get("bg") or theme["BG"]
        self.C_FG = self.cfg.get("fg") or theme["FG"]
        self.C_SUBTLE = self.cfg.get("subtle") or theme["SUBTLE"]
        self.C_ACCENT = self.cfg.get("accent") or theme["ACCENT"]
        self.C_BAR = self.cfg.get("bar_bg") or theme["BAR_BG"]

        self.books: list[dict] = []
        self.cur_book: str = ""
        self.paragraphs: list[str] = []
        self.auto_scrolling = False
        self.disguised = False
        self.hidden = False
        self._total_chars = 1
        self._save_job = None
        self._restore_token = 0

        # 侧边收条状态
        self._docked = False            # 当前是否处于收起状态
        self._full_h = int(self.cfg["height"])
        self._wd_job = None             # 看门狗定时器
        self._zone_since = 0.0
        self._chrome_visible = True
        self._chrome_job = None

        self._build_window()
        self._build_toolbar()
        self._build_text()
        self._bind_keys()

        self._load_library()
        self._restore_last_book()
        self._init_edge_dock()

        # 首次运行给一次操作提示，免得不知道怎么缩放/关闭
        if not self.cfg.get("seen_hint"):
            self.cfg["seen_hint"] = True
            self.root.after(700, lambda: self._toast(
                "拖边缘可缩放 · 双击标题栏最大化 · Ctrl+Q 关闭"))

    # ------------------------------------------------------------ 配置读写
    def _load_config(self) -> dict:
        cfg = dict(DEFAULT_CONFIG)
        if CONFIG_PATH.exists():
            try:
                cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
            except Exception:
                pass
        return cfg

    def _save_config(self) -> None:
        # 收起成细缝时不要记录这份几何尺寸，否则下次打开会只剩一条缝
        if not getattr(self, "_docked", False):
            self.cfg["geometry"] = self.root.geometry()
        if self.cur_book:
            # 存字符偏移（绝对位置），而不是比例
            self.cfg["progress"][self.cur_book] = self._scroll_anchor()
        self._write_config()

    def _write_config(self) -> None:
        try:
            CONFIG_PATH.write_text(
                json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # -------------------------------------------------------------- 窗口搭建
    def _build_window(self) -> None:
        r = self.root
        r.title("摸鱼阅读器")
        r.configure(bg=self.C_BG)
        r.minsize(260, 200)                    # 防止缩小到看不见
        r.overrideredirect(True)               # 无系统边框，更隐蔽
        r.attributes("-topmost", True)          # 始终置顶
        r.attributes("-alpha", self.cfg["alpha"])

        geo = self.cfg.get("geometry") or f"{self.cfg['width']}x{self.cfg['height']}+120+120"
        r.geometry(geo)

        # 如果上次的位置跑到屏幕外了，拉回可见区域（否则窗口会「失踪」）
        r.update_idletasks()
        self._clamp_into_screen()
        try:
            self._full_h = max(200, r.winfo_height())
        except Exception:
            pass

        # 无边框窗口需要自己实现拖动 + 阴影感的细边框
        outer = tk.Frame(r, bg=self.C_SUBTLE, bd=0)
        outer.pack(fill="both", expand=True)
        self.outer = outer
        self.body = tk.Frame(outer, bg=self.C_BG, bd=0)
        self.body.pack(fill="both", expand=True, padx=1, pady=1)

        self.maximized = False
        self._normal_geo = geo
        self._build_resize_grips(outer)

    def _clamp_into_screen(self) -> None:
        """确保窗口至少有一部分留在屏幕内，避免拖出屏幕后找不回来。"""
        try:
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            margin = 60

            if x > sw - margin:
                x = max(0, sw - w - margin)
            if y > sh - margin:
                y = max(0, sh - h - margin)
            if x < -(w - margin):
                x = 0
            if y < 0:
                y = 0

            if (x, y) != (self.root.winfo_x(), self.root.winfo_y()):
                self.root.geometry(f"+{int(x)}+{int(y)}")
        except Exception:
            pass

    # ------------------------------------------------------- 侧边收条模式
    # 单看门狗状态机：一个 100ms 的循环同时负责「收起态探测鼠标」和
    # 「展开态判定离开」，彻底避免多路计时器互相触发导致的抖动。
    #
    #   收起态：鼠标在收条热区连续停留 peek_delay 毫秒 -> 展开
    #   展开态：鼠标连续离开窗口 hide_delay 毫秒 -> 收起
    #           （拖动中 / 有弹窗 / 老板键隐藏时 一律不收）

    def _init_edge_dock(self) -> None:
        self._wd_job = None
        self._zone_since = 0.0        # 鼠标进入热区/离开窗口的时刻
        self._chrome_visible = True
        self._chrome_job = None
        self._anim_job = None         # 收/展动画定时器
        self._anim = None             # 当前动画状态
        self._anim_gen = 0            # 动画代数（防止被取消的旧回调写几何）
        self._anim_until = 0.0        # 动画静默期截止时刻（看门狗在此期间不查几何）
        self._expand_until = 0.0      # 展开保护期截止时刻
        # 「已激活」标志：首次打开保持展开，只有鼠标真正进来过一次之后，
        # 才开始「离开就收起」的自动收展。避免刚启动就被收走。
        self._armed = False
        # 看门狗常驻（负责鼠标探测 + 工具栏自动显隐）
        self.root.after(600, self._watchdog)

    def _toggle_dock(self) -> None:
        """工具栏 ⇥ 按钮 / Ctrl+E：开关侧边收条。"""
        self.cfg["edge_dock"] = not self.cfg.get("edge_dock", True)
        self._write_config()
        if self.cfg["edge_dock"]:
            self._toast("侧边收条已开启 · 鼠标移入才展开")
            self._drag_active = False
            self._full_h = max(200, self.root.winfo_height())
            if not self._docked:
                # 手动开启收条：视为用户已「接手」，立刻激活自动收展，
                # 否则首次打开不判离开的规则会让收条永远展开不回去。
                self._armed = True
                self._dock()
        else:
            self._armed = True
            self._undock()
            self._toast("侧边收条已关闭 · 常驻显示")

    def _edge_x(self, w: int) -> int:
        """收条状态下窗口应该贴在哪条边。"""
        sw = self.root.winfo_screenwidth()
        if self.cfg.get("edge_side", "right") == "left":
            return 0
        return max(0, sw - w)

    def _has_toplevel(self) -> bool:
        """书库/导入等弹窗开着时不许收起，否则弹窗会跟着消失。"""
        try:
            return any(w.winfo_ismapped()
                       for w in self.root.winfo_children()
                       if isinstance(w, tk.Toplevel))
        except Exception:
            return False

    # --- 宽度动画 -----------------------------------------------------
    # tkinter 改 geometry 是瞬间生效的，硬跳很突兀。这里用 ~14 帧插值，
    # 每帧 12ms，总长 160ms 左右，看起来就是「滑进去 / 滑出来」。
    #
    # 关键：动画期间必须让看门狗彻底闭嘴。看门狗每 45ms 要查 6 次 winfo_*
    # （都是同步 IPC 往返），一旦和动画的 geometry 抢通道，动画就会掉帧卡顿。
    # 用 _anim_until（动画预计结束时刻）来做「静默期」，比只看 _anim 标志更稳
    # ——因为 _anim 在最后一帧就被清空，但 Tk 侧的几何变更还没落盘。
    ANIM_FRAMES = 14
    ANIM_MS = 12

    def _anim_cancel(self) -> None:
        if self._anim_job:
            try:
                self.root.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None
        self._anim = None
        self._anim_until = 0.0
        # 每次取消都推进代数，让可能已经排进事件队列的旧回调自然失效
        self._anim_gen = getattr(self, "_anim_gen", 0) + 1

    def _animate_width(self, from_w: int, to_w: int, y: int, h: int,
                       alpha_from: float, alpha_to: float,
                       on_done=None) -> None:
        """把窗口宽度从 from_w 平滑变到 to_w，同时贴边 + 渐变透明度。"""
        self._anim_cancel()
        side_right = self.cfg.get("edge_side", "right") == "right"
        sw = self.root.winfo_screenwidth()
        self._anim = {
            "from": from_w, "to": to_w, "y": y, "h": h,
            "af": alpha_from, "at": alpha_to,
            "step": 0, "side_right": side_right, "sw": sw, "done": on_done,
            "gen": self._anim_gen,
        }
        # 静默期：动画全程 + 一点点余量，期间看门狗不做任何 winfo 查询
        self._anim_until = time.monotonic() + \
            (self.ANIM_FRAMES * self.ANIM_MS + 60) / 1000.0
        self._anim_tick(self._anim_gen)

    def _anim_tick(self, gen: int | None = None) -> None:
        a = self._anim
        if not a:
            return
        # 被更新的一轮动画顶替了：旧回调直接退出，绝不写几何
        if gen is not None and gen != a.get("gen"):
            return
        a["step"] += 1
        t = min(1.0, a["step"] / self.ANIM_FRAMES)
        # ease-out：开头快、结尾慢，观感更顺
        e = 1 - (1 - t) ** 2
        w = int(round(a["from"] + (a["to"] - a["from"]) * e))
        alpha = a["af"] + (a["at"] - a["af"]) * e

        x = (a["sw"] - w) if a["side_right"] else 0
        try:
            self.root.geometry(f"{max(1, w)}x{a['h']}+{x}+{a['y']}")
            self.root.attributes("-alpha", round(alpha, 3))
        except Exception:
            self._anim = None
            return

        if a["step"] >= self.ANIM_FRAMES:
            done = a["done"]
            self._anim = None
            self._anim_job = None
            if done:
                done()
            return
        g = a["gen"]
        self._anim_job = self.root.after(
            self.ANIM_MS, lambda: self._anim_tick(g))

    def _dock(self) -> None:
        """收起：留一条细缝贴在屏幕边上（平滑动画）。"""
        if self.hidden or not self.cfg.get("edge_dock"):
            return
        if getattr(self, "_drag_active", False) or self._has_toplevel():
            return
        if self._docked:
            return

        self._docked = True
        self._zone_since = 0.0
        self._expand_until = 0.0        # 收起时清掉保护期
        self._hide_chrome()          # 收起前先把工具栏藏掉，避免动画时闪

        w = max(3, int(self.cfg.get("edge_width", 6)))
        # minsize 会把窗口撑回 260 宽，动画前必须先放开限制
        self.root.minsize(1, 1)

        cur_w = max(1, self.root.winfo_width())
        # 收起时保持原有的顶部位置，不再强行拉高（避免高度突变也显突兀）
        y = self.root.winfo_y()
        h = max(200, self.root.winfo_height())

        self.root.attributes("-topmost", True)
        self._animate_width(
            cur_w, w, y, h,
            float(self.cfg["alpha"]), float(self.cfg.get("edge_alpha", 0.18)),
        )

    def _undock(self) -> None:
        """展开：平滑恢复窗口原来的大小与不透明度。"""
        if not self._docked:
            return
        # 先掐掉可能残留的收起动画，否则它挂着的 after 回调会在稍后
        # 用旧帧数据把窗口又改窄，展开就永远到不了目标宽度。
        self._anim_cancel()

        self._docked = False
        self._zone_since = 0.0
        # 展开后 900ms 内不做「离开」判定（详见 _watchdog 里的说明）
        self._expand_until = time.monotonic() + 0.9

        # 动画的起点：必须用 minsize 放开之前的真实宽度去量
        cur_w = max(1, self.root.winfo_width())
        self.root.minsize(260, 200)          # 恢复最小尺寸限制

        # 目标几何：用上次保存的尺寸
        tw, th = int(self.cfg["width"]), int(self._full_h)
        geo = self.cfg.get("geometry", "")
        try:
            head = geo.split("+")[0]
            if "x" in head:
                tw, th = (int(v) for v in head.split("x")[:2])
        except Exception:
            pass
        tw = max(260, tw)
        th = max(200, th)

        sw = self.root.winfo_screenwidth()
        side_right = self.cfg.get("edge_side", "right") == "right"
        # 纵向位置：尽量沿用收条时的 y，并保证整体在屏内
        sh = self.root.winfo_screenheight()
        y = max(0, min(self.root.winfo_y(), sh - th - 40))
        x = (sw - tw) if side_right else 0

        # 先把窗口撑到目标高度（高度突变发生在极窄时，几乎看不到）
        self.root.geometry(f"{cur_w}x{th}+{x if side_right else 0}+{y}")
        self.root.update_idletasks()

        self._full_h = th
        self.root.attributes("-topmost", True)
        self._animate_width(
            cur_w, tw, y, th,
            float(self.cfg.get("edge_alpha", 0.18)), float(self.cfg["alpha"]),
            on_done=self._show_chrome,
        )

    # --- 唯一的鼠标监视循环 -------------------------------------------
    def _watchdog(self) -> None:
        self._wd_job = self.root.after(45, self._watchdog)

        # 动画（含静默期）：不做任何几何查询，否则会和动画抢 IPC，肉眼就是卡顿
        if self._anim is not None or time.monotonic() < getattr(
                self, "_anim_until", 0.0):
            return

        try:
            px = self.root.winfo_pointerx()
            py = self.root.winfo_pointery()
        except Exception:
            return

        now = time.monotonic()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        w, h = self.root.winfo_width(), self.root.winfo_height()

        if self._docked:
            if not self.cfg.get("edge_dock"):
                self._undock()
                return
            # 收条热区：比收条宽一些，容错手抖
            pad = 5
            in_zone = (x - pad <= px <= x + w + pad) and (y <= py <= y + h)
            if in_zone:
                if self._zone_since == 0.0:
                    self._zone_since = now
                elif (now - self._zone_since) * 1000 >= \
                        int(self.cfg.get("peek_delay", 150)):
                    self._undock()
            else:
                self._zone_since = 0.0
            return

        # ---------------- 展开态 ----------------
        inside = (x - 2 <= px <= x + w + 2) and (y - 2 <= py <= y + h + 2)

        # 工具栏自动隐藏：鼠标不在窗内就藏起来，只留正文
        if not inside:
            self._hide_chrome()
        else:
            self._show_chrome()

        # 鼠标「真正进到窗口里」过一次，才算激活了自动收展。
        # 在那之前（刚打开时）一直保持展开，不会自己收走。
        if inside:
            self._armed = True

        if not self.cfg.get("edge_dock") or self.hidden or self.disguised:
            self._zone_since = 0.0
            return
        if getattr(self, "_drag_active", False) or self._has_toplevel() \
                or getattr(self, "maximized", False):
            self._zone_since = 0.0
            return

        # 尚未激活：保持展开，不判离开
        if not self._armed:
            self._zone_since = 0.0
            return

        # 刚展开的保护期内：只有鼠标已经进入窗口才算「真的在用」，
        # 否则一律不判离开。收条贴着屏幕边缘，展开后窗口是往屏幕内侧
        # 「长出来」的，鼠标此刻通常还在窗外——若立刻判定离开，就会
        # 「展开→收起」无限震荡，用户看到的就是「碰一下浮窗就没了」。
        if not inside and now < getattr(self, "_expand_until", 0.0):
            self._zone_since = 0.0
            return

        if inside:
            self._zone_since = 0.0
        else:
            if self._zone_since == 0.0:
                self._zone_since = now
            elif (now - self._zone_since) * 1000 >= \
                    int(self.cfg.get("hide_delay", 280)):
                self._zone_since = 0.0
                self._dock()

    # --- 工具栏自动显隐 -----------------------------------------------
    def _show_chrome(self) -> None:
        if self._chrome_visible or self.disguised:
            return
        self._chrome_visible = True
        self.bar.pack(fill="x", before=self.text.master)
        self.status.pack(side="bottom", fill="x")

    def _hide_chrome(self) -> None:
        if not self._chrome_visible or self.disguised:
            return
        self._chrome_visible = False
        self.bar.pack_forget()
        self.status.pack_forget()

    def _build_resize_grips(self, parent) -> None:
        """无边框窗口必须自己实现缩放。

        四周 + 四角共 8 个透明热区，鼠标移上去变成对应的缩放光标。
        """
        GRIP = 4          # 边缘热区厚度（太厚会挡住内容）
        CORNER = 14       # 角落热区大小

        # (方向, relx, rely, 光标)
        zones = [
            ("n",  0.0, 0.0, "size_ns"),
            ("s",  0.0, 1.0, "size_ns"),
            ("w",  0.0, 0.0, "size_we"),
            ("e",  1.0, 0.0, "size_we"),
            ("nw", 0.0, 0.0, "size_nw_se"),
            ("se", 1.0, 1.0, "size_nw_se"),
            ("ne", 1.0, 0.0, "size_ne_sw"),
            ("sw", 0.0, 1.0, "size_ne_sw"),
        ]

        for name, rx, ry, cur in zones:
            g = tk.Frame(parent, bg=self.C_SUBTLE, cursor=cur)
            if name == "n":
                g.place(relx=0, rely=0, relwidth=1.0, height=GRIP)
            elif name == "s":
                g.place(relx=0, rely=1.0, relwidth=1.0, height=GRIP, y=-GRIP)
            elif name == "w":
                g.place(relx=0, rely=0, relheight=1.0, width=GRIP)
            elif name == "e":
                g.place(relx=1.0, rely=0, relheight=1.0, width=GRIP, x=-GRIP)
            else:
                # 角落
                g.configure(width=CORNER, height=CORNER)
                x = 0 if "w" in name else -CORNER
                y = 0 if "n" in name else -CORNER
                g.place(relx=rx, rely=ry, x=x, y=y)

            g.bind("<Button-1>", lambda e, n=name: self._grip_start(e, n))
            g.bind("<B1-Motion>", self._grip_drag)
            g.bind("<ButtonRelease-1>", lambda e: self._grip_end())
            g.lift()

    # ------------------------------------------------------------ 缩放逻辑
    def _grip_start(self, event, direction: str) -> None:
        self._gdir = direction
        self._gx = event.x_root
        self._gy = event.y_root
        self._gw = self.root.winfo_width()
        self._gh = self.root.winfo_height()
        self._gox = self.root.winfo_x()
        self._goy = self.root.winfo_y()

    def _grip_drag(self, event) -> None:
        d = self._gdir
        dx = event.x_root - self._gx
        dy = event.y_root - self._gy
        MIN_W, MIN_H = 260, 200

        w, h, x, y = self._gw, self._gh, self._gox, self._goy

        if "e" in d:
            w = max(MIN_W, self._gw + dx)
        if "s" in d:
            h = max(MIN_H, self._gh + dy)
        if "w" in d:
            w = max(MIN_W, self._gw - dx)
            x = self._gox + (self._gw - w)
        if "n" in d:
            h = max(MIN_H, self._gh - dy)
            y = self._goy + (self._gh - h)

        self.root.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")

    def _grip_end(self) -> None:
        self._full_h = self.root.winfo_height()
        self._save_config()

    # ------------------------------------------------------------ 最大化
    def toggle_maximize(self) -> None:
        """双击标题栏：最大化 / 还原。"""
        if self.maximized:
            self.root.geometry(self._normal_geo)
            self.maximized = False
        else:
            self._normal_geo = self.root.geometry()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            # 留出一点边距，避免完全贴边不好拖回来
            self.root.geometry(f"{sw - 80}x{sh - 120}+40+40")
            self.maximized = True
        self.root.after(80, self._update_status)

    def _build_toolbar(self) -> None:
        """顶部拖拽条 + 一排在摸鱼时够用的小按钮。"""
        self.bar = tk.Frame(self.body, bg=self.C_BAR, height=26)
        self.bar.pack(fill="x")
        self.bar.pack_propagate(False)

        # 拖拽区：整条 bar 都可拖；双击 = 最大化/还原
        for w in (self.bar,):
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)
            w.bind("<ButtonRelease-1>", self._end_move)
            w.bind("<Double-Button-1>", lambda e: self.toggle_maximize())

        self.title_var = tk.StringVar(value="摸鱼阅读器")
        self.title_lbl = tk.Label(
            self.bar, textvariable=self.title_var, bg=self.C_BAR, fg=self.C_ACCENT,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.title_lbl.pack(side="left", padx=(10, 4))
        self.title_lbl.bind("<Button-1>", self._start_move)
        self.title_lbl.bind("<B1-Motion>", self._do_move)
        self.title_lbl.bind("<ButtonRelease-1>", self._end_move)
        self.title_lbl.bind("<Double-Button-1>", lambda e: self.toggle_maximize())

        # 右侧按钮：×关闭  ▣伪装  ≡书库
        def mk_btn(text, cmd, tip):
            b = tk.Label(self.bar, text=text, bg=self.C_BAR, fg=self.C_SUBTLE,
                         font=("Microsoft YaHei UI", 10), cursor="hand2", padx=6)
            b.pack(side="right")
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>", lambda e: (b.configure(fg=self.C_ACCENT), self._tip(tip)))
            b.bind("<Leave>", lambda e: (b.configure(fg=self.C_SUBTLE), self._tip("")))
            return b

        # 关闭按钮：低调灰，不做成红色大按钮（隐蔽优先；Ctrl+Q/Esc 也能关）
        self.close_btn = mk_btn("✕", self.quit, "关闭 (Ctrl+Q / Esc)")
        self.close_btn.configure(padx=8)

        mk_btn("▣", self.toggle_disguise, "伪装模式 Ctrl+D")
        mk_btn("≡", self.open_library, "书库 Ctrl+B")
        mk_btn("📂", self.import_txt, "导入 txt Ctrl+O")
        mk_btn("⏯", self.toggle_auto, "自动滚动 空格")
        mk_btn("⛶", self.toggle_maximize, "最大化 / 还原（也可双击标题栏）")
        mk_btn("⇥", self._toggle_dock, "侧边收条：鼠标移入展开 / 移出收起（Ctrl+E）")

        # 底部状态条（显示进度/字号）
        self.status = tk.Label(
            self.body, text="", bg=self.C_BAR, fg=self.C_SUBTLE,
            font=("Microsoft YaHei UI", 8), anchor="w",
        )
        self.status.pack(side="bottom", fill="x")
        self.status.bind("<Button-1>", self._start_move)
        self.status.bind("<B1-Motion>", self._do_move)
        self.status.bind("<ButtonRelease-1>", self._end_move)

    def _build_text(self) -> None:
        """正文区：用 Text 控件但去掉一切交互感，做成纯阅读面。"""
        wrap = tk.Frame(self.body, bg=self.C_BG)
        wrap.pack(fill="both", expand=True)

        self.font = tkfont.Font(family="Microsoft YaHei", size=self.cfg["font_size"])

        self.text = tk.Text(
            wrap,
            wrap="word",                  # 按词换行，中文同样适用
            bg=self.C_BG, fg=self.C_FG,
            font=self.font,
            spacing1=2,
            spacing2=self.cfg["line_spacing"],
            spacing3=self.cfg["line_spacing"],
            bd=0, highlightthickness=0,
            cursor="arrow",
            padx=18, pady=12,
            insertwidth=0,
            selectbackground=self.C_BG,
            selectforeground=self.C_FG,
            takefocus=0,
        )
        self.text.pack(side="left", fill="both", expand=True)

        # 极简细滚动条
        self.sb = tk.Scrollbar(wrap, orient="vertical", command=self.text.yview,
                               width=6, bd=0, highlightthickness=0,
                               troughcolor=self.C_BG, bg=self.C_SUBTLE,
                               activebackground=self.C_ACCENT,
                               relief="flat")
        self.sb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=self._on_scroll)

        # 只读但仍可滚动：放行导航键，拦截其余按键
        _ALLOW = {"Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End"}
        self.text.bind("<Key>", lambda e: None if e.keysym in _ALLOW else "break")
        self.text.bind("<MouseWheel>", self._on_wheel)
        self.text.bind("<Button-1>", self._start_move)
        self.text.bind("<B1-Motion>", self._do_move)
        self.text.bind("<ButtonRelease-1>", self._end_move)

    def _on_scroll(self, first, last) -> None:
        self.sb.set(first, last)
        self._update_status()
        self._schedule_save()

    def _schedule_save(self) -> None:
        """滚动停止 1.5 秒后存档，避免频繁写盘，也避免强杀丢进度。"""
        if getattr(self, "_save_job", None):
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.root.after(1500, self._save_config)

    # ---------------------------------------------------------------- 拖动
    def _start_move(self, event) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()
        self._drag_active = True          # 看门狗看到此标记不会收起

    def _do_move(self, event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y

        # 限制拖动范围，保证标题栏始终留在屏幕内（否则会「拖丢」窗口）
        sw = self.root.winfo_screenwidth()
        margin = 80
        w = self.root.winfo_width()
        x = max(margin - w, min(sw - margin, x))
        y = max(0, min(self.root.winfo_screenheight() - 30, y))

        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _end_move(self, event=None) -> None:
        """拖动结束：记下新的位置和高度。"""
        if not getattr(self, "_drag_active", False):
            return
        self._drag_active = False
        self._full_h = self.root.winfo_height()
        self._save_config()

    # ---------------------------------------------------------------- 滚动
    def _on_wheel(self, event) -> str:
        if event.state & 0x4:            # Ctrl + 滚轮 -> 调透明度
            self._change_alpha(-0.03 if event.delta < 0 else 0.03)
        else:
            self.text.yview_scroll(-3 if event.delta > 0 else 3, "units")
        return "break"

    def _scroll_ratio(self) -> float:
        """当前滚动比例，仅用于界面显示。"""
        try:
            return float(self.text.yview()[0])
        except Exception:
            return 0.0

    # --- 进度定位：用「字符绝对偏移」而不是「比例」-------------------
    # 比例会随排版进度和窗口尺寸漂移（同样 50% 在不同窗高下对应不同位置），
    # 而字符偏移是绝对位置，恢复后一定回到同一句话。

    def _scroll_anchor(self) -> int:
        """返回视野顶部那个字符在全文中是第几个字。"""
        try:
            idx = self.text.index("@0,0")
            c = self.text.count("1.0", idx, "chars")
            if isinstance(c, (tuple, list)):
                c = c[0] if c else 0
            return int(c)
        except Exception:
            return 0

    def _restore_anchor(self, offset: int, tries: int = 0) -> None:
        """把视野滚回指定字符处。

        刚打开时正文可能还没排版完，一次定位未必到位，
        所以定位后回读校验，没到位就再试几次。
        """
        try:
            self.text.update_idletasks()
            self.text.yview(f"1.0 + {int(offset)} chars")
            self.text.update_idletasks()
        except Exception:
            return

        landed = self._scroll_anchor()
        if abs(landed - int(offset)) > 30 and tries < 8:
            self.root.after(60, lambda: self._restore_anchor(offset, tries + 1))

    def _normalize_progress(self, prog) -> int:
        """兼容旧的「比例」存档，统一转成字符偏移。"""
        if prog is None:
            return 0
        if isinstance(prog, bool):
            return 0
        if isinstance(prog, int):
            return max(0, prog)
        if isinstance(prog, float):
            if prog <= 1.0:                       # 旧格式：比例
                return int(prog * max(1, self._total_chars))
            return int(prog)
        return 0

    def toggle_auto(self) -> None:
        self.auto_scrolling = not self.auto_scrolling
        if self.auto_scrolling:
            self._auto_tick()

    def _auto_tick(self) -> None:
        if not self.auto_scrolling:
            return
        self.text.yview_scroll(int(round(self.cfg["auto_speed"])) or 1, "units")
        self.root.after(48, self._auto_tick)

    # ---------------------------------------------------------------- 快捷键
    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<space>", lambda e: self.toggle_auto())
        r.bind("<Control-Up>", lambda e: self._change_font(1))
        r.bind("<Control-Down>", lambda e: self._change_font(-1))
        r.bind("<Control-Left>", lambda e: self._change_speed(-0.2))
        r.bind("<Control-Right>", lambda e: self._change_speed(0.2))
        r.bind("<Control-d>", lambda e: self.toggle_disguise())
        r.bind("<Control-h>", lambda e: self.toggle_hidden())
        r.bind("<Control-e>", lambda e: self._toggle_dock())
        r.bind("<Control-o>", lambda e: self.import_txt())
        r.bind("<Control-b>", lambda e: self.open_library())
        r.bind("<Control-q>", lambda e: self.quit())
        r.bind("<Control-equal>", lambda e: self._change_alpha(0.03))
        r.bind("<Control-minus>", lambda e: self._change_alpha(-0.03))
        r.bind("<Escape>", lambda e: self.quit())
        r.bind("<F11>", lambda e: self.toggle_maximize())

    def _tip(self, text: str) -> None:
        """把操作提示显示在状态栏右侧。"""
        if text:
            self._tip_backup = self.status.cget("text")
            self.status.configure(text=f"  {text}")
        elif getattr(self, "_tip_backup", None):
            self.status.configure(text=self._tip_backup)
            self._tip_backup = None

    def _change_font(self, delta: int) -> None:
        size = max(10, min(40, self.cfg["font_size"] + delta))
        self.cfg["font_size"] = size
        self.font.configure(size=size)
        self._update_status()

    def _change_speed(self, delta: float) -> None:
        self.cfg["auto_speed"] = round(max(0.2, min(6.0, self.cfg["auto_speed"] + delta)), 1)
        self._update_status()

    def _change_alpha(self, delta: float) -> None:
        self.cfg["alpha"] = round(max(0.25, min(1.0, self.cfg["alpha"] + delta)), 2)
        self.root.attributes("-alpha", self.cfg["alpha"])
        self._update_status()

    # ------------------------------------------------------------ 视图模式
    def toggle_disguise(self) -> None:
        """伪装模式：固定隐藏标题栏与状态栏（自动显隐被接管为手动）。"""
        self.disguised = not self.disguised
        if self.disguised:
            self._chrome_visible = False
            self.bar.pack_forget()
            self.status.pack_forget()
        else:
            self._chrome_visible = True
            self.bar.pack(fill="x", before=self.text.master)
            self.status.pack(side="bottom", fill="x")

    def toggle_hidden(self) -> None:
        """老板键：整窗瞬间隐藏 / 恢复。"""
        if self.hidden:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.hidden = False
        else:
            self.root.withdraw()
            self.hidden = True

    # ---------------------------------------------------------------- 书库
    def _load_library(self) -> None:
        index = BOOKS_DIR / "books.json"
        if index.exists():
            try:
                self.books = json.loads(index.read_text(encoding="utf-8"))
            except Exception:
                self.books = []
        if not self.books:
            # 没有索引就扫目录
            self.books = [
                {"id": p.stem, "title": p.stem, "file": p.name}
                for p in sorted(BOOKS_DIR.glob("*.txt"))
            ]

    def _restore_last_book(self) -> None:
        book = self.cfg.get("book")
        ids = {b["file"]: b for b in self.books}
        if book and book in ids:
            self.load_book(book)
        elif self.books:
            self.load_book(self.books[0]["file"])
        else:
            self._set_text([("摸鱼阅读器", "title"),
                            ("还没有书。按 Ctrl+O 导入一本本地 txt 小说，或把 txt 放进 books 目录。", "p")])

    def load_book(self, filename: str) -> None:
        path = BOOKS_DIR / filename
        if not path.exists():
            return
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        # 切书前，先把「当前这本」的进度记下来，否则切回来就丢了
        if self.cur_book and self.cur_book != filename:
            self.cfg["progress"][self.cur_book] = self._scroll_anchor()
            self._write_config()

        self.cur_book = filename
        self.cfg["book"] = filename
        self.paragraphs = [ln for ln in raw.split("\n") if ln.strip()]
        self._render_paragraphs()

        # 恢复进度：等窗口排版稳定后，用字符偏移精确复位
        offset = self._normalize_progress(
            self.cfg.get("progress", {}).get(filename)
        )
        self.text.yview_moveto(0)                 # 先归零，避免残留位置干扰
        self._restore_token = getattr(self, "_restore_token", 0) + 1
        token = self._restore_token

        def do_restore():
            # 期间若切了书，就放弃这次恢复，避免把旧书进度套到新书上
            if token != getattr(self, "_restore_token", 0):
                return
            self._restore_anchor(offset)
            if offset > 0:
                pct = int(offset / max(1, self._total_chars) * 100)
                self._toast(f"已回到上次阅读处（约 {pct}%）")

        self.root.after(120, do_restore)

        meta = next((b for b in self.books if b["file"] == filename), None)
        title = meta["title"] if meta else path.stem
        self.title_var.set(f"📖 {title}")

    def _render_paragraphs(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for p in self.paragraphs:
            # 短行且无句末标点 -> 视作小标题
            if len(p) <= 20 and not any(c in p for c in "。！？…；，"):
                self.text.insert("end", p + "\n", "h")
            else:
                self.text.insert("end", p + "\n", "p")
        self.text.tag_configure("h", foreground=self.C_ACCENT,
                                font=(self.font.actual("family"), self.cfg["font_size"], "bold"),
                                spacing1=14, spacing3=6)
        self.text.tag_configure("p", foreground=self.C_FG, lmargin1=0, lmargin2=0)
        self.text.configure(state="disabled")
        self._total_chars = max(1, len(self.text.get("1.0", "end-1c")))
        self._update_status()

    def _set_text(self, items) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for content, tag in items:
            self.text.insert("end", content + "\n\n", tag)
        self.text.configure(state="disabled")

    def open_library(self) -> None:
        """简单书库面板。"""
        win = tk.Toplevel(self.root)
        win.title("书库")
        win.configure(bg=self.C_BG)
        win.attributes("-topmost", True)
        win.geometry("300x380")
        win.resizable(False, False)

        tk.Label(win, text="书库", bg=self.C_BG, fg=self.C_ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(pady=(12, 6))

        listbox = tk.Listbox(
            win, bg=self.C_BG, fg=self.C_FG, font=("Microsoft YaHei", 11),
            bd=0, highlightthickness=0, activestyle="none",
            selectbackground="#E8E0D0", selectforeground=self.C_ACCENT,
        )
        listbox.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for b in self.books:
            chars = b.get("chars")
            label = f"{b['title']}" + (f"   {chars//1000}k字" if chars else "")
            listbox.insert("end", label)

        def choose(_e=None):
            sel = listbox.curselection()
            if sel:
                self.load_book(self.books[sel[0]]["file"])
                win.destroy()

        listbox.bind("<Double-Button-1>", choose)
        listbox.bind("<Return>", choose)

        tk.Button(win, text="打开所选", command=choose, bg=self.C_ACCENT, fg="white",
                  bd=0, font=("Microsoft YaHei UI", 10), cursor="hand2",
                  activebackground="#55555A", activeforeground="white").pack(pady=(0, 14), ipadx=16, ipady=4)

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(
            title="选择一本 txt 小说",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not path:
            return
        src = Path(path)
        try:
            raw = src.read_bytes()
            for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "big5", "utf-16"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = raw.decode("utf-8", errors="replace")
        except Exception as e:
            self._toast(f"读取失败：{e}")
            return

        BOOKS_DIR.mkdir(parents=True, exist_ok=True)
        dest = BOOKS_DIR / src.name
        dest.write_text(text, encoding="utf-8", newline="\n")

        # 更新书库索引
        chars = len("".join(text.split()))
        self.books = [b for b in self.books if b["file"] != dest.name]
        self.books.append({"id": dest.stem, "title": dest.stem, "file": dest.name, "chars": chars})
        try:
            (BOOKS_DIR / "books.json").write_text(
                json.dumps(self.books, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        self.load_book(dest.name)
        self._toast(f"已导入《{dest.stem}》")

    # ---------------------------------------------------------------- 状态
    def _toast(self, msg: str) -> None:
        self.status.configure(text=f"  {msg}")

    def _update_status(self) -> None:
        if getattr(self, "_tip_backup", None):
            return          # 正在显示悬停提示，不要覆盖
        pct = int(self._scroll_ratio() * 100)
        bits = [f" {pct}%"]
        if self.auto_scrolling:
            bits.append("▶ 自动")
        bits.append(f"字号{self.cfg['font_size']}")
        bits.append(f"速度{self.cfg['auto_speed']}")
        bits.append(f"透明{int(self.cfg['alpha']*100)}%")
        bits.append(f"{self.root.winfo_width()}×{self.root.winfo_height()}")
        self.status.configure(text="   ·   ".join(bits))

    # ---------------------------------------------------------------- 退出
    def quit(self) -> None:
        self.auto_scrolling = False
        # 取消还没触发的延迟任务，避免窗口销毁后回调报错
        for job in (getattr(self, "_save_job", None),
                    getattr(self, "_wd_job", None),
                    getattr(self, "_anim_job", None),
                    getattr(self, "_chrome_job", None)):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        self._save_job = None
        self._wd_job = None
        self._anim_job = None
        self._anim = None
        self._chrome_job = None
        # 退出前若是收起状态，不要把这副「细缝」尺寸存成下次的窗口大小
        if not self._docked:
            self.cfg["geometry"] = self.root.geometry()
        self._save_config()          # 退出前最后一次存档（存字符偏移）
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = MoyuReader(root)

    # 定期保存进度
    def autosave():
        app._save_config()
        root.after(20000, autosave)

    root.after(20000, autosave)
    root.mainloop()


if __name__ == "__main__":
    main()
