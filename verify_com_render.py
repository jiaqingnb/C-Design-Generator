# -*- coding: utf-8 -*-
"""快速验证 COM 渲染器：只解析 C 文件并生成 VSDX + PNG 预览。

在 Windows + Visio 环境下运行：
    python verify_com_render.py test_simple.c

预期：
  - output/design_com.vsdx   （可编辑 Visio 文件，含连线）
  - output/design_com_p1.png ... （各页 PNG 预览，方便肉眼检查排版）

需要本机安装 Microsoft Visio 与 pywin32（COM 自动化调用）。
"""

import os
import sys

from parser.file_loader import FileLoader
from parser.ast_parser import ASTParser

from generator.com_renderer import ComVsdxRenderer


def main():
    if len(sys.argv) < 2:
        print("用法: python verify_com_render.py <C文件>")
        return 1

    filename = sys.argv[1]
    code = FileLoader().load(filename)
    cfile = ASTParser().parse(code)

    os.makedirs("output", exist_ok=True)

    renderer = ComVsdxRenderer(output_dir="output")
    renderer.generate(cfile, "output/design_com.vsdx", export_png=True)
    print("COM 渲染成功 → output/design_com.vsdx (+ PNG 预览)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
