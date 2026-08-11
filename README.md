# C 代码自动解析与软件详细设计生成工具

个人版嵌入式软件辅助开发工具：输入一个 C 源文件，自动解析函数结构、调用关系、全局变量与执行流程，生成**软件详细设计文档**与**流程图**。

- **函数说明表** → Word 格式（`.docx`）
- **函数流程图** → Visio 格式（`.vsdx`，每函数一页）

## 功能概览

对输入的 `.c` 文件（UTF-8 或 GBK 编码均可）自动完成：

| 能力 | 说明 |
|---|---|
| 函数解析 | 函数名、返回类型、参数列表（含指针/数组/const）、static 标识 |
| 数据结构 | struct 成员、enum 枚举项、typedef |
| 调用关系 | 函数直接调用列表，生成调用关系图 |
| 全局变量 | 识别引用的全局变量、修改的全局变量 |
| 执行流程 | 以**注释为块边界**还原函数流程（if/else、switch、for/while 分支结构） |
| Word 说明表 | 原型、概述、参数、返回值、引用、全局变量引用/修改 |
| Visio 流程图 | 每个函数一页，标准流程图符号，块间自动连线 |

### 流程图规则

- 流程块按**注释**填充：每个注释对应一个块，注释到下一注释之间的语句并入该块；无注释的语句回退用代码文本。
- 分支标签：`if/else` 用「是/否」，`for/while` 循环用「遍历未结束/遍历结束」。
- 块按列对齐（主流程一列，分支右移），块间中点连线。

## 安装与依赖

### 运行环境

- **Windows**（COM 自动化调用本机 Visio 必需）
- Python 3.8+

### 1. Python 依赖

```bash
pip install tree-sitter tree-sitter-c python-docx pywin32 PySide6
```

| 包 | 用途 | 必装 |
|---|---|---|
| `tree-sitter` + `tree-sitter-c` | C 语言 AST 解析（解析核心） | ✅ 必需 |
| `python-docx` | 生成 Word 函数说明表 | ✅ 必需 |
| `pywin32` | 调用本机 Visio COM 接口绘制连线 | ✅ 必需（COM 自动化调用） |
| `PySide6` | GUI 界面（V6.1） | ✅ 使用 GUI 时必需 |
| `vsdx` | 读取/校验 VSDX（仅开发调试用） | 可选 |

### 2. 软件

- **Microsoft Visio 桌面版**（2016+，推荐 2019 专业版）——生成 Visio 流程图时通过 COM 自动化调用，**必需安装**。

### 3. 模板文件

`templates/` 目录内置了微软官方基本流程图形状的模板（`vsdx_model/`），**无需额外配置**。运行时自动打包为临时 `.vsdx` 供 Visio 打开。

## 快速开始

### 方式一：GUI（推荐，V6.1）

```bash
cd py_pro
python gui_main.py
```

打开窗口后：把 `.c` 文件**拖进窗口**（或点「选择文件」），再点「**一键生成**」。产物按输入文件名放入独立文件夹，默认在 `output/<文件名>/` 下（可在界面里改输出基目录）。

### 方式二：命令行

```bash
cd py_pro
python main.py <你的源文件.c>
```

例如 `python main.py inner_udpcomm.c`，会在 `output/inner_udpcomm/` 目录生成：

| 文件 | 说明 |
|---|---|
| `design.docx` | 软件详细设计说明书（函数说明表） |
| `design.vsdx` | Visio 流程图（每函数一页） |
| `design.md` | 同内容的 Markdown 版本 |
| `call_graph.puml` / `*_flow.puml` | PlantUML 调用关系图与流程图 |
| `design_p1.png` … | 各页 PNG 预览 |

> 用 Visio 打开 `design.vsdx` 即可查看和继续编辑流程图。
>
> 命令行也支持指定输出基目录：`python main.py test.c my_out`（产物进 `my_out/test/`）。

### 输入文件编码

