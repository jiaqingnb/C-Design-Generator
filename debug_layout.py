# -*- coding: utf-8 -*-
"""调试脚本：打印 test_simple.c 各函数的 Visio 布局明细。

不依赖 Visio / COM，直接复用布局引擎，输出每条连接线的：
  - 端点坐标（canvas，英寸）
  - begin_part / end_part（1=上 2=下 3=左 4=右）
  - 分支标签

用途：定位"开始块左边出线"到底是
  (A) 布局引擎算错 part/坐标，还是
  (B) COM 渲染胶合没生效。

用法：
    python debug_layout.py test_simple.c
"""

import os
import sys

from parser.file_loader import FileLoader
from parser.ast_parser import ASTParser
from generator.vsdx_generator import VsdxGenerator, VisioShape, VisioConnector

PART_NAME = {1: "上", 2: "下", 3: "左", 4: "右"}


def dump_layout():
    if len(sys.argv) < 2:
        print("用法: python debug_layout.py <C文件>")
        return

    filename = sys.argv[1]
    code = FileLoader().load(filename)
    cfile = ASTParser().parse(code)

    engine = VsdxGenerator(output_dir="output")
    VisioShape._id_counter = 1
    VisioConnector._id_counter = 1000

    for idx, func in enumerate(cfile.functions):
        print("=" * 70)
        print("函数[%d]: %s" % (idx + 1, func.name))

        layout = engine._layout_flow(func.flow)
        start = VisioShape("term", "开始", 0, 0, engine.term_w, engine.term_h)
        end = VisioShape("term", "结束", 0, 0, engine.term_w, engine.term_h)
        total = engine._assemble(func.name, start, layout, end)
        engine._normalize(total)

        # 形状清单
        print("--- 形状 (%d 个) ---" % len(total.shapes))
        for sh in total.shapes:
            print("  id=%2d kind=%-7s x=%.2f y=%.2f w=%.2f h=%.2f text=%r"
                  % (sh.id, sh.kind, sh.x, sh.y, sh.w, sh.h, sh.text))

        print("--- 连接线 (%d 条) ---" % len(total.connectors))
        for cn in total.connectors:
            bx, by = cn.begin
            ex, ey = cn.end
            bp = PART_NAME.get(cn.begin_part, "?")
            ep = PART_NAME.get(cn.end_part, "?")
            label = cn.label or ""
            # 判断这条线的几何方向
            if abs(ex - bx) > abs(ey - by):
                direction = "水平(左->右)" if ex > bx else "水平(右->左)"
            else:
                direction = "垂直(上->下)" if ey > by else "垂直(下->上)"
            print("  id=%4d begin=(%.2f,%.2f)[%s] end=(%.2f,%.2f)[%s] %s label=%r"
                  % (cn.id, bx, by, bp, ex, ey, ep, direction, label))


if __name__ == "__main__":
    dump_layout()
