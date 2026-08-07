import re
import os


class PlantUMLGenerator:
    """生成 PlantUML 流程图（含分支结构）。"""

    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _path(self, name):
        return os.path.join(self.output_dir, name)

    def generate_call_graph(self, functions):
        with open(self._path("call_graph.puml"), "w", encoding="utf8") as f:
            f.write("@startuml\n\ntitle 函数调用关系\n\n")
            for func in functions:
                for call in func.calls:
                    f.write('%s --> %s\n' % (func.name, call))
            f.write("\n@enduml\n")

    def generate_flow(self, function):
        safe_name = re.sub(r'[^A-Za-z0-9_]', '_', function.name)
        filename = self._path(safe_name + "_flow.puml")
        with open(filename, "w", encoding="utf8") as f:
            f.write("@startuml\n\nstart\n\n")
            self._write_flow(f, function.flow)
            f.write("\nstop\n\n@enduml\n")

    # ---------- 流程树渲染 ----------

    def _write_flow(self, f, node):
        if node is None:
            return
        kind = node.kind
        if kind == "block":
            for c in node.children:
                self._write_flow(f, c)
        elif kind == "sequence":
            self._write_step(f, node.label)
        elif kind == "if":
            self._write_if(f, node)
        elif kind in ("for", "while", "do_while"):
            self._write_loop(f, node)
        elif kind == "switch":
            self._write_switch(f, node)
        elif kind == "case":
            # case 在 switch 中处理
            pass
        elif kind == "return":
            label = "返回" + (" " + node.label if node.label else "")
            f.write(':%s;\n' % self._safe(label))
        elif kind in ("break", "continue"):
            f.write(':%s;\n' % self._safe("break" if kind == "break" else "continue"))
        else:
            if node.label:
                self._write_step(f, node.label)

    def _write_step(self, f, label):
        f.write(':%s;\n' % self._safe(label))

    def _write_if(self, f, node):
        cond = self._safe(node.condition) or "条件"
        f.write('if (%s) then (是)\n' % cond)
        for c in node.children:
            self._write_flow(f, c)
        if node.alternate is not None:
            f.write('else (否)\n')
            for c in node.alternate.children:
                self._write_flow(f, c)
        f.write('endif\n\n')

    def _write_loop(self, f, node):
        cond = self._safe(node.condition)
        if node.kind == "for":
            f.write('repeat\n')
            for c in node.children:
                self._write_flow(f, c)
            f.write('repeat while (%s)\n\n' % (cond or "条件"))
        else:
            f.write('while (%s) is (真)\n' % (cond or "条件"))
            for c in node.children:
                self._write_flow(f, c)
            f.write('endwhile\n\n')

    def _write_switch(self, f, node):
        cond = self._safe(node.condition)
        f.write('switch (%s)\n' % cond)
        for case in node.children:
            if case.kind == "case":
                f.write('case ( %s )\n' % self._safe(case.label))
                for c in case.children:
                    self._write_flow(f, c)
                # 每个 case 自动闭合
            elif case.kind == "default":
                f.write('case ( default )\n')
                for c in case.children:
                    self._write_flow(f, c)
        f.write('endswitch\n\n')

    def _safe(self, text):
        """转义 PlantUML 特殊字符。"""
        if text is None:
            return ""
        text = str(text)
        text = text.replace("\n", " ")
        text = re.sub(r'\s+', ' ', text).strip()
        text = text.replace("\\", "\\\\").replace("\"", "\\\"")
        text = text.replace("(", "(").replace(")", ")")
        # PlantUML 中 % 和 | 需转义
        text = text.replace("%", "%%").replace("|", "\\|")
        return text