源文件支持 **UTF-8**（含 BOM）与 **GBK/GB2312** 中文编码，工具会自动检测并归一化为 UTF-8 后解析。

## 目录结构

```
py_pro/
├── main.py                    # CLI 入口：解析 → 分析 → 生成
├── gui_main.py                # GUI 入口（V6.1，PySide6：拖拽 + 一键生成）
├── pipeline.py                # 生成流水线封装（CLI/GUI 共用，按文件名建输出文件夹）
├── gui.spec                   # PyInstaller 打包配置
├── build.bat                  # Windows 一键打包脚本
├── debug_layout.py            # 调试：打印布局明细（不依赖 Visio）
├── verify_com_render.py       # 调试：仅验证 COM 渲染
├── parser/                    # 解析层（tree-sitter）
│   ├── file_loader.py         # 读取文件 + 编码归一化（UTF-8/GBK）
│   └── ast_parser.py          # AST 解析：函数/struct/enum/流程树
├── model/
│   └── code_model.py          # 数据模型（FunctionInfo/FlowNode/...）
├── analyzer/                  # 分析层
│   ├── call_analyzer.py       # 调用关系
│   ├── flow_analyzer.py       # 流程摘要与结构统计
│   ├── global_variable_analyzer.py  # 全局变量引用/修改
│   ├── io_analyzer.py         # 输入输出
│   ├── description_analyzer.py # 功能描述
│   └── variable_analyzer.py   # 局部变量
├── generator/                 # 生成层
│   ├── docx_generator.py      # Word 函数说明表
│   ├── vsdx_generator.py      # 布局引擎（生成坐标中间表示）
│   ├── com_renderer.py        # COM 渲染后端（调本机 Visio 绘制连线）
│   ├── markdown_generator.py  # Markdown 文档
│   └── plantuml_generator.py  # PlantUML 图
├── templates/
│   └── vsdx_model/            # Visio 官方流程图形状模板
└── output/                    # 生成结果（按文件名分子文件夹）
```

> 提示：仓库不含示例 C 源文件（`output/` 下的 docx/vsdx/png 等是运行时生成，不入库）。

## 开发调试

```bash
# 查看某函数在 Visio 中的布局明细（不依赖 Visio）
python debug_layout.py <你的源文件.c>

# 仅验证 COM 渲染（输出 VSDX + PNG 预览）
python verify_com_render.py <你的源文件.c>
```

## 打包成 exe（可选）

用 PyInstaller 把 GUI 打包成免 Python 环境的独立程序（文件夹模式）。

```bash
# 1. 安装 PyInstaller
pip install pyinstaller

# 2. 一键打包（Windows）
#    在 PowerShell 里执行，或直接双击 build.bat
.\build.bat
```

产物在 `dist/gui/` 文件夹：

| 路径 | 说明 |
|---|---|
| `dist/gui/gui.exe` | 主程序，双击运行 |
| `dist/gui/templates/` | Visio 模板（打包进去的） |

把 `dist/gui` **整个文件夹**拷贝到目标机器即可运行，无需装 Python。注意：生成 Visio 流程图仍需要目标机器安装 Microsoft Visio 桌面版（COM 调用）。

> 打包必须在你自己的 Windows 机器上进行（PyInstaller 不支持跨平台打包）。模板定位已做兼容处理（`com_renderer._default_template_dir` 支持 PyInstaller 的 `_MEIPASS` 解压目录）。

## 技术路线

1. **解析**：`tree-sitter-c` 生成 C AST，提取函数、结构体、枚举、调用关系，并把函数体按注释边界递归还原为**流程树**（`FlowNode`）。
2. **分析**：调用关系、全局变量引用/修改、输入输出参数、局部变量统计。
3. **Word 生成**：`python-docx` 按标准函数说明表格式输出。
4. **Visio 生成**：`pywin32` 调用本机 Visio COM，使用官方「基本流程图形状」master 落块、用 Dynamic Connector 连线并胶合到连接点，拖动块时连线自动跟随。
