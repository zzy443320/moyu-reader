# -*- coding: utf-8 -*-
"""真机验证：低调节色 + 看门狗收条 + 平滑动画 + 更快收起。

关键：动画用 `after` 逐帧驱动，必须用真实 mainloop 泵事件；
用 while(root.update()) 会把所有到期回调一次性跑完，测不出中间帧。
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
import moyu_reader as M

fails = []
def check(name, cond, extra=""):
    print(("  OK  " if cond else "  FAIL") + f"  {name} {extra}")
    if not cond:
        fails.append(name)

M.CONFIG_PATH = M.APP_DIR / "tools" / "_test_config.json"
if M.CONFIG_PATH.exists():
    M.CONFIG_PATH.unlink()

root = tk.Tk()
app = M.MoyuReader(root)

def run_mainloop(ms, on_tick=None, tick_ms=16):
    """真实 mainloop 跑 ms 毫秒，期间每 tick_ms 调一次 on_tick。"""
    done = {"v": False}
    def tick():
        if on_tick:
            on_tick()
        if not done["v"]:
            root.after(tick_ms, tick)
    root.after(tick_ms, tick)
    root.after(int(ms), lambda: (done.__setitem__("v", True), root.quit()))
    root.mainloop()

def set_mouse(x, y):
    app.root.winfo_pointerx = lambda: x
    app.root.winfo_pointery = lambda: y
def reset_mouse():
    for n in ("winfo_pointerx", "winfo_pointery"):
        try: delattr(app.root, n)
        except AttributeError: pass

def settle(extra_ms=400, tick_ms=16):
    """跑到「没有动画在跑」为止，再补一点时间让看门狗做完判定。

    动画现在长 14*12≈168ms，直接按固定时长断言会在动画中途取样，
    所以统一用这个 helper 等稳定（上限 2s，防死循环）。
    """
    waited = 0
    while app._anim is not None and waited < 2000:
        run_mainloop(tick_ms, None, tick_ms)
        waited += tick_ms
    run_mainloop(extra_ms, None, tick_ms)

print("== 1. 默认值 ==")
check("透明度 0.85", app.cfg["alpha"] == 0.85)
check("收起延迟更快(280ms)", app.cfg["hide_delay"] == 280, app.cfg["hide_delay"])
check("展开延迟 150ms", app.cfg["peek_delay"] == 150)
check("收条 6px / 0.18", app.cfg["edge_width"] == 6 and app.cfg["edge_alpha"] == 0.18)
check("收条贴左边", app.cfg.get("edge_side") == "left", app.cfg.get("edge_side"))
check("左缘收条 x=0", app._edge_x(6) == 0, app._edge_x(6))
check("初始未激活(_armed=False)", app._armed is False)
check("首次打开保持展开", app._docked is False)

print("== 2. 收起动画平滑（从动画内部逐帧采样） ==")
run_mainloop(700)                      # 等过 init 的自动收起
app._undock(); settle(300)
app._drag_active = False
# 把假鼠标固定在窗口内部，避免真实鼠标位置带来的不确定性
def pin_inside():
    set_mouse(root.winfo_x() + max(5, root.winfo_width() // 2),
              root.winfo_y() + max(5, root.winfo_height() // 2))
pin_inside()
settle(200)
w_before = root.winfo_width()
check("前置：已展开", w_before > 200, w_before)

# 采样必须发生在动画自己的每一帧里：用 16ms 外部轮询去套 12ms 的帧定时器
# 会漏帧甚至一帧都采不到（别名效应），所以钩住 _anim_tick 逐帧记录。
_anim_samples = []
_orig_tick = M.MoyuReader._anim_tick
def _recording_tick(self, gen=None):
    if self._anim is not None:
        _anim_samples.append(self.root.winfo_width())
    return _orig_tick(self, gen)
M.MoyuReader._anim_tick = _recording_tick
try:
    app._dock()                        # 主动触发收起动画
    settle(120)
finally:
    M.MoyuReader._anim_tick = _orig_tick
frames = _anim_samples
run_mainloop(200)
w_after = root.winfo_width()
mids = [w for w in frames if 6 < w < w_before - 5]
check("收窄过程出现多个中间宽度", len(set(mids)) >= 3, f"unique mids={sorted(set(mids))}")
check("最终收到 6px", w_after == 6, w_after)
check("是逐渐变小(首帧>末帧)", frames[0] > frames[-1], f"{frames[0]}->{frames[-1]}")

print("== 3. 展开动画平滑 ==")
# 前置：确保处于收起态（第2步已收起到 6px）
set_mouse(-999, -999)
run_mainloop(400)
check("前置：处于收起态", app._docked is True, f"docked={app._docked}")
target_w = app.cfg["width"]
frames2 = []
# 同样在动画内部逐帧采样，并把鼠标钉在窗口里，防止展开后被看门狗收回
_orig_tick2 = M.MoyuReader._anim_tick
def _recording_tick2(self, gen=None):
    frames2.append(root.winfo_width())
    if not self._docked:
        set_mouse(root.winfo_x() + 20, root.winfo_y() + 20)
    return _orig_tick2(self, gen)
M.MoyuReader._anim_tick = _recording_tick2
try:
    app._undock()                      # 真正触发展开动画
    settle(120)
finally:
    M.MoyuReader._anim_tick = _orig_tick2
set_mouse(root.winfo_x() + 20, root.winfo_y() + 20)
run_mainloop(300)
w_now = root.winfo_width()
uniq = sorted(set(frames2))
mids2 = [w for w in uniq if w < target_w - 5]
check("展开过程有多个中间宽度", len(mids2) >= 2, f"unique={uniq}")
check("恢复到目标宽度", w_now == target_w, w_now)
check("动画是逐步变宽", uniq[0] < uniq[-1], f"{uniq[0]}->{uniq[-1]}")

print("== 4. 动画期间看门狗被跳过（不抢 IPC） ==")
# 前置：展开态
app._undock(); settle(200)
app._drag_active = False
app._dock()
seen_anim = []
run_mainloop(400, lambda: seen_anim.append(app._anim is not None), 12)
check("动画期间 _anim 非空", any(seen_anim), f"{sum(seen_anim)}/{len(seen_anim)} 帧")
run_mainloop(300)

print("== 5. 鼠标停在收条上 -> 自动展开 ==")
check("已收起", app._docked is True)
set_mouse(root.winfo_x() + 2, root.winfo_y() + max(20, root.winfo_height() // 2))
run_mainloop(900)
check("自动展开", app._docked is False)
settle(200)

print("== 6. 离开后很快收起（跟手，不再是 1.2s） ==")
app._undock(); settle(300)
set_mouse(root.winfo_x() + 20, root.winfo_y() + 20)
settle(200)
check("前置：展开态", app._docked is False)
set_mouse(-999, -999)
t0 = time.monotonic()
dock_at = {"t": None}
def watch():
    if app._docked and dock_at["t"] is None:
        dock_at["t"] = time.monotonic() - t0
# hide_delay 280ms + 动画 ~170ms，给 1.5s 富余
run_mainloop(1500, watch, 20)
check("已收起", app._docked is True)
d = dock_at["t"] or 9.9
check("开始收起 < 0.6s（旧的约 0.7s+）", d < 0.6, f"≈{d:.2f}s")

print("== 7. 拖动中 / 弹窗时不收起 ==")
app._undock(); settle(200)
app._drag_active = True
run_mainloop(1200)
check("拖动中不收起", app._docked is False)
app._drag_active = False
tl = tk.Toplevel(root); tl.geometry("1x1+0+0"); tl.update()
run_mainloop(1200)
check("有弹窗不收起", app._docked is False)
tl.destroy()
run_mainloop(1400)
check("弹窗关闭后收起", app._docked is True)

print("== 9. 回归：鼠标碰到收条展开后不会「又消失」 ==")
# 这是用户报的 bug：碰一下收条展开，浮窗随即缩回去（来回震荡）。
# 复现真实时序：鼠标停在屏幕左缘的收条上 -> 展开 -> 保持不动 -> 应稳定展开。
app._undock(); app._drag_active = False
app._dock(); run_mainloop(400)
check("前置：已收起", app._docked is True, f"docked={app._docked}")
set_mouse(2, root.winfo_y() + max(20, root.winfo_height() // 2))
run_mainloop(900)          # peek_delay 150ms + 动画 170ms
settle(200)
w1 = root.winfo_width()
check("碰收条 -> 展开", app._docked is False and w1 > 200, f"w={w1}")
# 鼠标保持在收条位置不动，窗口应一直稳定展开
run_mainloop(1200)
w2 = root.winfo_width()
check("保持不动 1.2s 仍然稳定展开", app._docked is False and w2 > 200,
      f"w={w2} docked={app._docked}")
# 再连续多次「碰一下就走」，不应出现卡死在收起态或尺寸异常
oks = []
for i in range(3):
    set_mouse(2, root.winfo_y() + 30)
    run_mainloop(400)
    settle(200)
    oks.append(root.winfo_width() > 200)
    set_mouse(-999, -999)
    run_mainloop(900)
check("反复碰触展开均正常", all(oks), oks)
# 最后再确保鼠标在外面、并且等到动画彻底停下来，收条才算真正归位
set_mouse(-999, -999)
run_mainloop(900)
settle(300)
check("结束后能正常收起", app._docked is True, f"docked={app._docked}")

print("== 11. 首次打开保持展开，鼠标进过一次后才自动收展 ==")
app._armed = False
app._undock(); run_mainloop(500)
app._drag_active = False
# 鼠标全程在窗外：窗口必须一直保持展开（不能自己收走）
set_mouse(-999, -999)
run_mainloop(1500)
check("未激活时不自动收起", app._docked is False, f"docked={app._docked}")
check("仍未激活", app._armed is False)
# 鼠标进窗口一次 -> 激活
set_mouse(root.winfo_x() + 30, root.winfo_y() + 30)
run_mainloop(300)
check("鼠标进入后已激活", app._armed is True)
# 再移开 -> 应该收起
set_mouse(-999, -999)
run_mainloop(1500)
check("激活后移开会收起", app._docked is True, f"docked={app._docked}")
# 手动开启收条时立即激活（否则会卡在展开）
app._undock(); run_mainloop(400)
app._armed = False
app.cfg["edge_dock"] = False
app._toggle_dock()          # 关 -> 开，内部应把 _armed 置 True
check("手动开启收条会激活", app._armed is True)

print("== 12. 左侧收条 x 坐标为 0 ==")
app._undock(); run_mainloop(400)
app._dock(); run_mainloop(400)
check("收起态贴左缘 x=0", root.winfo_x() == 0, root.winfo_x())
app._undock(); run_mainloop(400)
check("展开态也贴左缘 x=0", root.winfo_x() == 0, root.winfo_x())
check("展开后宽度恢复", root.winfo_width() >= 260, root.winfo_width())

print("== 10. 存档不吃细缝尺寸 ==")
check("cfg geometry 不是 6px", "6x" not in str(app.cfg.get("geometry", "")),
      app.cfg.get("geometry"))

reset_mouse()
app.quit()
print()
if fails:
    print(f"❌ {len(fails)} 项失败: {fails}"); sys.exit(1)
print("✅ 全部通过")
