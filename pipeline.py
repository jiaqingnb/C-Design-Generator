# -*- coding: utf-8 -*-
"""V6.1 生成流水线封装。

把 main.py 的「加载 → 解析 → 分析 → 生成」整条流水线封装为可复用函数，
供 CLI（main.py）与 GUI（gui_main.py）共同调用。

输出目录规则：按输入文件名（去扩展名）在指定基目录下创建独立子文件夹，
所有产物（design.docx / design.vsdx / design.md / *.puml / *_pN.png）都放进去。
"""

import os


def make_output_dir(src_file, base_dir="output"):
    """按输入文件名（去扩展名）创建独立输出文件夹。

    例：src_file = "test.c" → base_dir 下建 "test/" 子目录，返回其绝对路径。
    """
    stem = os.path.splitext(os.path.basename(src_file))[0]
    out_dir = os.path.join(base_dir, stem)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.abspath(out_dir)


def generate_design(src_file, out_dir=None, base_dir="output",
                    export_png=True, report=None):
    """加载 → 解析 → 分析 → 生成全部产物。

    Args:
        src_file: C 源文件路径（UTF-8 或 GBK）。
        out_dir: 输出目录；为 None 时用 make_output_dir(src_file, base_dir) 自动创建。
        base_dir: 仅当 out_dir 为 None 时生效，子文件夹的基目录。
        export_png: 是否导出 Visio PNG 预览。
        report: 可选回调 report(msg)，用于 GUI 日志输出（每步调用一次）。

    Returns:
        dict：{"out_dir", "design_docx", "design_vsdx", "design_md",
               "functions", "structs", "enums", "visio_error"}
        其中 design_vsdx 在 Visio 依赖缺失时为 None，visio_error 含原因。

    Raises:
        RuntimeError: 源文件读取失败或解析出 0 个函数。
    """
    from parser.file_loader import FileLoader
    from parser.ast_parser import ASTParser
    from analyzer.call_analyzer import CallAnalyzer
    from analyzer.variable_analyzer import VariableAnalyzer
    from analyzer.flow_analyzer import FlowAnalyzer
    from analyzer.io_analyzer import IOAnalyzer
    from analyzer.description_analyzer import DescriptionAnalyzer
    from analyzer.global_variable_analyzer import GlobalVariableAnalyzer
    from generator.markdown_generator import MarkdownGenerator
    from generator.plantuml_generator import PlantUMLGenerator
    from generator.docx_generator import DocxGenerator
    from generator.com_renderer import ComVsdxRenderer, ComRendererError

    if out_dir is None:
        out_dir = make_output_dir(src_file, base_dir)
    os.makedirs(out_dir, exist_ok=True)

    _log(report, "解析文件: %s" % src_file)
    code = FileLoader().load(src_file)
    if not code:
        raise RuntimeError("读取文件失败: %s" % src_file)

    cfile = ASTParser().parse(code)
    if not cfile.functions:
        raise RuntimeError("未解析到任何函数: %s" % src_file)
    # 修正：ASTParser 未给 cfile.filename 赋值，文档里"解析文件"一直显示"未知"
    cfile.filename = os.path.basename(src_file)

    analyzers = [
        CallAnalyzer(),
        VariableAnalyzer(),
        FlowAnalyzer(),
        IOAnalyzer(),
        DescriptionAnalyzer(),
        GlobalVariableAnalyzer(cfile.globals),
    ]
    for func in cfile.functions:
        for analyzer in analyzers:
            analyzer.analyze(func)

    _log(report, "解析完成：函数 %d，结构体 %d，枚举 %d" % (
        len(cfile.functions), len(cfile.structs), len(cfile.enums)))

    # 1) Markdown
    md_path = os.path.join(out_dir, "design.md")
    MarkdownGenerator().generate(cfile, md_path)
    _log(report, "已生成 Markdown: %s" % md_path)

    # 2) Word 函数说明表
    docx_path = os.path.join(out_dir, "design.docx")
    DocxGenerator().generate(cfile, docx_path)
    _log(report, "已生成 Word 说明表: %s" % docx_path)

    # 3) PlantUML 调用关系图 + 每函数流程图
    puml = PlantUMLGenerator(output_dir=out_dir)
    puml.generate_call_graph(cfile.functions)
    for func in cfile.functions:
        puml.generate_flow(func)
    _log(report, "已生成 PlantUML：call_graph.puml + %d 个 *_flow.puml" % len(cfile.functions))

    # 4) Visio 流程图（COM 调用本机 Visio；缺失时不阻塞其他产物）
    vsdx_path = os.path.join(out_dir, "design.vsdx")
    visio_error = None
    try:
        renderer = ComVsdxRenderer(output_dir=out_dir)
        renderer.generate(cfile, vsdx_path, export_png=export_png)
        _log(report, "已生成 Visio 流程图: %s" % vsdx_path)
    except ComRendererError as exc:
        visio_error = str(exc)
        _log(report, "Visio 依赖环境未就绪，跳过 .vsdx：%s" % exc)

    result = {
        "out_dir": out_dir,
        "design_docx": docx_path,
        "design_vsdx": vsdx_path if os.path.exists(vsdx_path) else None,
        "design_md": md_path,
        "functions": len(cfile.functions),
        "structs": len(cfile.structs),
        "enums": len(cfile.enums),
        "visio_error": visio_error,
    }
    _log(report, "完成：%s" % out_dir)
    return result


def _log(report, msg):
    print(msg)
    if report is not None:
        report(msg)
