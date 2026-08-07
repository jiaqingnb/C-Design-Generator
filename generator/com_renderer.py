# -*- coding: utf-8 -*-
"""Visio (.vsdx) 流程图生成器 —— COM 自动化渲染后端。

思路借鉴 md2visio / Auto-Visio-Helper：
  - 复用 vsdx_generator 的布局引擎（VisioLayoutNode/VisioShape/VisioConnector），
    布局输出的坐标 + 连接端点 + 分支标签就是"中间表示"。
  - 本后端通过 pywin32 调用本机 Microsoft Visio COM 接口完成最终绘制：
      1. 打开打包好的模板 .vsdx（含官方 Start/End、Process、Decision、Dynamic connector master）
      2. 按布局坐标 Drop 对应 master 形状
      3. 用 Dynamic connector master 画连接线，Begin/End 精确对准布局端点
      4. 用 GlueTo 把连接线两端胶合到形状的连接点（拖动形状时连线跟随）
  - 动态连接线的胶合（_WALKGLUE / PAR(PNT) / Trigger / Connects）全部由 Visio
    原生生成，彻底避免手写 VSDX XML 导致连线不粘/拖动不跟随的问题。

前置条件：
  - Windows + Microsoft Visio 桌面版（测试环境：Visio 2019 专业版）
  - pip install pywin32

坐标系约定（与 vsdx_generator 完全一致）：
  - 布局引擎使用 canvas 坐标系：X 向右、Y 向下，单位英寸，原点左上。
  - Visio 使用绘图页坐标：X 向右、Y 向上，单位英寸。
  - 落图时对 Y 轴翻转：pin_y = page_h - canvas_y - h/2。
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    import win32com.client
except ImportError:
    win32com_client = None
else:
    win32com_client = win32com.client

# 复用 vsdx_generator 的布局数据结构与布局引擎
from generator.vsdx_generator import VsdxGenerator, VisioShape

# 形状类型 -> 模板 master 的 NameU（跨语言稳定，界面语言无关）
MASTER_NAMES = {
    "term": "Start/End",
    "rect": "Process",
    "diamond": "Decision",
}

# Visio 内置模具（备用，模板不可用时使用）
# 常用名：Basic Flowchart Shapes 模具（含 Start/End、Process、Decision）
STENCIL_CANDIDATES = [
    "BASFLO_U.VSSX",       # Basic Flowchart (US)
    "BASFLO.VSSX",         # 中文本地化可能名
    "BASIC_U.VSSX",        # Basic Shapes（含 Rectangle/Diamond，无 Start/End）
]

# 连接点行映射 —— 按块类型区分（用户在 Visio ShapeSheet 实测确认）：
#   开始/结束 (Start/End) : X1=下  X2=上  X3=左  X4=右
#   过程块   (Process)    : X1=左  X2=右  X3=下  X4=上
#   判定块   (Decision)   : X1=左  X2=右  X3=上  X4=下
# vsdx_generator 的 part 约定：1=上, 2=下, 3=左, 4=右
PART_TO_CONNECTION_ROW = {
    "term":    {1: "X2", 2: "X1", 3: "X3", 4: "X4"},  # Start/End: 上/下/左/右
    "rect":    {1: "X4", 2: "X3", 3: "X1", 4: "X2"},  # Process:   上/下/左/右
    "diamond": {1: "X3", 2: "X4", 3: "X1", 4: "X2"},  # Decision:  上/下/左/右
}

# 分支标签（与 vsdx_generator 保持一致）
LABEL_YES = "是"
LABEL_NO = "否"
LABEL_LOOP_CONT = "遍历未结束"
LABEL_LOOP_END = "遍历结束"


class ComRendererError(RuntimeError):
    """COM 渲染相关错误。"""


class ComVsdxRenderer:
    """COM 渲染后端：把布局引擎的输出绘制成可编辑的 VSDX。"""

    def __init__(self, template_dir=None, output_dir="output"):
        self.visio = None
        self.doc = None
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        if template_dir is None:
            here = os.path.dirname(os.path.abspath(__file__))
            template_dir = os.path.join(here, "..", "templates", "vsdx_model")
        self.template_dir = os.path.abspath(template_dir)
        self._masters = {}

    # ---------- 生命周期 ----------

    def start(self):
        """启动 Visio 应用并打开模板文档（含 master）。"""
        if win32com_client is None:
            raise ComRendererError(
                "缺少 pywin32，请先安装：pip install pywin32"
            )
        try:
            # DispatchEx 创建独立实例，不干扰用户已打开的 Visio
            self.visio = win32com_client.DispatchEx("Visio.Application")
            self.visio.Visible = False
        except Exception as exc:
            raise ComRendererError(
                f"无法启动 Visio COM：{exc}\n请确认本机已安装 Microsoft Visio 桌面版。"
            ) from exc

        template_vsdx = self._prepare_template()
        try:
            self.doc = self.visio.Documents.Open(template_vsdx)
        except Exception as exc:
            self.visio.Quit()
            raise ComRendererError(f"无法打开模板 {template_vsdx}：{exc}") from exc

        self._load_masters()

    def _prepare_template(self):
        """确保得到一个可被 Visio 打开的 .vsdx 模板文件。

        templates/vsdx_model 是解压后的目录，需要打包成临时 .vsdx。
        """
        if self.template_dir.lower().endswith(".vsdx") and os.path.isfile(self.template_dir):
            return self.template_dir

        # 目录 -> 打包为临时 vsdx（放在 output 下，便于排查）
        out_tpl = os.path.join(self.output_dir, "_com_template.vsdx")
        if os.path.isdir(self.template_dir):
            with zipfile.ZipFile(out_tpl, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(self.template_dir):
                    for fname in files:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, self.template_dir).replace("\\", "/")
                        zf.write(full, rel)
            return out_tpl

        raise ComRendererError(f"模板路径无效：{self.template_dir}")

    def _load_masters(self):
        """按 NameU 预取模板 master（跨语言稳定）。"""
        for kind, name in MASTER_NAMES.items():
            master = self._find_master(name)
            if master is None:
                raise ComRendererError(
                    f"模板中找不到 master '{name}'（{kind}）。"
                )
            self._masters[kind] = master
        self._masters["connector"] = self._find_master("Dynamic connector")
        if self._masters["connector"] is None:
            # 退回用 Process master 画线（几何上可凑合，但优先保证能跑）
            self._masters["connector"] = self._masters["rect"]

    def _find_master(self, name):
        """尝试多种方式查找 master：NameU / Name / 遍历。"""
        masters = self.doc.Masters
        # 1) ItemU
        try:
            return masters.ItemU(name)
        except Exception:
            pass
        # 2) Item
        try:
            return masters.Item(name)
        except Exception:
            pass
        # 3) 遍历 NameU/Name 精确匹配
        try:
            for i in range(1, masters.Count + 1):
                m = masters.Item(i)
                try:
                    if m.NameU == name or m.Name == name:
                        return m
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def stop(self):
        """关闭 Visio 应用，释放 COM 资源。"""
        if self.doc is not None:
            try:
                self.doc.Close()
            except Exception:
                pass
            self.doc = None
        if self.visio is not None:
            try:
                self.visio.Quit()
            except Exception:
                pass
            self.visio = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()

    # ---------- 主入口 ----------

    def generate(self, cfile, filename, export_png=False):
        """生成整个文件的 VSDX：每个函数一页。

        复用 vsdx_generator 的布局引擎计算坐标与连接端点。
        首次调用会自动启动 Visio 并打开模板；结束时自动关闭。
        """
        started = self.visio is None
        if started:
            self.start()
        try:
            if not cfile.functions:
                raise ComRendererError("没有可绘制的函数。")

            # 复用布局引擎（重置 ID 计数器，避免跨运行残留）
            layout_engine = VsdxGenerator(output_dir=self.output_dir)
            VisioShape._id_counter = 1
            from generator.vsdx_generator import VisioConnector
            VisioConnector._id_counter = 1000

            # 逐函数布局
            pages_data = []  # [(func_name, layout, page_w, page_h)]
            for i, func in enumerate(cfile.functions):
                page_no = i + 1
                layout = layout_engine._layout_flow(func.flow)
                start = VisioShape("term", "开始", 0, 0,
                                   layout_engine.term_w, layout_engine.term_h)
                end = VisioShape("term", "结束", 0, 0,
                                 layout_engine.term_w, layout_engine.term_h)
                total = layout_engine._assemble(func.name, start, layout, end)
                layout_engine._normalize(total)
                page_w = max(total.w + 2 * layout_engine.margin, 8.0)
                page_h = max(total.h + 2 * layout_engine.margin, 10.0)
                pages_data.append((func.name, total, page_w, page_h))

            self._render_pages(pages_data, filename, export_png)
        finally:
            if started:
                self.stop()

    # ---------- 渲染 ----------

    def _render_pages(self, pages_data, filename, export_png=False):
        """把每个函数的布局绘制到独立页面。"""
        out_path = os.path.abspath(filename)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        # 清空模板自带页（page1 可能有示例内容），复用它作为第一页
        page1 = self.doc.Pages.Item(1)
        self._clear_page(page1)

        first = True
        for idx, (func_name, layout, page_w, page_h) in enumerate(pages_data):
            if first:
                page = page1
                first = False
            else:
                page = self.doc.Pages.Add()
            # 页面命名：中文函数名可能含非法字符，用 函数名 或 页-N 兜底
            try:
                page.Name = func_name or f"页-{idx + 1}"
            except Exception:
                page.Name = f"页-{idx + 1}"

            # 页面尺寸（英寸）——模板 DrawingScale 是 MM，必须显式设为英寸，
            # 否则 page.Drop 的裸坐标会被当作毫米，图形缩小 25.4 倍。
            try:
                page.PageSheet.CellsU("PageWidth").FormulaU = f"{page_w} in"
                page.PageSheet.CellsU("PageHeight").FormulaU = f"{page_h} in"
                # 绘图单位与页面单位统一为 1 英寸，保证 Drop 坐标 = 英寸
                page.PageSheet.CellsU("DrawingScale").FormulaU = "1 in"
                page.PageSheet.CellsU("PageScale").FormulaU = "1 in"
            except Exception:
                pass

            self._draw_page(page, layout, page_h)

        # 保存
        try:
            self.doc.SaveAs(out_path)
        except Exception as exc:
            raise ComRendererError(f"保存 VSDX 失败：{exc}") from exc
        print(f"VSDX saved (COM): {out_path} ({len(pages_data)} pages)")

        # 可选：导出 PNG 预览（便于快速检查排版，无需打开 Visio）
        if export_png:
            self._export_pngs(pages_data, out_path)

    def _clear_page(self, page):
        """删除页面上的所有形状。"""
        try:
            while page.Shapes.Count > 0:
                page.Shapes.Item(1).Delete()
        except Exception:
            pass

    def _export_pngs(self, pages_data, out_path):
        """把每一页导出为 PNG 预览，放在 VSDX 同目录下。"""
        base = os.path.splitext(out_path)[0]
        try:
            for idx in range(1, len(pages_data) + 1):
                page = self.doc.Pages.Item(idx)
                png_path = f"{base}_p{idx}.png"
                try:
                    page.Export(png_path)
                except Exception:
                    pass
            print(f"PNG previews exported next to: {base}")
        except Exception:
            pass

    # ---------- 单页绘制 ----------

    def _draw_page(self, page, layout, page_h):
        """绘制单页：先画形状，再画连接线，最后胶合。

        用布局引擎的 canvas 几何（VisioShape.x/y/w/h）做连接端点匹配，
        避免通过 COM 读取形状尺寸带来的单位歧义。
        """
        shape_by_id = {}  # VisioShape.id -> COM shape
        geo_by_id = {}    # VisioShape.id -> VisioShape (canvas 几何)
        for sh in layout.shapes:
            com_shape = self._drop_shape(page, sh, page_h)
            shape_by_id[sh.id] = com_shape
            geo_by_id[sh.id] = sh

        for cn in layout.connectors:
            self._draw_connector(page, cn, shape_by_id, geo_by_id, page_h)

    # ---------- 形状 ----------

    def _drop_shape(self, page, sh, page_h):
        """按坐标放置一个形状（引用模板 master）。"""
        master = self._masters[sh.kind]
        # canvas Y 向下 -> Visio Y 向上
        pin_x = sh.x + sh.w / 2.0
        pin_y = page_h - sh.y - sh.h / 2.0

        com_shape = page.Drop(master, pin_x, pin_y)
        try:
            com_shape.CellsU("Width").FormulaU = f"{sh.w} in"
        except Exception:
            pass
        try:
            com_shape.CellsU("Height").FormulaU = f"{sh.h} in"
        except Exception:
            pass
        try:
            com_shape.Text = sh.text or ""
        except Exception:
            pass
        return com_shape

    # ---------- 连接线 ----------

    def _draw_connector(self, page, cn, shape_by_id, geo_by_id, page_h):
        """画一条连接线：Dynamic connector + 精确端点 + 胶合到正确连接点。

        布局引擎（vsdx_generator）已按"最短连接"原则算好端点：
          - 上下关系 -> 上块下边框中点 -> 下块上边框中点
          - 左右关系 -> 左块右边框中点 -> 右块左边框中点
          - 判定/循环分支 -> 按语义从菱形特定边出/入
        这里用 Dynamic connector master 画线，具备自动正交拐弯能力；
        胶合时用布局指定的边连接点（begin_part/end_part），保证
        开始块从下边框出线、结束块从上边框进线，不被自动路由带偏。
        """
        # 定位源/目标形状（用 canvas 几何就近匹配）。
        # on_edge 表示端点是否真的落在形状边上：
        #   - True  -> 正常胶合到该形状的连接点
        #   - False -> 端点是不贴任何形状的"自由点"（如 if 汇合点），
        #              不能胶合（否则线两端粘到同一形状形成回环）
        src_shape, src_guess, src_on_edge = self._locate(cn.begin, geo_by_id)
        dst_shape, dst_guess, dst_on_edge = self._locate(cn.end, geo_by_id)
        # 至少一端贴边才画（汇合点这类自由端点允许存在，另一端仍要连上形状）。
        if not src_on_edge and not dst_on_edge:
            return
        src_com = shape_by_id[src_shape.id] if src_on_edge else None
        dst_com = shape_by_id[dst_shape.id] if dst_on_edge else None

        # 精确端点（canvas -> Visio Y 翻转）
        bx = cn.begin[0]
        by = page_h - cn.begin[1]
        ex = cn.end[0]
        ey = page_h - cn.end[1]

        # 用 Dynamic connector master 放置连接线，PinX/PinY 放中点
        conn_master = self._masters["connector"]
        mid_x = (bx + ex) / 2.0
        mid_y = (by + ey) / 2.0
        com_cn = page.Drop(conn_master, mid_x, mid_y)

        # 设精确端点作为初始位置（胶合后会吸附到连接点）
        try:
            com_cn.CellsU("BeginX").FormulaU = f"{bx} in"
            com_cn.CellsU("BeginY").FormulaU = f"{by} in"
            com_cn.CellsU("EndX").FormulaU = f"{ex} in"
            com_cn.CellsU("EndY").FormulaU = f"{ey} in"
        except Exception:
            pass

        # 分支标签
        if cn.label:
            try:
                com_cn.Text = cn.label
            except Exception:
                pass

        # 胶合：仅当端点真正贴边时才胶合（防止汇合点被误胶合形成回环）。
        src_edge = cn.begin_part if cn.begin_part is not None else src_guess
        dst_edge = cn.end_part if cn.end_part is not None else dst_guess
        if src_on_edge:
            self._glue(com_cn, src_com, src_edge, begin=True)
        if dst_on_edge:
            self._glue(com_cn, dst_com, dst_edge, begin=False)

        # 固定起点/终点连接点，防止动态路由把线重新绕到其他边；
        # 中间走线仍由 Visio 自动正交拐弯。
        try:
            com_cn.CellsU("ConFixedCode").FormulaU = "3"
        except Exception:
            pass

    def _locate(self, point, geo_by_id):
        """在 canvas 几何中找离 point 最近的形状及其方位（part）。

          - point 为 canvas 坐标（Y 向下）
          - 返回 (VisioShape, part, on_edge)
              part:    1=上 2=下 3=左 4=右
              on_edge: 端点是否真的落在形状边上（≤0.05 in）。
                       汇合点这类"自由点"不在任何形状边上，on_edge=False，
                       此时不应胶合（否则会把线两端都粘到同一形状形成回环）。
          - 找不到返回 (None, None, False)
        """
        px, py = point
        best = None
        best_dist = 1e9
        best_part = 2  # 默认下
        for sh in geo_by_id.values():
            x0, y0 = sh.x, sh.y
            x1, y1 = sh.x + sh.w, sh.y + sh.h
            dx = max(x0 - px, 0, px - x1)
            dy = max(y0 - py, 0, py - y1)
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = sh
                d_top = abs(py - y0)
                d_bot = abs(py - y1)
                d_left = abs(px - x0)
                d_right = abs(px - x1)
                m = min(d_top, d_bot, d_left, d_right)
                if m == d_top:
                    best_part = 1
                elif m == d_bot:
                    best_part = 2
                elif m == d_left:
                    best_part = 3
                else:
                    best_part = 4
        # 阈值：只有真正贴边才认为在边上（0.05 in ≈ 1.27mm）。
        # 布局端点精确落在形状边框中点，距离≈0；汇合点等自由点距离大。
        if best is not None and best_dist <= 0.05:
            return best, best_part, True
        return None, None, False

    def _glue(self, com_cn, com_shape, part, begin=True):
        """把连接线一端胶合到形状的指定连接点。

        用 GlueTo 绑定到形状的连接点单元格，拖动形状时连线自动跟随。
        按形状类型（term/rect/diamond）选择对应的连接点映射表。
        """
        kind = self._shape_kind(com_shape)
        mapping = PART_TO_CONNECTION_ROW.get(kind, PART_TO_CONNECTION_ROW["rect"])
        row = mapping.get(part, "X3")
        # 连接点单元格名：Connections.X1..X4（行索引从 1 起）
        cell_name = f"Connections.{row}"
        try:
            # 通过形状名引用单元格（Sheet.N!Connections.Xk）
            target = com_shape.CellsU(cell_name)
        except Exception:
            try:
                target = com_shape.Cells(cell_name)
            except Exception:
                return
        try:
            if begin:
                com_cn.CellsU("BeginX").GlueTo(target)
            else:
                com_cn.CellsU("EndX").GlueTo(target)
        except Exception:
            # 胶合失败不致命：保留精确端点坐标，至少线段位置正确
            pass

    def _shape_kind(self, com_shape):
        """根据 master 判断形状类型（term/rect/diamond）。"""
        try:
            name = com_shape.Master.NameU
        except Exception:
            return "rect"
        if name in ("Start/End", "开始/结束"):
            return "term"
        if name in ("Decision", "判定"):
            return "diamond"
        return "rect"


# ---------- 便捷入口 ----------

def render_with_com(cfile, filename, template_dir=None, export_png=False):
    """一行调用：用 COM 渲染器生成 VSDX。返回是否成功。

    generate() 内部会自动 start/stop，因此这里无需重复管理生命周期。
    """
    renderer = ComVsdxRenderer(template_dir=template_dir,
                               output_dir=os.path.dirname(os.path.abspath(filename)) or "output")
    return renderer.generate(cfile, filename, export_png=export_png)
