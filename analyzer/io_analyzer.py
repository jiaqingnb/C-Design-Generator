class IOAnalyzer:
    """分析函数的输入输出参数。"""

    def analyze(self, function):
        function.inputs = []
        function.outputs = []

        for p in function.parameters:
            if p.name:
                function.inputs.append({
                    "name": p.name,
                    "type": p.type,
                    "direction": "in",
                })

        # 有返回值（非 void）则加入输出
        ret = function.return_type
        if ret and ret != "void" and "void" not in ret:
            function.outputs.append({
                "name": "返回值",
                "type": ret,
                "direction": "out",
            })
        # 指针参数可能作为输出
        for p in function.parameters:
            if p.name and p.type and "*" in p.type:
                function.outputs.append({
                    "name": p.name,
                    "type": p.type,
                    "direction": "out",
                })

        return function
