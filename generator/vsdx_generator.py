# -*- coding: utf-8 -*-
"""Visio 流程图布局引擎。

本模块只负责**布局**：把流程树（FlowNode）递归转换为带坐标的
中间表示（VisioLayoutNode / VisioShape / VisioConnector），
供 COM 渲染器（com_renderer.py）调用本机 Visio 绘制。

布局规则（用户确认）：
  1. 每列的块中线对齐（同列 PinX 相同）
  2. 块之间必须连线，中点连接中点（竖线上下中点、横线左右中点）
  3. 分支注释：if/else 用「是/否」，for 循环用「遍历未结束/遍历结束」

坐标系统：canvas 坐标系（X 向右、Y 向下），单位英寸，原点左上。
实际落图时由 COM 渲染器做 Y 翻转。
"""

import os


# 分支标签
LABEL_YES = "是"
LABEL_NO = "否"
LABEL_LOOP_CONT = "执行循环"
LABEL_LOOP_END = "循环结束"


class VisioLayoutNode:
    """布局块。

    坐标：canvas 坐标系（X 向右、Y 向下），单位英寸，原点左上。
    """

    def __init__(self, x=0, y=0, w=0, h=0):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.shapes = []      # 块内所有形状（绝对坐标）
        self.connectors = []  # 块内连接线
        self.entry = None     # 顶部入口锚点 (x, y)
        self.exit = None      # 底部出口锚点 (x, y)
        self.column = 0       # 所在列（0=主列，1=第一分支列...）
        self.leaf_exits = []  # 叶子出口点列表（canvas 坐标）。
                              # 普通块=[exit]；嵌套 if 未汇聚时为各分支体
                              # 出口；最外层 if 汇聚后=[汇合点]。
        self.exit_label = ""  # 出口线的分支标签（如循环"遍历结束"）。
                              # 由 _layout_sequence 连接本块到下一块时使用。
        self.exit_part = 2    # 出口连接边（1上 2下 3左 4右）。默认下。
                              # 循环块等出口从右点出时设为 4，保证胶合正确。
        self.exit_labels = []  # 与 leaf_exits 一一对应的出口标签（可为空）。
                              # 用于无 else 的 if："否"直接穿过出口标"否"。


class VisioShape:
    """一个 Visio 形状。"""

    _id_counter = 1

    def __init__(self, kind="rect", text="", x=0, y=0, w=1, h=0.5):
        self.id = VisioShape._id_counter
        VisioShape._id_counter += 1
        self.kind = kind          # term / rect / diamond
        self.text = text
        self.x = x                # 左上角 X（canvas，英寸）
        self.y = y                # 左上角 Y（canvas，英寸）
        self.w = w
        self.h = h


class VisioConnector:
    """一条连接线。"""

    _id_counter = 1000

    def __init__(self, begin, end, label="", begin_part=None, end_part=None):
        self.id = VisioConnector._id_counter
        VisioConnector._id_counter += 1
        self.begin = begin        # (x, y) canvas 坐标
        self.end = end
        self.label = label
        self.from_id = None       # begin 端连接形状
        self.to_id = None         # end 端连接形状
        self.begin_part = begin_part  # 连接点：上1 下2 左3 右4
        self.end_part = end_part


