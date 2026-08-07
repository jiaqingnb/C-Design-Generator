class ParameterInfo:
    """函数参数信息"""

    def __init__(self, name="", type=""):
        self.name = name      # 参数名（无名字段如 void 时为空）
        self.type = type      # 类型声明，如 "UINT8*"、"const DASS_sn_t *"


class FlowNode:
    """流程树节点。

    kind 取值:
      sequence  顺序步骤（函数调用/赋值/表达式），label 为描述
      if         条件判断，condition 为条件表达式；children 为 then 分支
      else        else 分支节点（kind=if 的节点的 alternate 字段指向其 else 分支）
      switch     多路分支，children 为 case 节点
      case       case 分支，label 为 case 表达式
      default    default 分支
      for        计数循环
      while      条件循环
      do_while   do-while 循环
      return     函数返回，label 为返回值表达式（可能为空）
      break      跳出循环
      continue   继续循环
      block      普通代码块（仅为结构分组）
    """

    def __init__(self, kind="sequence", label=""):
        self.kind = kind
        self.label = label
        self.children = []          # 顺序子节点
        self.condition = ""         # if/while/switch 的条件
        self.alternate = None       # if 的 else 分支（FlowNode，kind="else"）

    def add(self, node):
        self.children.append(node)
        return node

    def to_dict(self):
        return {
            "kind": self.kind,
            "label": self.label,
            "condition": self.condition,
            "children": [c.to_dict() for c in self.children],
            "alternate": self.alternate.to_dict() if self.alternate else None,
        }

    def __repr__(self):
        return f"FlowNode({self.kind}, {self.label!r}, {len(self.children)} children)"


class FunctionInfo:
    def __init__(self):
        self.name = ""
        self.return_type = ""
        self.is_static = False
        self.parameters = []        # [ParameterInfo]
        self.body = ""              # 函数体原始源码
        self.calls = []             # 直接调用的函数名列表
        self.local_variables = []   # [{"type":..., "name":...}]
        self.flow = FlowNode("block")  # 流程树根节点
        self.description = ""
        self.inputs = []            # [{"name":..., "type":..., "direction":"in"}]
        self.outputs = []           # [{"name":..., "type":...}]
        self.comments = []          # 函数相关注释
        self.pre_comment = ""       # 函数定义前的注释块（提取的原始文本）
        self.global_refs = []       # 引用的全局变量名列表
        self.global_mods = []       # 修改的全局变量名列表
        self.flow_summary = []      # 由 FlowAnalyzer 填充：线性步骤摘要
        self.structure_counts = {"if": 0, "loop": 0, "switch": 0, "return": 0}


class StructInfo:
    def __init__(self):
        self.name = ""
        self.members = []           # [{"name":..., "type":...}]
        self.raw = ""


class EnumInfo:
    def __init__(self):
        self.name = ""
        self.items = []             # [{"name":..., "value":...}]
        self.raw = ""


class GlobalVariable:
    def __init__(self):
        self.type = ""
        self.name = ""


class CFileInfo:
    def __init__(self):
        self.filename = ""
        self.functions = []
        self.structs = []
        self.enums = []
        self.globals = []
        self.macros = []
        self.includes = []          # 头文件包含
        self.typedefs = []          # typedef 声明
