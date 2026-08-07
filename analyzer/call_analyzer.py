import re


class CallAnalyzer:
    """调用关系分析器。

    解析器已基于 AST 提取函数直接调用（function.calls）。
    此分析器从流程树中再次收集调用序列节点，作为补充与校验，
    最终合并去重。过滤 sizeof 等 C 关键字。
    """

    KEYWORDS = {
        "if", "for", "while", "switch", "sizeof", "return",
        "do", "else", "case", "break", "continue", "goto",
        "int", "char", "float", "double", "void", "unsigned",
        "static", "const", "struct", "enum", "union",
    }

    def analyze(self, function):
        calls = list(function.calls)

        # 从流程树中收集调用（sequence 节点标签形如 "func(...)"）
        def walk(node):
            if node is None:
                return
            if node.kind == "sequence":
                label = node.label or ""
                for name in re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', label):
                    if name not in calls and name not in self.KEYWORDS:
                        calls.append(name)
            for c in node.children:
                walk(c)
            walk(node.alternate)

        walk(function.flow)

        function.calls = calls
        return function
