#!/usr/bin/env python3
"""
Agnes AI Studio - 图片 & 视频生成可视化工具
后端服务 (Flask) - 支持 PyInstaller 打包为独立 .exe
"""

import os
import socket
import sys
import threading
import webbrowser

# 禁用 Windows 控制台快速编辑模式（防止点击控制台窗口导致程序卡住）
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # 清除 ENABLE_QUICK_EDIT_MODE (0x0040)，保留 ENABLE_EXTENDED_FLAGS (0x0080)
        kernel32.SetConsoleMode(handle, (mode.value & ~0x0040) | 0x0080)
    except Exception:
        pass  # 非控制台环境（如服务）忽略

from src import create_app
from src.config import get_config_path, shutdown_event

app = create_app()


def get_available_port(start_port=5000):
    """返回从默认端口开始的首个可用本地端口。"""
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('127.0.0.1', port)) != 0:
                return port
        port += 1


def main():
    """主入口"""
    port = get_available_port()
    local_url = f'http://127.0.0.1:{port}'

    print("=" * 60)
    print("  Agnes AI Studio - 图片 & 视频生成可视化工具 v1.0")
    print("  项目目录: " + os.path.dirname(get_config_path()))
    print("=" * 60)
    print(f"  本地访问: {local_url}")
    print(f"  局域网访问: http://你的IP地址:{port}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)

    # 自动打开浏览器：打包版保持原行为；开发重启时浏览器里多半已有同一 URL 的标签页，
    # 每次再开一个太吵（macOS ControlCenter 常驻 5000，端口永远漂到 5001 刷新即可），
    # 需要恢复自动弹出：AGNES_OPEN_BROWSER=1 venv/bin/python app.py
    if getattr(sys, 'frozen', False) or os.environ.get('AGNES_OPEN_BROWSER') == '1':
        threading.Timer(1.5, lambda: webbrowser.open(local_url)).start()
    else:
        print("  (浏览器未自动打开：已有标签页直接刷新，或 AGNES_OPEN_BROWSER=1 启动)")

    print("  提示: 按 Ctrl+C 可停止服务")
    print("=" * 60)

    try:
        app.run(host='0.0.0.0', port=port, debug=False)
    except KeyboardInterrupt:
        print("\n[关闭] 收到 Ctrl+C，正在停止服务...")
        shutdown_event.set()
        print("[关闭] 服务已停止")


if __name__ == '__main__':
    main()
