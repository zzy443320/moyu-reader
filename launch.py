# -*- coding: utf-8 -*-
"""
启动器：带错误捕获的入口。

双击 `摸鱼阅读器.bat` 实际调用的就是这个文件。
如果 moyu_reader.py 启动时崩溃，这里会把错误信息显示出来，
而不是无声无息地关掉窗口。
"""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def show_error(msg: str) -> None:
    """用系统弹窗 + 控制台双通道显示错误。"""
    print(msg, file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("摸鱼阅读器 启动失败", msg)
        r.destroy()
    except Exception:
        pass
    try:
        input("\n按回车键关闭...")
    except Exception:
        pass


def main() -> int:
    # 先检查环境
    try:
        import tkinter  # noqa: F401
    except ImportError:
        show_error(
            "当前 Python 没有 tkinter 模块，无法显示窗口。\n\n"
            f"用的解释器：{sys.executable}\n\n"
            "解决办法：到 python.org 安装官方 Python 3.12+，\n"
            "安装时勾选『Add python.exe to PATH』和『tcl/tk and IDLE』。"
        )
        return 1

    try:
        import moyu_reader
        moyu_reader.main()
        return 0
    except Exception:
        show_error("程序运行时出错：\n\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
