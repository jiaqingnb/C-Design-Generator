class FlowAnalyzer:
    """流程分析器。

    解析器已把函数体解析为流程树（function.flow）。
    此分析器从流程树中提取线性的执行步骤摘要（供 Markdown 展示），
    并统计分支/循环/return 数量。注意：不覆盖 function.flow。
    """

    def analyze(self, function):
        steps = []

        def walk(node):
            if node is None:
                return
            if node.kind == "block":
                for c in node.children:
                    walk(c)
            elif node.kind == "sequence":
                if node.label:
                    steps.append(node.label)
            elif node.kind == "if":
                steps.append(f"如果 {node.condition}")
                for c in node.children:
                    walk(c)
                if node.alternate:
                    steps.append("否则:")
                    for c in node.alternate.children:
                        walk(c)
            elif node.kind in ("for", "while", "do_while"):
                steps.append(f"{node.kind}循环({node.condition})")
                for c in node.children:
                    walk(c)
            elif node.kind == "switch":
                steps.append(f"switch({node.condition})")
                for c in node.children:
                    walk(c)
            elif node.kind in ("case", "default"):
                steps.append(f"分支 {node.label}")
                for c in node.children:
                    walk(c)
            elif node.kind == "return":
                steps.append("返回 " + node.label if node.label else "返回")
            elif node.kind in ("break", "continue"):
                steps.append(node.kind)

        walk(function.flow)

        # 统计结构
        counts = {"if": 0, "loop": 0, "switch": 0, "return": 0}

        def count(node):
            if node is None:
                return
            if node.kind == "if":
                counts["if"] += 1
            elif node.kind in ("for", "while", "do_while"):
                counts["loop"] += 1
            elif node.kind == "switch":
                counts["switch"] += 1
            elif node.kind == "return":
                counts["return"] += 1
            for c in node.children:
                count(c)
            count(node.alternate)

        count(function.flow)

        function.flow_summary = steps
        function.structure_counts = counts
        return function
