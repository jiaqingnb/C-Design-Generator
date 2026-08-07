import sys


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


if __name__ == "__main__":

    filename = sys.argv[1]


    loader = FileLoader()


    code = loader.load(filename)


    parser = ASTParser()


    cfile = parser.parse(code)


    analyzers = [
        CallAnalyzer(),
        VariableAnalyzer(),
        FlowAnalyzer(),
        IOAnalyzer(),
        DescriptionAnalyzer(),
        GlobalVariableAnalyzer(cfile.globals)
    ]


    for func in cfile.functions:

        for analyzer in analyzers:
            analyzer.analyze(func)


    md = MarkdownGenerator()
    md.generate(cfile, "output/design.md")


    docx_gen = DocxGenerator()
    docx_gen.generate(cfile, "output/design.docx")


    puml = PlantUMLGenerator()
    puml.generate_call_graph(cfile.functions)

    for func in cfile.functions:
        puml.generate_flow(func)


    # Visio 流程图：通过 COM 渲染调用本机 Visio 绘制（含原生连线）。
    try:
        com_renderer = ComVsdxRenderer(output_dir="output")
        com_renderer.generate(cfile, "output/design.vsdx", export_png=True)
    except ComRendererError as exc:
        print("依赖环境未安装完毕不可使用")
        print("  详情: %s" % exc)
        print("  请先安装 Microsoft Visio 桌面版，并执行：pip install pywin32")
        sys.exit(1)


    print("V6 COMPLETE  (functions: %d, structs: %d, enums: %d, docx: design.docx, vsdx: design.vsdx)" % (
        len(cfile.functions),
        len(cfile.structs),
        len(cfile.enums),
    ))
