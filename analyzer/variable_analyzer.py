import re


class VariableAnalyzer:
    """分析函数的局部变量。

    解析器已基于 AST 提取函数体顶层的局部变量；
    此分析器从流程树中补充嵌套块内的变量声明，
    并对每个变量统计使用次数。
    """

    def analyze(self, function):
        variables = []
        seen = {}

        # 1) 解析器已提取的顶层局部变量
        for v in function.local_variables:
            key = v["name"]
            if key not in seen:
                seen[key] = {"type": v["type"], "name": key, "usage": 0}
                variables.append(seen[key])

        # 2) 从流程树递归收集嵌套块中的声明/赋值
        def walk(node):
            if node is None:
                return
            if node.kind == "sequence":
                label = node.label or ""
                m = re.match(
                    r'^\s*((?:unsigned\s+|const\s+)?[A-Za-z_][A-Za-z0-9_]*(?:\s+\*?)*)\s+([A-Za-z_][A-Za-z0-9_]*)\b',
                    label,
                )
                if m:
                    key = m.group(2)
                    if key not in seen:
                        seen[key] = {"type": m.group(1).strip(), "name": key, "usage": 0}
                        variables.append(seen[key])
            for c in node.children:
                walk(c)
            walk(node.alternate)

        walk(function.flow)

        # 3) 统计变量在函数体中的出现次数
        for v in variables:
            v["usage"] = len(re.findall(r'\b' + re.escape(v["name"]) + r'\b', function.body))

        function.local_variables = variables
        return function
