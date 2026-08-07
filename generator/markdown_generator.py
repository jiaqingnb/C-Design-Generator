class MarkdownGenerator:
    """生成软件详细设计 Markdown 文档。"""

    def generate(self, cfile, filename):
        with open(filename, "w", encoding="utf8") as f:
            f.write("# 软件详细设计\n\n")

            # 模块概览
            f.write("## 1 模块说明\n\n")
            f.write("- 解析文件: %s\n" % (cfile.filename or "未知"))
            f.write("- 函数数量: %d\n" % len(cfile.functions))
            f.write("- 结构体数量: %d\n" % len(cfile.structs))
            f.write("- 枚举数量: %d\n" % len(cfile.enums))
            f.write("- 宏定义数量: %d\n" % len(cfile.macros))
            f.write("\n")

            # 数据结构
            if cfile.structs or cfile.enums:
                f.write("## 2 数据结构设计\n\n")
                for s in cfile.structs:
                    f.write("### struct %s\n\n" % s.name)
                    f.write("| 成员 | 类型 |\n|---|---|\n")
                    for m in s.members:
                        f.write("| %s | `%s` |\n" % (m["name"], m["type"]))
                    f.write("\n")
                for e in cfile.enums:
                    f.write("### enum %s\n\n" % e.name)
                    f.write("| 枚举项 | 值 |\n|---|---|\n")
                    for it in e.items:
                        f.write("| %s | %s |\n" % (it["name"], it["value"]))
                    f.write("\n")

            # 函数设计
            f.write("## 3 函数设计\n\n")
            for func in cfile.functions:
                self._write_function(f, func)

    def _write_function(self, f, func):
        f.write("### %s\n\n" % func.name)
        f.write("```c\n")
        f.write("%s %s(%s)\n" % (
            func.return_type,
            func.name,
            ", ".join(p.type + (" " + p.name if p.name else "") for p in func.parameters),
        ))
        f.write("```\n\n")

        f.write("#### 功能描述\n\n")
        f.write(func.description + "\n\n")

        f.write("#### 输入参数\n\n")
        if func.inputs:
            f.write("| 参数 | 类型 | 方向 |\n|---|---|---|\n")
            for i in func.inputs:
                f.write("| %s | `%s` | %s |\n" % (i["name"], i["type"], i["direction"]))
        else:
            f.write("无\n")
        f.write("\n")

        f.write("#### 输出\n\n")
        if func.outputs:
            f.write("| 名称 | 类型 | 方向 |\n|---|---|---|\n")
            for o in func.outputs:
                f.write("| %s | `%s` | %s |\n" % (o["name"], o["type"], o["direction"]))
        else:
            f.write("无\n")
        f.write("\n")

        f.write("#### 局部变量\n\n")
        if func.local_variables:
            f.write("| 变量 | 类型 | 使用次数 |\n|---|---|---|\n")
            for v in func.local_variables:
                f.write("| %s | `%s` | %s |\n" % (v["name"], v["type"], v.get("usage", "")))
        else:
            f.write("无\n")
        f.write("\n")

        f.write("#### 调用关系\n\n")
        if func.calls:
            for c in func.calls:
                f.write("- %s\n" % c)
        else:
            f.write("无\n")
        f.write("\n")

        # 结构统计
        counts = getattr(func, "structure_counts", None)
        if counts:
            f.write("#### 结构复杂度\n\n")
            f.write("- 条件分支(if): %d\n" % counts["if"])
            f.write("- 循环: %d\n" % counts["loop"])
            f.write("- switch: %d\n" % counts["switch"])
            f.write("- return: %d\n" % counts["return"])
            f.write("\n")

        f.write("#### 执行流程\n\n")
        flow_summary = getattr(func, "flow_summary", None)
        if flow_summary:
            for index, s in enumerate(flow_summary, 1):
                f.write("%d. %s\n" % (index, s))
        else:
            f.write("无\n")
        f.write("\n")

        f.write("#### 源代码\n\n")
        f.write("```c\n")
        f.write(func.body)
        f.write("\n```\n\n")
