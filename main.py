import sys

import pipeline


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("用法: python main.py <source.c> [输出基目录，默认 output/]")
        sys.exit(1)

    filename = sys.argv[1]
    base_dir = sys.argv[2] if len(sys.argv) > 2 else "output"

    try:
        result = pipeline.generate_design(filename, base_dir=base_dir)
    except RuntimeError as exc:
        print("错误: %s" % exc)
        sys.exit(1)

    vsdx_value = result["design_vsdx"] or "<Visio 不可用>"
    if result["design_vsdx"] is None:
        print("提示: 未生成 .vsdx，请先安装 Microsoft Visio 桌面版，并执行: pip install pywin32")

    print("V6.1 COMPLETE  (functions: %d, structs: %d, enums: %d, docx: %s, vsdx: %s)" % (
        result["functions"],
        result["structs"],
        result["enums"],
        result["design_docx"],
        vsdx_value,
    ))
