# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：C 代码详细设计生成工具 GUI（文件夹模式）。

用法：
    pyinstaller gui.spec

产物：dist/gui/ 目录（gui.exe + 依赖 + templates 模板）
"""

import os

# PyInstaller 6.x 的 spec 命名空间没有 __file__，用 SPECPATH（spec 所在目录）
ROOT = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, "gui_main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # Visio 模板：打包进 exe 解压目录，运行时通过 sys._MEIPASS 定位
        (os.path.join(ROOT, "templates", "vsdx_model"), "templates/vsdx_model"),
    ],
    hiddenimports=[
        # tree-sitter 的 C 语言解析器扩展，PyInstaller 可能检测不到，显式声明
        "tree_sitter",
        "tree_sitter_c",
        # win32com 相关
        "win32com",
        "win32com.client",
        "win32com.client.gencache",
        "pythoncom",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除调试/开发脚本，避免打入包内
        "debug_layout",
        "verify_com_render",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI 程序，不弹命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="gui",
)
