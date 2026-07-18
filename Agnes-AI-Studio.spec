# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件
用于将 Agnes AI Studio 打包为单个 .exe 文件
"""

import sys
import os
from pathlib import Path

# 获取项目根目录
project_dir = Path.cwd()

# 查找 imageio-ffmpeg 内置的 ffmpeg 二进制文件
ffmpeg_binary = None
try:
    import imageio_ffmpeg
    ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    pass

binaries_list = []
if ffmpeg_binary and os.path.exists(ffmpeg_binary):
    binaries_list.append((ffmpeg_binary, 'imageio_ffmpeg/binaries'))
    print(f'[spec] 找到 ffmpeg: {ffmpeg_binary}')
else:
    print('[spec] 警告: 未找到 ffmpeg 二进制文件，视频拼接功能将不可用')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries_list,
    datas=[
        # 将 static 目录打包进 exe
        ('static/index.html', 'static'),
    ],
    hiddenimports=[
        'flask',
        'flask.json',
        'flask_cors',
        'requests',
        'json',
        'threading',
        'subprocess',
        'os',
        'sys',
        'webbrowser',
        'imageio_ffmpeg',
        # requests / urllib3 底层依赖 email 模块
        'email',
        'email.mime.text',
        'email.mime.multipart',
        'email.mime.base',
        'email.utils',
        'email.header',
        'email.encoders',
        'email.parser',
        'email.message',
        'email.policy',
        'email.charset',
        'email.contentmanager',
        'email.errors',
        'email.generator',
        'email.iterators',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'xmlrpc',
        'pydoc',
        'test',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Agnes-AI-Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # 显示控制台窗口，方便查看日志和 Ctrl+C 退出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # 可添加 .ico 图标路径
    # 添加版本信息
    version='version_info.txt',
)