class VsdxGenerator:
    """流程图布局引擎（供 COM 渲染器复用）。"""

    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._if_depth = 0  # if 嵌套深度：0=最外层，>0=嵌套
        # 布局参数（英寸）——与 master 默认尺寸一致：
        # Process/StartEnd 宽 25mm≈0.984in，Decision 宽 29mm≈1.14in
        self.node_w = 0.984    # 流程块宽（master 默认 25mm）
        self.node_h = 0.6      # 流程块高
        self.dia_w = 1.14      # 判定块宽（master 默认 29mm）
        self.dia_h = 1.0       # 判定块高
        self.term_w = 0.984    # 开始/结束宽（master 默认 25mm）
        self.term_h = 0.5      # 开始/结束高
        self.col_gap = 2.6     # 列间距
        self.row_gap = 0.8     # 行间距
        self.margin = 1.0      # 页面边距

    # ---------- 组装 ----------

    def _assemble(self, func_name, start, body_layout, end):
        body_w = max(body_layout.w, start.w, end.w)

        # 开始在上
        self._offset(start, (body_w - start.w) / 2, 0)
        # 主体在中间
        self._offset(body_layout,
                     (body_w - body_layout.w) / 2,
                     start.h + self.row_gap)
        # 结束在下
        end_y = start.h + self.row_gap + body_layout.h + self.row_gap
        self._offset(end, (body_w - end.w) / 2, end_y)

        total_h = end_y + end.h

        # 连接：开始 -> 主体 -> 结束
        conn1 = VisioConnector(
            (start.x + start.w / 2, start.y + start.h),   # 开始底部中点
            (body_layout.entry[0], body_layout.entry[1]) if body_layout.entry
            else (body_layout.x + body_layout.w / 2, body_layout.y),
            begin_part=2, end_part=1)
        conn1.from_id = start.id

        # 主体 -> 结束：主体可能有多个叶子出口（if 各分支），逐个连到结束。
        end_enter = (end.x + end.w / 2, end.y)
        conns2 = []
        if body_layout.leaf_exits:
            exits = body_layout.leaf_exits
        elif body_layout.exit is not None:
            exits = [body_layout.exit]
        else:
            exits = [(body_layout.x + body_layout.w / 2, body_layout.y + body_layout.h)]
        for ex in exits:
            conn2 = VisioConnector(
                ex, end_enter,
                begin_part=body_layout.exit_part, end_part=1)
            if body_layout.exit_label:
                conn2.label = body_layout.exit_label
            conn2.to_id = end.id
            conns2.append(conn2)

        total = VisioLayoutNode(0, 0, body_w, total_h)
        total.shapes = [start] + body_layout.shapes + [end]
        total.connectors = [conn1] + body_layout.connectors + conns2
        return total

    # ---------- 递归布局 ----------

    def _offset(self, layout, dx, dy):
        if layout is None:
            return
        if isinstance(layout, VisioShape):
            layout.x += dx
            layout.y += dy
            return
        layout.x += dx
        layout.y += dy
        for s in layout.shapes:
            s.x += dx
            s.y += dy
        for c in layout.connectors:
            c.begin = (c.begin[0] + dx, c.begin[1] + dy)
            c.end = (c.end[0] + dx, c.end[1] + dy)
        if layout.entry:
            layout.entry = (layout.entry[0] + dx, layout.entry[1] + dy)
        if layout.exit:
            layout.exit = (layout.exit[0] + dx, layout.exit[1] + dy)
        if layout.leaf_exits:
            layout.leaf_exits = [(x + dx, y + dy) for (x, y) in layout.leaf_exits]

    def _layout_flow(self, node):
        """布局单个流程节点。

        通过 self._if_depth 计数判断 if 是否嵌套：
          - _if_depth==0 时遇到的 if 是"最外层 if"，需要创建最终汇合点
          - _if_depth>0 时遇到的 if 是"嵌套 if"（在别的 if 分支体内），
            不创建汇合点，叶子出口上传给外层统一汇聚
        """
        if node is None:
            return VisioLayoutNode()
        kind = node.kind
        if kind == "block":
            return self._layout_sequence(node.children)
        if kind == "sequence":
            return self._layout_step(node.label)
        if kind == "if":
            return self._layout_if(node)
        if kind in ("for", "while", "do_while"):
            return self._layout_loop(node)
        if kind == "switch":
            return self._layout_sequence(node.children)
        if kind == "return":
            return self._layout_step(node.label or "返回")
        if kind in ("break", "continue"):
            return self._layout_step(node.kind)
        if node.children:
            return self._layout_sequence(node.children)
        return self._layout_step(node.label)

    def _layout_step(self, text):
        """处理步骤 -> 流程块（矩形）。"""
        lines = text.split("\n")
        w = max(self.node_w, self._text_width(text))
        h = max(self.node_h, 0.3 * len(lines) + 0.3)
        shape = VisioShape("rect", text, 0, 0, w, h)
        node = VisioLayoutNode(0, 0, w, h)
        node.shapes = [shape]
        node.entry = (w / 2, 0)
        node.exit = (w / 2, h)
        node.leaf_exits = [(w / 2, h)]
        return node

    def _layout_sequence(self, children):
        """纵向堆叠，所有块同列中线对齐。"""
        blocks = [self._layout_flow(c) for c in children if c is not None]
        blocks = [b for b in blocks if b.shapes or b.connectors]
        if not blocks:
            return VisioLayoutNode()

        max_w = max(b.w for b in blocks)
        y = 0
        for b in blocks:
            self._offset(b, (max_w - b.w) / 2 - b.x, y - b.y)
            y += b.h + self.row_gap
        total_h = y - self.row_gap

        total = VisioLayoutNode(0, 0, max_w, total_h)
        for b in blocks:
            total.shapes.extend(b.shapes)
            total.connectors.extend(b.connectors)
        # 块间连接：上块的每个出口 -> 下块顶部入口。
        # 注意：上块可能是未汇聚的嵌套 if，有多个 leaf_exits（多出口），
        # 必须逐个都连到下块入口，保证每个分支都能继续向下执行。
        for i in range(len(blocks) - 1):
            prev = blocks[i]
            cur = blocks[i + 1]
            cur_enter = cur.entry if cur.entry else (cur.x + cur.w / 2, cur.y)
            # 收集上块所有出口：优先用 leaf_exits（多出口），否则用 exit（单出口）
            if prev.leaf_exits:
                prev_exits = prev.leaf_exits
            elif prev.exit is not None:
                prev_exits = [prev.exit]
            else:
                prev_exits = [(prev.x + prev.w / 2, prev.y + prev.h)]
            for idx, pe in enumerate(prev_exits):
                conn = VisioConnector(
                    pe, cur_enter,
                    begin_part=prev.exit_part, end_part=1)
                # 出口标签：优先用 exit_labels（与 leaf_exits 对应，支持
                # 多出口各自不同标签，如无 else if 的"否"），否则用 exit_label。
                if prev.exit_labels and idx < len(prev.exit_labels):
                    conn.label = prev.exit_labels[idx]
                elif prev.exit_label:
                    conn.label = prev.exit_label
                total.connectors.append(conn)

        if blocks:
            first = blocks[0]
            last = blocks[-1]
            total.entry = (first.x + first.w / 2, first.y)
            # 出口：最后一个块的叶子出口集合（最外层 if 汇聚后为单汇合点，
            # 未汇聚的嵌套 if 为多出口）。
            if last.leaf_exits:
                total.leaf_exits = list(last.leaf_exits)
                total.exit = last.leaf_exits[0]
                # 传播出口标签/连接边（如循环块的"循环结束" + 右点出）
                total.exit_label = last.exit_label
                total.exit_part = last.exit_part
                total.exit_labels = list(last.exit_labels) if last.exit_labels else []
            elif last.exit is not None:
                total.leaf_exits = [last.exit]
                total.exit = last.exit
                total.exit_label = last.exit_label
                total.exit_part = last.exit_part
            else:
                total.exit = (last.x + last.w / 2, last.y + last.h)
                total.leaf_exits = [total.exit]
        return total

    def _layout_if(self, node):
        """if 分支：菱形判定 + 是/否两列。

        出口设计（用户确认）：不做物理汇合点。if 块的每个叶子出口
        （各分支体最后一个块的底部）直接作为 leaf_exits 暴露，
        由外层 _layout_sequence 逐个直接连接到后续节点（如 result 块）。
        这样分支执行完直接进入下一个块，不经过中间汇聚点。

        嵌套处理：通过 self._if_depth 区分"最外层 if"和"嵌套 if"，均不建汇合点。
        """
        cond = node.condition or "条件"
        dia = VisioShape("diamond", cond, 0, 0, self.dia_w, self.dia_h)

        # 是分支（右列）和否分支（左列）
        self._if_depth += 1
        try:
            then_layout = self._layout_sequence(node.children)
            else_layout = None
            if node.alternate is not None:
                else_layout = self._layout_sequence(node.alternate.children)
        finally:
            self._if_depth -= 1

        col_w = max(
            then_layout.w if then_layout.shapes else 0,
            else_layout.w if else_layout and else_layout.shapes else 0,
            self.node_w,
        )
        # 菱形居中，是右，否左
        dia_x = col_w + self.col_gap * 0.8
        dia_y = 0
        self._offset(dia, dia_x, 0)

        top_h = self.dia_h + self.row_gap
        then_x = dia_x + self.dia_w / 2 + self.col_gap * 0.6
        else_x = dia_x - self.dia_w / 2 - self.col_gap * 0.6 - col_w

        if then_layout.shapes:
            self._offset(then_layout, then_x + (col_w - then_layout.w) / 2, top_h)
        if else_layout and else_layout.shapes:
            self._offset(else_layout, else_x + (col_w - else_layout.w) / 2, top_h)

        then_bottom = top_h + (then_layout.h if then_layout.shapes else 0)
        else_bottom = top_h + (else_layout.h if else_layout and else_layout.shapes else 0)
        bottom = max(then_bottom, else_bottom)

        total_w = max(dia_x + self.dia_w / 2 + self.col_gap * 0.6 + col_w,
                      dia_x - self.dia_w / 2 - self.col_gap * 0.6)
        merge_x = dia_x + self.dia_w / 2

        total = VisioLayoutNode(0, 0, total_w, bottom)
        total.shapes = [dia]
        total.entry = (merge_x, 0)

        # 收集所有分支体的叶子出口（canvas 坐标）
        leaf_exits = []
        exit_labels = []
        if then_layout.shapes:
            total.shapes.extend(then_layout.shapes)
            total.connectors.extend(then_layout.connectors)
            # 菱形右点 -> 是分支入口
            total.connectors.append(VisioConnector(
                (dia_x + self.dia_w, dia_y + self.dia_h / 2),
                then_layout.entry if then_layout.entry else
                (then_layout.x + then_layout.w / 2, then_layout.y),
                label=LABEL_YES, begin_part=4, end_part=3))
            then_exits = (then_layout.leaf_exits
                          if then_layout.leaf_exits
                          else ([then_layout.exit] if then_layout.exit else []))
            leaf_exits.extend(then_exits)
            exit_labels.extend([""] * len(then_exits))

        if else_layout and else_layout.shapes:
            total.shapes.extend(else_layout.shapes)
            total.connectors.extend(else_layout.connectors)
            # 菱形左点 -> 否分支入口
            total.connectors.append(VisioConnector(
                (dia_x, dia_y + self.dia_h / 2),
                else_layout.entry if else_layout.entry else
                (else_layout.x + else_layout.w / 2, else_layout.y),
                label=LABEL_NO, begin_part=3, end_part=4))
            else_exits = (else_layout.leaf_exits
                          if else_layout.leaf_exits
                          else ([else_layout.exit] if else_layout.exit else []))
            leaf_exits.extend(else_exits)
            exit_labels.extend([""] * len(else_exits))
        else:
            # 无 else：判定块下点作为"否"出口（条件不成立直接向下穿过，
            # 连到顺序执行的第一个块）。
            dia_bottom = (merge_x, self.dia_h)
            leaf_exits.append(dia_bottom)
            exit_labels.append(LABEL_NO)

        # 无任何分支体：菱形底部直接作为叶子出口
        if not leaf_exits:
            leaf_exits = [(merge_x, self.dia_h)]
            exit_labels.append("")

        # 不做物理汇合点：直接把所有叶子出口暴露给外层。
        # total.exit 取最后一个叶子出口（供单出口上下文使用）。
        total.exit = leaf_exits[-1]
        total.leaf_exits = leaf_exits
        total.exit_labels = exit_labels

        return total

    def _layout_loop(self, node):
        """循环：菱形判定 + 循环体。

        连接点分工（用户确认，就近 + 进出分开 + 不撞线）：
          - 判定块上点 <- 前块入口（sequence 连入）
          - 判定块左点 -> 循环体入口（label=遍历未结束）
          - 循环体出口 -> 判定块下点（回流，无标签；线短就近）
          - 判定块右点 -> 循环外块（label=遍历结束），从右边空闲点出，
            与回环线（走下方/左侧）不相撞，作为本块 exit / leaf_exits，
            由外层 _layout_sequence 连到循环外。
        """
        cond = node.condition or "条件"
        dia = VisioShape("diamond", cond, 0, 0, self.dia_w, self.dia_h)
        body_layout = self._layout_sequence(node.children)

        body_w = max(body_layout.w if body_layout.shapes else 0, self.node_w)
        body_h = body_layout.h if body_layout.shapes else 0

        # 判定块在右侧（留左边给循环体），循环体在判定块左侧
        dia_x = self.margin + self.col_gap + body_w
        body_x = self.margin
        # 垂直居中：判定块与循环体顶部对齐，整体高度取两者较大
        top_h = max(self.dia_h, body_h)
        total_w = dia_x + self.dia_w + self.margin

        self._offset(dia, dia_x, 0)
        if body_layout.shapes:
            self._offset(body_layout, body_x, 0)

        # 判定块四个连接点
        dia_right = (dia_x + self.dia_w, self.dia_h / 2)          # 右
        dia_top = (dia_x + self.dia_w / 2, 0)                     # 上
        dia_bottom = (dia_x + self.dia_w / 2, self.dia_h)         # 下
        dia_left = (dia_x, self.dia_h / 2)                        # 左

        total = VisioLayoutNode(0, 0, total_w, top_h)
        total.shapes = [dia]
        total.entry = dia_top                                       # 上点 = 入口

        if body_layout.shapes:
            total.shapes.extend(body_layout.shapes)
            total.connectors.extend(body_layout.connectors)
            # 判定块左点 -> 循环体入口（执行循环）
            total.connectors.append(VisioConnector(
                dia_left,
                body_layout.entry if body_layout.entry else
                (body_layout.x + body_layout.w / 2, body_layout.y),
                label=LABEL_LOOP_CONT, begin_part=3, end_part=4))
            # 循环体所有出口 -> 判定块下点（回流；线短就近）。
            # 必须用 leaf_exits 而不是 exit：循环体内可能有嵌套 if，
            # 其多个分支出口（是/否）都要回流到判定块，否则嵌套 if 的
            # "否"分支会丢失。回流线带上对应的出口标签（如嵌套 if 的"否"）。
            body_exits = (body_layout.leaf_exits
                          if body_layout.leaf_exits
                          else ([body_layout.exit] if body_layout.exit else []))
            body_labels = (body_layout.exit_labels
                           if getattr(body_layout, "exit_labels", None)
                           else ([""] * len(body_exits)))
            for bi, be in enumerate(body_exits):
                lab = body_labels[bi] if bi < len(body_labels) else ""
                total.connectors.append(VisioConnector(
                    be, dia_bottom,
                    label=lab, begin_part=2, end_part=2))
            # 判定块右点 -> 循环外（循环结束），从右边空闲点出
            exit_pt = dia_right
            total.exit = exit_pt
            total.leaf_exits = [exit_pt]
            total.exit_label = LABEL_LOOP_END
            total.exit_part = 4   # 从右点出（胶合到 Connections.X2）
        else:
            # 无循环体：判定块右点直接为出口
            exit_pt = dia_right
            total.exit = exit_pt
            total.leaf_exits = [exit_pt]
            total.exit_label = LABEL_LOOP_END
            total.exit_part = 4   # 从右点出

        return total

    def _text_width(self, text, default=None):
        if not text:
            return self.node_w
        max_len = max(len(l) for l in text.split("\n"))
        w = max_len * 0.11 + 0.4
        return max(w, default or self.node_w)

    # ---------- 归一化 ----------

    def _normalize(self, layout):
        min_x = min((s.x for s in layout.shapes), default=0)
        min_y = min((s.y for s in layout.shapes), default=0)
        for c in layout.connectors:
            min_x = min(min_x, c.begin[0], c.end[0])
            min_y = min(min_y, c.begin[1], c.end[1])
        dx = self.margin - min_x if min_x < self.margin else 0
        dy = self.margin - min_y if min_y < self.margin else 0
        if dx or dy:
            self._offset(layout, dx, dy)
